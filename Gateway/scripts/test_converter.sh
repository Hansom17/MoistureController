#!/bin/sh
# Tests of the Zigbee2MQTT converter: the generated data is current, the codec, and the converter loaded
# into the real zigbee-herdsman-converters / zigbee-herdsman libraries of a Zigbee2MQTT checkout.
#
#   scripts/test_converter.sh                  # Z2M_DIR defaults to ~/zigbee2mqtt (needs `pnpm install` done there)
#   UPDATE_FIXTURES=1 scripts/test_converter.sh   # rewrite the fixtures shared with the hub's tests
set -eu
here="$(cd "$(dirname "$0")" && pwd)"
root="$here/../.."
conv="$here/../firmware/zigbee2mqtt"
py="$root/.venv/bin/python"
[ -x "$py" ] || py=python3

"$py" "$here/gen_converter.py" --check

z2m="${Z2M_DIR:-$HOME/zigbee2mqtt}"
[ -d "$z2m/node_modules/zigbee-herdsman-converters" ] || { echo "no Zigbee2MQTT install with node_modules at $z2m (set Z2M_DIR)"; exit 2; }
# the converter imports zigbee-herdsman and zigbee-herdsman-converters, as it does inside the Zigbee2MQTT container
ln -sfn "$z2m/node_modules" "$conv/node_modules"

cd "$conv"
node --test test/*.test.mjs
