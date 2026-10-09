"""Message envelopes of Gateway/mqtt-contract.yaml."""
import json
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

V = 1
P = "mc/v1"


class Actor(BaseModel):
    user_id: str
    role: Literal["owner", "admin", "member", "viewer"]


class Request(BaseModel):
    v: int
    id: str
    ts: datetime
    deadline: datetime
    reply_to: str
    actor: Actor
    body: dict[str, Any] = Field(default_factory=dict)


def ok(id: str, body: dict | None = None) -> dict:
    return {"v": V, "id": id, "ok": True, "body": body or {}}


def err(id: str, error: dict) -> dict:
    return {"v": V, "id": id, "ok": False, "error": error}


def dumps(obj: Any) -> bytes:
    return json.dumps(obj, separators=(",", ":"), default=str).encode()


T_REQUEST = f"{P}/req/hub/"          # + kind
T_EVENT = f"{P}/event/"              # + kind
T_STATE = f"{P}/state/"              # + name
T_STATUS_HUB = f"{P}/status/hub"
