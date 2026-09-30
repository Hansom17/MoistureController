#!/usr/bin/env python3
"""Builds tests/core for qemu_x86 and runs it (QEMU never exits by itself: watch the output).

    firmware/scripts/test.py            build + run
    firmware/scripts/test.py --no-build just run the last build

Needs the Zephyr workspace (~/zephyrproject) and SDK (~/zephyr-sdk-*); override with
ZEPHYR_BASE, ZEPHYR_SDK_INSTALL_DIR, MC_ZEPHYR_VENV.
"""

import glob
import os
import subprocess
import sys
import time
from pathlib import Path

fw = Path(__file__).resolve().parents[1]
home = Path.home()
zbase = Path(os.environ.get("ZEPHYR_BASE", home / "zephyrproject" / "zephyr"))
sdk = Path(os.environ.get("ZEPHYR_SDK_INSTALL_DIR", next(iter(sorted(glob.glob(str(home / "zephyr-sdk-*")))), "")))
venv = Path(os.environ.get("MC_ZEPHYR_VENV", home / "zephyrproject" / ".venv"))
build = Path(os.environ.get("MC_FW_BUILD", "/tmp/mc-fw-tests")) / "core"

env = dict(os.environ, ZEPHYR_BASE=str(zbase), ZEPHYR_SDK_INSTALL_DIR=str(sdk),
           PATH=f"{venv}/bin:{sdk}/hosttools/usr/bin:{os.environ['PATH']}")

if "--no-build" not in sys.argv:
    r = subprocess.run(["west", "build", "-p", "auto", "-b", "qemu_x86", str(fw / "tests" / "core"),
                        "-d", str(build)], env=env)
    if r.returncode:
        sys.exit(r.returncode)

elf = build / "zephyr" / "zephyr.elf"
cmd = ["qemu-system-i386", "-m", "32", "-cpu", "qemu32,+nx,+pae", "-machine", "q35",
       "-device", "isa-debug-exit,iobase=0xf4,iosize=0x04", "-no-reboot", "-display", "none", "-monitor", "none",
       "-serial", "stdio", "-kernel", str(elf)]
q = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
lines, deadline = [], time.time() + 120
for line in q.stdout:
    lines.append(line)
    if "TESTSUITE SUMMARY END" in line or time.time() > deadline:
        break
q.kill()
out = "".join(lines)
start = out.find("Running TESTSUITE")
print(out[start:] if start >= 0 else out)
ok = "TESTSUITE SUMMARY END" in out and "SUITE FAIL" not in out and " FAIL - " not in out

# The messages the tests produced must validate with the Python models the server uses.
py = fw.parent / ".venv" / "bin" / "python"
if py.exists():
    r = subprocess.run([str(py), str(fw / "scripts" / "check_contract.py")], input=out, text=True)
    ok = ok and r.returncode == 0
else:
    print("contract check skipped: no .venv/bin/python with mc_core")
print("RESULT:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
