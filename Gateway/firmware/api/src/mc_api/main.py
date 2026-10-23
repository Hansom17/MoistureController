import asyncio
import json
import logging

import uvicorn

from .app import create_app
from .bus.transport import MqttTransport, Will
from .config import Settings
from .db import migrate
from .db.session import make_engine, make_sessionmaker


def configure_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


async def run(settings: Settings) -> None:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    await migrate.upgrade(settings.db_path)
    engine = make_engine(settings.db_path)
    status_topic = f"mc/v1/status/api/{settings.instance}"
    will = Will(status_topic, json.dumps({"state": "offline"}).encode(), retain=True)
    transport = MqttTransport(settings.mqtt_host, settings.mqtt_port, settings.mqtt_user, settings.mqtt_password,
                              will=will, client_id=f"mc-{settings.instance}", ca=settings.mqtt_ca)
    app = create_app(settings, transport, make_sessionmaker(engine), engine=engine)
    online = json.dumps({"state": "online"}).encode()

    async def announce() -> None:
        await transport.publish(status_topic, online, retain=True)

    transport.on_reconnect.append(announce)
    await transport.connect()
    await announce()
    server = uvicorn.Server(uvicorn.Config(app, host=settings.bind, port=settings.port, log_level="info"))
    await server.serve()
    await transport.publish(status_topic, json.dumps({"state": "offline"}).encode(), retain=True)
    await transport.close()
    await engine.dispose()
