#!/usr/bin/env python3
"""Zigbee2MQTT + PlantModule simulator.

Publishes and answers what Zigbee2MQTT and a PlantModule would on the same MQTT topics, so the hub
(and later the api and the app) can be developed without a coordinator.

    python Gateway/scripts/z2m_sim.py --port 1884 --modules 1 --pending 1 --report-interval 5

--modules  modules that are already part of the network
--pending  modules that join when a join window is opened (permit_join)
--speed    time compression for pump runs (10 = ten times faster)
"""
import argparse
import asyncio
import json
import random
import sys
from pathlib import Path

BASE = "zigbee2mqtt"
MODEL = "MC-PLANT"


class Module:
    def __init__(self, n: int, board: str = "carrier-v1") -> None:
        self.ieee = f"0x00124b00{n:08x}"
        self.name = self.ieee
        self.board = board
        self.cfg_rev = 0
        self.config: dict = {}
        self.seq = 0
        self.boot_id = random.randint(1, 60000)
        self.n_ack = self.n_event = 0
        self.moisture = {0: 35.0}
        self.runs: dict[int, asyncio.Task] = {}   # cmd_id -> task
        self.done: dict[int, int] = {}            # cmd_id -> n of its final ack (idempotency)
        self.state: dict = {}
        self.status = "operational"
        self.interview = "SUCCESSFUL"

    def entry(self) -> dict:
        return {"ieee_address": self.ieee, "friendly_name": self.name, "type": "EndDevice", "supported": True,
                "interview_state": self.interview, "model_id": MODEL,
                "software_build_id": "sim-0.1", "definition": {"model": MODEL, "vendor": "MoistureController"}}


class Sim:
    def __init__(self, transport, modules: int = 1, pending: int = 0, speed: float = 1.0,
                 report_interval: float = 5.0, join_delay: float = 1.0, fail_interview: bool = False,
                 reject_config: bool = False, base: str = BASE) -> None:
        self.t, self.speed, self.report_interval, self.join_delay = transport, speed, report_interval, join_delay
        self.fail_interview, self.reject_config, self.base = fail_interview, reject_config, base
        self.modules = {m.ieee: m for m in (Module(i + 1) for i in range(modules))}
        self.pending = [Module(100 + i) for i in range(pending)]
        self.join_open = False
        self.install_codes: list[str] = []
        self.tasks: set[asyncio.Task] = set()

    # ---- life cycle -------------------------------------------------------------------------

    async def start(self) -> None:
        await self.t.publish(f"{self.base}/bridge/state", b'{"state":"online"}', retain=True)
        await self._devices()
        await self.t.subscribe(f"{self.base}/bridge/request/#", self._on_request)
        await self.t.subscribe(f"{self.base}/+/set", self._on_set)
        for m in self.modules.values():
            await self._availability(m, "online")
            await self.report(m)

    async def run(self) -> None:
        await self.start()
        while True:
            await asyncio.sleep(self.report_interval)
            for m in list(self.modules.values()):
                m.moisture = {k: max(0.0, v - random.uniform(0.2, 0.8)) for k, v in m.moisture.items()}
                await self.report(m)

    def _spawn(self, coro) -> None:
        t = asyncio.get_running_loop().create_task(coro)
        self.tasks.add(t)
        t.add_done_callback(self.tasks.discard)

    # ---- what Zigbee2MQTT publishes ---------------------------------------------------------

    async def _devices(self) -> None:
        coordinator = {"ieee_address": "0x00124b0000000000", "friendly_name": "Coordinator", "type": "Coordinator"}
        entries = [coordinator] + [m.entry() for m in self.modules.values()]
        await self.t.publish(f"{self.base}/bridge/devices", json.dumps(entries).encode(), retain=True)

    async def _availability(self, m: Module, state: str) -> None:
        await self.t.publish(f"{self.base}/{m.name}/availability", json.dumps({"state": state}).encode(), retain=True)

    async def report(self, m: Module, **extra) -> None:
        """One state publication: Z2M merges the new keys into the device state and publishes it all."""
        m.seq = (m.seq + 1) % 65536
        st = m.state
        st.update(seq=m.seq, boot_id=m.boot_id, status=m.status, fast_mode=bool(m.runs), safe_reason="none",
                  cfg_rev=m.cfg_rev, cfg_result=st.get("cfg_result", "ok"), board=m.board, interface="1.0",
                  config_schema=1, linkquality=random.randint(80, 200), voltage_mv=0, uptime_s=m.seq * 5,
                  boot_reason="power_on", reset_count=0, rejoin_count=0, last_error=0, free_heap=143000)
        for sl in m.config.get("slots", []):
            n = sl["slot"]
            if sl["module"] == "moisture":
                v = m.moisture.get(n, 35.0)
                st.update({f"slot{n}_type": "moisture", f"slot{n}_value": round(v, 1),
                           f"slot{n}_raw": int(3000 - v * 18), f"slot{n}_error": "ok"})
            elif sl["module"] == "pump":
                running = any(True for _ in m.runs)
                st.update({f"slot{n}_type": "pump", f"slot{n}_value": 100 if running else 0,
                           f"slot{n}_raw": 0, f"slot{n}_error": "ok"})
        st.update(extra)
        await self.t.publish(f"{self.base}/{m.name}", json.dumps(st).encode())

    async def _ack(self, m: Module, cmd_id: int, state: str, reason: str = "none", ends_in_s: int = 0) -> None:
        m.n_ack += 1
        await self.report(m, cmd_ack={"n": m.n_ack, "cmd_id": cmd_id, "state": state, "reason": reason,
                                      "ends_in_s": ends_in_s})

    # ---- requests to Zigbee2MQTT ------------------------------------------------------------

    async def _on_request(self, topic: str, payload: bytes) -> None:
        what = topic[len(f"{self.base}/bridge/request/"):]
        try:
            data = json.loads(payload or b"{}")
        except ValueError:
            return
        if what == "permit_join":
            t = int(data.get("time", 0))
            self.join_open = t > 0
            await self.t.publish(f"{self.base}/bridge/response/permit_join",
                                 json.dumps({"data": {"time": t}, "status": "ok"}).encode())
            if self.join_open and self.pending:
                self._spawn(self._join_next())
        elif what == "install_code/add":
            self.install_codes.append(str(data.get("value", "")))
        elif what == "device/rename":
            for m in self.modules.values():
                if m.name == data.get("from"):
                    m.name = data["to"]
                    await self._devices()
                    await self._availability(m, "online")
                    await self.report(m)
        elif what == "device/remove":
            m = self.modules.pop(data.get("id"), None)
            if m:
                await self._devices()
        elif what == "device/interview":
            m = self.modules.get(data.get("id"))
            if m:
                m.interview = "SUCCESSFUL"
                await self._devices()
                await self._availability(m, "online")
                await self.report(m)

    async def _join_next(self) -> None:
        await asyncio.sleep(self.join_delay / self.speed)
        if not (self.join_open and self.pending):
            return
        m = self.pending.pop(0)
        self.modules[m.ieee] = m
        await self.t.publish(f"{self.base}/bridge/event", json.dumps(
            {"type": "device_joined", "data": {"ieee_address": m.ieee, "friendly_name": m.name}}).encode())
        m.interview = "PENDING"
        await self._devices()
        await asyncio.sleep(self.join_delay / self.speed)
        m.interview = "FAILED" if self.fail_interview else "SUCCESSFUL"
        self.fail_interview = False                        # the retry succeeds
        await self._devices()
        if m.interview == "SUCCESSFUL":
            await self._availability(m, "online")
            await self.report(m)

    # ---- commands to a module ---------------------------------------------------------------

    def _find(self, name: str) -> Module | None:
        return next((m for m in self.modules.values() if m.name == name), None)

    async def _on_set(self, topic: str, payload: bytes) -> None:
        m = self._find(topic[len(self.base) + 1:-len("/set")])
        if m is None:
            return
        try:
            msg = json.loads(payload)
        except ValueError:
            return
        if "config" in msg:
            cfg = msg["config"]
            if self.reject_config:
                m.state.update(cfg_result="rejected", cfg_error=0x0301)
            else:
                m.config, m.cfg_rev = cfg, cfg["rev"]
                m.state.update(cfg_result="ok", cfg_error=None)
                for sl in cfg.get("slots", []):
                    if sl["module"] == "moisture":
                        m.moisture.setdefault(sl["slot"], 35.0)
            await self.report(m)
        elif "pump_run" in msg:
            await self._pump_run(m, **msg["pump_run"])
        elif "pump_stop" in msg:
            c = msg["pump_stop"]
            for cid, task in list(m.runs.items()):
                task.cancel()
                m.runs.pop(cid, None)
                await self._ack(m, cid, "cancelled")
            await self._ack(m, c["cmd_id"], "done")
        elif "cancel" in msg:
            c = msg["cancel"]
            task = m.runs.pop(c["target"], None)
            if task:
                task.cancel()
            await self._ack(m, c["target"], "cancelled")
            await self._ack(m, c["cmd_id"], "done")
        elif "device_action" in msg:
            c = msg["device_action"]
            if c["action"] == "reboot":
                m.boot_id += 1
                m.seq = 0
            elif c["action"] == "clear_safe_mode":
                m.status = "operational"
            await self._ack(m, c["cmd_id"], "done")

    async def _pump_run(self, m: Module, cmd_id: int, slot: int, seconds: int, ttl_s: int) -> None:
        if cmd_id in m.done:                                # a repeated id is never executed twice
            return
        pump = next((s for s in m.config.get("slots", []) if s["slot"] == slot and s["module"] == "pump"), None)
        if pump is None:
            return await self._ack(m, cmd_id, "rejected", "slot_not_actuator")
        if seconds > pump.get("max_run_s", 60):
            return await self._ack(m, cmd_id, "rejected", "limit")
        if m.runs:
            return await self._ack(m, cmd_id, "rejected", "busy")
        await self._ack(m, cmd_id, "running", ends_in_s=seconds)

        async def finish() -> None:
            await asyncio.sleep(seconds / self.speed)
            m.runs.pop(cmd_id, None)
            m.done[cmd_id] = m.n_ack
            m.moisture = {k: min(100.0, v + 20.0) for k, v in m.moisture.items()}
            await self._ack(m, cmd_id, "done")

        m.runs[cmd_id] = asyncio.get_running_loop().create_task(finish())


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=1884)
    ap.add_argument("--user")
    ap.add_argument("--password")
    ap.add_argument("--modules", type=int, default=1)
    ap.add_argument("--pending", type=int, default=0)
    ap.add_argument("--speed", type=float, default=1.0)
    ap.add_argument("--report-interval", type=float, default=5.0)
    ap.add_argument("--fail-interview", action="store_true", help="the first joining module fails its interview")
    ap.add_argument("--reject-config", action="store_true")
    a = ap.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "firmware" / "hub" / "src"))
    from mc_hub.bus.transport import MqttTransport
    t = MqttTransport(a.host, a.port, a.user, a.password, client_id="z2m-sim")
    sim = Sim(t, a.modules, a.pending, a.speed, a.report_interval, fail_interview=a.fail_interview,
              reject_config=a.reject_config)
    await t.connect()
    await sim.run()


if __name__ == "__main__":
    asyncio.run(main())
