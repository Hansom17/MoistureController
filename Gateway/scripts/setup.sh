#!/bin/sh
# First-time setup of the gateway stack: .env with generated MQTT passwords and the Mosquitto password file.
# Needs: openssl and docker. Safe to run again: existing passwords are kept.
set -eu
cd "$(dirname "$0")/../firmware"

[ -f .env ] || cp .env.example .env
for name in HUB API Z2M; do
  key="MQTT_${name}_PASSWORD"
  if ! grep -q "^${key}=.\+" .env; then
    pw=$(openssl rand -hex 24)
    if grep -q "^${key}=" .env; then sed -i.bak "s|^${key}=.*|${key}=${pw}|" .env; rm -f .env.bak; else echo "${key}=${pw}" >> .env; fi
  fi
done
chmod 600 .env

get() { grep "^$1=" .env | cut -d= -f2-; }
rm -f mosquitto/passwd
docker run --rm -v "$(pwd)/mosquitto:/work" eclipse-mosquitto:2.0.20 sh -c "
  mosquitto_passwd -b -c /work/passwd hub '$(get MQTT_HUB_PASSWORD)' &&
  mosquitto_passwd -b /work/passwd api '$(get MQTT_API_PASSWORD)' &&
  mosquitto_passwd -b /work/passwd z2m '$(get MQTT_Z2M_PASSWORD)' &&
  chmod 644 /work/passwd"

echo "ready: firmware/.env and firmware/mosquitto/passwd"
echo "next: set ZIGBEE_DEVICE in firmware/.env to your coordinator (ls /dev/serial/by-id/), then: docker compose up -d"
