#!/usr/bin/env bash
# Starts everything for local testing on this Mac:
#   cloud stack (backend + broker + Postgres) · seeded household "Dev home"
#   · simulated plant board · web app on http://localhost:8420
#   with --hub also a home hub, claimed automatically, device moved onto it.
#
#   ./scripts/dev-start.sh            cloud only
#   ./scripts/dev-start.sh --hub      cloud + hub
#   ./scripts/dev-stop.sh [--wipe]    stop (and delete all data)
#
# Options: --no-app (skip the web app), --skip-app-build (serve the last build),
#          --interval N (simulator wake interval in s, default 20),
#          --moisture N (simulator start moisture in %), --no-open
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEV="$ROOT/.dev"
mkdir -p "$DEV"

MODE=cloud APP=1 BUILD_APP=1 OPEN=1 INTERVAL=20 MOISTURE=""
while [ $# -gt 0 ]; do
  case "$1" in
    --hub) MODE=hub ;;
    --no-app) APP=0 ;;
    --skip-app-build) BUILD_APP=0 ;;
    --no-open) OPEN=0 ;;
    --interval) INTERVAL="$2"; shift ;;
    --moisture) MOISTURE="$2"; shift ;;
    -h|--help) sed -n '2,15p' "$0"; exit 0 ;;
    *) echo "unknown option $1 (see --help)"; exit 1 ;;
  esac
  shift
done

DEV_UID=dev-user
API=http://localhost:8000/api/v1
cloud() { docker compose -f "$ROOT/server/docker-compose.yml" --env-file "$ROOT/server/.env.dev" "$@"; }
hub() { docker compose -f "$ROOT/hub/docker-compose.yml" --env-file "$ROOT/hub/.env.dev" "$@"; }
api() { curl -s -H "Authorization: Bearer dev:$DEV_UID" -H 'content-type: application/json' "$@"; }
field() { python3 -c "import sys,json; d=json.load(sys.stdin); print($1)"; }
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

# --- 2. Python (simulator) ----------------------------------------------------------------
step "Python environment"
if [ ! -x "$ROOT/.venv/bin/python" ]; then
  # Outside ~/Documents: iCloud hides files in synced venvs, which breaks imports.
  python3.13 -m venv ~/.venvs/moisturecontroller
  ln -sfn ~/.venvs/moisturecontroller "$ROOT/.venv"
  "$ROOT/.venv/bin/pip" install -q --upgrade pip
  "$ROOT/.venv/bin/pip" install -q -e "$ROOT/core" -e "$ROOT/server[dev]" -e "$ROOT/hub[dev]"
fi
echo "  $("$ROOT/.venv/bin/python" --version) at $ROOT/.venv"

# --- 3. Cloud stack -------------------------------------------------------------------------
step "Cloud stack (backend, broker, Postgres)"
"$ROOT/server/scripts/make-secrets.sh" >/dev/null
cloud up -d --build --quiet-pull 2>&1 | grep -E "Error|error" || true
wait_for 180 "the API" curl -sf http://localhost:8000/healthz

seed() { cloud exec -T backend mc-server seed-dev --uid "$DEV_UID" > "$DEV/bundle.json"; }
seed
HID=$(api "$API/me/households" | field "d[0]['id']")
echo "  household Dev home: $HID"

hub_json() { api "$API/households/$HID/hub"; }
has_hub() { hub_json | grep -q '"id"'; }

# --- 4. Hub (optional) -----------------------------------------------------------------------
if [ "$MODE" = hub ]; then
  step "Hub"
  "$ROOT/hub/scripts/make-secrets.sh" >/dev/null
  if ! has_hub; then
    # The cloud doesn't know a hub: start the agent from scratch so it enrolls.
    hub down -v >/dev/null 2>&1 || true
    hub up -d --build --quiet-pull 2>&1 | grep -E "Error|error" || true
    code_in_logs() { hub logs agent 2>/dev/null | grep -oE '[0-9A-Z]{4}-[0-9A-Z]{4}' | tail -1; }
    have_code() { [ -n "$(code_in_logs)" ]; }  # re-evaluated on every try
    wait_for 90 "the enrollment code" have_code
    CODE=$(code_in_logs)
    echo "  claiming the hub with code $CODE"
    api -X POST "$API/households/$HID/hub" -d "{\"user_code\":\"$CODE\"}" | field "'  hub ' + d.get('id', str(d))"
  else
    hub up -d --build --quiet-pull 2>&1 | grep -E "Error|error" || true
  fi
  wait_for 120 "the hub bridge (online, in sync)" \
    sh -c "curl -s -H 'Authorization: Bearer dev:$DEV_UID' $API/households/$HID/hub | grep -q '\"online\":true.*\"in_sync\":true'"
  seed  # device was set to "no gateway" by the claim: rekey onto the hub
else
  if has_hub; then
    step "Removing the hub (cloud-only mode)"
    api -X DELETE "$API/households/$HID/hub" >/dev/null
    hub down -v >/dev/null 2>&1 || true   # the agent must enroll again next time
    seed  # rekey the device back onto the cloud broker
  fi
fi
BUNDLE_TARGET=$(field "d['mqtt']['host'] + ':' + str(d['mqtt']['port'])" < "$DEV/bundle.json")

# --- 5. Simulated plant board ------------------------------------------------------------------
step "Simulated device → $BUNDLE_TARGET"
stop_pid simulator
SIM_ARGS=(--bundle "$DEV/bundle.json" --interval "$INTERVAL" --state "$DEV/simulator-state.json")
[ -n "$MOISTURE" ] && SIM_ARGS+=(--moisture "$MOISTURE")
nohup "$ROOT/.venv/bin/python" -u "$ROOT/server/tools/fake_device.py" "${SIM_ARGS[@]}" \
  > "$DEV/simulator.log" 2>&1 &
echo $! > "$DEV/simulator.pid"
wait_for 30 "the first wake cycle" grep -q '"sleeping"' "$DEV/simulator.log"

# --- 6. Web app -----------------------------------------------------------------------------------
if [ "$APP" = 1 ]; then
  step "Web app"
  if [ "$BUILD_APP" = 1 ] || [ ! -f "$ROOT/app/build/web/index.html" ]; then
    (cd "$ROOT/app" && flutter build web --release -t lib/main_local.dart 2>&1 | tail -1)
  fi
  stop_pid web
  if lsof -iTCP:8420 -sTCP:LISTEN >/dev/null 2>&1; then
    echo "  port 8420 is already in use — assuming it serves app/build/web"
  else
    nohup python3 -m http.server 8420 --bind 127.0.0.1 --directory "$ROOT/app/build/web" \
      > "$DEV/web.log" 2>&1 &
    echo $! > "$DEV/web.pid"
    wait_for 10 "the web server" curl -sf http://localhost:8420/
  fi
  [ "$OPEN" = 1 ] && open http://localhost:8420
fi

# --- summary ------------------------------------------------------------------------------------------
cat <<EOF

$(printf '\033[1m')Ready ($MODE mode)$(printf '\033[0m')
  App          http://localhost:8420            (signed in as $DEV_UID)
  API docs     http://localhost:8000/docs       (token: dev:$DEV_UID)
  Device       $(field "d['device_id']" < "$DEV/bundle.json") → $BUNDLE_TARGET, wakes every ${INTERVAL}s

Logs
  simulator    tail -f .dev/simulator.log
  backend      docker compose -f server/docker-compose.yml --env-file server/.env.dev logs -f backend
EOF
if [ "$MODE" = hub ]; then cat <<EOF
  hub agent    docker compose -f hub/docker-compose.yml --env-file hub/.env.dev logs -f agent
  hub CLI      docker compose -f hub/docker-compose.yml --env-file hub/.env.dev exec agent mc-hub status
EOF
fi
echo
echo "Stop with ./scripts/dev-stop.sh (add --wipe to delete all data)"
