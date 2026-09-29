#!/bin/sh
# Local stack on this machine: backend + Mosquitto (TLS-PSK) + Postgres in
# Docker, dev login, one seeded household and device (dev-bundle.json).
set -eu
cd "$(dirname "$0")/.."
./scripts/make-secrets.sh
docker compose --env-file .env.dev up -d --build
printf "waiting for the API"
until curl -sf http://localhost:8000/healthz >/dev/null; do printf "."; sleep 1; done
echo
docker compose --env-file .env.dev exec -T backend mc-server seed-dev --uid dev-user > dev-bundle.json
echo "ready: API http://localhost:8000/docs · broker localhost:8883 · bundle dev-bundle.json"
