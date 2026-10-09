"""Events, snapshots and the retained status of the hub."""
import secrets

from mc_hub import CONTRACT, __version__
from mc_hub.clock import Clock

from .envelope import T_EVENT, T_STATE, T_STATUS_HUB, V, dumps
from .transport import Transport, Will


def status_payload(state: str, boot_id: int) -> bytes:
    return dumps({"state": state, "contract": CONTRACT, "version": __version__, "boot_id": boot_id})


def make_will(boot_id: int) -> Will:
    return Will(T_STATUS_HUB, status_payload("offline", boot_id), retain=True)


class Publisher:
    def __init__(self, transport: Transport, clock: Clock) -> None:
        self.t = transport
        self.clock = clock
        self.boot_id = secrets.randbelow(2**31)
        self.seq = 0

    async def event(self, kind: str, body: dict) -> None:
        self.seq += 1
        env = {"v": V, "boot_id": self.boot_id, "seq": self.seq, "ts": self.clock.dt().isoformat(),
               "kind": kind, "body": body}
        await self.t.publish(T_EVENT + kind, dumps(env))

    async def snapshot(self, name: str, body: dict | list) -> None:
        await self.t.publish(T_STATE + name, dumps(body), retain=True)

    async def status(self, state: str = "online") -> None:
        await self.t.publish(T_STATUS_HUB, status_payload(state, self.boot_id), retain=True)
