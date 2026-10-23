#!/usr/bin/env bash
# A throwaway Zigbee2MQTT + Mosquitto for bench tests of the PlantModule with the SONOFF dongle.
#   z2m_throwaway.sh start <work-dir> [source-data-dir]   # copies the configuration, starts both
#   z2m_throwaway.sh stop <work-dir>
# Own broker on 127.0.0.1:1884, frontend on 127.0.0.1:8081, the converter folder of this repository is linked in.
# The source data directory (default ~/zigbee2mqtt/data) is only read: configuration.yaml, coordinator_backup.json and
# database.db are copied, so the dongle keeps its network. Never run it next to another Zigbee2MQTT on the dongle.
set -euo pipefail
Z2M="${Z2M_DIR:-$HOME/zigbee2mqtt}"
MOSQUITTO="${MOSQUITTO:-/opt/homebrew/sbin/mosquitto}"
REPO="$(cd "$(dirname "$0")/../.." && pwd)"

case "${1:-}" in
start)
  work="${2:?work directory}"; src="${3:-$Z2M/data}"
  mkdir -p "$work/data/external_converters"
  for f in configuration.yaml coordinator_backup.json database.db; do [ -e "$work/data/$f" ] || cp "$src/$f" "$work/data/$f"; done
  sed -i.bak 's/port: 8080/port: 8081/' "$work/data/configuration.yaml"
  conv="$REPO/Gateway/firmware/zigbee2mqtt/external_converters"
  ln -sfn "$conv/mc-plant.mjs" "$work/data/external_converters/mc-plant.mjs"
  ln -sfn "$conv/mc-plant" "$work/data/external_converters/mc-plant"
  printf 'listener 1884 127.0.0.1\nallow_anonymous true\npersistence false\n' > "$work/mosquitto.conf"
  nohup "$MOSQUITTO" -c "$work/mosquitto.conf" > "$work/mosquitto.log" 2>&1 & echo $! > "$work/mosquitto.pid"
  sleep 1
  (cd "$Z2M" && ZIGBEE2MQTT_DATA="$work/data" nohup node index.js > "$work/z2m.log" 2>&1 & echo $! > "$work/z2m.pid")
  echo "started; log: $work/z2m.log; open the join window with:"
  echo "  mosquitto_pub -h 127.0.0.1 -p 1884 -t zigbee2mqtt/bridge/request/permit_join -m '{\"time\":254}'"
  ;;
stop)
  work="${2:?work directory}"   # only the processes this script started (pid files), never another broker
  for n in z2m mosquitto; do [ -f "$work/$n.pid" ] && kill "$(cat "$work/$n.pid")" 2>/dev/null || true; done
  ;;
*) sed -n 2,9p "$0"; exit 1 ;;
esac
