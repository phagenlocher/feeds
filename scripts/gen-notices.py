#!/usr/bin/env python3
"""Generate the third-party notices.

``python3 scripts/gen-notices.py``
    Writes ``THIRD-PARTY-NOTICES``: every Rust crate (via cargo-about) and
    every JavaScript package (via pnpm), one ``name version — license`` line
    each, deduplicated and sorted.

Run through the ``notices`` just recipe.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UI = ROOT / "crates" / "feeds-app" / "ui"

COMPACT_HEADER = """\
Third-Party Notices
===================

This project is built with the third-party software listed below. This file is
generated — do not edit it by hand.

Regenerate it with:

    just notices

"""


def run(cmd: list[str], cwd: Path) -> str:
    return subprocess.run(
        cmd, cwd=cwd, check=True, capture_output=True, text=True
    ).stdout


def pnpm() -> list[str]:
    # The system npm is often unavailable; fall back to corepack's pnpm.
    if shutil.which("pnpm"):
        return ["pnpm"]
    return ["corepack", "pnpm"]


def compact() -> None:
    raw = run(["cargo", "about", "generate", "templates/about.hbs"], ROOT)
    crates: dict[tuple[str, str], str] = {}
    for line in raw.splitlines():
        if not line.startswith("- "):
            continue
        name_version, _, license = line[2:].partition(" — ")
        name, _, version = name_version.rpartition(" ")
        if name:
            crates[(name, version)] = license

    rust = ["Rust crates", "-----------", ""]
    rust += [
        f"- {name} {version} — {crates[(name, version)]}"
        for name, version in sorted(crates, key=lambda k: (k[0].lower(), k[1]))
    ]

    data = json.loads(run(pnpm() + ["licenses", "list", "--json"], UI))
    entries: set[tuple[str, str, str]] = set()
    for license_id, packages in data.items():
        for pkg in packages:
            for version in pkg.get("versions", []):
                entries.add((pkg["name"], version, license_id))
    js = ["JavaScript packages", "-------------------", ""]
    js += [
        f"- {name} {version} — {license}"
        for name, version, license in sorted(
            entries, key=lambda e: (e[0].lower(), e[1])
        )
    ]

    output = COMPACT_HEADER + "\n" + "\n".join(rust) + "\n\n" + "\n".join(js) + "\n"
    (ROOT / "THIRD-PARTY-NOTICES").write_text(output)
    print("wrote THIRD-PARTY-NOTICES")


def main() -> None:
    compact()


if __name__ == "__main__":
    main()
