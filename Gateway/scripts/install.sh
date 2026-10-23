#!/bin/sh
# Sets up the gateway stack on this device (Linux with Docker): checks, .env, Mosquitto passwords, Zigbee dongle,
# `docker compose up`, then prints the address and the setup code.   Guide: Gateway/INSTALL.md
#
#   Gateway/scripts/install.sh --check      only look and report, change nothing
#   Gateway/scripts/install.sh              set everything up and start it
#   Gateway/scripts/install.sh --web DIR    use DIR as the Flutter web build (default App/build/web)
#
# Safe to run again: existing passwords and the Zigbee data are kept.
set -eu

here="$(cd "$(dirname "$0")" && pwd)"
repo="$(cd "$here/../.." && pwd)"
fw="$repo/Gateway/firmware"
check_only=0
web="$repo/App/build/web"
while [ $# -gt 0 ]; do
  case "$1" in
    --check) check_only=1 ;;
    --web) shift; web="$(cd "$1" && pwd)" ;;
    -h|--help) sed -n 2,10p "$0"; exit 0 ;;
    *) echo "unknown option: $1"; exit 2 ;;
  esac
  shift
done

problems=0
ok()   { printf '  ok    %s\n' "$*"; }
warn() { printf '  WARN  %s\n' "$*"; }
bad()  { printf '  FAIL  %s\n' "$*"; problems=$((problems + 1)); }

echo "Checking this device"
# --- tools ------------------------------------------------------------------------------------------------
if command -v docker >/dev/null 2>&1; then
  ok "docker $(docker --version | sed 's/Docker version //; s/,.*//')"
  if docker compose version >/dev/null 2>&1; then ok "docker compose $(docker compose version --short)"; else bad "docker compose (v2 plugin) is missing: install docker-compose-plugin"; fi
  if docker info >/dev/null 2>&1; then ok "docker daemon reachable"; else bad "cannot talk to the docker daemon (is it running? are you in the docker group, or use sudo?)"; fi
else
  bad "docker is not installed (see Gateway/INSTALL.md, step 2)"
fi
command -v openssl >/dev/null 2>&1 && ok "openssl" || bad "openssl is missing (needed to generate the MQTT passwords)"

# --- architecture and clock -----------------------------------------------------------------------------------
arch="$(uname -m)"
case "$arch" in
  x86_64|aarch64|arm64) ok "architecture $arch" ;;
  *) warn "architecture $arch: the images need a 64-bit system (arm64 or amd64)" ;;
esac
if command -v timedatectl >/dev/null 2>&1; then
  if [ "$(timedatectl show -p NTPSynchronized --value 2>/dev/null)" = "yes" ]; then ok "clock is synchronised"; else warn "clock is not NTP-synchronised: quiet hours and rule limits depend on the time"; fi
fi

# --- web build ------------------------------------------------------------------------------------------------
if [ -f "$web/index.html" ]; then
  ok "web build in $web"
else
  bad "no web build at $web: build it on a computer with Flutter (cd App && flutter build web --release --no-web-resources-cdn) and copy App/build/web here, or pass --web DIR"
fi

# --- Zigbee dongle --------------------------------------------------------------------------------------------
dongle=""
if [ -d /dev/serial/by-id ]; then
  list="$(ls /dev/serial/by-id/ 2>/dev/null || true)"
  count="$(printf '%s\n' "$list" | grep -c . || true)"
  if [ "$count" -eq 1 ]; then
    dongle="/dev/serial/by-id/$list"
    ok "Zigbee dongle: $dongle"
  elif [ "$count" -eq 0 ]; then
    bad "no serial device in /dev/serial/by-id: plug in the Zigbee dongle"
  else
    warn "several serial devices found, set ZIGBEE_DEVICE in $fw/.env yourself:"
    printf '          %s\n' $list
  fi
else
  warn "no /dev/serial/by-id here (not Linux?): set ZIGBEE_DEVICE in $fw/.env to the dongle's device"
fi

# --- ports ----------------------------------------------------------------------------------------------------
port="$(grep '^MC_PORT=' "$fw/.env" 2>/dev/null | cut -d= -f2 || true)"
port="${port:-80}"
if command -v ss >/dev/null 2>&1 && ss -ltn 2>/dev/null | awk '{print $4}' | grep -q ":$port\$"; then
  if docker ps --format '{{.Names}}' 2>/dev/null | grep -q '^moisture-api-1$'; then ok "port $port is used by this stack already"; else warn "port $port is already in use by something else: set MC_PORT in $fw/.env"; fi
else
  ok "port $port is free"
fi

if [ "$check_only" -eq 1 ]; then
  [ "$problems" -eq 0 ] && echo "Everything needed is in place." || echo "$problems problem(s) to fix before installing."
  exit "$problems"
fi
if [ "$problems" -gt 0 ]; then
  echo "Fix the FAIL lines above and run this again."
  exit 1
fi

# --- set up ---------------------------------------------------------------------------------------------------
echo "Setting up"
sh "$here/setup.sh"
cd "$fw"
setenv() { # key value
  if grep -q "^$1=" .env; then sed -i.bak "s|^$1=.*|$1=$2|" .env && rm -f .env.bak; else echo "$1=$2" >> .env; fi
}
[ -n "$dongle" ] && setenv ZIGBEE_DEVICE "$dongle"
setenv WEB_DIR "$web"
grep -q '^ZIGBEE_DEVICE=.*XXXX' .env && { echo "Set ZIGBEE_DEVICE in $fw/.env, then run this script again."; exit 1; }

echo "Starting (the first start builds the two service images, this takes a few minutes)"
docker compose up -d --build

echo "Waiting for the api"
up=0
for _ in $(seq 1 60); do
  if curl -fsS "http://127.0.0.1:$port/api/v1/meta" >/dev/null 2>&1; then up=1; break; fi
  sleep 2
done
[ "$up" -eq 1 ] || { echo "The api did not come up. Look at: docker compose -f $fw/docker-compose.yml logs api hub zigbee2mqtt"; exit 1; }

echo
echo "The gateway is running."
for ip in $(hostname -I 2>/dev/null || true); do echo "  open  http://$ip:$port/"; done
code="$(docker compose logs api 2>/dev/null | grep -o 'SETUP CODE: [A-Z0-9]*' | tail -1 | cut -d' ' -f3 || true)"
if [ -n "$code" ]; then
  echo "  first visit: create the owner account with the setup code  $code"
else
  echo "  no setup code in the log: the gateway was set up before (sign in as usual)"
fi
echo "Next: add your modules (Gateway/INSTALL.md, step 7). Back up with Gateway/scripts/backup.sh."
