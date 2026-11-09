"""release-v1 3.2: the wheel content check."""

import importlib.util
import zipfile
from pathlib import Path

SCRIPT = Path(__file__).parent.parent / "scripts" / "check_wheel.py"
spec = importlib.util.spec_from_file_location("check_wheel", SCRIPT)
check_wheel = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check_wheel)


def make_wheel(tmp_path, names):
    path = tmp_path / "fc_manager-1.0.0-py3-none-any.whl"
    with zipfile.ZipFile(path, "w") as wheel:
        for name in names:
            wheel.writestr(name, "x")
    return str(path)


def test_clean_wheel_passes(tmp_path):
    path = make_wheel(tmp_path, ["fc_manager/__init__.py", "fc_manager-1.0.0.dist-info/METADATA"])
    assert check_wheel.bad_entries(path) == []
    assert check_wheel.main([path]) == 0


def test_stray_files_fail(tmp_path, capsys):
    path = make_wheel(
        tmp_path,
        ["fc_manager/__init__.py", ".env", "tests/fixtures/fc/x.json", "fc_manager-x/evil.py"],
    )
    assert check_wheel.bad_entries(path) == [
        ".env",
        "tests/fixtures/fc/x.json",
        "fc_manager-x/evil.py",
    ]
    assert check_wheel.main([path]) == 1
    assert ".env" in capsys.readouterr().err
