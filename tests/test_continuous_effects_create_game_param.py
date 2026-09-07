"""Defect 4: `ContinuousEffects.create` can crash on a `game=None` call.

`ContinuousEffects.create` (`machines/layers.py`) grew a `game` parameter so
`effect.holds(game)` can check a `condition` (CR 611.2b's "for as long as").
`holds` raises `ValueError` when the built effect carries a condition and no
`game` was given to check it against - by design, per its own docstring
("a caller that forgot to plumb one through ... fails loudly rather than
guessing"). That guard is not the bug; it is working as intended.

The bug is that `machines/effects.py`'s two *generic* call sites -
`create_continuous_effect` and `create_continuous_effect_of_ability` - never
pass `game` at all, so either one crashes resolution outright the moment it
ever dispatches to a registry row that builds a conditioned effect.

`LAYER_EFFECTS["Tishana's Tidebinder"]` (`_tishanas_tidebinder`,
`machines/layers.py`) is the only row that does today, and the one call site
that actually resolves her (`_counter_tidebinder_target`) already passes
`game=game`, so this is unreachable through any real card in the pool right
now. It is reachable directly, though: nothing about `create_continuous_
effect` requires its `spell` argument to genuinely be resolving off the stack
- it only reads the `CardState`'s own `targets`, `card`, and controller - so
calling it with a real, battlefield Tishana's Tidebinder whose `targets`
already names a real creature reaches the exact same `LAYER_EFFECTS` row and
the exact same crash, with no fabricated `AbilityOnStack`/targeting machinery
that has nothing to do with this defect.
"""

from magic_cards_model.machines.effects import create_continuous_effect
from magic_cards_model.models.card_state import TargetRef
from tests.scenarios.harness import Scenario


def _tishana_targeting_the_bears():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Tishana's Tidebinder", "Grizzly Bears"])
        .player("bob")
        .build()
    )
    game = scenario.game
    tishana = next(state for state in game.battlefield if state.name == "Tishana's Tidebinder")
    bears = next(state for state in game.battlefield if state.name == "Grizzly Bears")
    tishana.targets = [TargetRef.to_card(bears)]
    return game, tishana, bears


def test_create_continuous_effect_keeps_a_conditioned_effect_instead_of_crashing():
    """Before the fix, this raised `ValueError` - `create_continuous_effect`
    called `ContinuousEffects.create` with no `game`, and `holds` refuses to
    guess whether a "for as long as" condition holds with none given. Quoted
    in the review report: `ValueError: "Tishana's Tidebinder: Grizzly Bears
    loses all abilities" has a "for as long as" condition but no game was
    given to check it against`.

    The fix passes `game=game` through, the same keyword `_counter_tidebinder_
    target` already uses, so the condition is checked instead of crashing and
    the effect is kept.
    """
    game, tishana, bears = _tishana_targeting_the_bears()

    create_continuous_effect(game, tishana)

    kept = game.continuous_effects.effects
    assert len(kept) == 1
    assert kept[0].condition is not None
    assert bears.name in kept[0].description
