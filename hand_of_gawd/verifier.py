"""Deterministic post-action verification."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from hand_of_gawd.contracts import ExpectedAssertion, ExpectedResult


@dataclass(frozen=True)
class AssertionCheck:
    """Result of one structured verifier assertion."""

    type: str
    passed: bool
    reason: str
    expected: Any = None
    actual: Any = None
    ref: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result = {
            "type": self.type,
            "passed": self.passed,
            "reason": self.reason,
            "expected": self.expected,
            "actual": self.actual,
        }
        if self.ref is not None:
            result["ref"] = self.ref
        return result


@dataclass(frozen=True)
class VerificationResult:
    """Deterministic verifier output for an action result."""

    passed: bool
    checks: tuple[AssertionCheck, ...]
    fallback_description: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result = {
            "passed": self.passed,
            "checks": [check.to_dict() for check in self.checks],
        }
        if self.fallback_description is not None:
            result["fallback_description"] = self.fallback_description
        return result


def verify_expected_result(
    expected_result: ExpectedResult | Mapping[str, Any],
    snapshot: Mapping[str, Any],
) -> VerificationResult:
    """Check structured post-action assertions against a snapshot."""

    expected = (
        expected_result
        if isinstance(expected_result, ExpectedResult)
        else ExpectedResult.from_mapping(expected_result)
    )

    if not expected.assertions:
        return VerificationResult(
            passed=False,
            checks=(
                AssertionCheck(
                    type="no_assertions",
                    passed=False,
                    reason="no deterministic assertions were supplied",
                ),
            ),
            fallback_description=expected.fallback_description,
        )

    checks = tuple(_check_assertion(assertion, snapshot) for assertion in expected.assertions)
    return VerificationResult(
        passed=all(check.passed for check in checks),
        checks=checks,
        fallback_description=expected.fallback_description,
    )


def _check_assertion(
    assertion: ExpectedAssertion,
    snapshot: Mapping[str, Any],
) -> AssertionCheck:
    if assertion.type == "url_equals":
        return _check_text_value("url_equals", snapshot.get("url"), assertion.value, equals=True)
    if assertion.type == "url_contains":
        return _check_text_value("url_contains", snapshot.get("url"), assertion.value, equals=False)
    if assertion.type == "title_equals":
        return _check_text_value(
            "title_equals", snapshot.get("title"), assertion.value, equals=True
        )
    if assertion.type == "title_contains":
        return _check_text_value(
            "title_contains", snapshot.get("title"), assertion.value, equals=False
        )
    if assertion.type == "text_present":
        text = _snapshot_text(snapshot)
        expected = str(assertion.value or "")
        return AssertionCheck(
            type=assertion.type,
            passed=expected in text,
            reason="text present" if expected in text else "text not present",
            expected=expected,
            actual=text,
        )
    if assertion.type == "text_absent":
        text = _snapshot_text(snapshot)
        expected = str(assertion.value or "")
        return AssertionCheck(
            type=assertion.type,
            passed=expected not in text,
            reason="text absent" if expected not in text else "text still present",
            expected=expected,
            actual=text,
        )
    if assertion.type == "element_state":
        return _check_element_state(assertion, snapshot)

    return AssertionCheck(
        type=assertion.type,
        passed=False,
        reason="unsupported assertion type",
        expected=assertion.to_dict(),
    )


def _check_text_value(
    assertion_type: str,
    actual_value: Any,
    expected_value: Any,
    *,
    equals: bool,
) -> AssertionCheck:
    actual = str(actual_value or "")
    expected = str(expected_value or "")
    passed = actual == expected if equals else expected in actual
    return AssertionCheck(
        type=assertion_type,
        passed=passed,
        reason="matched" if passed else "did not match",
        expected=expected,
        actual=actual,
    )


def _check_element_state(
    assertion: ExpectedAssertion,
    snapshot: Mapping[str, Any],
) -> AssertionCheck:
    if assertion.ref is None or assertion.property is None:
        return AssertionCheck(
            type=assertion.type,
            passed=False,
            reason="element_state requires ref and property",
            expected=assertion.to_dict(),
        )

    element = _find_element(snapshot, assertion.ref)
    if element is None:
        return AssertionCheck(
            type=assertion.type,
            passed=False,
            reason="element ref not found",
            expected=assertion.equals,
            ref=assertion.ref,
        )

    actual = element.get(assertion.property)
    passed = actual == assertion.equals
    return AssertionCheck(
        type=assertion.type,
        passed=passed,
        reason="matched" if passed else "did not match",
        expected=assertion.equals,
        actual=actual,
        ref=assertion.ref,
    )


def _snapshot_text(snapshot: Mapping[str, Any]) -> str:
    parts = [snapshot.get("title"), snapshot.get("text")]
    for element in snapshot.get("elements", ()) or ():
        if isinstance(element, Mapping):
            parts.extend(
                [
                    element.get("name"),
                    element.get("text"),
                    element.get("label"),
                    element.get("placeholder"),
                    element.get("value"),
                ]
            )
    return "\n".join(str(part) for part in parts if part is not None)


def _find_element(snapshot: Mapping[str, Any], ref: str) -> Mapping[str, Any] | None:
    for element in snapshot.get("elements", ()) or ():
        if isinstance(element, Mapping) and element.get("ref") == ref:
            return element
    return None

