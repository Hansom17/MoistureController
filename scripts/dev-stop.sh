#!/usr/bin/env bash
# Stops everything started by dev-start.sh.
#   --wipe   also delete all data (database, dev state) for a fresh start
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

if docker info >/dev/null 2>&1; then
  # No arrays: macOS bash 3.2 treats an empty array as unset under `set -u`.
  for stack in gateway api; do
    if [ "$WIPE" = 1 ]; then
      docker compose -f "$ROOT/$stack/docker-compose.yml" --env-file "$ROOT/$stack/.env.dev" down -v 2>&1 | tail -1
    else
      docker compose -f "$ROOT/$stack/docker-compose.yml" --env-file "$ROOT/$stack/.env.dev" down 2>&1 | tail -1
    fi
  done
fi

if [ "$WIPE" = 1 ]; then
  rm -rf "$DEV"
  echo "all data deleted (secrets in api/secrets and gateway/secrets kept)"
fi
