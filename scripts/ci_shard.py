"""Split the test files into balanced CI shards.

    python scripts/ci_shard.py INDEX COUNT        print shard INDEX's files (0-based)
    python scripts/ci_shard.py --check COUNT      assert the shards partition every test file
    python scripts/ci_shard.py --weights JUNIT... rewrite tests/ci_weights.json from junit XMLs

Every `tests/**/test_*.py` except the behavioural sweep (its own task) is assigned to
exactly one shard by greedy longest-first bin packing on `tests/ci_weights.json`
(file -> estimated cpu seconds). A file missing from the weights gets DEFAULT_WEIGHT, so
a new test file lands in some shard without anyone editing the weights; refresh them with
`--weights` after a measured run. Sharding is by file, never by test, so each shard only
collects its own files (collection of the whole tree alone takes minutes).
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parent.parent
WEIGHTS = ROOT / "tests" / "ci_weights.json"
EXCLUDED = {"tests/test_behavioural_sweep.py"}
DEFAULT_WEIGHT = 30.0


def test_files() -> list[str]:
    files = (p.relative_to(ROOT).as_posix() for p in (ROOT / "tests").rglob("test_*.py"))
    return sorted(f for f in files if f not in EXCLUDED)


def shards(count: int) -> list[list[str]]:
    weights = json.loads(WEIGHTS.read_text()) if WEIGHTS.exists() else {}
    files = sorted(test_files(), key=lambda f: (-weights.get(f, DEFAULT_WEIGHT), f))
    bins: list[list[str]] = [[] for _ in range(count)]
    load = [0.0] * count
    for f in files:
        i = min(range(count), key=lambda k: (load[k], k))
        bins[i].append(f)
        load[i] += weights.get(f, DEFAULT_WEIGHT)
    return bins


def update_weights(junits: list[str]) -> None:
    secs: dict[str, float] = defaultdict(float)
    for junit in junits:
        for case in ElementTree.parse(junit).iter("testcase"):
            module = case.get("classname", "").split(".")
            # classname is dotted module (plus optional Class); find the file on disk
            for cut in range(len(module), 0, -1):
                rel = "/".join(module[:cut]) + ".py"
                if (ROOT / rel).exists():
                    secs[rel] += float(case.get("time", 0))
                    break
    rounded = {k: round(v, 1) for k, v in sorted(secs.items())}
    WEIGHTS.write_text(json.dumps(rounded, indent=1) + "\n")


def main(argv: list[str]) -> int:
    if argv[:1] == ["--weights"]:
        update_weights(argv[1:])
        return 0
    if argv[:1] == ["--check"]:
        bins = shards(int(argv[1]))
        flat = [f for b in bins for f in b]
        covered = sorted(flat) == test_files() and len(flat) == len(set(flat))
        assert covered, "shards do not partition"
        assert all(bins), "an empty shard"
        print(f"ok: {len(flat)} files in {len(bins)} shards")
        return 0
    index, count = int(argv[0]), int(argv[1])
    if not 0 <= index < count:
        print("INDEX must be in [0, COUNT)", file=sys.stderr)
        return 2
    print("\n".join(shards(count)[index]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
