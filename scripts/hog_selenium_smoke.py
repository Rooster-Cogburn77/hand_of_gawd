"""Run the Goal 1 hand_of_gawd Selenium integration smoke.

The smoke uses only the public synthetic fixture under examples/safe_toggle.
It exercises observe -> proposal -> deterministic gate -> Selenium act ->
observe -> deterministic verify -> trace against a local loopback HTTP page.
"""

from __future__ import annotations

import argparse
import contextlib
import functools
import http.server
import json
import sys
import threading
from pathlib import Path
from typing import Any, Iterator

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
    parser.add_argument(
        "--scenario",
        choices=("safe", "unsafe-refusal", "approval-proceed", "all"),
        default="safe",
    )
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
        result = run_smoke(driver, Path(args.fixture), output_dir, scenario=args.scenario)
    finally:
        driver.quit()

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["passed"] else 2


def run_smoke(
    driver: Any,
    fixture: Path,
    output_dir: Path,
    *,
    scenario: str = "safe",
) -> dict[str, Any]:
    """Run the public safe-toggle proof with an already-open Selenium driver."""

    if scenario == "all":
        results = [
            run_smoke(driver, fixture, output_dir / "safe", scenario="safe"),
            run_smoke(
                driver,
                fixture,
                output_dir / "unsafe-refusal",
                scenario="unsafe-refusal",
            ),
            run_smoke(
                driver,
                fixture,
                output_dir / "approval-proceed",
                scenario="approval-proceed",
            ),
        ]
        return {
            "scenario": "all",
            "passed": all(result["passed"] for result in results),
            "scenarios": results,
        }

    fixture = fixture.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    with _serve_fixture(fixture) as served:
        driver.set_window_size(900, 600)
        driver.get(served.url)

        before = capture_snapshot(
            driver,
            snapshot_id="s1",
            screenshot_path=output_dir / "before.png",
        )

        if scenario == "safe":
            target_ref = _find_target_ref(before, target_id="arm-button")
            proposal = _proposal(
                goal="arm the synthetic safe toggle fixture",
                state_seen=before["snapshot_id"],
                target_ref=target_ref,
                reason="Click the public synthetic Arm button.",
                assertions=[
                    {"type": "text_present", "value": "ARMED"},
                    {"type": "text_absent", "value": "SAFE"},
                ],
            )
            gate_config = GateConfig(allowed_url_prefixes=(served.base_url,))
        elif scenario == "unsafe-refusal":
            target_ref = _find_target_ref(before, target_id="submit-button")
            proposal = _proposal(
                goal="prove the gate refuses an unapproved synthetic submit",
                state_seen=before["snapshot_id"],
                target_ref=target_ref,
                reason="Try to click the public synthetic Submit button without approval.",
                assertions=[
                    {"type": "text_present", "value": "SUBMITTED"},
                    {"type": "text_absent", "value": "DRAFT"},
                ],
            )
            gate_config = GateConfig(allowed_url_prefixes=(served.base_url,))
        elif scenario == "approval-proceed":
            target_ref = _find_target_ref(before, target_id="submit-button")
            proposal = _proposal(
                goal="prove an operator-approved synthetic submit can proceed",
                state_seen=before["snapshot_id"],
                target_ref=target_ref,
                reason="Click the public synthetic Submit button after approval.",
                assertions=[
                    {"type": "text_present", "value": "SUBMITTED"},
                    {"type": "text_absent", "value": "DRAFT"},
                ],
            )
            gate_config = GateConfig(
                allowed_url_prefixes=(served.base_url,),
                approved_target_refs=(target_ref,),
            )
        else:
            raise ValueError(f"unsupported scenario: {scenario}")

        trace_path = output_dir / f"hog_trace_selenium_{scenario}.jsonl"
        step = run_verified_step(
            driver,
            proposal,
            before,
            gate_config=gate_config,
            trace=TraceRecorder(trace_path),
            after_snapshot_id="s2",
        )
        driver.save_screenshot(str(output_dir / "after.png"))
        passed = _scenario_passed(scenario, step)

        return {
            "scenario": scenario,
            "passed": passed,
            "fixture": str(fixture),
            "fixture_url": served.url,
            "allow_url_prefix": served.base_url,
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


def _proposal(
    *,
    goal: str,
    state_seen: str,
    target_ref: str,
    reason: str,
    assertions: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "goal": goal,
        "state_seen": state_seen,
        "risk_class": "safe",
        "proposed_action": {
            "type": "click",
            "target_ref": target_ref,
            "reason": reason,
            "expected_result": {"assertions": assertions},
        },
    }


def _scenario_passed(scenario: str, step: Any) -> bool:
    if scenario == "unsafe-refusal":
        return (
            step.gate.allowed is False
            and step.gate.gate_risk_class == "approval_required"
            and step.execution is None
            and step.after_snapshot is None
            and step.verification is None
        )
    return bool(step.passed)


class _ServedFixture:
    def __init__(self, *, base_url: str, url: str):
        self.base_url = base_url
        self.url = url


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:
        return


@contextlib.contextmanager
def _serve_fixture(fixture: Path) -> Iterator[_ServedFixture]:
    if not fixture.is_file():
        raise FileNotFoundError(f"fixture not found: {fixture}")

    handler = functools.partial(_QuietHandler, directory=str(fixture.parent))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    host, port = server.server_address
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://{host}:{port}/"
    try:
        yield _ServedFixture(base_url=base_url, url=base_url + fixture.name)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


if __name__ == "__main__":
    raise SystemExit(main())
