# Gateway

The box at home that runs the whole system: Zigbee coordinator with Zigbee2MQTT, an internal Mosquitto, and the hub service (rules, command queue, SQLite, REST + SSE API, hosting of the Flutter web build). Design: [`specs.md`](specs.md).

**State:** specification only; no code yet. The target layout is in `specs.md` §15.3 (`firmware/` for the hub service and compose files, `scripts/`, `hardware/`). The previous gateway and server implementation is in git history at commit `eb97b07`; `specs.md` §19 lists what to take from it.

## Planned run

```bash
docker compose up -d      # zigbee2mqtt, mosquitto, hub
```

The first start prints a one-time setup code in the hub's log; open `http://<gateway>/` and create the owner account.
