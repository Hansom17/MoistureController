#!/bin/sh
# Downloads a backup of a gateway that runs the packaged (Yocto/systemd) services: everything that is lost when the
# image is installed again.
#
#   Gateway/scripts/gateway_backup.sh [--encrypt] [--out DIR] [root@moisture.local]
#
# What is in the archive (one .tar.gz, or .tar.gz.enc with --encrypt):
#   hub.db, api.db              consistent copies made with SQLite's own backup, safe while the services run
#   zigbee2mqtt/                configuration.yaml (network key, channel), coordinator_backup.json, database.db
#                               (the paired devices), state.json
#   manifest.json               when, from where, which database revisions
# The archive contains secrets (Zigbee network key, password hashes, the Telegram token): keep it private. --encrypt asks
# for a passphrase (or reads MC_BACKUP_PASSPHRASE) and wraps it with AES-256 (openssl).
# Put it back with Gateway/scripts/gateway_restore.sh.
set -eu

encrypt=0
out="."
target="root@moisture.local"
while [ $# -gt 0 ]; do
  case "$1" in
    --encrypt) encrypt=1 ;;
    --out) shift; out="$1" ;;
    -h|--help) sed -n 2,16p "$0"; exit 0 ;;
    -*) echo "unknown option: $1"; exit 2 ;;
    *) target="$1" ;;
  esac
  shift
done
mkdir -p "$out"
stamp="$(date +%Y%m%d-%H%M%S)"
host="${target#*@}"
file="$out/gateway-backup-$host-$stamp.tar.gz"

echo "Backing up $target ..."
ssh -o BatchMode=yes "$target" 'set -eu
d=$(mktemp -d /tmp/mc-backup.XXXXXX)
trap "rm -rf $d" EXIT
mkdir -p "$d/zigbee2mqtt"
python3 - "$d" <<\PY
import json, os, shutil, socket, sqlite3, sys, time
d = sys.argv[1]
man = {"created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "host": socket.gethostname(), "format": 1, "databases": {}}
for name, path in (("hub.db", "/var/lib/moisture/hub/hub.db"), ("api.db", "/var/lib/moisture/api/api.db")):
    src = sqlite3.connect("file:%s?mode=ro" % path, uri=True)
    dst = sqlite3.connect(os.path.join(d, name))
    src.backup(dst)                                   # the online backup API: a consistent copy while the service writes
    rev = None
    try:
        rev = dst.execute("select version_num from alembic_version").fetchone()
        rev = rev[0] if rev else None
    except sqlite3.Error:
        pass
    ok = dst.execute("pragma integrity_check").fetchone()[0]
    man["databases"][name] = {"alembic": rev, "integrity": ok, "bytes": os.path.getsize(os.path.join(d, name))}
    dst.close(); src.close()
for f in ("configuration.yaml", "coordinator_backup.json", "database.db", "state.json"):
    p = os.path.join("/var/lib/zigbee2mqtt", f)
    if os.path.exists(p):
        shutil.copy2(p, os.path.join(d, "zigbee2mqtt", f))
        man.setdefault("zigbee2mqtt", []).append(f)
try:
    man["os"] = [l.split("=", 1)[1].strip().strip(chr(34)) for l in open("/etc/os-release") if l.startswith("PRETTY_NAME=")][0]
except Exception:
    pass
json.dump(man, open(os.path.join(d, "manifest.json"), "w"), indent=2)
PY
tar czf - -C "$d" .' > "$file"

# a local check of what came back
python3 - "$file" <<'PY'
import json, sys, tarfile
t = tarfile.open(sys.argv[1])
names = [m.name for m in t.getmembers() if m.isfile()]
need = {"./hub.db", "./api.db", "./manifest.json", "./zigbee2mqtt/configuration.yaml", "./zigbee2mqtt/coordinator_backup.json", "./zigbee2mqtt/database.db"}
missing = sorted(need - set(names))
if missing:
    sys.exit("the backup is incomplete, missing: " + ", ".join(missing))
man = json.load(t.extractfile("./manifest.json"))
bad = [k for k, v in man["databases"].items() if v["integrity"] != "ok"]
if bad:
    sys.exit("integrity check failed for: " + ", ".join(bad))
print("  ok: %s from %s (%s)" % (man["created"], man["host"], man.get("os", "?")))
for k, v in man["databases"].items():
    print("  %-8s %8d bytes, schema %s" % (k, v["bytes"], v["alembic"]))
print("  zigbee2mqtt: " + ", ".join(man.get("zigbee2mqtt", [])))
PY

if [ "$encrypt" -eq 1 ]; then
  if [ -z "${MC_BACKUP_PASSPHRASE:-}" ]; then
    printf "Passphrase for the archive: " >&2; stty -echo 2>/dev/null || true; read -r MC_BACKUP_PASSPHRASE; stty echo 2>/dev/null || true; echo >&2
    export MC_BACKUP_PASSPHRASE
  fi
  openssl enc -aes-256-cbc -pbkdf2 -salt -pass env:MC_BACKUP_PASSPHRASE -in "$file" -out "$file.enc"
  rm -f "$file"
  file="$file.enc"
fi
chmod 600 "$file"
echo "Saved: $file ($(wc -c < "$file" | tr -d ' ') bytes, sha256 $(shasum -a 256 "$file" | cut -c1-16)...)"
echo "It holds the Zigbee network key and the password hashes: keep it private."
