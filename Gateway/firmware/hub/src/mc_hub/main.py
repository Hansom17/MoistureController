import asyncio
import logging
import signal

from .bus.publisher import Publisher, make_will
from .bus.transport import MqttTransport
from .clock import Clock
from .config import Settings
from .db import migrate
from .db.session import make_engine, make_sessionmaker
from .hub import Hub


async def run(settings: Settings) -> None:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    await migrate.upgrade(settings.db_path)
    engine = make_engine(settings.db_path)
    clock = Clock()
    # the publisher owns the boot id; the last will must carry the same one
    probe = Publisher(None, clock)  # type: ignore[arg-type]
    transport = MqttTransport(settings.mqtt_host, settings.mqtt_port, settings.mqtt_user, settings.mqtt_password,
                              will=make_will(probe.boot_id), client_id="mc-hub")
    pub = Publisher(transport, clock)
    pub.boot_id = probe.boot_id
    hub = Hub(transport, make_sessionmaker(engine), clock, pub, settings.z2m_base_topic,
              engine=engine, backup_dir=settings.data_dir / "backups")
    await transport.connect()
    transport.on_reconnect.append(hub.on_reconnect)
    await hub.start()
    logging.getLogger("mc_hub").info("hub running (boot_id %s)", pub.boot_id)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    async def ticker() -> None:
        while True:
            await asyncio.sleep(1)
            try:
                await hub.tick()
            except Exception:
                logging.getLogger("mc_hub").exception("job tick failed")

    ticks = asyncio.create_task(ticker())
    await stop.wait()
    ticks.cancel()
    await hub.stop()
    await transport.close()
    await engine.dispose()


def configure_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
