# The hub: devices, commands, rules, alerts. Build context: Gateway/firmware/hub
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 MC_DATA_DIR=/data
WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN pip install . && useradd --system --uid 10001 --no-create-home mc && mkdir /data && chown mc /data

USER mc
VOLUME /data
# no HTTP port: the hub only talks MQTT
CMD ["mc-hub", "run"]
