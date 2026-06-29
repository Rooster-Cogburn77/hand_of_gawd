import importlib.util
import json
import os
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

    firefox = os.environ.get("HOG_FIREFOX_BINARY")
    geckodriver = _first_existing(
        [
            shutil.which("geckodriver"),
            shutil.which("geckodriver.exe"),
            "/snap/bin/geckodriver",
        ]
    )
    if geckodriver is None:
        pytest.skip("geckodriver is not available")

    cmd = [
        sys.executable,
        str(REPO_ROOT / "scripts" / "hog_selenium_smoke.py"),
        "--output-dir",
        str(tmp_path),
        "--scenario",
        "all",
        "--geckodriver",
        geckodriver,
    ]
    if firefox:
        cmd.extend(["--firefox-binary", firefox])

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
    assert [scenario["scenario"] for scenario in result["scenarios"]] == [
        "safe",
        "unsafe-refusal",
        "approval-proceed",
        "stale-state",
        "identity-mismatch",
        "varied-snapshot",
    ]

    safe, refusal, approved, stale, mismatch, varied = result["scenarios"]
    assert safe["gate"]["allowed"] is True
    assert safe["execution"]["ok"] is True
    assert safe["verification"]["passed"] is True
    assert refusal["gate"]["allowed"] is False
    assert refusal["gate"]["gate_risk_class"] == "approval_required"
    assert refusal["execution"] is None
    assert approved["gate"]["allowed"] is True
    assert approved["gate"]["gate_risk_class"] == "approval_granted"
    assert approved["approval"]["approved"] is True
    assert approved["approval"]["mode"] == "auto-approve"
    assert approved["execution"]["ok"] is True
    assert approved["verification"]["passed"] is True
    assert stale["gate"]["allowed"] is False
    assert stale["gate"]["gate_risk_class"] == "blocked"
    assert stale["execution"] is None
    assert mismatch["gate"]["allowed"] is True
    assert mismatch["execution"]["ok"] is False
    assert mismatch["execution"]["reason"] == "target_identity_mismatch"
    assert varied["snapshot"]["warnings"] == [
        "iframes_not_traversed",
        "shadow_dom_not_traversed",
    ]
    assert "main-action" in varied["snapshot"]["element_ids"]
    assert "iframe-button" not in varied["snapshot"]["element_ids"]
    assert "shadow-button" not in varied["snapshot"]["element_ids"]

    for scenario in result["scenarios"]:
        assert scenario["fixture_url"].startswith("http://127.0.0.1:")
        assert scenario["allow_url_prefix"].startswith("http://127.0.0.1:")
        if scenario["scenario"] != "varied-snapshot":
            assert scenario["target_ref"]
        assert Path(scenario["trace"]).exists()
        assert Path(scenario["before_screenshot"]).exists()
        assert Path(scenario["after_screenshot"]).exists()


def _first_existing(candidates):
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return str(Path(candidate))
    return None
