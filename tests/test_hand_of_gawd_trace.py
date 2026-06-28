import json

from hand_of_gawd.trace import TraceRecorder, redact_trace_payload


def test_redact_trace_payload_redacts_sensitive_keys_recursively():
    redacted = redact_trace_payload(
        {
            "authorization": "Bearer abc",
            "nested": {
                "api_token": "secret-token",
                "safe": "kept",
            },
            "proposed_action": {
                "type": "type",
                "target_ref": "e1",
                "value": "private typed text",
            },
            "element": {
                "name": "Jane Doe",
                "text": "jane@example.test",
            },
            "items": [{"cookie": "session"}],
        }
    )

    assert redacted["authorization"] == "[REDACTED]"
    assert redacted["nested"]["api_token"] == "[REDACTED]"
    assert redacted["nested"]["safe"] == "kept"
    assert redacted["proposed_action"]["value"] == "[REDACTED]"
    assert redacted["element"]["name"] == "[REDACTED]"
    assert redacted["element"]["text"] == "[REDACTED]"
    assert redacted["items"][0]["cookie"] == "[REDACTED]"


def test_trace_recorder_writes_jsonl_with_redaction(tmp_path):
    trace_path = tmp_path / "hog_trace_test.jsonl"
    event = TraceRecorder(trace_path).record(
        "policy_gate",
        {"snapshot_id": "s1", "password": "not-written"},
    )

    assert event["event_type"] == "policy_gate"
    rows = [json.loads(line) for line in trace_path.read_text().splitlines()]
    assert len(rows) == 1
    assert rows[0]["payload"]["snapshot_id"] == "s1"
    assert rows[0]["payload"]["password"] == "[REDACTED]"
