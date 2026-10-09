# Server

The central API (FastAPI + PostgreSQL, package `mc_api`) and the Firebase project config. Design: [`specs.md`](specs.md) (includes Firebase and the gateway ↔ API interface).

```
src/mc_api/   the service (api, auth, db, jobs, notify, realtime, services, migrations)
tests/        pytest suites
firebase/     Firebase config (login, push, hosting); no own code
scripts/      make-secrets.sh, advertise_mdns.py (LAN discovery for the app)
Dockerfile · docker-compose.yml · alembic.ini · pyproject.toml · .env.example
```

## Run

```bash
Server/scripts/make-secrets.sh
cp Server/.env.example Server/.env
docker compose -f Server/docker-compose.yml up -d --build
```

Dev stack incl. gateway, simulator and app: `scripts/dev-start.sh` from the repo root.

## Test

```bash
cd Server && ../.venv/bin/python -m pytest
```
