#!/bin/sh
# Puts the hub, api, Zigbee2MQTT converter and the web build of THIS checkout onto a gateway that runs the packaged
# (Yocto) services, without rebuilding the image. A backup of what was there is kept on the gateway.
#
#   Gateway/scripts/deploy_overlay.sh [root@moisture.local]
#
# Needs: the web build (App/scripts/build_web.sh) and ssh access as root. The gateway is a BusyBox system: only tar
# and sh are used there. Undo: tar xzf /root/backup-before-overlay/originals.tgz -C / on the gateway, then restart.
set -eu

target="${1:-root@moisture.local}"
here="$(cd "$(dirname "$0")" && pwd)"
repo="$(cd "$here/../.." && pwd)"
web="$repo/App/build/web"
[ -f "$web/index.html" ] || { echo "no web build in $web: run App/scripts/build_web.sh first"; exit 1; }

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
# COPYFILE_DISABLE: macOS tar would add ._* files that Python (alembic) and Zigbee2MQTT then try to load
export COPYFILE_DISABLE=1
tar czf "$tmp/hub.tgz" --exclude=__pycache__ -C "$repo/Gateway/firmware/hub/src" mc_hub
tar czf "$tmp/api.tgz" --exclude=__pycache__ -C "$repo/Gateway/firmware/api/src" mc_api
tar czf "$tmp/conv.tgz" --exclude=node_modules -C "$repo/Gateway/firmware/zigbee2mqtt" external_converters
tar czf "$tmp/web.tgz" -C "$repo/App/build" web
scp -q "$tmp"/*.tgz "$target:/tmp/"

ssh "$target" 'set -eu
site=/usr/lib/python3.12/site-packages
if [ ! -f /root/backup-before-overlay/originals.tgz ]; then
  mkdir -p /root/backup-before-overlay
  tar czf /root/backup-before-overlay/originals.tgz -C / usr/lib/python3.12/site-packages/mc_hub usr/lib/python3.12/site-packages/mc_api usr/share/zigbee2mqtt/external_converters usr/share/moisture-web
  echo "backup: /root/backup-before-overlay/originals.tgz"
fi
cd /tmp
rm -rf $site/mc_hub $site/mc_api /usr/share/zigbee2mqtt/external_converters /usr/share/moisture-web /tmp/webx
tar xzf hub.tgz -C $site
tar xzf api.tgz -C $site
mkdir -p /usr/share/zigbee2mqtt
tar xzf conv.tgz -C /usr/share/zigbee2mqtt
mkdir -p /tmp/webx && tar xzf web.tgz -C /tmp/webx && mv /tmp/webx/web /usr/share/moisture-web
find $site/mc_hub $site/mc_api /usr/share/zigbee2mqtt /usr/share/moisture-web -name "._*" -exec rm -f {} +
rm -f /tmp/hub.tgz /tmp/api.tgz /tmp/conv.tgz /tmp/web.tgz
systemctl restart zigbee2mqtt moisture-hub moisture-api
sleep 12
systemctl is-active zigbee2mqtt moisture-hub moisture-api mosquitto
sed -n 1,2p /usr/share/moisture-web/build-info.txt'
echo "done: reload the web app in a private window (the browser caches the old build)"
