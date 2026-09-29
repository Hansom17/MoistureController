"""Every JSON example in contracts/*.md parses with the core models
(Api_Specs §14, "Contract" tests)."""

import json
import re
from pathlib import Path

import pytest

from mc_core.contract import device as d
from mc_core.contract import gateway as g

CONTRACTS = Path(__file__).resolve().parents[2] / "contracts"

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


def _blocks(path: Path) -> list[tuple[str, str]]:
    heading = ""
    out = []
    for m in re.finditer(r"^(#{2,3} [^\n]*)$|```json\n(.*?)```", path.read_text(), re.M | re.S):
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


MQTT = [(h, m, t) for h, t in _blocks(CONTRACTS / "mqtt.md")
        for prefix, m in MQTT_SECTIONS.items() if h.startswith(prefix)]
GATEWAY = _blocks(CONTRACTS / "gateway_api.md")


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
