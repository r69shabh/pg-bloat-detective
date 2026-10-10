#!/usr/bin/env python3
"""Fail fast when release metadata drifts.

The v0.1.4 release was tagged but pyproject still said 0.1.3, so PyPI rejected the
upload ("File already exists") after the whole build ran. Check before building.

Usage:
  scripts/check_versions.py            # pyproject == server.json (packages[].version)
  scripts/check_versions.py v0.1.6     # also require the tag to match pyproject
"""
from __future__ import annotations
import json
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def check(tag: str = "") -> list[str]:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text())
    version = pyproject["project"]["version"]
    server = json.loads((ROOT / "server.json").read_text())

    errors = []
    if server["version"] != version:
        errors.append(f"server.json version {server['version']} != pyproject {version}")
    for pkg in server.get("packages", []):
        if pkg.get("version") != version:
            errors.append(f"server.json package {pkg.get('identifier')} version {pkg.get('version')} != pyproject {version}")
    if len(server["description"]) > 100:
        errors.append(f"server.json description is {len(server['description'])} chars (registry max 100)")
    if tag and tag.lstrip("v") != version:
        errors.append(f"tag {tag} != pyproject version {version}")
    return errors


def main() -> None:
    errors = check(sys.argv[1] if len(sys.argv) > 1 else "")
    for e in errors:
        print(f"FAIL: {e}")
    if errors:
        sys.exit(1)
    print("versions consistent")


if __name__ == "__main__":
    main()
