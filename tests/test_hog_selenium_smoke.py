import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.integration
def test_public_safe_toggle_selenium_smoke(tmp_path):
    if importlib.util.find_spec("selenium") is None:
        pytest.skip("selenium is not installed")

    firefox = _first_existing(
        [
            shutil.which("firefox"),
            shutil.which("firefox.exe"),
            "/usr/bin/firefox",
        ]
    )
    geckodriver = _first_existing(
        [
            shutil.which("geckodriver"),
            shutil.which("geckodriver.exe"),
            "/snap/bin/geckodriver",
        ]
    )
    if firefox is None:
        pytest.skip("firefox is not available")
    if geckodriver is None:
        pytest.skip("geckodriver is not available")

    cmd = [
        sys.executable,
        str(REPO_ROOT / "scripts" / "hog_selenium_smoke.py"),
        "--output-dir",
        str(tmp_path),
        "--firefox-binary",
        firefox,
        "--geckodriver",
        geckodriver,
    ]
    completed = subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        timeout=45,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr + completed.stdout
    result = json.loads(completed.stdout)
    assert result["passed"] is True
    assert result["target_ref"]
    assert result["gate"]["allowed"] is True
    assert result["execution"]["ok"] is True
    assert result["verification"]["passed"] is True
    assert Path(result["trace"]).exists()
    assert Path(result["before_screenshot"]).exists()
    assert Path(result["after_screenshot"]).exists()


def _first_existing(candidates):
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return str(Path(candidate))
    return None
