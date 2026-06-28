from hand_of_gawd.policy import GateConfig, evaluate_policy_gate


def _snapshot(**overrides):
    snapshot = {
        "snapshot_id": "s1",
        "url": "file:///tmp/hand-of-gawd/index.html",
        "elements": [
            {
                "ref": "e1",
                "tag": "button",
                "role": "button",
                "name": "Arm",
                "text": "Arm",
                "enabled": True,
                "visible": True,
                "clickable": True,
                "bbox": [320, 220, 500, 290],
            }
        ],
    }
    snapshot.update(overrides)
    return snapshot


def _proposal(**overrides):
    proposal = {
        "goal": "arm the synthetic fixture",
        "state_seen": "s1",
        "risk_class": "safe",
        "proposed_action": {
            "type": "click",
            "target_ref": "e1",
            "expected_result": {
                "assertions": [{"type": "text_present", "value": "ARMED"}]
            },
        },
    }
    proposal.update(overrides)
    return proposal


def test_gate_allows_safe_click_on_fresh_allowlisted_snapshot():
    decision = evaluate_policy_gate(
        _proposal(),
        _snapshot(),
        GateConfig(allow_file_urls=True),
    )

    assert decision.allowed is True
    assert decision.gate_risk_class == "safe"
    assert decision.planner_risk_class == "safe"


def test_gate_rejects_stale_snapshot_ref_before_action():
    decision = evaluate_policy_gate(
        _proposal(state_seen="s0"),
        _snapshot(),
        GateConfig(allow_file_urls=True),
    )

    assert decision.allowed is False
    assert decision.gate_risk_class == "blocked"
    assert "state_seen" in decision.reason


def test_gate_overrides_planner_safe_label_for_delete_button():
    snapshot = _snapshot(
        elements=[
            {
                "ref": "danger",
                "tag": "button",
                "role": "button",
                "name": "Delete account",
                "text": "Delete account",
                "enabled": True,
                "visible": True,
                "clickable": True,
            }
        ]
    )
    proposal = _proposal(
        proposed_action={
            "type": "click",
            "target_ref": "danger",
        }
    )

    decision = evaluate_policy_gate(
        proposal,
        snapshot,
        GateConfig(allow_file_urls=True),
    )

    assert decision.allowed is False
    assert decision.gate_risk_class == "approval_required"
    assert decision.planner_risk_class == "safe"


def test_gate_blocks_password_field_even_when_planner_says_safe():
    snapshot = _snapshot(
        elements=[
            {
                "ref": "pw",
                "tag": "input",
                "role": "textbox",
                "name": "Password",
                "type": "password",
                "enabled": True,
                "visible": True,
                "clickable": True,
            }
        ]
    )
    proposal = _proposal(
        proposed_action={
            "type": "type",
            "target_ref": "pw",
            "value": "not-written",
        }
    )

    decision = evaluate_policy_gate(
        proposal,
        snapshot,
        GateConfig(allow_file_urls=True),
    )

    assert decision.allowed is False
    assert decision.gate_risk_class == "approval_required"
    assert decision.checks["target_sensitive"] is True


def test_gate_requires_approval_for_submit_control_without_label_keyword():
    snapshot = _snapshot(
        elements=[
            {
                "ref": "submit",
                "tag": "button",
                "role": "button",
                "name": "Continue",
                "text": "Continue",
                "is_submit": True,
                "form": {
                    "action": "file:///tmp/hand-of-gawd/next.html",
                    "method": "post",
                },
                "enabled": True,
                "visible": True,
                "clickable": True,
            }
        ]
    )
    proposal = _proposal(
        proposed_action={
            "type": "click",
            "target_ref": "submit",
        }
    )

    decision = evaluate_policy_gate(
        proposal,
        snapshot,
        GateConfig(allow_file_urls=True),
    )

    assert decision.allowed is False
    assert decision.gate_risk_class == "approval_required"
    assert decision.checks["target_form_submit"] is True


def test_gate_requires_approval_for_cross_origin_link():
    snapshot = _snapshot(
        url="https://safe.example/page",
        elements=[
            {
                "ref": "external",
                "tag": "a",
                "role": "link",
                "name": "Read more",
                "href": "https://other.example/page",
                "enabled": True,
                "visible": True,
                "clickable": True,
            }
        ],
    )
    proposal = _proposal(
        proposed_action={
            "type": "click",
            "target_ref": "external",
        }
    )

    decision = evaluate_policy_gate(
        proposal,
        snapshot,
        GateConfig(allowed_url_prefixes=("https://safe.example/", "https://other.example/")),
    )

    assert decision.allowed is False
    assert decision.gate_risk_class == "approval_required"
    assert decision.checks["target_cross_origin"] is True


def test_gate_requires_approval_for_cross_origin_navigation_even_if_allowlisted():
    proposal = _proposal(
        proposed_action={
            "type": "navigate",
            "value": "https://other.example/page",
        }
    )
    snapshot = _snapshot(url="https://safe.example/page")

    decision = evaluate_policy_gate(
        proposal,
        snapshot,
        GateConfig(allowed_url_prefixes=("https://safe.example/", "https://other.example/")),
    )

    assert decision.allowed is False
    assert decision.gate_risk_class == "approval_required"
    assert decision.checks["destination_cross_origin"] is True


def test_gate_requires_current_url_allowlist():
    decision = evaluate_policy_gate(
        _proposal(),
        _snapshot(url="https://example.com/"),
        GateConfig(allowed_url_prefixes=("https://allowed.example/",)),
    )

    assert decision.allowed is False
    assert decision.gate_risk_class == "blocked"
    assert decision.reason == "current URL is outside the allowlist"
