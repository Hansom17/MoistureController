#!/usr/bin/env bash
# The bench setup for testing the PlantModule with the app, without Docker:
#   Gateway/scripts/bench.sh start | stop | status
# Starts a throwaway Mosquitto (127.0.0.1:1884), Zigbee2MQTT on the SONOFF dongle, the hub and the api, with all state
# in Gateway/.bench (git-ignored): z2m/data, hub/hub.db, api/api.db, credentials.txt. The app (App/build/web) is served at
# http://127.0.0.1:8000 .  Needs Zigbee2MQTT in ~/zigbee2mqtt (Z2M_DIR) and Mosquitto from Homebrew.
# Never run it while another Zigbee2MQTT uses the dongle. It does not touch any other broker.
set -euo pipefail
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
B="$REPO/Gateway/.bench"
Z2M="${Z2M_DIR:-$HOME/zigbee2mqtt}"
MOSQUITTO="${MOSQUITTO:-/opt/homebrew/sbin/mosquitto}"
PORT="${MC_PORT:-8000}"

alive() { [ -f "$B/$1.pid" ] && kill -0 "$(cat "$B/$1.pid")" 2>/dev/null; }
spawn() { # name, command...
  local n="$1"; shift
  nohup "$@" > "$B/$n.log" 2>&1 & echo $! > "$B/$n.pid"
}

# Reports a service that is not running after the start, with the end of its log.
check() {
  for n in "$@"; do
    alive "$n" || { echo "!! $n did not start:"; tail -5 "$B/$n.log" | cut -c1-200; failed=1; }
  done
}

case "${1:-}" in
start)
  failed=0
  mkdir -p "$B/z2m/data/external_converters" "$B/hub" "$B/api"
  if [ ! -x "$B/venv/bin/mc-hub" ]; then
    python3 -m venv "$B/venv"; "$B/venv/bin/pip" install -q -e "$REPO/Gateway/firmware/hub" -e "$REPO/Gateway/firmware/api"
  fi
  if [ ! -e "$B/z2m/data/configuration.yaml" ]; then   # first time: take the network of the existing Zigbee2MQTT (read only)
    for f in configuration.yaml coordinator_backup.json database.db; do cp "$Z2M/data/$f" "$B/z2m/data/$f"; done
    sed -i.bak 's#port: 8080#port: 8081#' "$B/z2m/data/configuration.yaml"
  fi
  # macOS marks files in a dot-directory as hidden and Python then skips the venv's editable-install .pth files
  chflags -R nohidden "$B/venv" 2>/dev/null || true
  # The dongle's device name changes with the USB port it is plugged into: find it instead of trusting the config.
  conf="$B/z2m/data/configuration.yaml"
  port="$(sed -n 's/^ *port: *\(\/dev\/[^ ]*\).*/\1/p' "$conf" | head -1)"
  if [ -n "$port" ] && [ ! -e "$port" ]; then
    found=( $(ls /dev/cu.usbserial-* 2>/dev/null || true) )
    if ! ioreg -p IOUSB -l -w0 2>/dev/null | grep -q "SONOFF Dongle"; then
      echo "!! no SONOFF dongle is connected (looked at the USB bus). Plug it in, then start again."
      exit 1
    elif [ "${#found[@]}" = 1 ]; then
      echo "the dongle is now ${found[0]} (was $port): updating the Zigbee2MQTT configuration"
      sed -i.bak "s#port: $port#port: ${found[0]}#" "$conf"
    else
      echo "!! the dongle is connected but I cannot tell which serial device it is: ${found[*]:-none found}"
      echo "   Set 'port:' in $conf to the right one."
      exit 1
    fi
  fi
  conv="$REPO/Gateway/firmware/zigbee2mqtt/external_converters"
  ln -sfn "$conv/mc-plant.mjs" "$B/z2m/data/external_converters/mc-plant.mjs"
  ln -sfn "$conv/mc-plant" "$B/z2m/data/external_converters/mc-plant"
  printf 'listener 1884 127.0.0.1\nallow_anonymous true\npersistence false\n' > "$B/mosquitto.conf"
  alive mosquitto || spawn mosquitto "$MOSQUITTO" -c "$B/mosquitto.conf"
  sleep 1
  alive z2m || (cd "$Z2M" && ZIGBEE2MQTT_DATA="$B/z2m/data" spawn z2m node index.js)
  sleep 20
  export MC_MQTT_HOST=127.0.0.1 MC_MQTT_PORT=1884
  alive hub || MC_DATA_DIR="$B/hub" spawn hub "$B/venv/bin/mc-hub" run
  sleep 4
  alive api || MC_DATA_DIR="$B/api" MC_PORT="$PORT" MC_BIND=127.0.0.1 MC_WEB_DIR="$REPO/App/build/web" spawn api "$B/venv/bin/mc-api" run
  sleep 4
  check mosquitto z2m hub api
  [ "$failed" = 0 ] || { echo "not everything started, see the logs in $B"; exit 1; }
  echo "running: http://127.0.0.1:$PORT   (login in $B/credentials.txt; logs in $B/*.log)"
  grep -h "SETUP CODE" "$B/api.log" 2>/dev/null | tail -1 || true
  echo "open the join window for a new module:"
  echo "  mosquitto_pub -h 127.0.0.1 -p 1884 -t zigbee2mqtt/bridge/request/permit_join -m '{\"time\":254}'  (or Add device in the app)"
  ;;
stop)
  for n in api hub z2m mosquitto; do
    if alive $n; then
      pid="$(cat "$B/$n.pid")"; kill "$pid" || true
      for _ in 1 2 3 4 5 6; do kill -0 "$pid" 2>/dev/null || break; sleep 1; done
      kill -0 "$pid" 2>/dev/null && kill -9 "$pid" || true   # the api waits for open live-update connections
    fi
  done
  ;;
status)
  for n in mosquitto z2m hub api; do alive $n && echo "$n: running" || echo "$n: stopped"; done
  curl -s -m 3 "http://127.0.0.1:$PORT/api/v1/meta" || true; echo
  ;;
*) sed -n 2,9p "$0"; exit 1 ;;
esac
