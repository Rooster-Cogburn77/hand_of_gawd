import pytest

from hand_of_gawd.contracts import ActionProposal, normalize_action_proposal


def test_action_proposal_normalizes_structured_expected_result():
    result = normalize_action_proposal(
        {
            "goal": "arm the local synthetic page",
            "state_seen": "s1",
            "risk_class": "safe",
            "needs_holo": False,
            "proposed_action": {
                "type": "click",
                "target_ref": "e7",
                "reason": "Arm is the requested control",
                "expected_result": {
                    "assertions": [
                        {"type": "url_contains", "value": "clicked.html"},
                        {"type": "text_present", "value": "ARMED"},
                    ],
                    "fallback_description": "the page should show ARMED",
                },
            },
        }
    )

    assert result["goal"] == "arm the local synthetic page"
    assert result["state_seen"] == "s1"
    assert result["risk_class"] == "safe"
    assert result["proposed_action"]["target_ref"] == "e7"
    assertions = result["proposed_action"]["expected_result"]["assertions"]
    assert assertions == [
        {"type": "url_contains", "value": "clicked.html"},
        {"type": "text_present", "value": "ARMED"},
    ]


def test_action_proposal_preserves_planner_risk_as_advisory_field():
    proposal = ActionProposal.from_mapping(
        {
            "goal": "delete the account",
            "state_seen": "s1",
            "risk_class": "safe",
            "proposed_action": {
                "type": "click",
                "target_ref": "danger",
            },
        }
    )

    assert proposal.planner_risk_class == "safe"


@pytest.mark.parametrize("action_type", ["script", "submit", ""])
def test_action_proposal_rejects_unsupported_action_types(action_type):
    with pytest.raises(ValueError):
        normalize_action_proposal(
            {
                "goal": "bad action",
                "state_seen": "s1",
                "proposed_action": {"type": action_type},
            }
        )


def test_action_proposal_requires_snapshot_identity():
    with pytest.raises(ValueError, match="state_seen"):
        normalize_action_proposal(
            {
                "goal": "click",
                "state_seen": "",
                "proposed_action": {"type": "click", "target_ref": "e1"},
            }
        )

