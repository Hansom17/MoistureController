"""PSK file for the local Mosquitto (Broker_Specs §2.1, §3).

Written atomically; the watcher in the broker container sends SIGHUP.
"""

import os
from pathlib import Path


def _write_atomic(path: Path, content: str, mode: int = 0o640) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text() == content:
        return False
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(content)
    os.chmod(tmp, mode)  # 0640 + shared group mcbroker: Mosquitto can read it
    tmp.replace(path)
    return True


def write_psk(broker_dir: Path, devices: list[dict]) -> bool:
    """`identity:hexkey` per `esp32-mqtt` device of the `keys` set."""
    content = "".join(f"{d['id']}:{d['psk']}\n" for d in devices
                      if d.get("adapter", "esp32-mqtt") == "esp32-mqtt")
    return _write_atomic(broker_dir / "psk", content)


def clear_psk(broker_dir: Path) -> None:
    _write_atomic(broker_dir / "psk", "")
