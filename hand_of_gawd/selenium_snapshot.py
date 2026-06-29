"""Selenium-backed compact browser snapshot extraction.

This module does not import Selenium directly. Any object with Selenium-like
``execute_script`` and optional ``save_screenshot`` methods can be used.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, Mapping


SNAPSHOT_JS = r"""
const snapshotId = arguments[0];
const TOP_DOCUMENT = document;
const warnings = [];
const seenWarnings = new Set();

function addWarning(warning) {
  if (!seenWarnings.has(warning)) {
    warnings.push(warning);
    seenWarnings.add(warning);
  }
}

function textOf(node) {
  if (!node) return "";
  return (node.innerText || node.textContent || "").replace(/\s+/g, " ").trim();
}

function associatedLabel(el) {
  if (!el) return "";
  if (el.labels && el.labels.length) {
    return Array.from(el.labels).map(textOf).filter(Boolean).join(" ");
  }
  const parentLabel = el.closest ? el.closest("label") : null;
  return textOf(parentLabel);
}

function getById(context, id) {
  if (context.root && typeof context.root.getElementById === "function") {
    return context.root.getElementById(id);
  }
  return context.doc.getElementById(id);
}

function ariaName(el, context) {
  const direct = el.getAttribute("aria-label");
  if (direct) return direct.trim();
  const labelledBy = el.getAttribute("aria-labelledby");
  if (!labelledBy) return "";
  return labelledBy
    .split(/\s+/)
    .map((id) => getById(context, id))
    .map(textOf)
    .filter(Boolean)
    .join(" ");
}

function isVisible(el, rect, style) {
  return (
    rect.width > 0 &&
    rect.height > 0 &&
    style.visibility !== "hidden" &&
    style.display !== "none" &&
    Number(style.opacity || "1") > 0
  );
}

function fallbackElementFromPoint(root, x, y) {
  if (!root || typeof root.querySelectorAll !== "function") {
    return null;
  }
  const hits = Array.from(root.querySelectorAll("*")).filter((el) => {
    const rect = el.getBoundingClientRect();
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

function deepElementFromPoint(root, x, y) {
  let top = rootElementFromPoint(root, x, y);
  while (top && top.shadowRoot) {
    const shadowTop = rootElementFromPoint(top.shadowRoot, x, y);
    if (!shadowTop || shadowTop === top) break;
    top = shadowTop;
  }
  return top;
}

function topmostAtCenter(el, rect, context) {
  const localX = rect.left + rect.width / 2;
  const localY = rect.top + rect.height / 2;
  const topX = context.offsetX + localX;
  const topY = context.offsetY + localY;
  if (topX < 0 || topY < 0 || topX > window.innerWidth || topY > window.innerHeight) {
    return false;
  }
  if (context.frameElement) {
    const frameTop = TOP_DOCUMENT.elementFromPoint(topX, topY);
    if (frameTop !== context.frameElement && !(context.frameElement.contains(frameTop))) {
      return false;
    }
  }
  const top = deepElementFromPoint(context.root, localX, localY);
  return top === el || (top && el.contains(top));
}

function sensitiveAutocomplete(value) {
  const text = (value || "").toLowerCase();
  return (
    text.includes("cc-") ||
    text.includes("credit-card") ||
    text.includes("password") ||
    text.includes("one-time-code")
  );
}

function formInfo(el) {
  const form = el.form || (el.closest ? el.closest("form") : null);
  if (!form) return null;
  return {
    id: form.id || null,
    name: form.getAttribute("name") || null,
    action: form.action || null,
    method: (form.method || "get").toLowerCase()
  };
}

function isSubmitControl(el) {
  const tag = el.tagName.toLowerCase();
  const type = (el.getAttribute("type") || "").toLowerCase();
  if (tag === "button") {
    return Boolean(el.form || (el.closest && el.closest("form"))) && (type === "" || type === "submit");
  }
  if (tag === "input") {
    return type === "submit" || type === "image";
  }
  return false;
}

function safeValue(el) {
  const tag = el.tagName.toLowerCase();
  const type = (el.getAttribute("type") || "").toLowerCase();
  const autocomplete = el.getAttribute("autocomplete") || "";
  if (type === "password" || sensitiveAutocomplete(autocomplete)) {
    return null;
  }
  if (tag === "input" || tag === "textarea" || tag === "select") {
    return el.value;
  }
  return null;
}

const selectors = [
  "a",
  "button",
  "input",
  "textarea",
  "select",
  "label",
  "h1",
  "h2",
  "h3",
  "h4",
  "h5",
  "h6",
  "[role]",
  "[aria-label]",
  "[aria-labelledby]",
  "[onclick]",
  "[tabindex]"
].join(",");

function collectContexts() {
  const contexts = [];
  const seenRoots = new Set();

  function addContext({root, doc, kind, offsetX = 0, offsetY = 0, frameElement = null, frameId = null, shadowHostId = null}) {
    if (!root || seenRoots.has(root)) return;
    seenRoots.add(root);
    const context = {root, doc, kind, offsetX, offsetY, frameElement, frameId, shadowHostId};
    contexts.push(context);

    if (typeof root.querySelectorAll !== "function") return;

    for (const el of Array.from(root.querySelectorAll("*"))) {
      if (el.shadowRoot) {
        addContext({
          root: el.shadowRoot,
          doc,
          kind: "shadow",
          offsetX,
          offsetY,
          frameElement,
          frameId,
          shadowHostId: el.id || null
        });
      }
    }

    for (const iframe of Array.from(root.querySelectorAll("iframe"))) {
      let childDoc = null;
      try {
        childDoc = iframe.contentDocument;
      } catch (err) {
        addWarning("iframes_not_traversed");
      }
      if (!childDoc) {
        addWarning("iframes_not_traversed");
        continue;
      }
      const rect = iframe.getBoundingClientRect();
      addContext({
        root: childDoc,
        doc: childDoc,
        kind: "iframe",
        offsetX: offsetX + rect.left,
        offsetY: offsetY + rect.top,
        frameElement: iframe,
        frameId: iframe.id || null
      });
    }
  }

  addContext({root: document, doc: document, kind: "document"});
  return contexts;
}

const contexts = collectContexts();
const activeElement = document.activeElement;
let focusRef = null;
const elements = [];

for (const context of contexts) {
  const candidates = Array.from(new Set(Array.from(context.root.querySelectorAll(selectors))));
  for (const el of candidates) {
    const rect = el.getBoundingClientRect();
    const style = context.doc.defaultView.getComputedStyle(el);
    const visible = isVisible(el, rect, style);
    if (!visible && !el.matches("input,textarea,select,[role],[aria-label],[aria-labelledby]")) {
      continue;
    }

    const tag = el.tagName.toLowerCase();
    const type = el.getAttribute("type") || null;
    const role = el.getAttribute("role") || (
      tag === "button" ? "button" :
      tag === "a" ? "link" :
      tag === "select" ? "combobox" :
      tag === "textarea" ? "textbox" :
      tag === "input" ? (type === "checkbox" ? "checkbox" : type === "radio" ? "radio" : "textbox") :
      null
    );
    const name = ariaName(el, context) || associatedLabel(el) || el.getAttribute("title") || el.getAttribute("placeholder") || textOf(el);
    const disabled = Boolean(el.disabled || el.getAttribute("aria-disabled") === "true");
    const readonly = Boolean(el.readOnly || el.getAttribute("aria-readonly") === "true");
    const clickable = visible && !disabled && topmostAtCenter(el, rect, context) && (
      tag === "button" ||
      tag === "a" ||
      tag === "input" ||
      tag === "select" ||
      tag === "textarea" ||
      el.hasAttribute("onclick") ||
      el.getAttribute("role") === "button" ||
      el.getAttribute("role") === "link" ||
      (el.hasAttribute("tabindex") && Number(el.getAttribute("tabindex")) >= 0)
    );

    const ref = "e" + String(elements.length + 1);
    if (el === activeElement || el === context.root.activeElement) {
      focusRef = ref;
    }
    elements.push({
      ref,
      context: context.kind,
      frame_id: context.frameId,
      shadow_host_id: context.shadowHostId,
      id: el.id || null,
      tag,
      role,
      name,
      text: textOf(el),
      type,
      placeholder: el.getAttribute("placeholder") || null,
      autocomplete: el.getAttribute("autocomplete") || null,
      value: safeValue(el),
      checked: typeof el.checked === "boolean" ? el.checked : null,
      selected: typeof el.selected === "boolean" ? el.selected : null,
      is_submit: isSubmitControl(el),
      form: formInfo(el),
      enabled: !disabled,
      readonly,
      visible,
      clickable,
      href: el.href || null,
      bbox: [
        context.offsetX + rect.left,
        context.offsetY + rect.top,
        context.offsetX + rect.right,
        context.offsetY + rect.bottom
      ].map((n) => Math.round(n * 1000) / 1000)
    });
  }
}

const aggregateText = contexts
  .map((context) => textOf(context.root.body || context.root))
  .filter(Boolean)
  .join(" ")
  .replace(/\s+/g, " ")
  .trim()
  .slice(0, 4000);

return {
  snapshot_id: snapshotId,
  url: window.location.href,
  title: document.title || "",
  viewport: {width: window.innerWidth, height: window.innerHeight},
  focus: focusRef ? {ref: focusRef} : null,
  text: aggregateText,
  elements,
  warnings
};
"""


def capture_snapshot(
    driver: Any,
    *,
    snapshot_id: str | None = None,
    screenshot_path: str | Path | None = None,
) -> dict[str, Any]:
    """Capture a compact browser snapshot from a Selenium-like driver."""

    snapshot_id = snapshot_id or f"s-{uuid.uuid4().hex[:12]}"
    raw = driver.execute_script(SNAPSHOT_JS, snapshot_id)
    if not isinstance(raw, Mapping):
        raise ValueError("snapshot script did not return an object")

    snapshot = dict(raw)
    snapshot["snapshot_id"] = str(snapshot.get("snapshot_id") or snapshot_id)

    if screenshot_path is not None:
        path = Path(screenshot_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        saved = driver.save_screenshot(str(path))
        if not saved:
            raise RuntimeError(f"failed to save screenshot: {path}")
        snapshot["screenshot_path"] = str(path)

    _validate_snapshot(snapshot)
    return snapshot


def _validate_snapshot(snapshot: Mapping[str, Any]) -> None:
    required = ("snapshot_id", "url", "title", "viewport", "elements")
    missing = [key for key in required if key not in snapshot]
    if missing:
        raise ValueError(f"snapshot missing required key(s): {', '.join(missing)}")
    if not isinstance(snapshot["elements"], list):
        raise ValueError("snapshot elements must be a list")
