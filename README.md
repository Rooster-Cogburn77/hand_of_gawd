# hand_of_gawd

`hand_of_gawd` is a local-first, safety-gated automation harness for browser and desktop UI work.

**The core idea is simple: an agent does not get to directly act.** It proposes an action, a deterministic policy gate evaluates that proposal against the current UI state, an executor performs only approved low-risk actions, and a verifier checks the result before the loop proceeds.

## Current Scope

This repository currently contains the Goal 1 browser substrate:

- Compact Selenium-compatible browser snapshots.
- Deterministic action proposal contracts.
- Policy gates that do not trust the planner's self-reported risk.
- Browser DOM/WebDriver-level execution with target identity re-checks.
- Deterministic result verification.
- JSONL trace recording with redaction enabled by default.
- Local JSONL approval storage for exact stable action keys.
- A public synthetic Selenium smoke that exercises the Goal 1 loop end to end.

This is not yet a production browser agent, not a password manager, and not an unrestricted desktop controller. Native desktop automation, OS pointer control, planner integration, credential handling, persistent approval policy, and production approval UX are separate future gates.

## Safety Model

The first-class object is an action proposal, not an action.

Each step follows this shape:

1. Observe the UI.
2. Propose one action.
3. Gate the proposal with deterministic rules.
4. Execute only if approved.
5. Observe again.
6. Verify the expected result.
7. Record a trace.

The planner's `risk_class` is treated as advisory metadata only. The policy gate computes its own decision from URL allowlists, action type, target identity, form metadata, cross-origin navigation, sensitive fields, and approval-required keywords.

When the gate returns a liftable `approval_required`, an operator can approve one exact stable action key. That key is derived from action type, a hash of the proposed action value when present, current URL, and stable target identity. Approval does not bypass blocked checks such as stale snapshots, missing targets, disabled targets, non-clickable targets, or sensitive fields.

Local approval storage is append-only JSONL. Approved keys can be loaded back into the gate, but denials are recorded too, and the latest record for a key wins. A stored approval is an indefinite grant for that exact action key until a later denial record or store deletion revokes it. The store grants only exact key matches; it does not override the deterministic gate checks.

The approval store is a local trust anchor. Anyone who can write the store can add or revoke exact action-key approvals, so the store belongs in an operator-controlled local path, not a synced, shared, or world-writable location. Persisted approval records reuse trace-style redaction for visible labels, typed values, placeholders, and expected assertion values.

## Proof Status

**Live-proven** on a real Firefox/geckodriver environment (synthetic, browser-Linux; commits `88044a9`, `6cf8684`, and `9593b74`):

- `safe` - a harmless control is allowed, identity-checked, executed, and verified.
- `unsafe-refusal` - a form-submit target is refused before execution (`approval_required`, `operator_approved_action: false`, trace `policy_gate` -> `step_result`).
- `approval-proceed` - the same target proceeds only with `operator_approved_action: true` from an external stable action key, then verifies.
- `stale-state` - a proposal with stale `state_seen` is blocked before execution.
- `identity-mismatch` - a page shift between snapshot and execution is refused by the live identity re-check before clicking the impostor.
- `iframe-action` - same-origin iframe control: observe, gate, identity-check, click, verify.
- `shadow-action` - open-shadow-root control: observe, gate, identity-check, click, verify.
- `varied-snapshot` - same-origin iframe and open-shadow-root controls are traversed and included in the snapshot.
- `blocked-iframe-snapshot` - an opaque sandboxed iframe must report `iframes_not_traversed`, proving blocked subtrees are warned about instead of silently claimed.

Approval keys are `hog-approval-v1:<sha256>` values derived from action type, a hash of the proposed action value when present, current URL, and stable target identity - not ephemeral snapshot refs such as `e5`.

Boundary: the live-proven tier covers the synthetic browser-Linux safety loop only. Native desktop automation, OS pointer control, planner integration, credential handling, and production use remain separate future gates.

## Selenium Smoke

The public smoke fixture lives at `examples/safe_toggle/index.html`. It starts a temporary `http://127.0.0.1` fixture server and exercises the browser loop against local synthetic pages; it does not enable `file://` access in the policy gate.

Run the full set:

```bash
python scripts/hog_selenium_smoke.py --scenario all --geckodriver /snap/bin/geckodriver --output-dir runtime/hog_selenium_smoke
```

Use the human approval prompt for the approval-proceed path:

```bash
python scripts/hog_selenium_smoke.py --scenario approval-proceed --approval-mode prompt --geckodriver /snap/bin/geckodriver --output-dir runtime/hog_selenium_smoke_prompt
```

Persist approval records to a local JSONL store:

```bash
python scripts/hog_selenium_smoke.py --scenario approval-proceed --approval-mode prompt --approval-store runtime/hog_approvals.jsonl --geckodriver /snap/bin/geckodriver --output-dir runtime/hog_selenium_smoke_prompt
```

The prompt shows the gate reason, URL, goal, action type, stable target identity, expected deterministic result, and approval key. The operator must type `YES`; anything else leaves the action unapproved. Approval-proceed traces include `approval_request` and `approval_response` events before the final `policy_gate`, `action_execution`, and `step_result` events. When `--approval-store` is used, the runner also writes an `approval_record` event and appends the same record to the JSONL store. Trace redaction hides visible element labels and action value previews by default.

The runner writes `before.png`, `after.png`, and `hog_trace_selenium_<scenario>.jsonl`. The integration test skips when Selenium, Firefox, or geckodriver are unavailable; the real evidence artifact is the runner output from an environment with those tools installed.

On snap-based Firefox installs, do not pass `/usr/bin/firefox` as `--firefox-binary` - that path may be a wrapper geckodriver rejects as not a Firefox executable. Pass only `--geckodriver` and let geckodriver locate Firefox.

## Public Status

This is an early public scaffold. The API may change while the harness is being shaped.

Licensed under the MIT License.
