"""firmware/tools/make_label.py: the factory CSV, the page and the lookup."""

import csv
import importlib.util
import os
import stat
from pathlib import Path

import pytest

from mc_core import ble

TOOL = Path(__file__).resolve().parents[3] / "PlantModule" / "scripts" / "make_label.py"
spec = importlib.util.spec_from_file_location("make_label", TOOL)
ml = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ml)


@pytest.fixture
def factory(tmp_path, monkeypatch):
    def fake_qr(text, out):
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text)
        return "test"

    monkeypatch.setattr(ml, "qr_png", fake_qr)
    return tmp_path


def run(factory, *args):
    return ml.main(["--dir", str(factory), *args])


def rows(factory):
    with (factory / "devices.csv").open(newline="") as f:
        return list(csv.DictReader(f))


def test_new_records_name_pop_and_label_and_draws_the_qr(factory, capsys):
    assert run(factory, "new", "--name", "MC-26EA", "--mac", "68:FE:71:81:26:EA") == 0
    (row,) = rows(factory)
    assert row["ble_name"] == "MC-26EA" and row["bt_mac"] == "68:FE:71:81:26:EA"
    pop = bytes.fromhex(row["pop_hex"])
    assert len(pop) == 16
    assert row["label"] == ble.label("MC-26EA", pop)
    assert ble.parse_label(row["label"]) == ("MC-26EA", pop)
    assert (factory / "labels" / "MC-26EA.png").read_text() == row["label"]  # the QR carries the label
    assert row["flashed_at"] == ""
    assert "MCPOP1:MC-26EA:" in capsys.readouterr().out


def test_the_csv_is_private(factory):
    run(factory, "new", "--name", "MC-0001")
    assert stat.S_IMODE(os.stat(factory / "devices.csv").st_mode) == 0o600


def test_each_device_gets_its_own_pop(factory):
    run(factory, "new", "--name", "MC-0001")
    run(factory, "new", "--name", "MC-0002")
    a, b = rows(factory)
    assert a["pop_hex"] != b["pop_hex"]


def test_an_existing_pop_can_be_recorded(factory):
    assert run(factory, "new", "--name", "MC-26EA", "--pop", "6887a2b1548813cb945d5cd64316e7d7") == 0
    assert rows(factory)[0]["label"] == "MCPOP1:MC-26EA:D23T5CAMH09WQ52XBKB465Q7TW"
    assert run(factory, "new", "--name", "MC-0003", "--pop", "abcd") == 1  # not 16 bytes


def test_a_device_is_not_added_twice(factory, capsys):
    assert run(factory, "new", "--name", "MC-0001", "--mac", "AA:BB:CC:DD:00:01") == 0
    assert run(factory, "new", "--name", "MC-0001", "--mac", "AA:BB:CC:DD:00:01") == 1
    assert "already in" in capsys.readouterr().err
    assert len(rows(factory)) == 1


def test_same_name_different_mac_needs_the_mac(factory, capsys):
    run(factory, "new", "--name", "MC-0001", "--mac", "AA:BB:CC:DD:00:01")
    run(factory, "new", "--name", "MC-0001", "--mac", "AA:BB:CC:EE:00:01")  # collision of the 4 digits
    assert len(rows(factory)) == 2
    reg = ml.Registry(factory / "devices.csv")
    with pytest.raises(ml.ToolError):
        reg.find(name="MC-0001")
    assert reg.find(mac="aa:bb:cc:ee:00:01")["bt_mac"] == "AA:BB:CC:EE:00:01"


def test_bad_names_are_refused(factory, capsys):
    assert run(factory, "new", "--name", "hello") == 1
    assert run(factory, "new") == 1
    assert not (factory / "devices.csv").exists()


def test_flash_writes_the_page_of_the_csv_row(factory, monkeypatch):
    run(factory, "new", "--name", "MC-26EA", "--pop", "6887a2b1548813cb945d5cd64316e7d7")
    calls = []
    monkeypatch.setattr(ml, "esptool", lambda *a, port: calls.append((a, port)) or "")
    assert run(factory, "flash", "--name", "MC-26EA", "--port", "/dev/x") == 0
    (args, port), = calls
    assert args[0] == "write-flash" and args[1] == hex(0x3FF000) and port == "/dev/x"
    page = Path(args[2]).read_bytes()
    assert page == ble.factory_page(bytes.fromhex("6887a2b1548813cb945d5cd64316e7d7"))
    assert rows(factory)[0]["flashed_at"] != ""


def test_flash_finds_the_board_by_its_mac(factory, monkeypatch):
    run(factory, "new", "--name", "MC-26EA", "--mac", "68:FE:71:81:26:EA")
    flashed = []
    monkeypatch.setattr(ml, "bluetooth_identity", lambda port: ("MC-26EA", "68:FE:71:81:26:EA"))
    monkeypatch.setattr(ml, "esptool", lambda *a, port: flashed.append(a) or "")
    assert run(factory, "flash", "--port", "/dev/x") == 0  # no name: asks the board who it is
    assert len(flashed) == 1


def test_flash_of_an_unknown_board_is_refused(factory, monkeypatch, capsys):
    monkeypatch.setattr(ml, "bluetooth_identity", lambda port: ("MC-9999", "AA:BB:CC:DD:99:99"))
    monkeypatch.setattr(ml, "esptool", lambda *a, port: pytest.fail("must not flash"))
    assert run(factory, "flash", "--port", "/dev/x") == 1
    assert "run `new` first" in capsys.readouterr().err


def test_bluetooth_name_from_the_wifi_mac(monkeypatch):
    # base MAC ...:E8 -> Bluetooth MAC ...:EA (+2), name = its last two bytes
    monkeypatch.setattr(ml, "esptool", lambda *a, port: "Chip is ESP32\nMAC: 68:fe:71:81:26:e8\n")
    assert ml.bluetooth_identity("/dev/x") == ("MC-26EA", "68:FE:71:81:26:EA")
    monkeypatch.setattr(ml, "esptool", lambda *a, port: "MAC: 68:fe:71:81:26:ff\n")
    assert ml.bluetooth_identity("/dev/x") == ("MC-2701", "68:FE:71:81:27:01")  # carries over


def test_list_and_qr(factory, capsys):
    run(factory, "new", "--name", "MC-0001")
    (factory / "labels" / "MC-0001.png").unlink()
    assert run(factory, "qr", "MC-0001") == 0
    assert (factory / "labels" / "MC-0001.png").exists()
    assert run(factory, "list") == 0
    assert "MC-0001" in capsys.readouterr().out
