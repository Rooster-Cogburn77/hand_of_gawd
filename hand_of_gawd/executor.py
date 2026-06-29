"""Browser action execution helpers."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Mapping

from hand_of_gawd.contracts import ActionProposal


DEEP_POINT_HELPERS_JS = r"""
function resolveElementFromTopPoint(x, y) {
  return resolveInRoot(document, x, y, 0, 0);
}

function fallbackElementFromPoint(root, x, y) {
  if (!root || typeof root.querySelectorAll !== "function") {
    return null;
  }
  const hits = Array.from(root.querySelectorAll("*")).filter((candidate) => {
    const rect = candidate.getBoundingClientRect();
    return x >= rect.left && x <= rect.right && y >= rect.top && y <= rect.bottom;
  });
  return hits.length ? hits[hits.length - 1] : null;
}

function rootElementFromPoint(root, x, y) {
  if (!root) return null;
  if (typeof root.elementFromPoint === "function") {
    return root.elementFromPoint(x, y);
  }
  return fallbackElementFromPoint(root, x, y);
}

function resolveInRoot(root, x, y, offsetX, offsetY) {
  const localX = x - offsetX;
  const localY = y - offsetY;
  let el = rootElementFromPoint(root, localX, localY);
  while (el && el.shadowRoot) {
    const shadowEl = rootElementFromPoint(el.shadowRoot, localX, localY);
    if (!shadowEl || shadowEl === el) break;
    el = shadowEl;
  }
  if (el && el.tagName && el.tagName.toLowerCase() === "iframe") {
    let childDoc = null;
    try {
      childDoc = el.contentDocument;
    } catch (err) {
      return {element: el, error: "iframe_not_accessible"};
    }
    if (!childDoc) {
      return {element: el, error: "iframe_not_accessible"};
    }
    const rect = el.getBoundingClientRect();
    return resolveInRoot(childDoc, x, y, offsetX + rect.left, offsetY + rect.top);
  }
  return {element: el, error: null};
}
"""


CLICK_AT_POINT_JS = r"""
const x = arguments[0];
const y = arguments[1];
const expected = arguments[2] || {};
const resolved = resolveElementFromTopPoint(x, y);
const el = resolved.element;
if (!el) {
  return {ok: false, error: resolved.error || "no_element_at_point"};
}
const identity = elementIdentity(el);
if (!matchesExpected(identity, expected)) {
  return {ok: false, error: "target_identity_mismatch", target: identity};
}
el.click();
return {
  ok: true,
  target: identity
};

function elementIdentity(node) {
  const tag = node.tagName ? node.tagName.toLowerCase() : null;
  const explicitRole = node.getAttribute ? node.getAttribute("role") : null;
  const role = explicitRole || (
    tag === "button" ? "button" :
    tag === "a" ? "link" :
    tag === "select" ? "combobox" :
    tag === "textarea" ? "textbox" :
    tag === "input" ? "textbox" :
    null
  );
  const text = (node.innerText || node.textContent || "").replace(/\s+/g, " ").trim().slice(0, 200);
  const name = (
    (node.getAttribute && (node.getAttribute("aria-label") || node.getAttribute("title") || node.getAttribute("placeholder"))) ||
    text ||
    ""
  ).replace(/\s+/g, " ").trim().slice(0, 200);
  return {
    tag,
    id: node.id || null,
    role,
    name,
    text
  };
}

function matchesExpected(actual, expected) {
  if (expected.id && actual.id !== expected.id) return false;
  if (expected.tag && actual.tag !== expected.tag) return false;
  if (expected.role && actual.role && actual.role !== expected.role) return false;
  const expectedName = (expected.name || expected.text || "").trim();
  if (expectedName) {
    const actualText = ((actual.name || "") + " " + (actual.text || "")).trim();
    if (!actualText.includes(expectedName)) return false;
  }
  return true;
}
""" + DEEP_POINT_HELPERS_JS

TYPE_AT_POINT_JS = r"""
const x = arguments[0];
const y = arguments[1];
const value = arguments[2];
const expected = arguments[3] || {};
const resolved = resolveElementFromTopPoint(x, y);
const el = resolved.element;
if (!el) {
  return {ok: false, error: resolved.error || "no_element_at_point"};
}
const identity = elementIdentity(el);
if (!matchesExpected(identity, expected)) {
  return {ok: false, error: "target_identity_mismatch", target: identity};
}
if (!("value" in el)) {
  return {ok: false, error: "element_has_no_value"};
}
el.focus();
el.value = value;
el.dispatchEvent(new Event("input", {bubbles: true}));
el.dispatchEvent(new Event("change", {bubbles: true}));
return {
  ok: true,
  target: identity
};

function elementIdentity(node) {
  const tag = node.tagName ? node.tagName.toLowerCase() : null;
  const explicitRole = node.getAttribute ? node.getAttribute("role") : null;
  const role = explicitRole || (
    tag === "button" ? "button" :
    tag === "a" ? "link" :
    tag === "select" ? "combobox" :
    tag === "textarea" ? "textbox" :
    tag === "input" ? "textbox" :
    null
  );
  const text = (node.innerText || node.textContent || "").replace(/\s+/g, " ").trim().slice(0, 200);
  const name = (
    (node.getAttribute && (node.getAttribute("aria-label") || node.getAttribute("title") || node.getAttribute("placeholder"))) ||
    text ||
    ""
  ).replace(/\s+/g, " ").trim().slice(0, 200);
  return {tag, id: node.id || null, role, name, text};
}

function matchesExpected(actual, expected) {
  if (expected.id && actual.id !== expected.id) return false;
  if (expected.tag && actual.tag !== expected.tag) return false;
  if (expected.role && actual.role && actual.role !== expected.role) return false;
  const expectedName = (expected.name || expected.text || "").trim();
  if (expectedName) {
    const actualText = ((actual.name || "") + " " + (actual.text || "")).trim();
    if (!actualText.includes(expectedName)) return false;
  }
  return true;
}
""" + DEEP_POINT_HELPERS_JS

SELECT_AT_POINT_JS = r"""
const x = arguments[0];
const y = arguments[1];
const value = arguments[2];
const expected = arguments[3] || {};
const resolved = resolveElementFromTopPoint(x, y);
const el = resolved.element;
if (!el) {
  return {ok: false, error: resolved.error || "no_element_at_point"};
}
const identity = elementIdentity(el);
if (!matchesExpected(identity, expected)) {
  return {ok: false, error: "target_identity_mismatch", target: identity};
}
if (el.tagName.toLowerCase() !== "select") {
  return {ok: false, error: "element_is_not_select"};
}
el.value = value;
el.dispatchEvent(new Event("input", {bubbles: true}));
el.dispatchEvent(new Event("change", {bubbles: true}));
return {
  ok: true,
  target: {
    tag: "select",
    id: el.id || null,
    value: el.value
  }
};

function elementIdentity(node) {
  const tag = node.tagName ? node.tagName.toLowerCase() : null;
  const explicitRole = node.getAttribute ? node.getAttribute("role") : null;
  const role = explicitRole || (
    tag === "button" ? "button" :
    tag === "a" ? "link" :
    tag === "select" ? "combobox" :
    tag === "textarea" ? "textbox" :
    tag === "input" ? "textbox" :
    null
  );
  const text = (node.innerText || node.textContent || "").replace(/\s+/g, " ").trim().slice(0, 200);
  const name = (
    (node.getAttribute && (node.getAttribute("aria-label") || node.getAttribute("title") || node.getAttribute("placeholder"))) ||
    text ||
    ""
  ).replace(/\s+/g, " ").trim().slice(0, 200);
  return {tag, id: node.id || null, role, name, text};
}

function matchesExpected(actual, expected) {
  if (expected.id && actual.id !== expected.id) return false;
  if (expected.tag && actual.tag !== expected.tag) return false;
  if (expected.role && actual.role && actual.role !== expected.role) return false;
  const expectedName = (expected.name || expected.text || "").trim();
  if (expectedName) {
    const actualText = ((actual.name || "") + " " + (actual.text || "")).trim();
    if (!actualText.includes(expectedName)) return false;
  }
  return true;
}
""" + DEEP_POINT_HELPERS_JS


@dataclass(frozen=True)
class ActionExecutionResult:
    """Result of executing an allowed browser action."""

    attempted: bool
    ok: bool
    action_type: str
    target_ref: str | None = None
    reason: str | None = None
    adapter_result: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "attempted": self.attempted,
            "ok": self.ok,
            "action_type": self.action_type,
            "target_ref": self.target_ref,
            "reason": self.reason,
            "adapter_result": self.adapter_result,
        }


def execute_browser_action(
    driver: Any,
    proposal: ActionProposal,
    snapshot: Mapping[str, Any],
) -> ActionExecutionResult:
    """Execute an already gate-approved browser action."""

    action = proposal.proposed_action

    if action.type == "stop":
        return ActionExecutionResult(
            attempted=False,
            ok=True,
            action_type=action.type,
            target_ref=action.target_ref,
            reason="stop requested",
        )

    if action.type == "wait":
        seconds = _wait_seconds(action.value)
        time.sleep(seconds)
        return ActionExecutionResult(
            attempted=True,
            ok=True,
            action_type=action.type,
            reason=f"waited {seconds:.3f}s",
        )

    if action.type == "navigate":
        destination = str(action.value or "")
        driver.get(destination)
        return ActionExecutionResult(
            attempted=True,
            ok=True,
            action_type=action.type,
            reason="navigated",
            adapter_result={"url": destination},
        )

    target = _find_target(snapshot, action.target_ref)
    if target is None:
        return ActionExecutionResult(
            attempted=False,
            ok=False,
            action_type=action.type,
            target_ref=action.target_ref,
            reason="target_ref not found in snapshot",
        )

    x, y = _bbox_center(target.get("bbox"))
    expected_identity = _expected_identity(target)
    if action.type == "click":
        adapter_result = driver.execute_script(CLICK_AT_POINT_JS, x, y, expected_identity)
    elif action.type == "type":
        adapter_result = driver.execute_script(
            TYPE_AT_POINT_JS, x, y, action.value or "", expected_identity
        )
    elif action.type == "select":
        adapter_result = driver.execute_script(
            SELECT_AT_POINT_JS, x, y, action.value or "", expected_identity
        )
    else:
        return ActionExecutionResult(
            attempted=False,
            ok=False,
            action_type=action.type,
            target_ref=action.target_ref,
            reason="unsupported action type",
        )

    if not isinstance(adapter_result, Mapping):
        adapter_result = {"ok": False, "error": "adapter_returned_non_object"}

    return ActionExecutionResult(
        attempted=True,
        ok=bool(adapter_result.get("ok")),
        action_type=action.type,
        target_ref=action.target_ref,
        reason=None if adapter_result.get("ok") else str(adapter_result.get("error")),
        adapter_result=dict(adapter_result),
    )


def _wait_seconds(value: Any) -> float:
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        seconds = 0.25
    return max(0.0, min(seconds, 5.0))


def _find_target(snapshot: Mapping[str, Any], target_ref: str | None) -> Mapping[str, Any] | None:
    if target_ref is None:
        return None
    for element in snapshot.get("elements", ()) or ():
        if isinstance(element, Mapping) and element.get("ref") == target_ref:
            return element
    return None


def _bbox_center(bbox: Any) -> tuple[float, float]:
    if not isinstance(bbox, list) or len(bbox) != 4:
        raise ValueError("target bbox must be [x1, y1, x2, y2]")
    x1, y1, x2, y2 = [float(value) for value in bbox]
    return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)


def _expected_identity(target: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": target.get("id"),
        "tag": target.get("tag"),
        "role": target.get("role"),
        "name": target.get("name"),
        "text": target.get("text"),
    }
