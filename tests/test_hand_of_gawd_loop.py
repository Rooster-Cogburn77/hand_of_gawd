import json

import pytest

from hand_of_gawd.loop import StepLimitExceeded, run_verified_plan, run_verified_step
from hand_of_gawd.policy import GateConfig
from hand_of_gawd.selenium_snapshot import SNAPSHOT_JS
from hand_of_gawd.trace import TraceRecorder


class FakeDriver:
    def __init__(self):
        self.clicked = False

    def execute_script(self, script, *args):
        if script == SNAPSHOT_JS:
            snapshot_id = args[0]
            return {
                "snapshot_id": snapshot_id,
                "url": "file:///tmp/clicked.html" if self.clicked else "file:///tmp/index.html",
                "title": "fixture",
                "viewport": {"width": 900, "height": 600},
                "text": "ARMED" if self.clicked else "SAFE",
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
        self.clicked = True
        return {"ok": True, "target": {"id": "arm"}}


def _before_snapshot():
    return {
        "snapshot_id": "s1",
        "url": "file:///tmp/index.html",
        "title": "fixture",
        "viewport": {"width": 900, "height": 600},
        "text": "SAFE",
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


def _proposal():
    return {
        "goal": "arm the fixture",
        "state_seen": "s1",
        "risk_class": "safe",
        "proposed_action": {
            "type": "click",
            "target_ref": "e1",
            "expected_result": {
                "assertions": [
                    {"type": "url_contains", "value": "clicked.html"},
                    {"type": "text_present", "value": "ARMED"},
                ]
            },
        },
    }


def test_run_verified_step_gates_executes_observes_and_verifies(tmp_path):
    trace_path = tmp_path / "hog_trace_test.jsonl"
    result = run_verified_step(
        FakeDriver(),
        _proposal(),
        _before_snapshot(),
        gate_config=GateConfig(allow_file_urls=True),
        trace=TraceRecorder(trace_path),
        after_snapshot_id="s2",
    )

    assert result.passed is True
    assert result.gate.allowed is True
    assert result.execution is not None
    assert result.execution.ok is True
    assert result.after_snapshot is not None
    assert result.after_snapshot["snapshot_id"] == "s2"
    assert result.verification is not None
    assert result.verification.passed is True

    rows = [json.loads(line) for line in trace_path.read_text().splitlines()]
    assert [row["event_type"] for row in rows] == [
        "policy_gate",
        "action_execution",
        "step_result",
    ]


def test_run_verified_step_stops_before_execution_when_gate_blocks():
    proposal = _proposal()
    proposal["state_seen"] = "stale"
    driver = FakeDriver()

    result = run_verified_step(
        driver,
        proposal,
        _before_snapshot(),
        gate_config=GateConfig(allow_file_urls=True),
    )

    assert result.passed is False
    assert result.gate.allowed is False
    assert result.execution is None
    assert driver.clicked is False


def test_run_verified_plan_enforces_max_steps():
    with pytest.raises(StepLimitExceeded):
        run_verified_plan(
            FakeDriver(),
            [_proposal(), _proposal()],
            _before_snapshot(),
            gate_config=GateConfig(allow_file_urls=True),
            max_steps=1,
        )
