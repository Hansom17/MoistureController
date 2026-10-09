#!/bin/sh
# Copies everything that is worth keeping into one folder: the two service databases (consistent copies
# made by the services themselves) and the Zigbee2MQTT data (network key, coordinator backup, devices).
#   scripts/backup.sh [target folder]       default: ./backup-YYYYmmdd-HHMMSS
set -eu
cd "$(dirname "$0")/../firmware"
target="${1:-backup-$(date +%Y%m%d-%H%M%S)}"
mkdir -p "$target"
for v in hub-data api-data; do
  docker run --rm -v "moisture_$v:/data:ro" -v "$(cd "$target" && pwd):/out" alpine \
    sh -c "mkdir -p /out/$v && cp -r /data/backups /out/$v/ 2>/dev/null || true"
done
docker run --rm -v moisture_z2m-data:/data:ro -v "$(cd "$target" && pwd):/out" alpine \
  sh -c "mkdir -p /out/z2m-data && cp -r /data/. /out/z2m-data/"
echo "Zigbee2MQTT data and the services' backup folders are in $target"
echo "Tip: POST /api/v1/backup (admin) first, so the newest database copies exist."
