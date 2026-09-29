#!/bin/sh
# Starts Mosquitto inside the gateway stack and reloads it when the gateway
# service rewrites the PSK file (Broker_Specs §3, §4).
#
#   MC_WATCH_DIR             directory with the generated psk file (/data/broker)
#   MC_BROKER_USER           internal user of the gateway service
#   MC_BROKER_PASSWORD_FILE  secret file with that user's password
set -eu

WATCH_DIR="${MC_WATCH_DIR:-/data/broker}"
PASSWD=/mosquitto/data/passwd

# 1. Internal listener credentials, hashed at every start.
: > "$PASSWD"
chmod 600 "$PASSWD"
mosquitto_passwd -b "$PASSWD" "${MC_BROKER_USER:?}" "$(cat "${MC_BROKER_PASSWORD_FILE:?}")"

# 2. The gateway service owns the PSK file; wait until it exists.
[ -e "$WATCH_DIR/psk" ] || echo "waiting for $WATCH_DIR/psk"
while [ ! -e "$WATCH_DIR/psk" ]; do sleep 1; done

mosquitto -c /mosquitto/config/mosquitto.conf &
PID=$!
trap 'kill -TERM "$PID" 2>/dev/null; wait "$PID"; exit 0' TERM INT

# 3. Watch, debounce 1 s, SIGHUP (reloads psk_file, connections stay up).
(
  while inotifywait -q -e close_write,moved_to "$WATCH_DIR" >/dev/null 2>&1; do
    sleep 1
    echo "psk file changed: reloading mosquitto"
    kill -HUP "$PID"
  done
) &

wait "$PID"
