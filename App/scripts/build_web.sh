#!/bin/sh
# Builds the web app the way the gateway serves it (no CDN, everything bundled) and packs it.
#   App/scripts/build_web.sh            builds App/build/web and App/build/moisture-web.tar.gz
# Used the same way by the CI job "Web build". Copy App/build/web (or unpack the archive) to the gateway device,
# see Gateway/INSTALL.md step 4.
set -eu
cd "$(dirname "$0")/.."

flutter pub get
flutter build web --release --no-web-resources-cdn

# what this build is, next to the app (served as /build-info.txt)
{
  echo "commit: $(git rev-parse --short HEAD 2>/dev/null || echo unknown)$(git diff --quiet 2>/dev/null || echo ' (modified)')"
  echo "built:  $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "flutter: $(flutter --version 2>/dev/null | head -1)"
} > build/web/build-info.txt

tar -C build -czf build/moisture-web.tar.gz web
echo
cat build/web/build-info.txt
echo "web build: App/build/web ($(du -sh build/web | cut -f1)), archive: App/build/moisture-web.tar.gz ($(du -h build/moisture-web.tar.gz | cut -f1))"
if command -v shasum >/dev/null 2>&1; then shasum -a 256 build/moisture-web.tar.gz; else sha256sum build/moisture-web.tar.gz; fi
