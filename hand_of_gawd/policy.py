"""Deterministic safety gate for planner proposals."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Mapping
from urllib.parse import urlparse

from hand_of_gawd.contracts import ActionProposal


APPROVAL_KEYWORDS = (
    "accept",
    "agree",
    "apply",
    "buy",
    "checkout",
    "comment",
    "confirm",
    "confirm purchase",
    "delete",
    "donate",
    "follow",
    "forward",
    "invite",
    "join",
    "log in",
    "login",
    "message",
    "order",
    "pay",
    "place order",
    "post",
    "publish",
    "purchase",
    "reply",
    "remove",
    "save",
    "send",
    "share",
    "sign in",
    "submit payment",
    "subscribe",
    "transfer",
    "tweet",
    "upload",
    "withdraw",
)

CREDENTIAL_FIELD_TYPES = {
    "password",
    "email",
    "file",
    "tel",
}

SENSITIVE_AUTOCOMPLETE_TOKENS = (
    "cc-",
    "credit-card",
    "current-password",
    "new-password",
    "one-time-code",
    "password",
)


@dataclass(frozen=True)
class GateConfig:
    """Policy inputs that should come from config, not the planner."""

    allowed_url_prefixes: tuple[str, ...] = ()
    allow_file_urls: bool = False
    require_snapshot_freshness: bool = True
    approval_keywords: tuple[str, ...] = APPROVAL_KEYWORDS
    approved_action_keys: tuple[str, ...] = ()


@dataclass(frozen=True)
class GateDecision:
    """Authoritative policy decision for a proposed action."""

    allowed: bool
    gate_risk_class: str
    reason: str
    action_type: str
    target_ref: str | None = None
    planner_risk_class: str | None = None
    checks: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "gate_risk_class": self.gate_risk_class,
            "reason": self.reason,
            "action_type": self.action_type,
            "target_ref": self.target_ref,
            "planner_risk_class": self.planner_risk_class,
            "checks": self.checks,
        }


def evaluate_policy_gate(
    proposal: ActionProposal | Mapping[str, Any],
    snapshot: Mapping[str, Any],
    config: GateConfig | None = None,
) -> GateDecision:
    """Return the deterministic gate decision for a planner proposal."""

    config = config or GateConfig()
    parsed = (
        proposal
        if isinstance(proposal, ActionProposal)
        else ActionProposal.from_mapping(proposal)
    )
    action = parsed.proposed_action
    target = _find_target(snapshot, action.target_ref)
    current_url = str(snapshot.get("url") or "")
    snapshot_id = str(snapshot.get("snapshot_id") or "")

    checks: dict[str, Any] = {
        "snapshot_id": snapshot_id,
        "state_seen": parsed.state_seen,
        "current_url_allowed": _url_allowed(current_url, config),
    }

    if config.require_snapshot_freshness and parsed.state_seen != snapshot_id:
        return _decision(
            False,
            "blocked",
            "planner state_seen does not match current snapshot",
            parsed,
            checks,
        )

    if action.type == "stop":
        return _decision(True, "safe", "stop action is always allowed", parsed, checks)

    if not _url_allowed(current_url, config):
        return _decision(
            False,
            "blocked",
            "current URL is outside the allowlist",
            parsed,
            checks,
        )

    if action.type == "wait":
        return _decision(True, "safe", "wait action is allowed", parsed, checks)

    if action.type == "navigate":
        destination = str(action.value or "")
        checks["destination_url_allowed"] = _url_allowed(destination, config)
        checks["destination_cross_origin"] = _cross_origin(current_url, destination)
        if not checks["destination_url_allowed"]:
            return _decision(
                False,
                "blocked",
                "navigation destination is outside the allowlist",
                parsed,
                checks,
            )
        if checks["destination_cross_origin"]:
            return _decision(
                False,
                "approval_required",
                "navigation destination crosses origin",
                parsed,
                checks,
            )
        return _decision(True, "safe", "allowlisted navigation", parsed, checks)

    if target is None:
        return _decision(
            False,
            "blocked",
            "target_ref was not found in current snapshot",
            parsed,
            checks,
        )

    checks["target_enabled"] = bool(target.get("enabled", True))
    checks["target_visible"] = bool(target.get("visible", True))
    checks["target_clickable"] = bool(target.get("clickable", False))
    checks["target_sensitive"] = _target_is_sensitive(target)
    checks["target_approval_keyword"] = _contains_approval_keyword(
        _target_text(target),
        config.approval_keywords,
    )
    checks["target_form_submit"] = bool(target.get("is_submit"))
    checks["target_cross_origin"] = _target_cross_origin(current_url, target)
    checks["target_approval_key"] = _approval_key(
        action.type,
        current_url,
        target,
        action.value,
    )

    if not checks["target_visible"] or not checks["target_enabled"]:
        return _decision(
            False,
            "blocked",
            "target is not visible and enabled",
            parsed,
            checks,
        )

    if action.type == "click" and not checks["target_clickable"]:
        return _decision(
            False,
            "blocked",
            "target is not topmost-clickable in the snapshot",
            parsed,
            checks,
        )

    if checks["target_sensitive"]:
        return _decision(
            False,
            "approval_required",
            "target is credential/payment/contact-sensitive",
            parsed,
            checks,
        )

    if checks["target_form_submit"]:
        return _approval_decision(
            "target submits a form",
            parsed,
            checks,
            config,
        )

    if checks["target_cross_origin"]:
        return _approval_decision(
            "target navigates or submits cross-origin",
            parsed,
            checks,
            config,
        )

    if checks["target_approval_keyword"]:
        return _approval_decision(
            "target text or label matches an approval-required action",
            parsed,
            checks,
            config,
        )

    return _decision(True, "safe", "deterministic gate passed", parsed, checks)


def compute_approval_key(
    proposal: ActionProposal | Mapping[str, Any],
    snapshot: Mapping[str, Any],
) -> str:
    """Return the stable approval key for the proposal's current target."""

    parsed = (
        proposal
        if isinstance(proposal, ActionProposal)
        else ActionProposal.from_mapping(proposal)
    )
    target = _find_target(snapshot, parsed.proposed_action.target_ref)
    if target is None:
        raise ValueError("target_ref was not found in current snapshot")
    current_url = str(snapshot.get("url") or "")
    return _approval_key(
        parsed.proposed_action.type,
        current_url,
        target,
        parsed.proposed_action.value,
    )


def _decision(
    allowed: bool,
    gate_risk_class: str,
    reason: str,
    proposal: ActionProposal,
    checks: Mapping[str, Any],
) -> GateDecision:
    action = proposal.proposed_action
    return GateDecision(
        allowed=allowed,
        gate_risk_class=gate_risk_class,
        reason=reason,
        action_type=action.type,
        target_ref=action.target_ref,
        planner_risk_class=proposal.planner_risk_class,
        checks=dict(checks),
    )


def _approval_decision(
    reason: str,
    proposal: ActionProposal,
    checks: Mapping[str, Any],
    config: GateConfig,
) -> GateDecision:
    checks_with_approval = dict(checks)
    checks_with_approval["operator_approved_action"] = (
        checks_with_approval.get("target_approval_key") in config.approved_action_keys
    )
    if checks_with_approval["operator_approved_action"]:
        return _decision(
            True,
            "approval_granted",
            f"operator approval granted: {reason}",
            proposal,
            checks_with_approval,
        )
    return _decision(
        False,
        "approval_required",
        reason,
        proposal,
        checks_with_approval,
    )


def _approval_key(
    action_type: str,
    current_url: str,
    target: Mapping[str, Any],
    action_value: Any,
) -> str:
    form = target.get("form")
    form_action = None
    if isinstance(form, Mapping):
        form_action = form.get("action")
    identity = {
        "action_type": action_type,
        "action_value_sha256": _action_value_hash(action_value),
        "current_url": current_url,
        "target": {
            "id": target.get("id"),
            "tag": target.get("tag"),
            "role": target.get("role"),
            "name": target.get("name"),
            "text": target.get("text"),
            "type": target.get("type"),
            "href": target.get("href"),
            "form_action": form_action,
            "is_submit": bool(target.get("is_submit")),
        },
    }
    canonical = json.dumps(identity, sort_keys=True, separators=(",", ":"), default=str)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"hog-approval-v1:{digest}"


def _action_value_hash(value: Any) -> str | None:
    if value is None:
        return None
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _find_target(snapshot: Mapping[str, Any], target_ref: str | None) -> Mapping[str, Any] | None:
    if not target_ref:
        return None
    for element in snapshot.get("elements", ()) or ():
        if isinstance(element, Mapping) and element.get("ref") == target_ref:
            return element
    return None


def _target_is_sensitive(target: Mapping[str, Any]) -> bool:
    field_type = str(target.get("type") or "").strip().lower()
    autocomplete = str(target.get("autocomplete") or "").strip().lower()
    name = _target_text(target).lower()
    if field_type in CREDENTIAL_FIELD_TYPES:
        return True
    if any(token in autocomplete for token in SENSITIVE_AUTOCOMPLETE_TOKENS):
        return True
    return any(token in name for token in ("password", "credit card", "card number", "cvv"))


def _target_text(target: Mapping[str, Any]) -> str:
    parts = [
        target.get("name"),
        target.get("text"),
        target.get("aria_label"),
        target.get("label"),
        target.get("placeholder"),
    ]
    return " ".join(str(part) for part in parts if part)


def _contains_approval_keyword(text: str, keywords: tuple[str, ...]) -> bool:
    normalized = " ".join(text.lower().split())
    return any(keyword in normalized for keyword in keywords)


def _url_allowed(url: str, config: GateConfig) -> bool:
    if not url:
        return False
    parsed = urlparse(url)
    if parsed.scheme == "file":
        return config.allow_file_urls
    return any(url.startswith(prefix) for prefix in config.allowed_url_prefixes)


def _target_cross_origin(current_url: str, target: Mapping[str, Any]) -> bool:
    href = str(target.get("href") or "")
    if href and _cross_origin(current_url, href):
        return True

    form = target.get("form")
    if isinstance(form, Mapping):
        action = str(form.get("action") or "")
        if action and _cross_origin(current_url, action):
            return True
    return False


def _cross_origin(source_url: str, destination_url: str) -> bool:
    source = urlparse(source_url)
    destination = urlparse(destination_url)
    if not source.scheme or not destination.scheme:
        return False
    if source.scheme == "file" or destination.scheme == "file":
        return source.scheme != destination.scheme
    source_origin = (source.scheme, source.hostname, source.port)
    destination_origin = (destination.scheme, destination.hostname, destination.port)
    return source_origin != destination_origin
