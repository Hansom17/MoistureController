"""The running agent: enrollment, then the local MQTT connection (Hub_Specs §3)."""

import asyncio
import logging

import aiomqtt

from mc_core.contract import topics

from .agent import Agent
from .config import HubConfig
from .enrollment import enroll
from .store import Store

log = logging.getLogger(__name__)


def connect(cfg: HubConfig, client_id: str) -> aiomqtt.Client:
    return aiomqtt.Client(hostname=cfg.mqtt_host, port=cfg.mqtt_port, identifier=client_id,
                          username=cfg.mqtt_username, password=cfg.mqtt_password,
                          clean_session=False, keepalive=60)


async def run(cfg: HubConfig) -> None:
    cfg.data_dir.mkdir(parents=True, exist_ok=True)
    # The broker waits for these; empty psk = no device can connect yet.
    (cfg.broker_dir / "conf.d").mkdir(parents=True, exist_ok=True)
    if not (cfg.broker_dir / "psk").exists():
        (cfg.broker_dir / "psk").write_text("")
        (cfg.broker_dir / "psk").chmod(0o640)
    store = Store(cfg.db_path)
    agent = Agent(cfg, store)

    if not agent.hub_id:
        log.info("not enrolled yet")
        creds = await enroll(cfg)
        agent.enrolled(creds.hub_id, creds.mqtt.host, creds.mqtt.port, creds.mqtt.psk)
        log.info("enrolled as %s for household '%s'; the broker restarts with the bridge",
                 creds.hub_id, creds.household_name)
    else:
        # Keep the bridge config in line with the stored device list.
        import json

        agent.write_bridge(json.loads(store.get("devices", "[]")))

    backoff = 1
    while True:
        try:
            async with connect(cfg, "mc-agent") as client:
                backoff = 1

                async def publish(topic: str, body: str, retain: bool) -> None:
                    await client.publish(topic, body, qos=1, retain=retain)

                agent.set_publisher(publish)
                await client.subscribe("mc/v1/+/#", qos=1)
                await client.subscribe(topics.hub(agent.hub_id, "#"), qos=1)
                log.info("connected to the local broker")
                await agent.publish_state()

                async def periodic():
                    while True:
                        await asyncio.sleep(cfg.state_interval_s)
                        agent.housekeeping()
                        await agent.publish_state()

                ticker = asyncio.create_task(periodic())
                try:
                    async for message in client.messages:
                        payload = message.payload if isinstance(message.payload, bytes) \
                            else str(message.payload or "").encode()
                        try:
                            await agent.on_message(str(message.topic), payload)
                        except Exception:
                            log.exception("handling %s failed", message.topic)
                finally:
                    ticker.cancel()
        except aiomqtt.MqttError as e:
            agent.set_publisher(None)
            log.warning("local broker connection lost (%s); retrying in %ss", e, backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30)
