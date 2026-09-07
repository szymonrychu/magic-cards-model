"""T10: every scenario proves it round-trips and replays, without opting in.

`harness.checkpoint` (see its own docstring) is the seam every path that
starts a scenario's `Game` crosses. This hook is what turns that seam into an
assertion: it runs each test function under `tests/scenarios/` once for
real, and - only if that run built at least one `Game` - a second time with
`checkpoint` swapping in a decode of the first run's own initial snapshot at
each of the same calls. Two literal runs of the same test body is "a replay
of the scenario's own commands": nothing about what the test does is
recorded or reinterpreted, because the test function itself already is that
command sequence, and `ids.py`'s per-`game_uid` deterministic id allocator is
what makes the second run mint the same ids the first run did, provided it
starts from a decode of the exact same game.

A file that builds no `Game` at all - `test_registry_is_minimal.py`, `test_
deck_construction.py`, the judge layer-only test - checkpoints nothing, so
this hook has nothing to check and gets out of the way after the first (and
only) run, at the cost of one `if not games: return True`.

`MTG_SCENARIO_REPLAY=0` disables the second (replay) run and keeps the
round-trip check on its own - see `docs/scenario-tests.md` for when that
trade is worth making; the full suite's own numbers are recorded in
`MEMORY.md`.
"""

from __future__ import annotations

import inspect
import os
from typing import Any

import pytest

from magic_cards_model.models.game import Game
from tests.scenarios import harness

REPLAY = os.environ.get("MTG_SCENARIO_REPLAY", "1") != "0"


def _assert_round_trips(game: Game, dumped: dict[str, Any]) -> None:
    """CR-agnostic: `dumped` (already taken) must decode and re-dump to
    itself, byte for byte - `test_ability_on_stack_round_trip.py`'s and
    `test_delayed_trigger_round_trip.py`'s own manual pattern, run for every
    scenario instead of the handful that opted in by hand."""
    decoded = Game.model_validate(dumped)
    redumped = decoded.model_dump(mode="json")
    diff = harness.diff_json(dumped, redumped)
    assert diff is None, f"game {game.game_uid} does not round-trip: {diff}"


@pytest.hookimpl(tryfirst=True)
def pytest_pyfunc_call(pyfuncitem: pytest.Function) -> bool | None:
    testfunction = pyfuncitem.obj
    if inspect.iscoroutinefunction(testfunction):
        return None  # not this suite's shape; let pytest's own impl run it.

    funcargs = pyfuncitem.funcargs
    argnames = pyfuncitem._fixtureinfo.argnames
    testargs = {name: funcargs[name] for name in argnames}

    harness.begin_recording()
    try:
        testfunction(**testargs)
    finally:
        games, initial_dumps = harness.end_recording()

    if not games:
        return True  # this test never checkpointed a Game - nothing to judge.

    final_dumps = [game.model_dump(mode="json") for game in games]
    for game, dumped in zip(games, final_dumps, strict=True):
        _assert_round_trips(game, dumped)

    if not REPLAY:
        return True

    if pyfuncitem.get_closest_marker("no_replay") is not None:
        # The test asserts something about CPython object identity, which a
        # decode cannot reproduce and which is not game state. It still gets
        # the round-trip assertion above; only the replay half is skipped, so
        # the live-run assertion it exists for keeps running.
        return True

    harness.begin_replaying(initial_dumps)
    try:
        testfunction(**testargs)
    except Exception as exc:
        raise AssertionError(
            "replaying this scenario's own commands from its decoded initial "
            f"snapshot raised where the first run did not: {exc!r}"
        ) from exc
    finally:
        replayed_games = harness.end_replaying()

    assert len(replayed_games) == len(games), (
        f"the replay checkpointed {len(replayed_games)} game(s), the first run "
        f"checkpointed {len(games)} - not deterministic enough for this "
        "invariant to judge"
    )
    for index, (original_dump, replayed) in enumerate(
        zip(final_dumps, replayed_games, strict=True)
    ):
        replayed_dump = replayed.model_dump(mode="json")
        diff = harness.diff_json(original_dump, replayed_dump)
        assert diff is None, (
            f"game #{index} replayed from its own decoded initial snapshot is "
            f"not byte-identical to the first run's own final game: {diff}"
        )

    return True


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "no_replay: skip this scenario's replay run, keeping its round-trip check. "
        "Only for assertions about CPython object identity, which a decode of "
        "value-equal models cannot reproduce and which is not game state.",
    )
