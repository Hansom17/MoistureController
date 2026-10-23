#!/bin/sh
# Lets an api on another device reach this box's Mosquitto over TLS.
#   scripts/remote-api.sh <address of this box>      e.g. moisture.local or 192.168.1.20
# Creates a small CA and a server certificate, enables the TLS listener (port 8883) and prints what to copy.
set -eu
[ $# -eq 1 ] || { echo "usage: $0 <address of this box>"; exit 2; }
host="$1"
cd "$(dirname "$0")/../firmware/mosquitto"
mkdir -p tls
cd tls
umask 077
if [ ! -f ca.key ]; then
  openssl req -x509 -newkey rsa:3072 -nodes -keyout ca.key -out ca.pem -days 3650 -subj "/CN=Moisture gateway CA" 2>/dev/null
fi
openssl req -newkey rsa:3072 -nodes -keyout server.key -out server.csr -subj "/CN=$host" 2>/dev/null
case "$host" in
  *[!0-9.]*) san="DNS:$host" ;;
  *)         san="IP:$host" ;;
esac
printf 'subjectAltName=%s\n' "$san" > san.cnf
openssl x509 -req -in server.csr -CA ca.pem -CAkey ca.key -CAcreateserial -out server.pem -days 825 -extfile san.cnf 2>/dev/null
rm -f server.csr san.cnf ca.srl
chmod 644 ca.pem server.pem server.key     # the broker runs as an unprivileged user in its container
cat > ../conf.d/remote.conf <<CONF
listener 8883
cafile /mosquitto/config/tls/ca.pem
certfile /mosquitto/config/tls/server.pem
keyfile /mosquitto/config/tls/server.key
CONF
cat <<MSG
TLS listener prepared for $host.
On this box:     docker compose -f docker-compose.yml -f docker-compose.remote.yml up -d
On the api device, in Gateway/firmware/:
  - copy mosquitto/tls/ca.pem  (only the certificate, never the .key files)
  - .env with: MC_MQTT_HOST=$host  MQTT_API_PASSWORD=<same as in this box's .env>  WEB_DIR=<web build>
  - docker compose -f docker-compose.api.yml up -d
MSG
