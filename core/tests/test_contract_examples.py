"""Every JSON example in contracts/*.md parses with the core models
(Server_Specs §14, "Contract" tests)."""

import json
import re
from pathlib import Path

import pytest

from mc_core.contract import device as d
from mc_core.contract import hub as h

CONTRACTS = Path(__file__).resolve().parents[2] / "contracts"

# Heading (section title prefix) → model for the JSON blocks under it.
MQTT_SECTIONS = {
    "### 4.1": d.Status,
    "### 4.2": d.Telemetry,
    "### 4.3": d.Event,
    "### 5.1": d.Command,
    "### 5.3": d.CmdAck,
    "### 6.1": d.ConfigDesired,
    "### 6.3": d.ConfigState,
}
HUB_SECTIONS = {
    "### 5.1": h.Snapshot,
    "### 5.2": h.Keys,
    "### 5.3": h.HubState,
    "### 5.4": h.RuleExec,
    "### 5.5": h.HubCmd,
}


def _blocks(path: Path, sections: dict) -> list[tuple[str, type, str]]:
    heading = ""
    out = []
    for m in re.finditer(r"^(#{2,3} [^\n]*)$|```json\n(.*?)```", path.read_text(), re.M | re.S):
        if m.group(1):
            heading = m.group(1)
            continue
        model = next((mdl for prefix, mdl in sections.items() if heading.startswith(prefix)), None)
        if model is not None:
            out.append((heading, model, m.group(2)))
    return out


def _fill_placeholders(text: str) -> str:
    # The docs abbreviate repeated content; replace with neutral values.
    text = re.sub(r'\[\s*"…[^"]*…"\s*\]', "[]", text)
    return text


EXAMPLES = _blocks(CONTRACTS / "mqtt.md", MQTT_SECTIONS) + _blocks(
    CONTRACTS / "hub.md", HUB_SECTIONS
)


def test_found_examples():
    # Guards against the extraction silently finding nothing.
    assert len(EXAMPLES) >= 15


@pytest.mark.parametrize(("heading", "model", "text"), EXAMPLES, ids=[e[0] for e in EXAMPLES])
def test_example_parses(heading, model, text):
    model.model_validate(json.loads(_fill_placeholders(text)))


def test_up_ack_inline_example():
    h.HubAck.model_validate({"topic": "down/snapshot", "rev": 42, "result": "applied"})
