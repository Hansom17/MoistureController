#!/bin/sh
# Builds the web app the way the gateway serves it (no CDN, everything bundled).
#   App/scripts/build_web.sh            builds App/build/web
# Used the same way by the CI job "App / web build"; the release workflow packs that build into the update bundle.
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

echo
cat build/web/build-info.txt
echo "web build: App/build/web ($(du -sh build/web | cut -f1))"
