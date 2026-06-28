from pathlib import Path

import pytest

from hand_of_gawd.selenium_snapshot import SNAPSHOT_JS, capture_snapshot


class FakeDriver:
    def __init__(self, snapshot, screenshot_ok=True):
        self.snapshot = snapshot
        self.screenshot_ok = screenshot_ok
        self.script = None
        self.script_args = None
        self.screenshot_path = None

    def execute_script(self, script, *args):
        self.script = script
        self.script_args = args
        return dict(self.snapshot)

    def save_screenshot(self, path):
        self.screenshot_path = path
        Path(path).write_bytes(b"fake")
        return self.screenshot_ok


def test_snapshot_script_uses_element_from_point_for_clickability():
    assert "document.elementFromPoint" in SNAPSHOT_JS
    assert "iframes_not_traversed" in SNAPSHOT_JS
    assert "shadow_dom_not_traversed" in SNAPSHOT_JS
    assert "Array.from(document.querySelectorAll(\"*\")).some" in SNAPSHOT_JS
    assert "isSubmitControl" in SNAPSHOT_JS
    assert "formInfo" in SNAPSHOT_JS


def test_capture_snapshot_adds_snapshot_id_and_screenshot_path(tmp_path):
    driver = FakeDriver(
        {
            "url": "file:///tmp/index.html",
            "title": "fixture",
            "viewport": {"width": 900, "height": 600},
            "elements": [],
        }
    )

    screenshot = tmp_path / "before.png"
    snapshot = capture_snapshot(driver, snapshot_id="s1", screenshot_path=screenshot)

    assert snapshot["snapshot_id"] == "s1"
    assert snapshot["screenshot_path"] == str(screenshot)
    assert driver.script_args == ("s1",)
    assert screenshot.read_bytes() == b"fake"


def test_capture_snapshot_rejects_non_object_script_result():
    class BadDriver:
        def execute_script(self, script, *args):
            return None

    with pytest.raises(ValueError, match="did not return an object"):
        capture_snapshot(BadDriver(), snapshot_id="s1")


def test_capture_snapshot_requires_elements_list():
    driver = FakeDriver(
        {
            "snapshot_id": "s1",
            "url": "file:///tmp/index.html",
            "title": "fixture",
            "viewport": {"width": 900, "height": 600},
            "elements": {},
        }
    )

    with pytest.raises(ValueError, match="elements"):
        capture_snapshot(driver, snapshot_id="s1")
