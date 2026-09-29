#!/bin/sh
# Starts Mosquitto and reloads/restarts it when generated files change
# (Broker_Specs §3.3, §4.3).
#
#   MC_BROKER_ROLE           cloud | hub
#   MC_WATCH_DIR             /broker-files (cloud) or /data/broker (hub)
#   MC_BROKER_USER           mc-backend | mc-agent (internal listener)
#   MC_BROKER_PASSWORD_FILE  secret file with that user's password
set -eu

ROLE="${MC_BROKER_ROLE:-cloud}"
WATCH_DIR="${MC_WATCH_DIR:-/broker-files}"
PASSWD=/mosquitto/data/passwd

# 1. Internal listener credentials, hashed at every start.
: > "$PASSWD"
chmod 600 "$PASSWD"
mosquitto_passwd -b "$PASSWD" "${MC_BROKER_USER:?}" "$(cat "${MC_BROKER_PASSWORD_FILE:?}")"

# 2. Generated files must exist before Mosquitto starts.
# The backend (cloud) or the agent (hub) owns these files; the broker only
# reads them, so wait until they exist.
if [ "$ROLE" = "hub" ]; then
  need="$WATCH_DIR/psk $WATCH_DIR/conf.d"
else
  need="$WATCH_DIR/psk $WATCH_DIR/acl"
fi
for f in $need; do
  [ -e "$f" ] || echo "waiting for $f"
  while [ ! -e "$f" ]; do sleep 1; done
done

checksum() { cat "$WATCH_DIR/conf.d/"*.conf 2>/dev/null | md5sum; }

mosquitto -c /mosquitto/config/mosquitto.conf &
PID=$!
trap 'kill -TERM "$PID" 2>/dev/null; wait "$PID"; exit 0' TERM INT

# 3. Watch, debounce 1 s, then SIGHUP (psk/acl) or restart (bridge config).
(
  bridge_sum="$(checksum)"
  while inotifywait -q -r -e close_write,moved_to "$WATCH_DIR" >/dev/null 2>&1; do
    sleep 1
    if [ "$ROLE" = "hub" ] && [ "$(checksum)" != "$bridge_sum" ]; then
      echo "bridge config changed: restarting mosquitto"
      kill -TERM "$PID"   # persistence is saved; Docker restarts the container
      exit 0
    fi
    echo "generated files changed: reloading mosquitto"
    kill -HUP "$PID"
  done
) &

wait "$PID"
