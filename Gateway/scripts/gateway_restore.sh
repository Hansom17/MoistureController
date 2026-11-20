#!/bin/sh
# Puts a backup made by gateway_backup.sh back onto a gateway (typically after the image was installed again).
#
#   Gateway/scripts/gateway_restore.sh [--dry-run] [--yes] ARCHIVE [root@moisture.local]
#
#   --dry-run   upload and check everything (archive, database integrity, schema versions) but change nothing
#   --yes       do not ask for the confirmation
#
# What happens on the gateway: the current files are kept in /root/before-restore-<time>.tgz, then moisture-api,
# moisture-hub and zigbee2mqtt are stopped, hub.db, api.db and the Zigbee2MQTT files (network key, coordinator backup,
# paired devices) are replaced, and the three services are started again. The users, the plants, the rules, the history
# and the Zigbee network come back as they were; the modules keep working without joining again as long as the same
# coordinator dongle is plugged in. An .enc archive is decrypted here (passphrase from MC_BACKUP_PASSPHRASE or asked).
set -eu

dry=0
yes=0
archive=""
target="root@moisture.local"
while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) dry=1 ;;
    --yes) yes=1 ;;
    -h|--help) sed -n 2,14p "$0"; exit 0 ;;
    -*) echo "unknown option: $1"; exit 2 ;;
    *) if [ -z "$archive" ]; then archive="$1"; else target="$1"; fi ;;
  esac
  shift
done
[ -n "$archive" ] || { echo "usage: gateway_restore.sh [--dry-run] [--yes] ARCHIVE [root@host]"; exit 2; }
[ -f "$archive" ] || { echo "no such file: $archive"; exit 1; }

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
plain="$tmp/backup.tar.gz"
case "$archive" in
  *.enc)
    if [ -z "${MC_BACKUP_PASSPHRASE:-}" ]; then
      printf "Passphrase of the archive: " >&2; stty -echo 2>/dev/null || true; read -r MC_BACKUP_PASSPHRASE; stty echo 2>/dev/null || true; echo >&2
      export MC_BACKUP_PASSPHRASE
    fi
    openssl enc -d -aes-256-cbc -pbkdf2 -pass env:MC_BACKUP_PASSPHRASE -in "$archive" -out "$plain" || { echo "wrong passphrase or damaged file"; exit 1; }
    ;;
  *) cp "$archive" "$plain" ;;
esac

python3 - "$plain" <<'PY'
import json, sys, tarfile
t = tarfile.open(sys.argv[1])
names = {m.name for m in t.getmembers() if m.isfile()}
need = {"./hub.db", "./api.db", "./manifest.json", "./zigbee2mqtt/configuration.yaml", "./zigbee2mqtt/coordinator_backup.json", "./zigbee2mqtt/database.db"}
missing = sorted(need - names)
if missing:
    sys.exit("not a complete gateway backup, missing: " + ", ".join(missing))
man = json.load(t.extractfile("./manifest.json"))
print("Backup of %s from %s (%s)" % (man["host"], man["created"], man.get("os", "?")))
for k, v in man["databases"].items():
    print("  %-8s %8d bytes, schema %s, integrity %s" % (k, v["bytes"], v["alembic"], v["integrity"]))
print("  zigbee2mqtt: " + ", ".join(man.get("zigbee2mqtt", [])))
PY

if [ "$dry" -eq 0 ] && [ "$yes" -eq 0 ]; then
  echo
  echo "This REPLACES the hub and api databases and the Zigbee2MQTT data on $target with the backup above."
  echo "The current files are kept in /root/before-restore-<time>.tgz on the gateway."
  printf 'Type "restore" to go on: '
  read -r answer
  [ "$answer" = "restore" ] || { echo "cancelled"; exit 1; }
fi

scp -q -o BatchMode=yes "$plain" "$target:/tmp/mc-restore.tar.gz"
ssh -o BatchMode=yes "$target" "DRY=$dry sh -s" <<'REMOTE'
set -eu
st=/tmp/mc-restore.d
rm -rf "$st"; mkdir -p "$st"
trap 'rm -rf "$st" /tmp/mc-restore.tar.gz' EXIT
tar xzf /tmp/mc-restore.tar.gz -C "$st"

python3 - "$st" <<'PY'
import json, os, re, sqlite3, sys
st = sys.argv[1]
man = json.load(open(os.path.join(st, "manifest.json")))
known = {"hub.db": "/usr/lib/python3.12/site-packages/mc_hub/migrations/versions"}
for name, v in man["databases"].items():
    c = sqlite3.connect(os.path.join(st, name))
    if c.execute("pragma integrity_check").fetchone()[0] != "ok":
        sys.exit("%s is damaged" % name)
    c.close()
    if name in known and v["alembic"]:
        revs = {re.match(r"(\d+)_", f).group(1) for f in os.listdir(known[name]) if re.match(r"\d+_.*\.py$", f)}
        if v["alembic"] not in revs:
            sys.exit("%s is from newer software (schema %s, this gateway knows %s): install a newer image first" % (name, v["alembic"], sorted(revs)))
print("checks passed: databases are intact and their schemas are known here")
PY

if [ "$DRY" = "1" ]; then
  echo "dry run: nothing was changed. A real restore would replace:"
  ls -l /var/lib/moisture/hub/hub.db /var/lib/moisture/api/api.db /var/lib/zigbee2mqtt/configuration.yaml /var/lib/zigbee2mqtt/database.db 2>&1 | sed 's/^/  /'
  exit 0
fi

ts=$(date +%Y%m%d-%H%M%S)
keep=/root/before-restore-$ts.tgz
tar czf "$keep" -C / var/lib/private/moisture var/lib/private/zigbee2mqtt 2>/dev/null || tar czf "$keep" -C / var/lib/moisture var/lib/zigbee2mqtt
echo "current files kept in $keep"

systemctl stop moisture-api moisture-hub zigbee2mqtt

put() { # file destination-directory
  own=$(stat -c %u:%g "$2")
  cp "$1" "$2/"
  chown "$own" "$2/$(basename "$1")"
}
rm -f /var/lib/moisture/hub/hub.db-wal /var/lib/moisture/hub/hub.db-shm /var/lib/moisture/api/api.db-wal /var/lib/moisture/api/api.db-shm
put "$st/hub.db" /var/lib/moisture/hub
put "$st/api.db" /var/lib/moisture/api
for f in "$st"/zigbee2mqtt/*; do put "$f" /var/lib/zigbee2mqtt; done

systemctl start zigbee2mqtt moisture-hub moisture-api
sleep 12
systemctl is-active zigbee2mqtt moisture-hub moisture-api mosquitto
echo "restored. Open the web app in a private window (the browser may hold the old build) and sign in with your old login."
REMOTE
