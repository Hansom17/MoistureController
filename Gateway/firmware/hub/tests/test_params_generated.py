import subprocess
import sys
from pathlib import Path

from mc_hub.params import BATTERY, CONFIG

ROOT = Path(__file__).resolve().parents[4]


def test_generated_params_match_the_interface_file():
    r = subprocess.run([sys.executable, str(ROOT / "Gateway" / "scripts" / "gen_hub_params.py"), "--check"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_the_hub_uses_the_generated_numbers():
    from mc_hub.services import battery, config_sync
    assert battery.DEFAULT_LOW_MV == CONFIG["batt_low_mv"]["default"]
    assert battery.HIST == BATTERY["history_reports"] and battery.STALE_FACTOR == BATTERY["stale_factor"]
    assert config_sync.DEFAULTS["report_interval_s"] == CONFIG["report_interval_s"]["default"]
    assert set(config_sync.SCALARS) == set(CONFIG)
