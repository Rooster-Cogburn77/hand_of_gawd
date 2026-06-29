"""Operator approval helpers for approval-required proposals."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Mapping

from hand_of_gawd.contracts import ActionProposal
from hand_of_gawd.policy import GateConfig, GateDecision, compute_approval_key
from hand_of_gawd.trace import redact_trace_payload


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


@dataclass(frozen=True)
class ApprovalRecord:
    """Append-only local audit record for one approval request/response pair."""

    created_at: str
    approval_key: str
    approved: bool
    request: dict[str, Any]
    response: dict[str, Any]

    @classmethod
    def from_request_response(
        cls,
        request: ApprovalRequest,
        response: ApprovalResponse,
        *,
        created_at: str | None = None,
    ) -> "ApprovalRecord":
        timestamp = created_at or datetime.now(UTC).isoformat()
        return cls(
            created_at=timestamp,
            approval_key=request.approval_key,
            approved=response.approved and response.approval_key == request.approval_key,
            request=redact_trace_payload(request.to_dict()),
            response=redact_trace_payload(response.to_dict()),
        )

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ApprovalRecord":
        return cls(
            created_at=str(payload.get("created_at") or ""),
            approval_key=str(payload.get("approval_key") or ""),
            approved=bool(payload.get("approved")),
            request=dict(payload.get("request") or {}),
            response=dict(payload.get("response") or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "created_at": self.created_at,
            "approval_key": self.approval_key,
            "approved": self.approved,
            "request": self.request,
            "response": self.response,
        }


class ApprovalStore:
    """Local JSONL store for exact stable action approvals."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def append(
        self,
        request: ApprovalRequest,
        response: ApprovalResponse,
        *,
        created_at: str | None = None,
    ) -> ApprovalRecord:
        record = ApprovalRecord.from_request_response(
            request,
            response,
            created_at=created_at,
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record.to_dict(), sort_keys=True, default=str))
            handle.write("\n")
        return record

    def records(self) -> tuple[ApprovalRecord, ...]:
        if not self.path.exists():
            return ()

        records: list[ApprovalRecord] = []
        with self.path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    payload = json.loads(stripped)
                except json.JSONDecodeError as exc:
                    raise ValueError(
                        f"invalid approval store JSON on line {line_number}: {exc.msg}"
                    ) from exc
                records.append(ApprovalRecord.from_dict(payload))
        return tuple(records)

    def approved_keys(self) -> tuple[str, ...]:
        latest_by_key: dict[str, bool] = {}
        for record in self.records():
            if record.approval_key:
                latest_by_key[record.approval_key] = record.approved
        return tuple(key for key, approved in latest_by_key.items() if approved)


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


def gate_config_with_approval_store(
    config: GateConfig,
    store: ApprovalStore,
) -> GateConfig:
    """Return a config with currently approved exact keys loaded from a store."""

    keys = tuple(dict.fromkeys((*config.approved_action_keys, *store.approved_keys())))
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
