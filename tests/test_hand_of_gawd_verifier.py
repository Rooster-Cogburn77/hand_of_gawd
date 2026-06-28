from hand_of_gawd.verifier import verify_expected_result


def _snapshot(**overrides):
    snapshot = {
        "snapshot_id": "s2",
        "url": "file:///tmp/hand-of-gawd/clicked.html",
        "title": "clicked",
        "elements": [
            {
                "ref": "state",
                "tag": "div",
                "text": "ARMED",
                "visible": True,
            },
            {
                "ref": "toggle",
                "tag": "input",
                "role": "checkbox",
                "checked": True,
                "visible": True,
            },
        ],
    }
    snapshot.update(overrides)
    return snapshot


def test_verifier_passes_structured_url_and_text_assertions():
    result = verify_expected_result(
        {
            "assertions": [
                {"type": "url_contains", "value": "clicked.html"},
                {"type": "text_present", "value": "ARMED"},
            ]
        },
        _snapshot(),
    )

    assert result.passed is True
    assert [check.passed for check in result.checks] == [True, True]


def test_verifier_checks_element_state_by_snapshot_ref():
    result = verify_expected_result(
        {
            "assertions": [
                {
                    "type": "element_state",
                    "ref": "toggle",
                    "property": "checked",
                    "equals": True,
                }
            ]
        },
        _snapshot(),
    )

    assert result.passed is True
    assert result.checks[0].actual is True


def test_verifier_fails_missing_element_ref():
    result = verify_expected_result(
        {
            "assertions": [
                {
                    "type": "element_state",
                    "ref": "missing",
                    "property": "checked",
                    "equals": True,
                }
            ]
        },
        _snapshot(),
    )

    assert result.passed is False
    assert result.checks[0].reason == "element ref not found"


def test_verifier_fails_unsupported_assertions_instead_of_guessing():
    result = verify_expected_result(
        {"assertions": [{"type": "looks_good", "value": True}]},
        _snapshot(),
    )

    assert result.passed is False
    assert result.checks[0].reason == "unsupported assertion type"


def test_verifier_fails_when_only_freeform_fallback_exists():
    result = verify_expected_result(
        {"fallback_description": "the page should look armed"},
        _snapshot(),
    )

    assert result.passed is False
    assert result.checks[0].type == "no_assertions"

