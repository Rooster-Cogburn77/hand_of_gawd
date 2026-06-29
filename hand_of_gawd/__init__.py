"""Public package root for hand_of_gawd."""

from hand_of_gawd.approval import (
    ApprovalRequest,
    ApprovalResponse,
    approval_response_for_mode,
    build_approval_request,
    format_approval_request,
    gate_config_with_approval,
    prompt_for_operator_approval,
)
from hand_of_gawd.contracts import (
    ActionProposal,
    ExpectedAssertion,
    ExpectedResult,
    ProposedAction,
    normalize_action_proposal,
)
from hand_of_gawd.executor import ActionExecutionResult, execute_browser_action
from hand_of_gawd.loop import StepLimitExceeded, StepResult, run_verified_plan, run_verified_step
from hand_of_gawd.policy import GateConfig, GateDecision, evaluate_policy_gate
from hand_of_gawd.selenium_snapshot import capture_snapshot
from hand_of_gawd.trace import TraceRecorder, redact_trace_payload
from hand_of_gawd.verifier import AssertionCheck, VerificationResult, verify_expected_result

__all__ = [
    "ActionProposal",
    "ActionExecutionResult",
    "ApprovalRequest",
    "ApprovalResponse",
    "AssertionCheck",
    "ExpectedAssertion",
    "ExpectedResult",
    "GateConfig",
    "GateDecision",
    "ProposedAction",
    "TraceRecorder",
    "StepResult",
    "StepLimitExceeded",
    "VerificationResult",
    "approval_response_for_mode",
    "build_approval_request",
    "capture_snapshot",
    "execute_browser_action",
    "evaluate_policy_gate",
    "format_approval_request",
    "gate_config_with_approval",
    "normalize_action_proposal",
    "prompt_for_operator_approval",
    "redact_trace_payload",
    "run_verified_plan",
    "run_verified_step",
    "verify_expected_result",
]
