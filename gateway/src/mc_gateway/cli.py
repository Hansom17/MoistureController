"""`mc-gateway` — run the gateway service, or inspect it from a shell (Gateway_Specs §8)."""

import argparse
import asyncio
import json
import logging
import os
import time
from datetime import datetime

from mc_core.commands import CommandRejected

from .agent import Agent
from .config import GatewayConfig
from .store import Store


def _ago(ts: str | int | None) -> str:
    if not ts:
        return "—"
    s = int(time.time()) - int(ts)
    return f"{s}s ago" if s < 120 else f"{s // 60} min ago" if s < 7200 else f"{s // 3600} h ago"


def _time(ts: int | None) -> str:
    return datetime.fromtimestamp(ts).strftime("%H:%M:%S") if ts else "—"


def cmd_run(cfg: GatewayConfig, args) -> None:
    from .runtime import run

    asyncio.run(run(cfg))


def cmd_status(cfg: GatewayConfig, args) -> None:
    store = Store(cfg.db_path)
    gateway_id = store.get("gateway_id")
    if not gateway_id:
        print("not enrolled — the enrollment code is in the log (docker compose logs gateway)")
        return
    snap = store.snapshot() or {}
    depth, oldest = store.outbox_depth()
    print(f"gateway       {gateway_id}")
    print(f"outbox        {depth} messages{f', oldest {_ago(oldest)}' if oldest else ''}")
    print(f"snapshot rev  {store.get('snapshot_rev', '—')}   keys rev {store.get('keys_rev', '—')}")
    print(f"LAN address   {cfg.lan_host}:{cfg.lan_port}")
    print(f"time zone     {snap.get('timezone', '—')}")
    print("devices:")
    for dev in json.loads(store.get("devices", "[]")):
        print(f"  {dev}  last seen {_ago(store.get(f'last_seen:{dev}'))}, "
              f"next wake {_time(int(store.get(f'next_wake:{dev}', '0')) or None)}")


def cmd_plants(cfg: GatewayConfig, args) -> None:
    store = Store(cfg.db_path)
    snap = store.snapshot() or {"plants": [], "rules": []}
    for p in snap["plants"]:
        latest = store.latest_reading(p["sensor"]["device"], p["sensor"]["slot"]) \
            if p.get("sensor") else None
        value = "no reading" if latest is None else (
            f"{latest['value']:.1f} % ({_ago(latest['ts'])})" if latest["value"] is not None
            else f"error {latest['error']}")
        rules = [r for r in snap["rules"] if r["plant_id"] == p["id"]]
        rule_text = ", ".join(f"<{r['threshold']:g}% → {r['water_s']}s" +
                              ("" if r["enabled"] else " (off)") for r in rules) or "no rules"
        print(f"{p['id']}  {value:<28} pump: {'yes' if p.get('pump') else 'no':<4} {rule_text}")


def cmd_water(cfg: GatewayConfig, args) -> None:
    async def go():
        from .runtime import connect

        agent = Agent(cfg, Store(cfg.db_path))
        async with connect(cfg, f"mc-agent-cli-{os.getpid()}") as client:
            async def publish(topic, body, retain):
                await client.publish(topic, body, qos=1, retain=retain)

            agent.set_publisher(publish)
            cmd_id = await agent.water_plant(args.plant, args.seconds)
        print(f"queued command {cmd_id}; the device runs it on its next wake")

    try:
        asyncio.run(go())
    except CommandRejected as e:
        raise SystemExit(f"rejected: {e}") from e


def cmd_logs(cfg: GatewayConfig, args) -> None:
    store = Store(cfg.db_path)
    print("rule decisions:")
    for d in store.recent_decisions():
        print(f"  {_time(d['ts'])}  plant {d['plant_id']}  {d['value']}%  {d['decision']}"
              f"{' (' + d['skip_reason'] + ')' if d['skip_reason'] else ''}")
    print("commands:")
    for c in store.recent_commands():
        print(f"  {_time(c['created_at'])}  {c['device']} slot {c['slot']}  {c['action']} "
              f"{c['seconds'] or ''}s  {c['source']:<5} {c['status']}")


def cmd_outbox(cfg: GatewayConfig, args) -> None:
    for msg in Store(cfg.db_path).outbox_peek(args.peek):
        print(json.dumps(msg, separators=(",", ":"))[:200])


def cmd_reset(cfg: GatewayConfig, args) -> None:
    if not args.yes:
        raise SystemExit("this forgets the enrollment and all keys; remove the gateway in the app "
                         "too, then run `mc-gateway reset --yes` and restart the containers")
    Agent(cfg, Store(cfg.db_path)).reset()
    print("reset done — restart the agent to enroll again")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)  # one line per poll otherwise
    p = argparse.ArgumentParser(prog="mc-gateway")
    sub = p.add_subparsers(dest="cmd")
    sub.add_parser("run", help="run the service (container default)").set_defaults(func=cmd_run)
    sub.add_parser("status").set_defaults(func=cmd_status)
    sub.add_parser("plants").set_defaults(func=cmd_plants)
    w = sub.add_parser("water", help="water a plant locally (works without internet)")
    w.add_argument("plant")
    w.add_argument("seconds", type=int)
    w.set_defaults(func=cmd_water)
    sub.add_parser("logs").set_defaults(func=cmd_logs)
    o = sub.add_parser("outbox", help="show buffered up messages")
    o.add_argument("--peek", type=int, default=20)
    o.set_defaults(func=cmd_outbox)
    r = sub.add_parser("reset")
    r.add_argument("--yes", action="store_true")
    r.set_defaults(func=cmd_reset)
    args = p.parse_args()
    (args.func if args.cmd else cmd_run)(GatewayConfig.from_env(), args)


if __name__ == "__main__":
    main()
