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

To exercise the safe action, unsafe refusal, and approval-proceed paths in one run:

```powershell
python scripts/hog_selenium_smoke.py --scenario all --geckodriver /snap/bin/geckodriver --output-dir runtime/hog_selenium_smoke
```

If geckodriver is not discoverable, pass it explicitly:

```powershell
python scripts/hog_selenium_smoke.py --geckodriver /path/to/geckodriver --output-dir runtime/hog_selenium_smoke
```

The runner writes `before.png`, `after.png`, and `hog_trace_selenium_smoke.jsonl`. It does not enable `file://` access in the policy gate. A passing run means the fixture was observed, the Arm button proposal passed the deterministic URL allowlist gate, Selenium acted through the browser adapter, the page changed to `ARMED`, and the deterministic verifier passed.

The integration test skips when Selenium, Firefox, or geckodriver are unavailable; the real evidence artifact is the runner output from an environment with those tools installed.

On snap-based Firefox installs, do not pass `/usr/bin/firefox` as `--firefox-binary`; that path may be a wrapper and geckodriver can reject it as not being a Firefox executable. In that case, pass only `--geckodriver` and let geckodriver locate Firefox.

## Current Proof

The Selenium smoke has passed once on a real Firefox/geckodriver environment at repo commit `b75f75f`.

Sanitized result:

- Fixture served from a temporary `http://127.0.0.1:<port>/index.html` URL.
- Policy gate used the loopback URL allowlist; `file://` access was not enabled.
- Gate allowed the safe button: no sensitive field, no form submit, no cross-origin target, no approval keyword, and target was visible/clickable.
- Executor clicked the identity-checked `arm-button` element through Selenium.
- Deterministic verifier passed: armed state present and safe state absent.
- Trace event sequence: `policy_gate`, `action_execution`, `step_result`.

Boundary: this proves the happy path for a safe browser action. Unsafe-target refusal and approve-then-proceed are separate live gates; they are not claimed by this proof.

The next proof target is `--scenario all`, which must show:

- `safe`: the harmless button is allowed and verified.
- `unsafe-refusal`: the submit control is refused before execution.
- `approval-proceed`: the same submit control proceeds only when the gate config carries an external approval for the current target ref.
