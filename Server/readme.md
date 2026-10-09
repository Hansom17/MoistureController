# Server

The central API (FastAPI + PostgreSQL, package `mc_api`). **Superseded:** the redesign folds it into the Gateway hub ([`../Gateway/specs.md`](../Gateway/specs.md)); this folder stays as the code base to migrate from. Old design: [`specs.md`](specs.md).

```
src/mc_api/   the service (api, auth, db, jobs, notify, realtime, services, migrations)
tests/        pytest suites
scripts/      make-secrets.sh, advertise_mdns.py (LAN discovery for the app)
Dockerfile · docker-compose.yml · alembic.ini · pyproject.toml · .env.example
```

## Run

```bash
Server/scripts/make-secrets.sh
cp Server/.env.example Server/.env
docker compose -f Server/docker-compose.yml up -d --build
```

Dev stack incl. gateway and app: `scripts/dev-start.sh` from the repo root.

## Test

```bash
cd Server && ../.venv/bin/python -m pytest
```
