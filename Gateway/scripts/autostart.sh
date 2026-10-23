#!/bin/sh
# Installs a systemd service that brings the gateway containers up at boot and stops them cleanly at shutdown.
#
#   Gateway/scripts/autostart.sh            install and enable (asks for the sudo password)
#   Gateway/scripts/autostart.sh --print    only show the unit file
#   Gateway/scripts/autostart.sh --remove   disable and delete it
#
# The containers already have `restart: unless-stopped`, so Docker restarts a crashed one by itself and brings them back
# after a reboot. This service adds: the whole stack is brought up again at boot even after a `docker compose down` or
# when a container was removed, and `systemctl stop moisture-gateway` / a shutdown stops it gracefully (SQLite).
set -eu

here="$(cd "$(dirname "$0")" && pwd)"
fw="$(cd "$here/../firmware" && pwd)"
unit=moisture-gateway.service
path=/etc/systemd/system/$unit
user="${SUDO_USER:-$(id -un)}"
docker_bin="$(command -v docker || echo /usr/bin/docker)"

render() {
  cat <<UNIT
[Unit]
Description=MoistureController gateway (docker compose)
Requires=docker.service
After=docker.service network-online.target
Wants=network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
User=$user
WorkingDirectory=$fw
ExecStart=$docker_bin compose up -d
ExecStop=$docker_bin compose stop
TimeoutStartSec=600
TimeoutStopSec=120

[Install]
WantedBy=multi-user.target
UNIT
}

case "${1:-}" in
  --print) render; exit 0 ;;
  --remove)
    [ "$(id -u)" -eq 0 ] || exec sudo "$0" "$@"
    systemctl disable --now "$unit" 2>/dev/null || true
    rm -f "$path"
    systemctl daemon-reload
    echo "removed $unit"
    exit 0 ;;
  "") ;;
  *) echo "unknown option: $1"; exit 2 ;;
esac

[ -f "$fw/.env" ] || { echo "$fw/.env is missing: run Gateway/scripts/install.sh first"; exit 1; }
command -v systemctl >/dev/null 2>&1 || { echo "systemd is not available here"; exit 1; }
[ "$(id -u)" -eq 0 ] || exec sudo "$0" "$@"

render > "$path"
chmod 644 "$path"
systemctl daemon-reload
systemctl enable "$unit"
# no restart of what already runs: `up -d` only starts what is missing
systemctl start "$unit"
echo "installed $unit (user $user, $fw)"
systemctl --no-pager --lines=0 status "$unit" | sed -n 1,4p
