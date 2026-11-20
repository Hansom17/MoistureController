#!/usr/bin/env bash
# Verifies a release the way a gateway does: signature over manifest.json, then the bundle against the manifest.
#   verify_release.sh <dir with manifest.json, manifest.json.sig and the bundle> [public key (default: Gateway/update/update-pubkey.pem)]
set -euo pipefail
dir=${1:?usage: verify_release.sh <dir> [public key]}
pub=${2:-$(cd "$(dirname "$0")/.." && pwd)/update/update-pubkey.pem}

openssl pkeyutl -verify -pubin -inkey "$pub" -rawin -in "$dir/manifest.json" -sigfile "$dir/manifest.json.sig" >/dev/null \
  || { echo "signature of manifest.json is NOT valid" >&2; exit 1; }
python3 -I - "$dir" <<'PY'
import hashlib, json, sys
from pathlib import Path
d = Path(sys.argv[1])
m = json.loads((d / "manifest.json").read_text())
for k in ("schema", "version", "channel", "app_generation", "asset", "sha256", "size", "released_at"):
    assert k in m, f"manifest has no {k}"
a = d / m["asset"]
data = a.read_bytes()
assert hashlib.sha256(data).hexdigest() == m["sha256"], "sha256 of the bundle does not match the manifest"
assert len(data) == m["size"], "size of the bundle does not match the manifest"
assert m["asset"] == f"moisture-app-{m['version']}.tar.gz", "asset name does not match the version"
print(f"ok: {m['version']} ({m['channel']}, app_generation {m['app_generation']}) is signed and complete")
PY
