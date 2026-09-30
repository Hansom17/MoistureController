#!/bin/sh
# Creates the secret files once. Keep secrets/key_encryption_key safe: without
# it the device keys in the database can't be decrypted (§13.4).
set -eu
cd "$(dirname "$0")/.."
mkdir -p secrets/firebase
umask 077
for name in postgres_password; do
  [ -f "secrets/$name" ] || openssl rand -hex 24 > "secrets/$name"
done
[ -f secrets/key_encryption_key ] || openssl rand -hex 32 > secrets/key_encryption_key
echo "secrets ready in $(pwd)/secrets"
