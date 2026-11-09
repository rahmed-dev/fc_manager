"""cli-hub: one hyphenated command word; old forms fail with the new name."""

import pathlib
import re

OLD_FORM = re.compile(
    r"\bfcm(?:-dev)? (profile|team|bench|site) (list|show|add|remove|test|deploy)\b"
)
ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_no_old_command_form_in_source_or_readme():
    files = [*sorted((ROOT / "src").rglob("*.py")), ROOT / "README.md"]
    hits = [
        f"{path.relative_to(ROOT)}:{n}: {line.strip()}"
        for path in files
        for n, line in enumerate(path.read_text().splitlines(), 1)
        if OLD_FORM.search(line)
    ]
    assert hits == []
