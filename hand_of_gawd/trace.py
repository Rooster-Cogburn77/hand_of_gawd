"""Trace logging primitives for hand_of_gawd."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable, Mapping


DEFAULT_REDACT_KEYWORDS = (
    "api_key",
    "authorization",
    "cookie",
    "credential",
    "password",
    "secret",
    "token",
)

DEFAULT_REDACT_EXACT_KEYS = (
    "action_value_preview",
    "aria_label",
    "label",
    "name",
    "placeholder",
    "text",
    "value",
)


def redact_trace_payload(
    value: Any,
    *,
    redact_keywords: Iterable[str] = DEFAULT_REDACT_KEYWORDS,
    redact_exact_keys: Iterable[str] = DEFAULT_REDACT_EXACT_KEYS,
) -> Any:
    """Recursively redact sensitive keys before writing a shareable trace."""

    keywords = tuple(keyword.lower() for keyword in redact_keywords)
    exact_keys = tuple(key.lower() for key in redact_exact_keys)
    return _redact_trace_payload(value, keywords=keywords, exact_keys=exact_keys)


def _redact_trace_payload(
    value: Any,
    *,
    keywords: tuple[str, ...],
    exact_keys: tuple[str, ...],
) -> Any:
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            key_lower = key_text.lower()
            if key_lower in exact_keys or any(keyword in key_lower for keyword in keywords):
                result[key_text] = "[REDACTED]"
            else:
                result[key_text] = _redact_trace_payload(
                    item,
                    keywords=keywords,
                    exact_keys=exact_keys,
                )
        return result

    if isinstance(value, list):
        return [
            _redact_trace_payload(item, keywords=keywords, exact_keys=exact_keys)
            for item in value
        ]
    if isinstance(value, tuple):
        return [
            _redact_trace_payload(item, keywords=keywords, exact_keys=exact_keys)
            for item in value
        ]
    return value


@dataclass
class TraceRecorder:
    """Append-only JSONL trace writer."""

    path: Path | str

    def __post_init__(self) -> None:
        self.path = Path(self.path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, event_type: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        if not event_type.strip():
            raise ValueError("event_type must be non-empty")

        event = {
            "created_at": datetime.now(UTC).isoformat(),
            "event_type": event_type.strip(),
            "payload": redact_trace_payload(payload),
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, sort_keys=True) + "\n")
        return event
