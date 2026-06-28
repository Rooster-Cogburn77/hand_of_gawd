"""One-step observe/gate/act/verify plumbing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from hand_of_gawd.contracts import ActionProposal
from hand_of_gawd.executor import ActionExecutionResult, execute_browser_action
from hand_of_gawd.policy import GateConfig, GateDecision, evaluate_policy_gate
from hand_of_gawd.selenium_snapshot import capture_snapshot
from hand_of_gawd.trace import TraceRecorder
from hand_of_gawd.verifier import VerificationResult, verify_expected_result


class StepLimitExceeded(RuntimeError):
    """Raised when a plan would exceed the configured step limit."""


@dataclass(frozen=True)
class StepResult:
    """Full result for one proposed step."""

    gate: GateDecision
    execution: ActionExecutionResult | None
    after_snapshot: dict[str, Any] | None
    verification: VerificationResult | None

    @property
    def passed(self) -> bool:
        return (
            self.gate.allowed
            and self.execution is not None
            and self.execution.ok
            and self.verification is not None
            and self.verification.passed
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "gate": self.gate.to_dict(),
            "execution": self.execution.to_dict() if self.execution else None,
            "after_snapshot": self.after_snapshot,
            "verification": self.verification.to_dict() if self.verification else None,
        }


def run_verified_step(
    driver: Any,
    proposal: ActionProposal | Mapping[str, Any],
    before_snapshot: Mapping[str, Any],
    *,
    gate_config: GateConfig | None = None,
    trace: TraceRecorder | None = None,
    after_snapshot_id: str | None = None,
) -> StepResult:
    """Gate, execute, re-observe, and verify one planner proposal."""

    parsed = (
        proposal
        if isinstance(proposal, ActionProposal)
        else ActionProposal.from_mapping(proposal)
    )
    gate = evaluate_policy_gate(parsed, before_snapshot, gate_config or GateConfig())
    if trace:
        trace.record(
            "policy_gate",
            {
                "proposal": parsed.to_dict(),
                "snapshot_id": before_snapshot.get("snapshot_id"),
                "decision": gate.to_dict(),
            },
        )

    if not gate.allowed:
        result = StepResult(
            gate=gate,
            execution=None,
            after_snapshot=None,
            verification=None,
        )
        if trace:
            trace.record("step_result", result.to_dict())
        return result

    execution = execute_browser_action(driver, parsed, before_snapshot)
    if trace:
        trace.record("action_execution", execution.to_dict())

    after_snapshot = capture_snapshot(driver, snapshot_id=after_snapshot_id)
    verification = verify_expected_result(
        parsed.proposed_action.expected_result,
        after_snapshot,
    )
    result = StepResult(
        gate=gate,
        execution=execution,
        after_snapshot=after_snapshot,
        verification=verification,
    )
    if trace:
        trace.record("step_result", result.to_dict())
    return result


def run_verified_plan(
    driver: Any,
    proposals: list[ActionProposal | Mapping[str, Any]],
    initial_snapshot: Mapping[str, Any],
    *,
    gate_config: GateConfig | None = None,
    trace: TraceRecorder | None = None,
    max_steps: int = 5,
) -> list[StepResult]:
    """Run a bounded sequence of already-generated proposals."""

    if max_steps < 1:
        raise ValueError("max_steps must be at least 1")
    if len(proposals) > max_steps:
        raise StepLimitExceeded(
            f"proposal count {len(proposals)} exceeds max_steps {max_steps}"
        )

    results: list[StepResult] = []
    current_snapshot: Mapping[str, Any] = initial_snapshot
    for index, proposal in enumerate(proposals, start=1):
        parsed = (
            proposal
            if isinstance(proposal, ActionProposal)
            else ActionProposal.from_mapping(proposal)
        )
        result = run_verified_step(
            driver,
            parsed,
            current_snapshot,
            gate_config=gate_config,
            trace=trace,
            after_snapshot_id=f"s{index + 1}",
        )
        results.append(result)
        if not result.passed:
            break
        if result.after_snapshot is not None:
            current_snapshot = result.after_snapshot

    return results
