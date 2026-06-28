"""Evaluate one hand_of_gawd proposal against one snapshot.

This is a small public-safe scaffold for Goal 1: it does not open a browser,
click, type, navigate, or call a model. It only runs the deterministic gate.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from hand_of_gawd.contracts import ActionProposal
from hand_of_gawd.policy import GateConfig, evaluate_policy_gate
from hand_of_gawd.trace import TraceRecorder


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--proposal", required=True)
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--allow-url-prefix", action="append", default=[])
    parser.add_argument("--allow-file-urls", action="store_true")
    parser.add_argument("--trace")
    args = parser.parse_args()

    proposal = ActionProposal.from_mapping(_load_json(args.proposal))
    snapshot = _load_json(args.snapshot)
    decision = evaluate_policy_gate(
        proposal,
        snapshot,
        GateConfig(
            allowed_url_prefixes=tuple(args.allow_url_prefix),
            allow_file_urls=args.allow_file_urls,
        ),
    )
    output = decision.to_dict()

    if args.trace:
        TraceRecorder(Path(args.trace)).record(
            "policy_gate",
            {
                "proposal": proposal.to_dict(),
                "snapshot_id": snapshot.get("snapshot_id"),
                "decision": output,
            },
        )

    print(json.dumps(output, indent=2, sort_keys=True))
    return 0 if decision.allowed else 2


def _load_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data


if __name__ == "__main__":
    raise SystemExit(main())

