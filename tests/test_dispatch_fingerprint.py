"""S1 of the engine-modularization plan: the dispatch-chain winner
fingerprint must stay byte-identical through the whole migration.

`scripts/dispatch_fingerprint.py` records, for every real printing in the
pool, which parser wins each of the four order-sensitive dispatch chains in
`machines/effects.py`. This test recomputes that fingerprint fresh and
compares it against the committed baseline
(`tests/dispatch_fingerprint_baseline.json`), failing with a per-entry diff
- which chain, which input, old winner vs. new winner - the moment a change
(a split in S2-S5, or an unrelated parser edit) picks a different parser for
an input that used to resolve differently.

Regenerate the baseline with `mise run dispatch:fingerprint` - the one
documented way, needed once this branch is merged behind the remaining
Reality Fracture branches and the pool has moved on.
"""

from __future__ import annotations

import json
import pathlib

from scripts.dispatch_fingerprint import BASELINE_PATH, compute_fingerprint


def _load_baseline() -> dict:
    return json.loads(BASELINE_PATH.read_text())


def _diff(baseline: dict, current: dict) -> list[str]:
    lines: list[str] = []
    entries = sorted(set(baseline) | set(current))
    for entry in entries:
        if entry not in baseline:
            lines.append(f"{entry}: new chain, not in the baseline")
            continue
        if entry not in current:
            lines.append(f"{entry}: chain removed, still in the baseline")
            continue
        base_chain = baseline[entry]["chain"]
        cur_chain = current[entry]["chain"]
        if base_chain != cur_chain:
            lines.append(
                f"{entry}: chain order changed:\n    was {base_chain}\n    now {cur_chain}"
            )
        base_results = baseline[entry]["results"]
        cur_results = current[entry]["results"]
        for variant in sorted(set(base_results) | set(cur_results)):
            base_winners = base_results.get(variant, {})
            cur_winners = cur_results.get(variant, {})
            for value in sorted(set(base_winners) | set(cur_winners)):
                before = base_winners.get(value, "<missing from baseline>")
                after = cur_winners.get(value, "<missing from current run>")
                if before != after:
                    lines.append(f"{entry}/{variant}: {value!r}: {before!r} -> {after!r}")
    return lines


def test_dispatch_fingerprint_matches_baseline():
    assert BASELINE_PATH.exists(), (
        f"{BASELINE_PATH} is missing - regenerate it with `mise run dispatch:fingerprint`"
    )
    baseline = _load_baseline()
    current = compute_fingerprint()
    diff = _diff(baseline, current)
    assert not diff, (
        "dispatch fingerprint drifted from the committed baseline "
        f"({BASELINE_PATH.relative_to(pathlib.Path(__file__).parent.parent)}); "
        "regenerate it with `mise run dispatch:fingerprint` only if the change is "
        "an intended reordering, then re-review:\n" + "\n".join(diff)
    )


def test_dispatch_fingerprint_is_deterministic():
    """Two computations in the same process produce byte-identical JSON -
    the guarantee the baseline comparison above depends on."""
    first = json.dumps(compute_fingerprint(), sort_keys=True)
    second = json.dumps(compute_fingerprint(), sort_keys=True)
    assert first == second
