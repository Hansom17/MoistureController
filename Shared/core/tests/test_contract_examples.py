"""Every JSON example in the contract regions of Gateway/specs.md and Server/specs.md parses with the core models
(Server/specs.md Part A §14, "Contract" tests)."""

import json
import re
from pathlib import Path

import pytest

from mc_core.contract import device as d
from mc_core.contract import gateway as g

ROOT = Path(__file__).resolve().parents[3]


def _region(path: Path, name: str) -> str:
    """The contract text between <!-- contract:name --> markers in a specs.md."""
    m = re.search(rf"<!-- contract:{name} -->(.*?)<!-- /contract:{name} -->", path.read_text(), re.S)
    assert m, f"no contract:{name} region in {path}"
    return m.group(1)

# mqtt.md: heading (section title prefix) → model for the JSON blocks under it.
MQTT_SECTIONS = {
    "### 4.1": d.Status,
    "### 4.2": d.Telemetry,
    "### 4.3": d.Event,
    "### 5.1": d.Command,
    "### 5.3": d.CmdAck,
    "### 6.1": d.ConfigDesired,
    "### 6.3": d.ConfigState,
}


def _blocks(text: str) -> list[tuple[str, str]]:
    heading = ""
    out = []
    for m in re.finditer(r"^(#{2,3} [^\n]*)$|```json\n(.*?)```", text, re.M | re.S):
        if m.group(1):
            heading = m.group(1)
        else:
            out.append((heading, m.group(2)))
    return out


def _fill_placeholders(text: str) -> str:
    # The docs abbreviate repeated content; replace with neutral values.
    text = re.sub(r'\[\s*"…[^"]*…"\s*\]', "[]", text)
    text = re.sub(r'("secret_sha256":\s*)"[^"]*"', r'\1"' + "ab" * 32 + '"', text)
    return text


MQTT = [(h, m, t) for h, t in _blocks(_region(ROOT / "Gateway" / "specs.md", "mqtt"))
        for prefix, m in MQTT_SECTIONS.items() if h.startswith(prefix)]
GATEWAY = _blocks(_region(ROOT / "Server" / "specs.md", "gateway_api"))


def _gateway_model(body: dict):
    """gateway_api.md blocks are typed by `t`; enrollment bodies by their keys."""
    if "t" in body:
        return g.MESSAGES[body["t"]]
    if "secret_sha256" in body:
        return g.EnrollStartRequest
    if "user_code" in body:
        return g.EnrollStartResponse
    if "gateway_id" in body:
        return g.EnrollPollResponse
    raise AssertionError(f"no model for {sorted(body)}")


def test_found_examples():
    # Guards against the extraction silently finding nothing.
    assert len(MQTT) >= 12 and len(GATEWAY) >= 8


@pytest.mark.parametrize(("heading", "model", "text"), MQTT, ids=[e[0] for e in MQTT])
def test_mqtt_example_parses(heading, model, text):
    model.model_validate(json.loads(_fill_placeholders(text)))


@pytest.mark.parametrize(("heading", "text"), GATEWAY, ids=[e[0] for e in GATEWAY])
def test_gateway_example_parses(heading, text):
    body = json.loads(_fill_placeholders(text))
    msg = _gateway_model(body).model_validate(body)
    if isinstance(msg, g.DeviceMessage):
        msg.parsed()  # the embedded device payload is valid mqtt.md too


def test_down_ack_inline_example():
    g.DownAck.model_validate({"t": "down_ack", "id": "01J9", "result": "applied"})
