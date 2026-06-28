"""Shared contracts for hand_of_gawd agent loops.

The planner proposes actions in this shape, but the policy gate remains the
authority on whether an action is safe to execute.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


ACTION_TYPES = {"click", "type", "select", "navigate", "wait", "stop"}
PLANNER_RISK_CLASSES = {"safe", "approval_required", "blocked"}


@dataclass(frozen=True)
class ExpectedAssertion:
    """A verifier-friendly assertion about post-action state."""

    type: str
    value: Any = None
    ref: str | None = None
    property: str | None = None
    equals: Any = None

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "ExpectedAssertion":
        assertion_type = _required_str(data, "type")
        return cls(
            type=assertion_type,
            value=data.get("value"),
            ref=_optional_str(data, "ref"),
            property=_optional_str(data, "property"),
            equals=data.get("equals"),
        )

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"type": self.type}
        if self.value is not None:
            result["value"] = self.value
        if self.ref is not None:
            result["ref"] = self.ref
        if self.property is not None:
            result["property"] = self.property
        if self.equals is not None:
            result["equals"] = self.equals
        return result


@dataclass(frozen=True)
class ExpectedResult:
    """Structured verifier assertions plus optional human-readable fallback."""

    assertions: tuple[ExpectedAssertion, ...] = ()
    fallback_description: str | None = None

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any] | None) -> "ExpectedResult":
        if data is None:
            return cls()
        if not isinstance(data, Mapping):
            raise ValueError("expected_result must be an object")

        raw_assertions = data.get("assertions", [])
        if raw_assertions is None:
            raw_assertions = ()
        if not isinstance(raw_assertions, list):
            raise ValueError("expected_result.assertions must be a list")

        assertions = tuple(
            ExpectedAssertion.from_mapping(_require_mapping(item, "assertion"))
            for item in raw_assertions
        )
        return cls(
            assertions=assertions,
            fallback_description=_optional_str(data, "fallback_description"),
        )

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "assertions": [assertion.to_dict() for assertion in self.assertions]
        }
        if self.fallback_description is not None:
            result["fallback_description"] = self.fallback_description
        return result


@dataclass(frozen=True)
class ProposedAction:
    """One model-proposed UI action."""

    type: str
    target_ref: str | None = None
    value: Any = None
    reason: str | None = None
    expected_result: ExpectedResult = field(default_factory=ExpectedResult)

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "ProposedAction":
        action_type = _required_str(data, "type")
        if action_type not in ACTION_TYPES:
            raise ValueError(f"unsupported action type: {action_type}")
        return cls(
            type=action_type,
            target_ref=_optional_str(data, "target_ref"),
            value=data.get("value"),
            reason=_optional_str(data, "reason"),
            expected_result=ExpectedResult.from_mapping(data.get("expected_result")),
        )

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "type": self.type,
            "expected_result": self.expected_result.to_dict(),
        }
        if self.target_ref is not None:
            result["target_ref"] = self.target_ref
        if self.value is not None:
            result["value"] = self.value
        if self.reason is not None:
            result["reason"] = self.reason
        return result


@dataclass(frozen=True)
class ActionProposal:
    """Planner output consumed by the deterministic policy gate."""

    goal: str
    state_seen: str
    proposed_action: ProposedAction
    planner_risk_class: str | None = None
    needs_holo: bool = False

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "ActionProposal":
        planner_risk_class = _optional_str(data, "risk_class")
        if (
            planner_risk_class is not None
            and planner_risk_class not in PLANNER_RISK_CLASSES
        ):
            raise ValueError(f"unsupported planner risk_class: {planner_risk_class}")

        proposed_action = ProposedAction.from_mapping(
            _require_mapping(data.get("proposed_action"), "proposed_action")
        )
        return cls(
            goal=_required_str(data, "goal"),
            state_seen=_required_str(data, "state_seen"),
            proposed_action=proposed_action,
            planner_risk_class=planner_risk_class,
            needs_holo=bool(data.get("needs_holo", False)),
        )

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "goal": self.goal,
            "state_seen": self.state_seen,
            "proposed_action": self.proposed_action.to_dict(),
            "needs_holo": self.needs_holo,
        }
        if self.planner_risk_class is not None:
            result["risk_class"] = self.planner_risk_class
        return result


def normalize_action_proposal(data: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and normalize planner output into the public contract shape."""

    return ActionProposal.from_mapping(data).to_dict()


def _required_str(data: Mapping[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return value.strip()


def _optional_str(data: Mapping[str, Any], key: str) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string")
    value = value.strip()
    return value or None


def _require_mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be an object")
    return value
