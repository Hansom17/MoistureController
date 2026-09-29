#!/usr/bin/env bash
# Starts the central stack for local testing on this Mac:
#   API server (v1 backend code) + PostgreSQL · seeded household "Dev home"
#   · web app on http://localhost:8420
#
# Migration state (PROJECT.md §11): devices will reach the API through the
# gateway's WebSocket uplink, which doesn't exist yet — so there is no live
# device (simulator) in this stack for now.
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
    -h|--help) sed -n '2,14p' "$0"; exit 0 ;;
    *) echo "unknown option $1 (see --help)"; exit 1 ;;
  esac
  shift
done

DEV_UID=dev-user
central() { docker compose -f "$ROOT/server/docker-compose.yml" --env-file "$ROOT/server/.env.dev" "$@"; }
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

# --- 2. Central stack ------------------------------------------------------------------------
step "Central stack (API server, PostgreSQL)"
"$ROOT/server/scripts/make-secrets.sh" >/dev/null
central up -d --build --quiet-pull 2>&1 | grep -E "Error|error" || true
wait_for 180 "the API" curl -sf http://localhost:8000/healthz
central exec -T backend mc-server seed-dev --uid "$DEV_UID" > "$DEV/bundle.json"

# --- 3. Web app -----------------------------------------------------------------------------------
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

$(printf '\033[1m')Ready$(printf '\033[0m')
  App          http://localhost:8420            (signed in as $DEV_UID)
  API docs     http://localhost:8000/docs       (token: dev:$DEV_UID)
  Backend log  docker compose -f server/docker-compose.yml --env-file server/.env.dev logs -f backend

Stop with ./scripts/dev-stop.sh (add --wipe to delete all data)
EOF
