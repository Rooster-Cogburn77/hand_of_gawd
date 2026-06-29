from hand_of_gawd.approval import (
    approval_response_for_mode,
    build_approval_request,
    format_approval_request,
    gate_config_with_approval,
    prompt_for_operator_approval,
)
from hand_of_gawd.policy import GateConfig, evaluate_policy_gate


def _snapshot():
    return {
        "snapshot_id": "s1",
        "url": "https://safe.example/form",
        "elements": [
            {
                "ref": "e1",
                "id": "submit-button",
                "tag": "button",
                "role": "button",
                "name": "Submit fixture",
                "text": "Submit",
                "enabled": True,
                "visible": True,
                "clickable": True,
                "bbox": [10, 10, 80, 40],
                "is_submit": True,
                "form": {"action": "https://safe.example/form"},
            }
        ],
    }


def _proposal(value=None):
    action = {
        "type": "click",
        "target_ref": "e1",
        "reason": "Submit the synthetic form.",
        "expected_result": {
            "assertions": [{"type": "text_present", "value": "SUBMITTED"}]
        },
    }
    if value is not None:
        action["type"] = "type"
        action["value"] = value
    return {
        "goal": "submit the synthetic fixture",
        "state_seen": "s1",
        "risk_class": "safe",
        "proposed_action": action,
    }


def test_build_approval_request_formats_exact_action_identity():
    snapshot = _snapshot()
    proposal = _proposal()
    gate = evaluate_policy_gate(
        proposal,
        snapshot,
        GateConfig(allowed_url_prefixes=("https://safe.example/",)),
    )

    request = build_approval_request(proposal, snapshot, gate)
    text = format_approval_request(request)

    assert gate.allowed is False
    assert gate.gate_risk_class == "approval_required"
    assert request.approval_key.startswith("hog-approval-v1:")
    assert request.reason == "target submits a form"
    assert request.target_identity["id"] == "submit-button"
    assert "Type YES to approve this exact action, or NO to deny." in text
    assert request.approval_key in text


def test_prompt_approval_requires_explicit_yes():
    snapshot = _snapshot()
    proposal = _proposal()
    gate = evaluate_policy_gate(
        proposal,
        snapshot,
        GateConfig(allowed_url_prefixes=("https://safe.example/",)),
    )
    request = build_approval_request(proposal, snapshot, gate)
    outputs = []
    answers = iter(["yes", "y", "YES"])

    response = prompt_for_operator_approval(
        request,
        input_fn=lambda _prompt: next(answers),
        output_fn=outputs.append,
    )

    assert response.approved is True
    assert response.approval_key == request.approval_key
    assert sum("Please type exactly YES or NO." in item for item in outputs) == 2


def test_denied_approval_leaves_gate_refused():
    snapshot = _snapshot()
    proposal = _proposal()
    base_config = GateConfig(allowed_url_prefixes=("https://safe.example/",))
    gate = evaluate_policy_gate(proposal, snapshot, base_config)
    request = build_approval_request(proposal, snapshot, gate)

    response = approval_response_for_mode(request, "deny")
    config = gate_config_with_approval(base_config, response)
    decision = evaluate_policy_gate(proposal, snapshot, config)

    assert response.approved is False
    assert decision.allowed is False
    assert decision.gate_risk_class == "approval_required"
    assert decision.checks["operator_approved_action"] is False


def test_build_approval_request_rejects_non_liftable_sensitive_gate():
    snapshot = _snapshot()
    snapshot["elements"][0]["type"] = "password"
    snapshot["elements"][0]["is_submit"] = False
    proposal = _proposal()
    base_config = GateConfig(allowed_url_prefixes=("https://safe.example/",))
    gate = evaluate_policy_gate(proposal, snapshot, base_config)

    assert gate.gate_risk_class == "approval_required"
    assert gate.checks["operator_approval_liftable"] is False

    try:
        build_approval_request(proposal, snapshot, gate)
    except ValueError as exc:
        assert str(exc) == "gate decision is not operator-liftable"
    else:
        raise AssertionError("expected non-liftable gate to reject approval request")


def test_build_approval_request_supports_liftable_cross_origin_navigation():
    snapshot = _snapshot()
    snapshot["url"] = "https://safe.example/start"
    proposal = {
        "goal": "navigate to an allowlisted external page",
        "state_seen": "s1",
        "risk_class": "safe",
        "proposed_action": {
            "type": "navigate",
            "value": "https://other.example/page",
            "expected_result": {
                "assertions": [{"type": "url_contains", "value": "other.example"}]
            },
        },
    }
    gate = evaluate_policy_gate(
        proposal,
        snapshot,
        GateConfig(
            allowed_url_prefixes=("https://safe.example/", "https://other.example/")
        ),
    )

    request = build_approval_request(proposal, snapshot, gate)

    assert gate.gate_risk_class == "approval_required"
    assert gate.checks["operator_approval_liftable"] is True
    assert request.target_ref is None
    assert request.target_identity["destination_url"] == "https://other.example/page"
    assert request.action_value_preview == '"https://other.example/page"'


def test_approved_response_lifts_only_the_exact_stable_key():
    snapshot = _snapshot()
    approved_proposal = _proposal(value="approved text")
    changed_proposal = _proposal(value="changed text")
    base_config = GateConfig(allowed_url_prefixes=("https://safe.example/",))
    gate = evaluate_policy_gate(approved_proposal, snapshot, base_config)
    request = build_approval_request(approved_proposal, snapshot, gate)

    response = approval_response_for_mode(request, "auto-approve")
    config = gate_config_with_approval(base_config, response)
    approved_decision = evaluate_policy_gate(approved_proposal, snapshot, config)
    changed_decision = evaluate_policy_gate(changed_proposal, snapshot, config)

    assert approved_decision.allowed is True
    assert approved_decision.gate_risk_class == "approval_granted"
    assert changed_decision.allowed is False
    assert changed_decision.gate_risk_class == "approval_required"
    assert changed_decision.checks["operator_approved_action"] is False
