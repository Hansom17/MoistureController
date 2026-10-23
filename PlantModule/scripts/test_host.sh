#!/usr/bin/env bash
# Host tests of the portable firmware core (no ESP-IDF needed): generated files are current, then build and run.
set -euo pipefail
cd "$(dirname "$0")/.."
python3 scripts/gen_interface_h.py --check
python3 scripts/gen_boards.py --check
python3 ../Gateway/scripts/gen_converter.py --check
python3 ../Gateway/scripts/gen_hub_params.py --check
build="${1:-$(mktemp -d)/mc_host}"
cmake -S firmware/test -B "$build" >/dev/null
cmake --build "$build"
"$build/mc_host_tests"
