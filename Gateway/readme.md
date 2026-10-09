# Gateway

The household's box at home: Mosquitto for the ESP32 devices on the LAN, plus the gateway service that runs rules locally and talks to the Server over one outbound WebSocket. Design: [`specs.md`](specs.md) (includes the broker and the device ↔ gateway MQTT interface).

```
firmware/   gateway service (src/mc_gateway, tests), Dockerfile, docker-compose.yml, broker/ (Mosquitto image + config)
hardware/   empty for now
scripts/    make-secrets.sh, fake_device.py (ESP32 simulator for dev)
```

## Run

```bash
Gateway/scripts/make-secrets.sh
cp Gateway/firmware/.env.example Gateway/firmware/.env     # set MC_API_URL and MC_LAN_HOST
docker compose -f Gateway/firmware/docker-compose.yml up -d --build
docker compose -f Gateway/firmware/docker-compose.yml logs -f gateway    # shows the enrollment code
docker compose -f Gateway/firmware/docker-compose.yml exec gateway mc-gateway status
```

## Test

```bash
cd Gateway/firmware && ../../.venv/bin/python -m pytest
```
