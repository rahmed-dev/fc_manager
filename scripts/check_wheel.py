"""Check that a built wheel holds only the fc_manager package and its metadata.

Usage: python scripts/check_wheel.py dist/fc_manager-*.whl
Exit code 0 when the wheel is clean, 1 when it holds any other file.
"""

from __future__ import annotations

import sys
import zipfile


def bad_entries(path: str) -> list[str]:
    with zipfile.ZipFile(path) as wheel:
        names = wheel.namelist()
    bad = []
    for name in names:
        top = name.split("/", 1)[0]
        if name.startswith("fc_manager/"):
            continue
        if top.startswith("fc_manager-") and top.endswith(".dist-info"):
            continue
        bad.append(name)
    return bad


def main(paths: list[str]) -> int:
    if not paths:
        print("usage: check_wheel.py WHEEL...", file=sys.stderr)
        return 2
    status = 0
    for path in paths:
        bad = bad_entries(path)
        for name in bad:
            print(f"{path}: unexpected file {name}", file=sys.stderr)
        if bad:
            status = 1
        else:
            print(f"{path}: clean")
    return status


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
