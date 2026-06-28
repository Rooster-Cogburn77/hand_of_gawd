"""Run the Goal 1 hand_of_gawd Selenium integration smoke.

The smoke uses only the public synthetic fixture under examples/safe_toggle.
It proves observe -> proposal -> deterministic gate -> Selenium act ->
observe -> deterministic verify -> trace against a local file:// page.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from hand_of_gawd.loop import run_verified_step
from hand_of_gawd.policy import GateConfig
from hand_of_gawd.selenium_snapshot import capture_snapshot
from hand_of_gawd.trace import TraceRecorder


DEFAULT_FIXTURE = REPO_ROOT / "examples" / "safe_toggle" / "index.html"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", default=str(DEFAULT_FIXTURE))
    parser.add_argument("--output-dir", default=str(REPO_ROOT / "runtime" / "hog_selenium_smoke"))
    parser.add_argument("--firefox-binary")
    parser.add_argument("--geckodriver")
    parser.add_argument("--headed", action="store_true")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    driver = _open_firefox(
        firefox_binary=args.firefox_binary,
        geckodriver=args.geckodriver,
        headless=not args.headed,
    )
    try:
        result = run_smoke(driver, Path(args.fixture), output_dir)
    finally:
        driver.quit()

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["passed"] else 2


def run_smoke(driver: Any, fixture: Path, output_dir: Path) -> dict[str, Any]:
    """Run the public safe-toggle proof with an already-open Selenium driver."""

    fixture = fixture.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    driver.set_window_size(900, 600)
    driver.get(fixture.as_uri())

    before = capture_snapshot(
        driver,
        snapshot_id="s1",
        screenshot_path=output_dir / "before.png",
    )
    target_ref = _find_target_ref(before, target_id="arm-button")
    proposal = {
        "goal": "arm the synthetic safe toggle fixture",
        "state_seen": before["snapshot_id"],
        "risk_class": "safe",
        "proposed_action": {
            "type": "click",
            "target_ref": target_ref,
            "reason": "Click the public synthetic Arm button.",
            "expected_result": {
                "assertions": [
                    {"type": "text_present", "value": "ARMED"},
                    {"type": "text_absent", "value": "SAFE"},
                ]
            },
        },
    }

    trace_path = output_dir / "hog_trace_selenium_smoke.jsonl"
    step = run_verified_step(
        driver,
        proposal,
        before,
        gate_config=GateConfig(allow_file_urls=True),
        trace=TraceRecorder(trace_path),
        after_snapshot_id="s2",
    )
    driver.save_screenshot(str(output_dir / "after.png"))

    return {
        "passed": step.passed,
        "fixture": str(fixture),
        "target_ref": target_ref,
        "before_screenshot": str(output_dir / "before.png"),
        "after_screenshot": str(output_dir / "after.png"),
        "trace": str(trace_path),
        "gate": step.gate.to_dict(),
        "execution": step.execution.to_dict() if step.execution else None,
        "verification": step.verification.to_dict() if step.verification else None,
        "after_snapshot_id": step.after_snapshot.get("snapshot_id") if step.after_snapshot else None,
    }


def _open_firefox(*, firefox_binary: str | None, geckodriver: str | None, headless: bool) -> Any:
    try:
        from selenium import webdriver
        from selenium.webdriver.firefox.options import Options
        from selenium.webdriver.firefox.service import Service
    except ImportError as exc:
        raise RuntimeError("selenium is required for the smoke runner") from exc

    options = Options()
    if headless:
        options.add_argument("-headless")
    if firefox_binary:
        options.binary_location = firefox_binary

    service = Service(geckodriver) if geckodriver else Service()
    return webdriver.Firefox(service=service, options=options)


def _find_target_ref(snapshot: dict[str, Any], *, target_id: str) -> str:
    for element in snapshot.get("elements", ()):
        if element.get("id") == target_id:
            return str(element["ref"])
    raise RuntimeError(f"target id not found in snapshot: {target_id}")


if __name__ == "__main__":
    raise SystemExit(main())
