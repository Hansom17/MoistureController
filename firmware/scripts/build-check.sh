#!/usr/bin/env bash
# Compile-checks the firmware. Without the Espressif radio blobs (`west blobs fetch
# hal_espressif`) WiFi can't be built, so WiFi and BT are switched off for this check:
# the result is not runnable, it only proves that everything else compiles and links.
set -euo pipefail
FW="$(cd "$(dirname "$0")/.." && pwd)"
BUILD="${MC_FW_BUILD:-/tmp/mc-fw-tests}/app"
mkdir -p "$BUILD.extra"
cat > "$BUILD.extra/nowifi.overlay" <<'EOT'
&wifi { status = "disabled"; };
&esp32_bt_hci { status = "disabled"; };
EOT
printf 'CONFIG_WIFI=n\nCONFIG_NET_L2_WIFI_MGMT=y\n' > "$BUILD.extra/nowifi.conf"

export ZEPHYR_BASE="${ZEPHYR_BASE:-$HOME/zephyrproject/zephyr}"
export ZEPHYR_SDK_INSTALL_DIR="${ZEPHYR_SDK_INSTALL_DIR:-$(ls -d "$HOME"/zephyr-sdk-* | head -1)}"
source "${MC_ZEPHYR_VENV:-$HOME/zephyrproject/.venv}/bin/activate"

EXTRA=()
if [ "${1:-}" = "--wifi" ]; then
  shift # the real build: needs the blobs
  west build -b doit_esp32_devkit_v1/esp32/procpu "$FW" -d "$BUILD-wifi" -- "$@"
else
  west build -p auto -b doit_esp32_devkit_v1/esp32/procpu "$FW" -d "$BUILD" -- \
    -DEXTRA_DTC_OVERLAY_FILE="$BUILD.extra/nowifi.overlay" \
    -DEXTRA_CONF_FILE="$BUILD.extra/nowifi.conf" "$@"
fi
