#!/usr/bin/env bash
# Stops everything started by dev-start.sh.
#   --wipe   also delete all data (database, broker state, hub enrollment,
#            simulator state) for a fresh start
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEV="$ROOT/.dev"
WIPE=0
[ "${1:-}" = "--wipe" ] && WIPE=1

for name in simulator web; do
  if [ -f "$DEV/$name.pid" ]; then
    kill "$(cat "$DEV/$name.pid")" 2>/dev/null && echo "stopped $name"
    rm -f "$DEV/$name.pid"
  fi
done

down_args=()
[ "$WIPE" = 1 ] && down_args=(-v)
if docker info >/dev/null 2>&1; then
  docker compose -f "$ROOT/hub/docker-compose.yml" --env-file "$ROOT/hub/.env.dev" down "${down_args[@]}" 2>&1 | grep -v "^$" | tail -1
  docker compose -f "$ROOT/server/docker-compose.yml" --env-file "$ROOT/server/.env.dev" down "${down_args[@]}" 2>&1 | grep -v "^$" | tail -1
fi

if [ "$WIPE" = 1 ]; then
  rm -rf "$DEV"
  echo "all data deleted (secrets in server/secrets and hub/secrets kept)"
fi
