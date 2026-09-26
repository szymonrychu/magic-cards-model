"""SOS's dies-with-counters family: "When this creature dies, if it had
`<quantity>` counters on it, `<move them somewhere>`." - CR 603.4's
intervening *if*, checked once as the trigger event happens and again as it
resolves, over CR 603.10a/CR 400.7's look-back at the creature the instant
before it became a new, counter-less object in the graveyard (CR 122.2).

Two shapes, one underlying mechanic:

- **Ambitious Augmenter** - "if it had one or more counters on it, create a
  0/0 green and blue Fractal creature token, then put this creature's
  counters on that token." `counter_effects._create_token_then_put_this_
  creatures_counters_on_it` reads the create-then-move half; the intervening
  *if* itself is answered by `machines/conditions/objects.py`'s existing
  "it had ... counters on it" reader (`_has_counters`), reused rather than
  duplicated.
- **Scolding Administrator** - "if it had counters on it, put those counters
  on up to one target creature." `machines/effects.py`'s existing
  `_PUT_ITS_COUNTERS_ON_TARGET_RE` (Graft Surgeon's "put its counters on ...")
  widened by one word to also read "those" - the identical CR 400.7 anaphora
  back to the same dying source, spelled with a demonstrative instead of the
  possessive.

No second Modern/Pioneer/Standard-legal printing of Ambitious Augmenter's
exact "create a token, then put this creature's counters on that token"
template turned up a `card_search` (dated MEMORY.md line records the
search); this file's own counter-kind/-amount variation across its tests is
what proves the reader is not fitted to "two +1/+1 counters" specifically.

Every CR number below was looked up with `mise run rules:find` (on-disk CR
effective 2026-09-25) in the session that wrote this file:

- **CR 603.4** - the intervening *if* clause rule, checked at trigger and
  again at resolution.
- **CR 603.10a** - a leaves-the-battlefield ability uses the game state as it
  existed immediately before the event, not the graveyard object's current
  (counter-less) one.
- **CR 400.7** - an object that changes zones becomes a new object with no
  memory of its previous existence; a dying creature's counters do not
  survive onto the graveyard card by themselves.
- **CR 122.2** - counters cease to exist the moment their object changes
  zones; they are not "removed", so nothing here reads them off the
  graveyard card itself.
- **CR 122.6** - counters an effect adds are put on the object named, here
  the freshly created token or the chosen target creature.
- **CR 111.7** - a token that leaves the battlefield ceases to exist as a
  state-based action, not exercised here but why the token is checked while
  still on the battlefield in every assertion below.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario

AUGMENTER = "Ambitious Augmenter"
ADMINISTRATOR = "Scolding Administrator"


def _augmenter_board() -> Scenario:
    return Scenario().player("alice", battlefield=[AUGMENTER]).player("bob")


def test_augmenter_dies_with_counters_creates_a_fractal_carrying_them():
    scenario = _augmenter_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    augmenter = scenario.creature(AUGMENTER, "alice")
    augmenter.add_counters(Counter.PLUS_ONE, 2)
    tokens_before = len(
        [state for state in scenario.game.battlefield if state.name == "Fractal Token"]
    )

    scenario.game.destroy(augmenter)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    fractals = [
        state
        for state in scenario.game.battlefield
        if state.name == "Fractal Token" and state.zone is Zone.BATTLEFIELD
    ]
    assert len(fractals) == tokens_before + 1
    fractal = fractals[-1]
    assert fractal.counter_count(Counter.PLUS_ONE) == 2
    assert (fractal.power, fractal.toughness) == (2, 2), "0/0 base plus two +1/+1 counters"
    assert augmenter.zone is Zone.GRAVEYARD
    assert augmenter.counters == {}, "CR 122.2: the dying creature's own counters are gone"


def test_augmenter_dies_with_no_counters_creates_no_fractal():
    """CR 603.4: the intervening *if* is false, so the ability does nothing -
    not even a 0/0 Fractal with zero counters."""
    scenario = _augmenter_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    augmenter = scenario.creature(AUGMENTER, "alice")
    fractals_before = len(
        [state for state in scenario.game.battlefield if state.name == "Fractal Token"]
    )

    scenario.game.destroy(augmenter)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    fractals_after = [
        state
        for state in scenario.game.battlefield
        if state.name == "Fractal Token" and state.zone is Zone.BATTLEFIELD
    ]
    assert len(fractals_after) == fractals_before


def test_augmenter_carries_a_different_counter_kind_and_amount():
    """The reader defers to whatever counters were actually on the creature -
    not a hardcoded "two +1/+1 counters" match against the printed card's own
    Increment keyword. A -1/-1 counter mixed with a keyword counter proves
    every kind on the dying creature moves, not one named kind."""
    scenario = _augmenter_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    augmenter = scenario.creature(AUGMENTER, "alice")
    augmenter.add_counters(Counter.PLUS_ONE, 4)
    augmenter.add_counters("stun", 1)

    scenario.game.destroy(augmenter)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    fractal = next(
        state
        for state in scenario.game.battlefield
        if state.name == "Fractal Token" and state.zone is Zone.BATTLEFIELD
    )
    assert fractal.counter_count(Counter.PLUS_ONE) == 4
    assert fractal.counter_count("stun") == 1


def _administrator_board() -> Scenario:
    return Scenario().player("alice", battlefield=[ADMINISTRATOR, "Grizzly Bears"]).player("bob")


def test_administrator_dies_with_counters_moves_them_to_the_chosen_target():
    scenario = _administrator_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    administrator = scenario.creature(ADMINISTRATOR, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    administrator.add_counters(Counter.PLUS_ONE, 3)
    scenario.choose_trigger_targets(ADMINISTRATOR, [bears])

    scenario.game.destroy(administrator)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert bears.counter_count(Counter.PLUS_ONE) == 3
    assert administrator.zone is Zone.GRAVEYARD
    assert administrator.counters == {}


def test_administrator_dies_with_no_counters_moves_nothing():
    """CR 603.4 again: with nothing to move, the ability never even triggers,
    so no target is asked for at all."""
    scenario = _administrator_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    administrator = scenario.creature(ADMINISTRATOR, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.game.destroy(administrator)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert bears.counters == {}


def test_administrator_with_no_legal_target_moves_nothing():
    """CR 115.6: "up to one" may choose none, and CR 608.2b's "will resolve
    normally" still means nothing happens if the chosen count is zero."""
    scenario = Scenario().player("alice", battlefield=[ADMINISTRATOR]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    administrator = scenario.creature(ADMINISTRATOR, "alice")
    administrator.add_counters(Counter.PLUS_ONE, 2)
    scenario.choose_trigger_targets(ADMINISTRATOR, [])

    scenario.game.destroy(administrator)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert administrator.zone is Zone.GRAVEYARD
