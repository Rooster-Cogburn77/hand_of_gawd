# hand_of_gawd

`hand_of_gawd` is a local-first, safety-gated automation harness for browser and desktop UI work.

The core idea is simple: an agent does not get to directly act. It proposes an action, a deterministic policy gate evaluates that proposal against the current UI state, an executor performs only approved low-risk actions, and a verifier checks the result before the loop proceeds.

## Current Scope

This repository currently contains the Goal 1 browser substrate:

- Compact Selenium-compatible browser snapshots.
- Deterministic action proposal contracts.
- Policy gates that do not trust the planner's self-reported risk.
- Browser DOM/WebDriver-level execution with target identity re-checks.
- Deterministic result verification.
- JSONL trace recording with redaction enabled by default.
- A public synthetic Selenium smoke that exercises the Goal 1 loop end to end.

This is not yet a production browser agent, not a password manager, and not an unrestricted desktop controller. Native desktop automation, OS pointer control, planner integration, credential handling, and approval UX are separate future gates.

## Safety Model

The first-class object is an action proposal, not an action.

Each step is intended to follow this shape:

1. Observe the UI.
2. Propose one action.
3. Gate the proposal with deterministic rules.
4. Execute only if approved.
5. Observe again.
6. Verify the expected result.
7. Record a trace.

The planner's `risk_class` is treated as advisory metadata only. The policy gate computes its own decision from URL allowlists, action type, target identity, form metadata, cross-origin navigation, sensitive fields, and approval-required keywords.

## Public Status

This is an early public scaffold. The API may change while the harness is being shaped.

License has not been selected yet.

## Selenium Smoke

The public smoke fixture lives at `examples/safe_toggle/index.html`.

It starts a temporary `http://127.0.0.1` fixture server and exercises the browser loop against a local synthetic page:

```powershell
python scripts/hog_selenium_smoke.py --output-dir runtime/hog_selenium_smoke
```

If Firefox or geckodriver are not discoverable, pass them explicitly:

```powershell
python scripts/hog_selenium_smoke.py --firefox-binary /usr/bin/firefox --geckodriver /snap/bin/geckodriver --output-dir runtime/hog_selenium_smoke
```

The runner writes `before.png`, `after.png`, and `hog_trace_selenium_smoke.jsonl`. It does not enable `file://` access in the policy gate. A passing run means the fixture was observed, the Arm button proposal passed the deterministic URL allowlist gate, Selenium acted through the browser adapter, the page changed to `ARMED`, and the deterministic verifier passed.

The integration test skips when Selenium, Firefox, or geckodriver are unavailable; the real evidence artifact is the runner output from an environment with those tools installed.
