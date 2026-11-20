#!/usr/bin/env python3
"""Checks before a tag becomes a release (a release is installed by every gateway on the matching channel).

  release_checks.py <tag> <commit> [--releases v1.0.0,v1.1.0]

  - the tag looks like vX.Y.Z or vX.Y.Z-<alpha|beta|rc>[.N]
  - the tagged commit is on origin/main
  - the version is higher than every other release (pre-releases included, semver order: 1.0.0-rc.1 < 1.0.0)
Without --releases the existing releases come from `gh release list` (GH_TOKEN needed).
"""
import json
import re
import subprocess
import sys

from packaging.version import InvalidVersion, Version

TAG = re.compile(r"v([0-9]+\.[0-9]+\.[0-9]+(-(alpha|beta|rc)(\.?[0-9]+)?)?)")


def parse(tag: str) -> Version | None:
    m = TAG.fullmatch(tag)
    if not m:
        return None
    try:
        return Version(m.group(1))
    except InvalidVersion:
        return None


def main() -> int:
    tag, commit = sys.argv[1:3]
    errors = []
    version = parse(tag)
    if version is None:
        errors.append(f"{tag} is not a release tag (vX.Y.Z, or vX.Y.Z-alpha|beta|rc[.N])")
    if subprocess.run(["git", "merge-base", "--is-ancestor", commit, "origin/main"]).returncode != 0:
        errors.append(f"{tag} ({commit[:8]}) is not on main: only commits on main can be released")
    if "--releases" in sys.argv:
        others = [t for t in sys.argv[sys.argv.index("--releases") + 1].split(",") if t]
    else:
        out = subprocess.run(["gh", "release", "list", "--limit", "500", "--json", "tagName,isDraft"],
                             check=True, capture_output=True, text=True).stdout
        others = [r["tagName"] for r in json.loads(out) if not r["isDraft"]]
    if version is not None:
        for t in others:
            if t == tag:
                errors.append(f"a release for {tag} exists already")
                continue
            v = parse(t)
            if v is None:
                print(f"note: ignoring release {t} (not a release tag)")
            elif v >= version:
                errors.append(f"{tag} is not higher than the existing release {t}")
    for e in errors:
        print("error:", e)
    if not errors:
        print(f"{tag} is a valid next release")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
