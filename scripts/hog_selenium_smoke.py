"""Run the Goal 1 hand_of_gawd Selenium integration smoke.

The smoke uses public synthetic fixtures under examples/.
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

from hand_of_gawd.approval import (
    ApprovalResponse,
    ApprovalStore,
    approval_response_for_mode,
    build_approval_request,
    gate_config_with_approval,
    gate_config_with_approval_store,
)
from hand_of_gawd.loop import run_verified_step
from hand_of_gawd.policy import GateConfig, evaluate_policy_gate
from hand_of_gawd.selenium_snapshot import capture_snapshot
from hand_of_gawd.trace import TraceRecorder


DEFAULT_FIXTURE = REPO_ROOT / "examples" / "safe_toggle" / "index.html"
DEFAULT_VARIED_FIXTURE = REPO_ROOT / "examples" / "varied_page" / "index.html"
DEFAULT_BLOCKED_IFRAME_FIXTURE = REPO_ROOT / "examples" / "blocked_iframe" / "index.html"
ACTION_SCENARIOS = (
    "safe",
    "unsafe-refusal",
    "approval-proceed",
    "stale-state",
    "identity-mismatch",
    "iframe-action",
    "shadow-action",
)
SCENARIOS = (*ACTION_SCENARIOS, "varied-snapshot", "blocked-iframe-snapshot", "all")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", default=str(DEFAULT_FIXTURE))
    parser.add_argument("--output-dir", default=str(REPO_ROOT / "runtime" / "hog_selenium_smoke"))
    parser.add_argument(
        "--scenario",
        choices=SCENARIOS,
        default="safe",
    )
    parser.add_argument("--firefox-binary")
    parser.add_argument("--geckodriver")
    parser.add_argument("--headed", action="store_true")
    parser.add_argument(
        "--approval-mode",
        choices=("auto-approve", "prompt", "deny"),
        default="auto-approve",
        help="approval source for the approval-proceed scenario",
    )
    parser.add_argument(
        "--approval-store",
        help="optional local JSONL approval store for exact stable action keys",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    driver = _open_firefox(
        firefox_binary=args.firefox_binary,
        geckodriver=args.geckodriver,
        headless=not args.headed,
    )
    try:
        result = run_smoke(
            driver,
            Path(args.fixture),
            output_dir,
            scenario=args.scenario,
            approval_mode=args.approval_mode,
            approval_store=Path(args.approval_store) if args.approval_store else None,
        )
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
    approval_mode: str = "auto-approve",
    approval_store: Path | None = None,
) -> dict[str, Any]:
    """Run the public safe-toggle proof with an already-open Selenium driver."""

    if scenario == "all":
        results = [
            run_smoke(
                driver,
                fixture,
                output_dir / "safe",
                scenario="safe",
                approval_mode=approval_mode,
                approval_store=approval_store,
            ),
            run_smoke(
                driver,
                fixture,
                output_dir / "unsafe-refusal",
                scenario="unsafe-refusal",
                approval_mode=approval_mode,
                approval_store=approval_store,
            ),
            run_smoke(
                driver,
                fixture,
                output_dir / "approval-proceed",
                scenario="approval-proceed",
                approval_mode=approval_mode,
                approval_store=approval_store,
            ),
            run_smoke(
                driver,
                fixture,
                output_dir / "stale-state",
                scenario="stale-state",
                approval_mode=approval_mode,
                approval_store=approval_store,
            ),
            run_smoke(
                driver,
                fixture,
                output_dir / "identity-mismatch",
                scenario="identity-mismatch",
                approval_mode=approval_mode,
                approval_store=approval_store,
            ),
            run_smoke(
                driver,
                DEFAULT_VARIED_FIXTURE,
                output_dir / "iframe-action",
                scenario="iframe-action",
                approval_mode=approval_mode,
                approval_store=approval_store,
            ),
            run_smoke(
                driver,
                DEFAULT_VARIED_FIXTURE,
                output_dir / "shadow-action",
                scenario="shadow-action",
                approval_mode=approval_mode,
                approval_store=approval_store,
            ),
            run_smoke(
                driver,
                DEFAULT_VARIED_FIXTURE,
                output_dir / "varied-snapshot",
                scenario="varied-snapshot",
                approval_mode=approval_mode,
                approval_store=approval_store,
            ),
            run_smoke(
                driver,
                DEFAULT_BLOCKED_IFRAME_FIXTURE,
                output_dir / "blocked-iframe-snapshot",
                scenario="blocked-iframe-snapshot",
                approval_mode=approval_mode,
                approval_store=approval_store,
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

        trace_path = output_dir / f"hog_trace_selenium_{scenario}.jsonl"
        trace = TraceRecorder(trace_path)
        store = ApprovalStore(approval_store) if approval_store else None
        approval_response = None
        approval_record = None

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
            gate_config = GateConfig(allowed_url_prefixes=(served.base_url,))
            if store is not None:
                gate_config = gate_config_with_approval_store(gate_config, store)
            initial_gate = evaluate_policy_gate(proposal, before, gate_config)
            if initial_gate.allowed and initial_gate.gate_risk_class == "approval_granted":
                approval_response = ApprovalResponse(
                    approved=True,
                    approval_key=initial_gate.checks.get("target_approval_key"),
                    mode="store",
                    reason="approved by local approval store",
                )
                trace.record("approval_response", approval_response.to_dict())
            else:
                approval_request = build_approval_request(proposal, before, initial_gate)
                approval_response = approval_response_for_mode(
                    approval_request,
                    approval_mode,
                )
                trace.record("approval_request", approval_request.to_dict())
                trace.record("approval_response", approval_response.to_dict())
                if store is not None:
                    approval_record = store.append(approval_request, approval_response)
                    trace.record("approval_record", approval_record.to_dict())
                    gate_config = gate_config_with_approval_store(gate_config, store)
                else:
                    gate_config = gate_config_with_approval(gate_config, approval_response)
        elif scenario == "stale-state":
            target_ref = _find_target_ref(before, target_id="arm-button")
            proposal = _proposal(
                goal="prove stale planner state is blocked before execution",
                state_seen="stale-snapshot",
                target_ref=target_ref,
                reason="Try to click the public synthetic Arm button from stale state.",
                assertions=[
                    {"type": "text_present", "value": "ARMED"},
                    {"type": "text_absent", "value": "SAFE"},
                ],
            )
            gate_config = GateConfig(allowed_url_prefixes=(served.base_url,))
        elif scenario == "identity-mismatch":
            target_ref = _find_target_ref(before, target_id="arm-button")
            proposal = _proposal(
                goal="prove live identity mismatch blocks a shifted target",
                state_seen=before["snapshot_id"],
                target_ref=target_ref,
                reason="Try to click Arm after another element covers its center.",
                assertions=[
                    {"type": "text_present", "value": "ARMED"},
                    {"type": "text_absent", "value": "SAFE"},
                ],
            )
            gate_config = GateConfig(allowed_url_prefixes=(served.base_url,))
            _cover_arm_button_with_impostor(driver)
        elif scenario == "iframe-action":
            target_ref = _find_target_ref(before, target_id="iframe-button")
            proposal = _proposal(
                goal="prove a same-origin iframe button can be observed and clicked",
                state_seen=before["snapshot_id"],
                target_ref=target_ref,
                reason="Click the public synthetic iframe button.",
                assertions=[
                    {"type": "text_present", "value": "IFRAME"},
                    {"type": "text_absent", "value": "READY"},
                ],
            )
            gate_config = GateConfig(allowed_url_prefixes=(served.base_url,))
        elif scenario == "shadow-action":
            target_ref = _find_target_ref(before, target_id="shadow-button")
            proposal = _proposal(
                goal="prove an open-shadow-root button can be observed and clicked",
                state_seen=before["snapshot_id"],
                target_ref=target_ref,
                reason="Click the public synthetic shadow-root button.",
                assertions=[
                    {"type": "text_present", "value": "SHADOW"},
                    {"type": "text_absent", "value": "READY"},
                ],
            )
            gate_config = GateConfig(allowed_url_prefixes=(served.base_url,))
        elif scenario in {"varied-snapshot", "blocked-iframe-snapshot"}:
            trace.record(
                "snapshot_coverage",
                {
                    "snapshot_id": before.get("snapshot_id"),
                    "warnings": before.get("warnings", []),
                    "element_ids": [
                        element.get("id")
                        for element in before.get("elements", [])
                        if element.get("id")
                    ],
                },
            )
            driver.save_screenshot(str(output_dir / "after.png"))
            passed = (
                _varied_snapshot_passed(before)
                if scenario == "varied-snapshot"
                else _blocked_iframe_snapshot_passed(before)
            )
            return {
                "scenario": scenario,
                "passed": passed,
                "fixture": str(fixture),
                "fixture_url": served.url,
                "allow_url_prefix": served.base_url,
                "target_ref": None,
                "before_screenshot": str(output_dir / "before.png"),
                "after_screenshot": str(output_dir / "after.png"),
                "trace": str(trace_path),
                "snapshot": {
                    "warnings": before.get("warnings", []),
                    "element_count": len(before.get("elements", [])),
                    "element_ids": [
                        element.get("id")
                        for element in before.get("elements", [])
                        if element.get("id")
                    ],
                },
                "gate": None,
                "execution": None,
                "verification": None,
                "after_snapshot_id": None,
                "approval": None,
                "approval_store": str(approval_store) if approval_store else None,
                "approval_record": None,
            }
        else:
            raise ValueError(f"unsupported scenario: {scenario}")

        step = run_verified_step(
            driver,
            proposal,
            before,
            gate_config=gate_config,
            trace=trace,
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
            "approval": approval_response.to_dict() if scenario == "approval-proceed" else None,
            "approval_store": str(approval_store) if approval_store else None,
            "approval_record": approval_record.to_dict() if approval_record else None,
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
    if scenario == "stale-state":
        return (
            step.gate.allowed is False
            and step.gate.gate_risk_class == "blocked"
            and "state_seen" in step.gate.reason
            and step.execution is None
            and step.after_snapshot is None
            and step.verification is None
        )
    if scenario == "identity-mismatch":
        return (
            step.gate.allowed is True
            and step.execution is not None
            and step.execution.ok is False
            and step.execution.reason == "target_identity_mismatch"
            and step.execution.adapter_result.get("target", {}).get("id") == "impostor-button"
        )
    return bool(step.passed)


def _cover_arm_button_with_impostor(driver: Any) -> None:
    driver.execute_script(
        """
        const arm = document.getElementById("arm-button");
        const rect = arm.getBoundingClientRect();
        const impostor = document.createElement("button");
        impostor.id = "impostor-button";
        impostor.type = "button";
        impostor.setAttribute("aria-label", "Delete account");
        impostor.textContent = "Delete";
        Object.assign(impostor.style, {
          position: "fixed",
          left: rect.left + "px",
          top: rect.top + "px",
          width: rect.width + "px",
          height: rect.height + "px",
          zIndex: "999999",
          border: "0",
          background: "#991b1b",
          color: "white",
          fontSize: "28px",
          fontWeight: "700"
        });
        impostor.onclick = () => {
          document.body.dataset.impostorClicked = "1";
          document.getElementById("state").textContent = "IMPOSTOR";
        };
        document.body.appendChild(impostor);
        """
    )


def _varied_snapshot_passed(snapshot: dict[str, Any]) -> bool:
    warnings = set(snapshot.get("warnings", []))
    ids = {
        element.get("id")
        for element in snapshot.get("elements", [])
        if element.get("id")
    }
    return (
        "iframes_not_traversed" not in warnings
        and "shadow_dom_not_traversed" not in warnings
        and "main-action" in ids
        and "email-field" in ids
        and "iframe-button" in ids
        and "shadow-button" in ids
    )


def _blocked_iframe_snapshot_passed(snapshot: dict[str, Any]) -> bool:
    warnings = set(snapshot.get("warnings", []))
    ids = {
        element.get("id")
        for element in snapshot.get("elements", [])
        if element.get("id")
    }
    return (
        "iframes_not_traversed" in warnings
        and "blocked-main-action" in ids
        and "blocked-frame-button" not in ids
    )


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
