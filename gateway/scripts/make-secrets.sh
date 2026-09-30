#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
mkdir -p secrets
umask 077
[ -f secrets/mqtt_agent_password ] || openssl rand -hex 24 > secrets/mqtt_agent_password
echo "secrets ready in $(pwd)/secrets"
