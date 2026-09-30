"""The running service (Gateway_Specs §3): the local MQTT connection, and
enrollment followed by the WebSocket uplink to the API server. Both run
independently — devices keep being served (and the outbox keeps filling)
while the API is unreachable.
"""

import asyncio
import logging

import aiomqtt

from .agent import Agent
from .config import GatewayConfig
from .enrollment import enroll
from .store import Store
from .uplink import Uplink

log = logging.getLogger(__name__)


def connect(cfg: GatewayConfig, client_id: str) -> aiomqtt.Client:
    return aiomqtt.Client(hostname=cfg.mqtt_host, port=cfg.mqtt_port, identifier=client_id,
                          username=cfg.mqtt_username, password=cfg.mqtt_password,
                          clean_session=False, keepalive=60)


async def run(cfg: GatewayConfig) -> None:
    cfg.data_dir.mkdir(parents=True, exist_ok=True)
    # The broker waits for the psk file; empty = no device can connect yet.
    cfg.broker_dir.mkdir(parents=True, exist_ok=True)
    if not (cfg.broker_dir / "psk").exists():
        (cfg.broker_dir / "psk").write_text("")
        (cfg.broker_dir / "psk").chmod(0o640)
    store = Store(cfg.db_path)
    agent = Agent(cfg, store)
    local = asyncio.create_task(_local(cfg, agent))
    try:
        while True:
            if not agent.gateway_id or not agent.credential:
                log.info("not enrolled yet")
                creds = await enroll(cfg)
                agent.enrolled(creds.gateway_id, creds.credential)
                log.info("enrolled as %s for household '%s'", creds.gateway_id,
                         creds.household_name)
            await Uplink(cfg, agent).run()  # returns when removed in the app
            log.warning("removed: forgetting keys and snapshot, back to enrollment")
            agent.reset()
    finally:
        local.cancel()


async def _local(cfg: GatewayConfig, agent: Agent) -> None:
    backoff = 1
    while True:
        try:
            async with connect(cfg, "mc-agent") as client:
                backoff = 1

                async def publish(topic: str, body: str, retain: bool) -> None:
                    await client.publish(topic, body, qos=1, retain=retain)

                agent.set_publisher(publish)
                await client.subscribe("mc/v1/+/#", qos=1)
                log.info("connected to the local broker")
                agent.publish_state()

                async def periodic():
                    while True:
                        await asyncio.sleep(cfg.state_interval_s)
                        agent.housekeeping()
                        agent.publish_state()

                ticker = asyncio.create_task(periodic())
                try:
                    async for message in client.messages:
                        payload = message.payload if isinstance(message.payload, bytes) \
                            else str(message.payload or "").encode()
                        try:
                            await agent.on_message(str(message.topic), payload,
                                                   bool(message.retain))
                        except Exception:
                            log.exception("handling %s failed", message.topic)
                finally:
                    ticker.cancel()
        except aiomqtt.MqttError as e:
            agent.set_publisher(None)
            log.warning("local broker connection lost (%s); retrying in %ss", e, backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30)
