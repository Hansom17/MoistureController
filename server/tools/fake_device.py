#!/usr/bin/env python3
"""Plant device simulator — speaks contracts/mqtt.md like the real firmware.

Stands in for the ESP32 board until the hardware exists. Each wake cycle:
connect (persistent session, LWT) → status online → subscribe → telemetry →
apply newer config → run queued commands → acks → status sleeping → disconnect.

    # pairing bundle from `mc-server seed-dev` or the app's "add device" call
    python tools/fake_device.py --bundle bundle.json --interval 20

    # plain MQTT against a local dev broker (no TLS-PSK)
    python tools/fake_device.py --bundle bundle.json --plain --port 1883

Needs Python ≥ 3.13 for TLS-PSK (ssl.SSLContext.set_psk_client_callback) and
aiomqtt. Uses mc_core for config validation when installed, like the firmware
validating against its own pin table.
"""

import argparse
import asyncio
import json
import logging
import random
import ssl
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

import aiomqtt

log = logging.getLogger("fake_device")

HARD_LIMIT_S = 300
SLOTS_MAX = 6
RECENT_COMMANDS = 16

try:  # same pin rules as the backend; the firmware has its own copy
    from mc_core.contract.device import ConfigDesired, Limits
    from mc_core.pins import validate_config
except ImportError:  # pragma: no cover
    validate_config = None


# --- persisted device state (≈ NVS + RTC memory) ---------------------------------------


@dataclass
class State:
    seq: int = 0
    boot: int = 0
    config: dict = field(default_factory=lambda: {"rev": 0, "wake_interval_s": 600, "slots": []})
    config_published: bool = False
    recent: list = field(default_factory=list)  # [(command id, ack dict)]
    last_pump_end: float = 0.0
    moisture: float = 55.0
    last_model_update: float = field(default_factory=time.time)
    service_until: float = 0.0

    @classmethod
    def load(cls, path: Path) -> "State":
        if path.exists():
            return cls(**json.loads(path.read_text()))
        return cls()

    def save(self, path: Path) -> None:
        path.write_text(json.dumps(asdict(self), indent=2))


# --- the simulated plant ---------------------------------------------------------------------


class Soil:
    """Moisture drops by `dry_rate` %/h (scaled), watering adds `per_second` % per pump second."""

    def __init__(self, state: State, dry_rate: float, time_scale: float, per_second: float):
        self.state = state
        self.dry_rate = dry_rate
        self.time_scale = time_scale
        self.per_second = per_second

    def update(self) -> float:
        now = time.time()
        hours = (now - self.state.last_model_update) / 3600 * self.time_scale
        self.state.moisture = max(3.0, self.state.moisture - self.dry_rate * hours)
        self.state.last_model_update = now
        return self.state.moisture

    def water(self, seconds: float) -> None:
        self.state.moisture = min(95.0, self.state.moisture + seconds * self.per_second)


# --- device ------------------------------------------------------------------------------------


class FakeDevice:
    def __init__(self, args, bundle: dict):
        self.args = args
        self.id = bundle["device_id"]
        self.host = args.host or bundle["mqtt"]["host"]
        self.port = args.port or bundle["mqtt"]["port"]
        self.psk = bundle["mqtt"]["psk"]
        self.state_path = Path(args.state or f".fake-{self.id}.json")
        self.state = State.load(self.state_path)
        self.state.boot += 1
        self.soil = Soil(self.state, args.dry_rate, args.time_scale, args.water_per_s)
        if args.moisture is not None:
            self.state.moisture = args.moisture
        self.cold_boot = True

    def topic(self, suffix: str) -> str:
        return f"mc/v1/{self.id}/{suffix}"

    def tls(self) -> ssl.SSLContext | None:
        if self.args.plain:
            return None
        if not hasattr(ssl.SSLContext, "set_psk_client_callback"):
            sys.exit("TLS-PSK needs Python ≥ 3.13 (or use --plain against a dev broker)")
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        ctx.maximum_version = ssl.TLSVersion.TLSv1_2
        ctx.set_ciphers("PSK-AES128-GCM-SHA256")
        key = bytes.fromhex(self.psk)
        ctx.set_psk_client_callback(lambda hint: (self.id, key))
        return ctx

    def interval(self) -> int:
        return self.args.interval or self.state.config.get("wake_interval_s", 600)

    # --- one wake cycle ------------------------------------------------------------------

    async def cycle(self) -> None:
        incoming: list[aiomqtt.Message] = []
        will = aiomqtt.Will(self.topic("status"), json.dumps({"state": "offline"}), 1, True)
        async with aiomqtt.Client(
            hostname=self.host, port=self.port, identifier=self.id,
            username=self.id if self.args.plain else None, clean_session=False,
            keepalive=60, will=will, tls_context=self.tls(),
        ) as client:
            await self.pub(client, "status", {"state": "online", "fw": "0.4.0-sim",
                                              "boot": self.state.boot}, retain=True)
            await client.subscribe(self.topic("cmd"), qos=1)
            await client.subscribe(self.topic("config/desired"), qos=1)

            async def drain():
                async for m in client.messages:
                    incoming.append(m)

            reader = asyncio.create_task(drain())
            await asyncio.sleep(self.args.drain_s)  # queued messages arrive now

            await self.telemetry(client)
            if self.cold_boot:
                await self.pub(client, "event", {"seq": self.next_seq(), "ts": int(time.time()),
                                                 "kind": "boot", "detail": "power_on"})

            # Config before commands (mqtt.md §7).
            self.config_sent = False
            for m in [m for m in incoming if str(m.topic).endswith("config/desired")]:
                await self.apply_config(client, m.payload)
            if (self.cold_boot or not self.state.config_published) and not self.config_sent:
                await self.publish_config_state(client, "boot")
            for m in [m for m in incoming if str(m.topic).endswith("/cmd")]:
                await self.command(client, json.loads(m.payload))
            incoming.clear()

            # Service mode: stay connected and keep handling messages.
            while time.time() < self.state.service_until:
                await asyncio.sleep(1)
                for m in list(incoming):
                    incoming.remove(m)
                    if str(m.topic).endswith("config/desired"):
                        await self.apply_config(client, m.payload)
                    else:
                        await self.command(client, json.loads(m.payload))

            if self.args.crash:
                log.warning("simulating a crash: dropping the connection without 'sleeping'")
                reader.cancel()
                client._client._sock.close()  # noqa: SLF001 — no DISCONNECT → LWT fires
                raise SystemExit(1)

            await self.pub(client, "status", {"state": "sleeping", "next_wake_s": self.interval()},
                           retain=True)
            reader.cancel()
        self.cold_boot = False
        self.state.save(self.state_path)

    async def pub(self, client, suffix: str, payload: dict, retain: bool = False) -> None:
        body = json.dumps(payload, separators=(",", ":"))
        await client.publish(self.topic(suffix), body, qos=1, retain=retain)
        log.info("→ %-13s %s", suffix, body if len(body) < 160 else body[:157] + "…")

    def next_seq(self) -> int:
        self.state.seq += 1
        return self.state.seq

    def slots(self) -> list[dict]:
        return self.state.config.get("slots", [])

    async def telemetry(self, client) -> None:
        moisture = self.soil.update()
        readings = []
        for s in self.slots():
            if s["module"] in ("moisture_capacitive", "moisture_resistive"):
                if self.args.sensor_error:
                    readings.append({"slot": s["slot"], "type": "soil_moisture",
                                     "error": "no_signal", "raw": 4095})
                else:
                    value = round(moisture + random.uniform(-0.6, 0.6), 1)
                    cal = s.get("cal") or {"dry": 3000, "wet": 1200}
                    raw = int(cal["dry"] + (cal["wet"] - cal["dry"]) * value / 100)
                    readings.append({"slot": s["slot"], "type": "soil_moisture",
                                     "value": value, "unit": "%", "raw": raw})
            elif s["module"] == "ds18b20":
                readings.append({"slot": s["slot"], "type": "temperature",
                                 "value": round(21 + random.uniform(-1, 1), 1), "unit": "°C"})
        await self.pub(client, "telemetry", {
            "seq": self.next_seq(), "ts": int(time.time()),
            "cfg_rev": self.state.config.get("rev", 0), "readings": readings,
            "health": {"batt_mv": self.args.batt_mv + random.randint(-15, 15),
                       "rssi": random.randint(-72, -58),
                       "wake": "power_on" if self.cold_boot else "timer",
                       "cycle_ms": random.randint(1800, 2400),
                       "wifi_ms": random.randint(1100, 1600)}})

    # --- config (§6.2) ------------------------------------------------------------------------

    async def apply_config(self, client, payload: bytes) -> None:
        if not payload:
            return
        desired = json.loads(payload)
        if desired.get("rev", 0) <= self.state.config.get("rev", 0):
            return
        error = self.validate(desired)
        if error:
            log.warning("config rev %s rejected: %s", desired["rev"], error)
            await self.publish_config_state(client, "rejected", desired["rev"], error)
            return
        self.state.config = {k: desired[k] for k in ("rev", "wake_interval_s", "slots")}
        await self.publish_config_state(client, "applied")

    def validate(self, desired: dict) -> dict | None:
        if validate_config is None:
            return None
        try:
            cfg = ConfigDesired.model_validate(desired)
        except Exception as e:  # noqa: BLE001
            return {"code": "out_of_range", "detail": str(e)[:100]}
        errors = validate_config(cfg, Limits(max_run_s_hard=HARD_LIMIT_S, slots_max=SLOTS_MAX))
        return errors[0].model_dump(exclude_none=True) if errors else None

    async def publish_config_state(self, client, result: str, rejected_rev: int | None = None,
                                   error: dict | None = None) -> None:
        body = {**self.state.config, "result": result,
                "detected": [{"bus": "onewire", "pin": 27, "module": "ds18b20"}],
                "limits": {"max_run_s_hard": HARD_LIMIT_S, "slots_max": SLOTS_MAX}}
        if result == "rejected":
            body.update(rejected_rev=rejected_rev, error=error)
        await self.pub(client, "config/state", body, retain=True)
        self.state.config_published = True
        self.config_sent = True

    # --- commands (§5) ----------------------------------------------------------------------------

    async def command(self, client, cmd: dict) -> None:
        cid = cmd.get("id")
        for seen_id, ack in self.state.recent:
            if seen_id == cid:  # duplicate delivery: re-ack, don't execute twice
                await self.pub(client, "cmd/ack", ack)
                return
        ack = await self.execute(client, cmd)
        self.state.recent = (self.state.recent + [(cid, ack)])[-RECENT_COMMANDS:]
        await self.pub(client, "cmd/ack", ack)

    async def execute(self, client, cmd: dict) -> dict:
        cid, action, args = cmd["id"], cmd.get("action"), cmd.get("args", {})
        now = int(time.time())
        if cmd.get("exp", 0) < now:
            return {"id": cid, "status": "rejected", "reason": "expired"}
        if action == "pump.run":
            slot = next((s for s in self.slots() if s["slot"] == args.get("slot")), None)
            if slot is None or slot["module"] != "pump_relay":
                return {"id": cid, "status": "rejected", "reason": "slot_not_actuator"}
            seconds = args.get("seconds", 0)
            if not 1 <= seconds <= min(slot.get("max_run_s", 0), HARD_LIMIT_S):
                return {"id": cid, "status": "rejected", "reason": "safety_limit"}
            if time.time() - self.state.last_pump_end < slot.get("min_pause_s", 0):
                return {"id": cid, "status": "rejected", "reason": "safety_limit"}
            log.info("💧 pump on slot %s for %ss", slot["slot"], seconds)
            await asyncio.sleep(min(seconds, self.args.max_real_pump_s))
            self.soil.water(seconds)
            self.state.last_pump_end = time.time()
            return {"id": cid, "status": "done", "ts": int(time.time())}
        if action == "cmd.cancel":
            # Commands run in order within one wake, so the target already ran.
            return {"id": cid, "status": "rejected", "reason": "already_done"}
        if action == "pump.stop":
            return {"id": cid, "status": "done", "ts": now}
        if action == "device.identify":
            log.info("💡 blinking LED for %ss", args.get("seconds", 10))
            return {"id": cid, "status": "done", "ts": now}
        if action == "device.service":
            minutes = max(1, min(30, int(args.get("minutes", 15))))
            self.state.service_until = time.time() + minutes * 60
            await self.pub(client, "status", {"state": "service", "until_s": minutes * 60},
                           retain=True)
            return {"id": cid, "status": "done", "ts": now}
        if action == "device.reboot":
            self.cold_boot = True
            self.state.boot += 1
            return {"id": cid, "status": "done", "ts": now}
        return {"id": cid, "status": "rejected", "reason": "unknown_action"}


async def main_async(args) -> None:
    bundle = json.loads(Path(args.bundle).read_text()) if args.bundle else {
        "device_id": args.device_id, "mqtt": {"host": args.host, "port": args.port,
                                              "psk": args.psk}}
    device = FakeDevice(args, bundle)
    log.info("device %s → %s:%s (%s), wake every %ss", device.id, device.host, device.port,
             "plain" if args.plain else "TLS-PSK", device.interval())
    failures = 0
    while True:
        try:
            await device.cycle()
            failures = 0
        except aiomqtt.MqttError as e:
            failures += 1
            log.warning("wake cycle failed (%s); buffering is not simulated", e)
        if args.once:
            return
        await asyncio.sleep(min(device.interval(), 30 * (failures + 1)) if failures
                            else device.interval())


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--bundle", help="pairing bundle JSON {device_id, mqtt:{host,port,psk}}")
    p.add_argument("--device-id")
    p.add_argument("--psk")
    p.add_argument("--host", help="override the bundle's broker host")
    p.add_argument("--port", type=int, help="override the bundle's broker port")
    p.add_argument("--plain", action="store_true", help="no TLS; username = device id")
    p.add_argument("--interval", type=int, help="wake interval override in real seconds")
    p.add_argument("--time-scale", type=float, default=60.0,
                   help="soil model speed-up (default: 1 real minute = 1 simulated hour)")
    p.add_argument("--dry-rate", type=float, default=1.5, help="moisture loss in %%/hour")
    p.add_argument("--water-per-s", type=float, default=2.5, help="moisture gain per pump second")
    p.add_argument("--moisture", type=float, help="start value in %%")
    p.add_argument("--batt-mv", type=int, default=3950)
    p.add_argument("--sensor-error", action="store_true", help="report no_signal on sensors")
    p.add_argument("--crash", action="store_true", help="drop the connection → Last Will")
    p.add_argument("--drain-s", type=float, default=1.0, help="wait for queued messages")
    p.add_argument("--max-real-pump-s", type=float, default=3.0,
                   help="cap real waiting per pump run (the model uses the full seconds)")
    p.add_argument("--state", help="state file (default .fake-<id>.json)")
    p.add_argument("--once", action="store_true", help="one wake cycle, then exit")
    args = p.parse_args()
    if not args.bundle and not (args.device_id and args.psk and args.host):
        p.error("--bundle or --device-id/--psk/--host required")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    try:
        asyncio.run(main_async(args))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
