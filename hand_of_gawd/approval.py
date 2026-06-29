"""Operator approval helpers for approval-required proposals."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from typing import Any, Callable, Mapping

from hand_of_gawd.contracts import ActionProposal
from hand_of_gawd.policy import GateConfig, GateDecision, compute_approval_key


@dataclass(frozen=True)
class ApprovalRequest:
    """Human-readable request for one stable action approval key."""

    approval_key: str
    reason: str
    current_url: str
    goal: str
    action_type: str
    target_ref: str | None
    target_identity: dict[str, Any]
    expected_result: dict[str, Any]
    action_value_preview: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result = {
            "approval_key": self.approval_key,
            "reason": self.reason,
            "current_url": self.current_url,
            "goal": self.goal,
            "action_type": self.action_type,
            "target_ref": self.target_ref,
            "target_identity": self.target_identity,
            "expected_result": self.expected_result,
        }
        if self.action_value_preview is not None:
            result["action_value_preview"] = self.action_value_preview
        return result


@dataclass(frozen=True)
class ApprovalResponse:
    """Operator response to one approval request."""

    approved: bool
    approval_key: str | None = None
    mode: str = "prompt"
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "approved": self.approved,
            "approval_key": self.approval_key,
            "mode": self.mode,
            "reason": self.reason,
        }


def build_approval_request(
    proposal: ActionProposal | Mapping[str, Any],
    snapshot: Mapping[str, Any],
    gate: GateDecision,
) -> ApprovalRequest:
    """Build an operator-facing approval request from a gate refusal."""

    if gate.gate_risk_class != "approval_required":
        raise ValueError("approval request can only be built for approval_required gates")
    if gate.checks.get("operator_approval_liftable") is not True:
        raise ValueError("gate decision is not operator-liftable")

    parsed = (
        proposal
        if isinstance(proposal, ActionProposal)
        else ActionProposal.from_mapping(proposal)
    )
    action = parsed.proposed_action
    target = _find_target(snapshot, action.target_ref)
    if target is None and action.type != "navigate":
        raise ValueError("target_ref was not found in current snapshot")

    approval_key = str(gate.checks.get("target_approval_key") or "")
    if not approval_key:
        approval_key = compute_approval_key(parsed, snapshot)

    return ApprovalRequest(
        approval_key=approval_key,
        reason=gate.reason,
        current_url=str(snapshot.get("url") or ""),
        goal=parsed.goal,
        action_type=action.type,
        target_ref=action.target_ref,
        target_identity=(
            _target_identity(target)
            if target is not None
            else {"destination_url": action.value}
        ),
        expected_result=action.expected_result.to_dict(),
        action_value_preview=_preview_action_value(action.value),
    )


def format_approval_request(request: ApprovalRequest) -> str:
    """Return the exact text shown to the operator before approval."""

    lines = [
        "hand_of_gawd approval required",
        f"Reason: {request.reason}",
        f"URL: {request.current_url}",
        f"Goal: {request.goal}",
        f"Action: {request.action_type}",
    ]
    if request.target_ref:
        lines.append(f"Target ref: {request.target_ref}")

    lines.append("Target identity:")
    for key, value in request.target_identity.items():
        lines.append(f"  {key}: {_display_value(value)}")

    if request.action_value_preview is not None:
        lines.append(f"Action value: {request.action_value_preview}")

    lines.append("Expected result:")
    assertions = request.expected_result.get("assertions") or []
    if assertions:
        for assertion in assertions:
            lines.append(f"  - {_display_value(assertion)}")
    else:
        lines.append("  - <no deterministic assertions>")

    lines.extend(
        [
            f"Approval key: {request.approval_key}",
            "Type YES to approve this exact action, or NO to deny.",
        ]
    )
    return "\n".join(lines)


def prompt_for_operator_approval(
    request: ApprovalRequest,
    *,
    input_fn: Callable[[str], str] = input,
    output_fn: Callable[[str], None] = print,
) -> ApprovalResponse:
    """Prompt the operator and return an approval response."""

    output_fn(format_approval_request(request))
    while True:
        try:
            answer = input_fn("Approve this exact action? [YES/NO] ").strip()
        except (EOFError, KeyboardInterrupt):
            return ApprovalResponse(
                approved=False,
                approval_key=None,
                mode="prompt",
                reason="operator approval interrupted",
            )

        if answer == "YES":
            return ApprovalResponse(
                approved=True,
                approval_key=request.approval_key,
                mode="prompt",
                reason="operator typed YES",
            )
        if answer == "NO":
            return ApprovalResponse(
                approved=False,
                approval_key=None,
                mode="prompt",
                reason="operator typed NO",
            )
        output_fn("Please type exactly YES or NO.")


def approval_response_for_mode(
    request: ApprovalRequest,
    mode: str,
    *,
    input_fn: Callable[[str], str] = input,
    output_fn: Callable[[str], None] = print,
) -> ApprovalResponse:
    """Resolve an approval request using a smoke/testable approval mode."""

    if mode == "prompt":
        return prompt_for_operator_approval(
            request,
            input_fn=input_fn,
            output_fn=output_fn,
        )
    if mode == "auto-approve":
        return ApprovalResponse(
            approved=True,
            approval_key=request.approval_key,
            mode=mode,
            reason="auto-approved by caller",
        )
    if mode == "deny":
        return ApprovalResponse(
            approved=False,
            approval_key=None,
            mode=mode,
            reason="denied by caller",
        )
    raise ValueError(f"unsupported approval mode: {mode}")


def gate_config_with_approval(
    config: GateConfig,
    response: ApprovalResponse,
) -> GateConfig:
    """Return a config with the response's exact key added when approved."""

    if not response.approved or not response.approval_key:
        return config
    keys = tuple(dict.fromkeys((*config.approved_action_keys, response.approval_key)))
    return replace(config, approved_action_keys=keys)


def _find_target(snapshot: Mapping[str, Any], target_ref: str | None) -> Mapping[str, Any] | None:
    if not target_ref:
        return None
    for element in snapshot.get("elements", ()) or ():
        if isinstance(element, Mapping) and element.get("ref") == target_ref:
            return element
    return None


def _target_identity(target: Mapping[str, Any]) -> dict[str, Any]:
    form = target.get("form")
    form_action = form.get("action") if isinstance(form, Mapping) else None
    return {
        "id": target.get("id"),
        "tag": target.get("tag"),
        "role": target.get("role"),
        "name": target.get("name"),
        "text": target.get("text"),
        "type": target.get("type"),
        "href": target.get("href"),
        "form_action": form_action,
        "is_submit": bool(target.get("is_submit")),
    }


def _preview_action_value(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, sort_keys=True, default=str)


def _display_value(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, sort_keys=True, default=str)
