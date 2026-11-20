#!/usr/bin/env python3
"""Migration safety check for updates.

An update migrates the database on the first start. If the health check then fails, the device goes back to the previous
code (and restores a database backup), so a migration must not break the code of the previous release. Checks:
  - every package (hub, api) has exactly one head and an unbroken revision chain, and each revision has a downgrade()
  - with --base <ref>: migrations that already existed at <ref> are not edited, and new ones do not destroy data
    (drop_column, drop_table, alter_column, rename_table, drop_constraint, raw execute) unless the file says
    `# migration-unsafe-ok: <reason>` (then the release should be a major one, see Gateway/docs/RELEASING.md)

  check_migrations.py [--base origin/main]
"""
import ast
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
PACKAGES = {"hub": "Gateway/firmware/hub/src/mc_hub/migrations/versions",
            "api": "Gateway/firmware/api/src/mc_api/migrations/versions"}
DESTRUCTIVE = {"drop_column", "drop_table", "alter_column", "rename_table", "drop_constraint", "execute"}
MARKER = "# migration-unsafe-ok:"


def assigned(tree: ast.Module, name: str):
    for n in tree.body:
        if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in n.targets):
            return ast.literal_eval(n.value)
    return None


def func(tree: ast.Module, name: str):
    return next((n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name), None)


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True, text=True).stdout


def main() -> int:
    base = sys.argv[sys.argv.index("--base") + 1] if "--base" in sys.argv else None
    errors: list[str] = []
    for name, rel in PACKAGES.items():
        revs, downs = {}, set()
        for f in sorted((ROOT / rel).glob("*.py")):
            tree = ast.parse(f.read_text())
            rev, down = assigned(tree, "revision"), assigned(tree, "down_revision")
            if rev is None:
                errors.append(f"{f.name}: no revision")
                continue
            revs[rev] = f
            if down:
                downs.add(down)
            if func(tree, "downgrade") is None:
                errors.append(f"{name}/{f.name}: downgrade() is missing")
        heads = [r for r in revs if r not in downs]
        if len(heads) != 1:
            errors.append(f"{name}: expected one migration head, found {heads}")
        if base:
            existing = set(git("ls-tree", "-r", "--name-only", base, "--", rel).split())
            changed = set(git("diff", "--name-only", "--diff-filter=MDR", f"{base}...HEAD", "--", rel).split())
            for p in sorted(changed & existing):
                errors.append(f"{p}: a migration that was already released must not be edited, add a new revision")
            for p in sorted(set(git("diff", "--name-only", "--diff-filter=A", f"{base}...HEAD", "--", rel).split())):
                path = ROOT / p
                src = path.read_text()
                up = func(ast.parse(src), "upgrade")
                bad = sorted({n.attr for n in ast.walk(up) if isinstance(n, ast.Attribute) and n.attr in DESTRUCTIVE}) if up else []
                if bad and MARKER not in src:
                    errors.append(f"{p}: upgrade() uses {', '.join(bad)}; the previous release would break on the migrated database. "
                                  f"Add the change in two releases (expand, then contract) or mark the file with '{MARKER} <reason>'")
    for e in errors:
        print("error:", e)
    if not errors:
        print("migrations ok" + (f" (compared with {base})" if base else ""))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
