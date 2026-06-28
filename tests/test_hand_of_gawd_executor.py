from hand_of_gawd.contracts import ActionProposal
from hand_of_gawd.executor import (
    CLICK_AT_POINT_JS,
    SELECT_AT_POINT_JS,
    TYPE_AT_POINT_JS,
    execute_browser_action,
)


class FakeDriver:
    def __init__(self, result=None):
        self.result = result or {"ok": True}
        self.calls = []
        self.navigated_to = None

    def execute_script(self, script, *args):
        self.calls.append((script, args))
        return self.result

    def get(self, url):
        self.navigated_to = url


def _snapshot():
    return {
        "snapshot_id": "s1",
        "url": "file:///tmp/index.html",
        "elements": [
            {
                "ref": "e1",
                "id": "arm",
                "tag": "button",
                "role": "button",
                "name": "Arm",
                "text": "Arm",
                "bbox": [10, 20, 30, 40],
                "clickable": True,
                "visible": True,
                "enabled": True,
            }
        ],
    }


def _proposal(action_type="click", **action_overrides):
    action = {"type": action_type, "target_ref": "e1"}
    action.update(action_overrides)
    return ActionProposal.from_mapping(
        {
            "goal": "test",
            "state_seen": "s1",
            "proposed_action": action,
        }
    )


def test_execute_click_uses_bbox_center_with_element_from_point_script():
    driver = FakeDriver({"ok": True, "target": {"id": "arm"}})
    result = execute_browser_action(driver, _proposal(), _snapshot())

    assert result.ok is True
    assert driver.calls == [
        (
            CLICK_AT_POINT_JS,
            (
                20.0,
                30.0,
                {
                    "id": "arm",
                    "tag": "button",
                    "role": "button",
                    "name": "Arm",
                    "text": "Arm",
                },
            ),
        )
    ]
    assert result.adapter_result["target"]["id"] == "arm"


def test_execute_type_uses_bbox_center_and_value():
    driver = FakeDriver({"ok": True})
    result = execute_browser_action(
        driver,
        _proposal("type", value="hello"),
        _snapshot(),
    )

    assert result.ok is True
    assert driver.calls[0][0] == TYPE_AT_POINT_JS
    assert driver.calls[0][1][0:3] == (20.0, 30.0, "hello")
    assert driver.calls[0][1][3]["id"] == "arm"


def test_execute_select_uses_bbox_center_and_value():
    driver = FakeDriver({"ok": True})
    result = execute_browser_action(
        driver,
        _proposal("select", value="two"),
        _snapshot(),
    )

    assert result.ok is True
    assert driver.calls[0][0] == SELECT_AT_POINT_JS
    assert driver.calls[0][1][0:3] == (20.0, 30.0, "two")
    assert driver.calls[0][1][3]["id"] == "arm"


def test_execute_navigate_delegates_to_driver_get():
    driver = FakeDriver()
    result = execute_browser_action(
        driver,
        _proposal("navigate", target_ref=None, value="file:///tmp/next.html"),
        _snapshot(),
    )

    assert result.ok is True
    assert driver.navigated_to == "file:///tmp/next.html"


def test_execute_returns_failure_when_adapter_reports_failure():
    driver = FakeDriver({"ok": False, "error": "no_element_at_point"})
    result = execute_browser_action(driver, _proposal(), _snapshot())

    assert result.ok is False
    assert result.reason == "no_element_at_point"


def test_execute_reports_identity_mismatch_without_claiming_success():
    driver = FakeDriver({"ok": False, "error": "target_identity_mismatch"})
    result = execute_browser_action(driver, _proposal(), _snapshot())

    assert result.ok is False
    assert result.reason == "target_identity_mismatch"
