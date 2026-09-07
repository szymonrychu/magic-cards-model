"""The flow solver's chosen plan must not depend on `PYTHONHASHSEED`.

`_best_flow_plan` (`machines/cost.py`) built `all_buckets` as
`sorted({...set of _Bucket tuples...}, key=lambda bucket: (bucket[2] ==
UNRESTRICTED, bucket[1]))`. `_Bucket`'s first element is a `Color`, a
`StrEnum`, so the set itself is string-hashed - and the sort key above ties
for every pair of unrestricted, non-snow buckets of different colours (both
get `(True, False)`), so a tie leaves the underlying set's own iteration
order showing through in the final list. That order is `PYTHONHASHSEED`-
dependent (Python randomises string hashing per process by default), and
`all_buckets`'s order feeds straight into `_demand_list`'s generic demand
(`models/mana.py`), which is what the max-flow BFS walks to decide which
tied source gets the flow - so *which land is tapped* varied by process.

This is not cosmetic: which land is tapped is persisted game state, and so
are the ids minted for any trigger that tapping causes (`ids.py`), so a game
replayed in a different process than the one that first played it could
diverge. `tests/test_game_determinism.py` cannot catch this because it only
ever replays within one process, so this test drives the solver as a real
subprocess (via `sys.executable`, the same venv `mise run test` uses) with
`PYTHONHASHSEED` pinned to several different values and asserts the chosen
plan is identical every time - not a mock, the real engine, just launched
more than once.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]

#: Confirmed empirically (see the defect-2 report) to disagree under the
#: pre-fix sort: seeds 0/3/27 picked Plains, seeds 1/2/4/17 picked Island,
#: for the exact board/cost below. Kept as a spread rather than just two
#: values so a fix that happens to agree on one pair by luck cannot pass.
_SEEDS = ["0", "1", "2", "3", "4", "17", "27", "42"]

#: Built and run once per subprocess. Plains and Island can each pay a
#: generic `{1}` and nothing else on the board favours one over the other -
#: the tie the broken sort let hash order settle. Printed as JSON on stdout
#: so the parent process can compare plans byte-for-byte across seeds.
_SCRIPT = """
import json

from magic_cards_model.machines import Step
from magic_cards_model.machines.cost import _solve_auto_tap, _SpendContext
from magic_cards_model.models.mana import ManaCost
from tests.scenarios.harness import Scenario

scenario = Scenario().player("alice", battlefield=["Plains", "Island"]).build()
scenario.start_at(Step.PRECOMBAT_MAIN)
sources = scenario.game.permanents_controlled_by("alice")
context = _SpendContext(game=scenario.game, payer="alice", spend=None)
plan = _solve_auto_tap(
    context,
    sources,
    owed=ManaCost.parse("{1}"),
    base_floating={},
    base_snow={},
    base_restricted=[],
    life_available=0,
)
result = (
    []
    if plan is None
    else [[source.name, [c.value for c in colors]] for source, colors, _restriction in plan]
)
print(json.dumps(result))
"""


def _run_with_hash_seed(seed: str) -> list:
    env = dict(os.environ)
    env["PYTHONHASHSEED"] = seed
    completed = subprocess.run(
        [sys.executable, "-c", _SCRIPT],
        cwd=_REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert completed.returncode == 0, (
        f"subprocess with PYTHONHASHSEED={seed} failed:\n"
        f"stdout={completed.stdout}\nstderr={completed.stderr}"
    )
    return json.loads(completed.stdout)


def test_flow_solver_plan_is_identical_across_process_hash_seeds():
    plans = {seed: _run_with_hash_seed(seed) for seed in _SEEDS}
    first_seed, first_plan = next(iter(plans.items()))
    disagreeing = {seed: plan for seed, plan in plans.items() if plan != first_plan}
    assert not disagreeing, (
        f"flow solver's chosen plan depends on PYTHONHASHSEED: seed {first_seed!r} "
        f"chose {first_plan!r}, but {disagreeing!r} chose something else"
    )
