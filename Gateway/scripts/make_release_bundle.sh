#!/usr/bin/env bash
# Builds the update bundle moisture-app-<version>.tar.gz (api/ hub/ web/ z2m/ VERSION at the archive root).
#   make_release_bundle.sh <version> <web build dir> <output dir>
# e.g. make_release_bundle.sh 1.2.3 App/build/web dist
# The archive is deterministic: the same inputs give the same bytes (sorted names, fixed mtime, owner and modes, no gzip name/time).
# Needs GNU tar and gzip. Used by .github/workflows/release.yml and the "Gateway / update bundle" job of ci.yml.
set -euo pipefail

version=${1:?usage: make_release_bundle.sh <version> <web build dir> <output dir>}
web=${2:?web build dir}
out=${3:?output dir}
[[ $version =~ ^[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.]+)?$ ]] || { echo "bad version: $version" >&2; exit 1; }
[[ -f $web/index.html ]] || { echo "$web is not a Flutter web build (no index.html)" >&2; exit 1; }

root=$(cd "$(dirname "$0")/../.." && pwd)
fw=$root/Gateway/firmware
stage=$root/Gateway/.release/stage
rm -rf "$stage"
mkdir -p "$stage" "$out"
out=$(cd "$out" && pwd)

# a complete buildable source layout: pyproject.toml + src, without environments, caches, tests and container files
for pkg in api hub; do
  cp -a "$fw/$pkg" "$stage/$pkg"
  rm -rf "$stage/$pkg"/{tests,.venv,build,dist,.pytest_cache}
  find "$stage/$pkg" \( -name __pycache__ -o -name '*.egg-info' \) -prune -exec rm -rf {} +
  find "$stage/$pkg" -name '*.pyc' -delete
done

# the version the services report (/api/v1/meta) and the version setuptools builds
for pkg in api hub; do
  init=$(ls "$stage/$pkg"/src/mc_*/__init__.py)
  grep -q '^__version__ = ' "$init" || { echo "no __version__ in $init" >&2; exit 1; }
  sed -i "s/^__version__ = .*/__version__ = \"$version\"/" "$init"
  grep -q '^version = ' "$stage/$pkg/pyproject.toml" || { echo "no version in $pkg/pyproject.toml" >&2; exit 1; }
  sed -i "s/^version = .*/version = \"$version\"/" "$stage/$pkg/pyproject.toml"
done

cp -a "$web" "$stage/web"

mkdir "$stage/z2m"
cp -a "$fw/zigbee2mqtt/external_converters/." "$stage/z2m/"
rm -f "$stage/z2m/.gitkeep" "$stage/z2m/README.md"

echo "$version" > "$stage/VERSION"

chmod -R u=rwX,go=rX "$stage"
asset="moisture-app-$version.tar.gz"
tar --sort=name --mtime='2020-01-01 00:00:00Z' --owner=0 --group=0 --numeric-owner --format=gnu -cf - -C "$stage" . \
  | gzip -n -9 > "$out/$asset"
rm -rf "$stage"
echo "$out/$asset"
