#!/usr/bin/env bash
# Starts everything for local testing on this Mac:
#   API server + PostgreSQL · gateway stack (gateway service + Mosquitto),
#   enrolled and claimed automatically · seeded household "Dev home"
#   · web app on http://localhost:8420  (the plant device simulator is gone; a Zigbee2MQTT simulator is planned)
#
#   ./scripts/dev-start.sh            start (and build the web app)
#   ./scripts/dev-stop.sh [--wipe]    stop (and delete all data)
#
# Options: --no-app (skip the web app), --skip-app-build (serve the last build),
#          --no-open
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEV="$ROOT/.dev"
mkdir -p "$DEV"

APP=1 BUILD_APP=1 OPEN=1
while [ $# -gt 0 ]; do
  case "$1" in
    --no-app) APP=0 ;;
    --skip-app-build) BUILD_APP=0 ;;
    --no-open) OPEN=0 ;;
    -h|--help) sed -n '2,13p' "$0"; exit 0 ;;
    *) echo "unknown option $1 (see --help)"; exit 1 ;;
  esac
  shift
done

DEV_UID=dev-user
API=http://localhost:8000/api/v1
central() { docker compose -f "$ROOT/Server/docker-compose.yml" --env-file "$ROOT/Server/.env.dev" "$@"; }
gateway() { docker compose -f "$ROOT/Gateway/firmware/docker-compose.yml" --env-file "$ROOT/Gateway/firmware/.env.dev" "$@"; }
api() { curl -sf -H "Authorization: Bearer dev:$DEV_UID" -H "Content-Type: application/json" "$@"; }
field() { python3 -c "import json,sys; d=json.load(sys.stdin); print($1)"; }
step() { printf '\n\033[1m▸ %s\033[0m\n' "$*"; }
wait_for() { # wait_for <seconds> <description> <command…>
  local t=$1 what=$2; shift 2
  printf '  waiting for %s' "$what"
  for _ in $(seq 1 "$t"); do
    if "$@" >/dev/null 2>&1; then echo " ✓"; return 0; fi
    printf '.'; sleep 1
  done
  echo " ✗"; echo "  gave up after ${t}s — check the logs (see below)"; return 1
}
stop_pid() { [ -f "$DEV/$1.pid" ] && kill "$(cat "$DEV/$1.pid")" 2>/dev/null || true; rm -f "$DEV/$1.pid"; }

# --- 1. Docker --------------------------------------------------------------------------
step "Docker"
if ! docker info >/dev/null 2>&1; then
  open -a Docker
  wait_for 120 "Docker Desktop" docker info
fi
if ! docker compose version >/dev/null 2>&1; then
  plugins=/Applications/Docker.app/Contents/Resources/cli-plugins
  mkdir -p ~/.docker/cli-plugins
  for p in docker-compose docker-buildx; do ln -sfn "$plugins/$p" ~/.docker/cli-plugins/$p; done
fi
echo "  $(docker compose version)"

# --- 2. Python environment ----------------------------------------------------------------
step "Python environment"
if [ ! -x "$ROOT/.venv/bin/python" ]; then
  # Outside ~/Documents: iCloud hides files in synced venvs, which breaks imports.
  python3.13 -m venv ~/.venvs/moisturecontroller
  ln -sfn ~/.venvs/moisturecontroller "$ROOT/.venv"
  "$ROOT/.venv/bin/pip" install -q --upgrade pip
  "$ROOT/.venv/bin/pip" install -q -e "$ROOT/Shared/core" -e "$ROOT/Server[dev]" -e "$ROOT/Gateway/firmware[dev]"
fi
echo "  $("$ROOT/.venv/bin/python" --version) at $ROOT/.venv"

# --- 3. Central stack ------------------------------------------------------------------------
step "Central stack (API server, PostgreSQL)"
"$ROOT/Server/scripts/make-secrets.sh" >/dev/null
central up -d --build --quiet-pull 2>&1 | grep -E "Error|error" || true
wait_for 180 "the API" curl -sf http://localhost:8000/healthz

# --- 4. Gateway stack --------------------------------------------------------------------------
step "Gateway stack (gateway service, Mosquitto)"
"$ROOT/Gateway/scripts/make-secrets.sh" >/dev/null
gateway up -d --build --quiet-pull 2>&1 | grep -E "Error|error" || true
wait_for 30 "the gateway service" gateway exec -T gateway mc-gateway status
HID=$(api "$API/me/households" | field "next((h['id'] for h in d if h['name'] == 'Dev home'), '')")
if gateway exec -T gateway mc-gateway status | grep -q "not enrolled" && [ -n "$HID" ] \
    && api "$API/households/$HID/gateway" >/dev/null 2>&1; then
  # Fresh gateway data but the API still knows the old gateway: replace it.
  echo "  removing the stale gateway from Dev home"
  api -X DELETE "$API/households/$HID/gateway" >/dev/null
fi
# seed-dev claims the gateway's pending enrollment and keys the device onto it.
seed() { central exec -T api mc-api seed-dev --uid "$DEV_UID" > "$DEV/bundle.json" 2> "$DEV/seed.log"; }
wait_for 60 "the gateway enrollment (seeding Dev home)" seed
sed 's/^/  /' "$DEV/seed.log"
HID=$(api "$API/me/households" | field "next(h['id'] for h in d if h['name'] == 'Dev home')")
connected() { api "$API/households/$HID/gateway" | grep -q '"online":true.*"in_sync":true'; }
wait_for 90 "the gateway (online, in sync)" connected

# --- 5. Web app -----------------------------------------------------------------------------------
if [ "$APP" = 1 ]; then
  step "Web app"
  if [ "$BUILD_APP" = 1 ] || [ ! -f "$ROOT/App/build/web/index.html" ]; then
    (cd "$ROOT/App" && flutter build web --release -t lib/main_local.dart 2>&1 | tail -1)
  fi
  stop_pid web
  if lsof -iTCP:8420 -sTCP:LISTEN >/dev/null 2>&1; then
    echo "  port 8420 is already in use — assuming it serves App/build/web"
  else
    nohup python3 -m http.server 8420 --bind 127.0.0.1 --directory "$ROOT/App/build/web" \
      > "$DEV/web.log" 2>&1 &
    echo $! > "$DEV/web.pid"
    wait_for 10 "the web server" curl -sf http://localhost:8420/
  fi
  [ "$OPEN" = 1 ] && open http://localhost:8420
fi

# --- summary ------------------------------------------------------------------------------------------
cat <<EOF

$(printf '\033[1m')Ready$(printf '\033[0m')
  App          http://localhost:8420            (signed in as $DEV_UID)
  API docs     http://localhost:8000/docs       (token: dev:$DEV_UID)

Logs
  API          docker compose -f Server/docker-compose.yml --env-file Server/.env.dev logs -f api
  gateway      docker compose -f Gateway/firmware/docker-compose.yml --env-file Gateway/firmware/.env.dev logs -f gateway
  gateway CLI  docker compose -f Gateway/firmware/docker-compose.yml --env-file Gateway/firmware/.env.dev exec gateway mc-gateway status

Stop with ./scripts/dev-stop.sh (add --wipe to delete all data)
EOF
