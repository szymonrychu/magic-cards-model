"""Scenario: "When you cast this spell, target opponent reveals their hand.
You choose from it a nonland card with mana value 3 or less and a card with
mana value 4 or greater. That player discards those cards." - Distended
Mindbender.

The same reveal-and-choose shape Thoughtseize/Grief/Thought-Knot Seer already
use (`_merge_reveal_hand_choose_discard_clauses`), but with *two* independent
picks instead of one shared bound - one card at mana value 3 or less, a
second at mana value 4 or greater, each asked for separately and skipped when
no card in the revealed hand satisfies it.

Every CR number below was looked up with `mise run rules:find` in the session
that wrote this file.

- **CR 117.2a / 603.3** - the trigger resolves above its own spell.
- **CR 701.20a** - to reveal a card is to show it to all players.
- **CR 701.9a / 701.9b** - to discard is to move from hand to graveyard;
  "you choose" is an explicit override of the default (the affected player's
  own choice).
- **CR 202.3** - mana value, a printed characteristic, checked against each
  bound.
- **CR 608.2d** - a choice among a player's own qualifying objects with none
  available is an impossible option: skipped, not asked.

The effect is `_parse_reveal_hand_choose_two_bounded_cards_then_discard_clause`
in `machines/effects.py`, tried by `_ability_effect_or_notice`.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

MOUNTAINS_FOR_MINDBENDER = ["Wastes"] * 8


def _mindbender_board(bob_hand: list[str]) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=["Distended Mindbender"],
            battlefield=list(MOUNTAINS_FOR_MINDBENDER),
        )
        .player("bob", hand=list(bob_hand), library=["Mountain"] * 5)
    )


def test_the_cast_trigger_sits_above_its_own_spell_on_the_stack():
    scenario = _mindbender_board(["Grizzly Bears", "Colossal Dreadmaw"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.choose_trigger_targets("Distended Mindbender", [scenario.player("bob")])
    sources = scenario.untapped_sources(*MOUNTAINS_FOR_MINDBENDER)

    scenario.cast_onto_stack("Distended Mindbender", *sources)

    assert scenario.stack_names() == [
        "Distended Mindbender",
        "Distended Mindbender's triggered ability",
    ]


def test_discards_one_cheap_nonland_card_and_one_expensive_card():
    """Grizzly Bears (mana value 2) is the cheap nonland pick, Colossal
    Dreadmaw (mana value 6) the expensive one - both leave bob's hand."""
    scenario = _mindbender_board(["Grizzly Bears", "Colossal Dreadmaw", "Forest"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.choose_trigger_targets("Distended Mindbender", [scenario.player("bob")])
    sources = scenario.untapped_sources(*MOUNTAINS_FOR_MINDBENDER)

    scenario.cast_onto_stack("Distended Mindbender", *sources)
    scenario.pass_until_resolved()  # the trigger only

    graveyard_names = [state.name for state in scenario.player("bob").graveyard]
    assert set(graveyard_names) == {"Grizzly Bears", "Colossal Dreadmaw"}
    remaining = [state.name for state in scenario.player("bob").hand]
    assert remaining == ["Forest"]


def test_a_land_does_not_satisfy_the_nonland_bracket():
    """Forest (mana value 0) would satisfy "mana value 3 or less" on its
    own, but the printed "nonland" excludes it - only Colossal Dreadmaw is
    discarded, and the impossible nonland pick is simply skipped."""
    scenario = _mindbender_board(["Forest", "Colossal Dreadmaw"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.choose_trigger_targets("Distended Mindbender", [scenario.player("bob")])
    sources = scenario.untapped_sources(*MOUNTAINS_FOR_MINDBENDER)

    scenario.cast_onto_stack("Distended Mindbender", *sources)
    scenario.pass_until_resolved()

    graveyard_names = [state.name for state in scenario.player("bob").graveyard]
    assert graveyard_names == ["Colossal Dreadmaw"]
    remaining = [state.name for state in scenario.player("bob").hand]
    assert remaining == ["Forest"]


def test_no_qualifying_expensive_card_discards_only_the_cheap_one():
    """A hand with nothing at mana value 4 or greater leaves that bracket an
    impossible option (CR 608.2d) - the cheap pick still happens."""
    scenario = _mindbender_board(["Grizzly Bears", "Forest"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.choose_trigger_targets("Distended Mindbender", [scenario.player("bob")])
    sources = scenario.untapped_sources(*MOUNTAINS_FOR_MINDBENDER)

    scenario.cast_onto_stack("Distended Mindbender", *sources)
    scenario.pass_until_resolved()

    graveyard_names = [state.name for state in scenario.player("bob").graveyard]
    assert graveyard_names == ["Grizzly Bears"]


def test_an_empty_hand_discards_nothing_and_the_spell_still_resolves():
    scenario = _mindbender_board([]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.choose_trigger_targets("Distended Mindbender", [scenario.player("bob")])
    sources = scenario.untapped_sources(*MOUNTAINS_FOR_MINDBENDER)

    scenario.cast_onto_stack("Distended Mindbender", *sources)
    scenario.pass_until_resolved()  # the trigger
    scenario.pass_until_resolved()  # Distended Mindbender itself

    assert scenario.player("bob").graveyard == []
    assert "Distended Mindbender" in scenario.battlefield_names()


def test_two_qualifying_cheap_cards_let_the_caster_choose_which_one():
    """CR 701.9b's override hands the choice to the resolving spell's
    controller (alice), not the revealed player (bob) - `will_choose_cards`
    stages alice's answer the same way it stages any other CHOOSE_CARDS
    question asked of a non-default chooser."""
    scenario = _mindbender_board(["Grizzly Bears", "Watchwolf", "Colossal Dreadmaw"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.choose_trigger_targets("Distended Mindbender", [scenario.player("bob")])
    sources = scenario.untapped_sources(*MOUNTAINS_FOR_MINDBENDER)

    watchwolf = scenario.find("Watchwolf", Zone.HAND, "bob")
    scenario.will_choose_cards(watchwolf, username="alice")

    scenario.cast_onto_stack("Distended Mindbender", *sources)
    scenario.pass_until_resolved()

    graveyard_names = {state.name for state in scenario.player("bob").graveyard}
    assert graveyard_names == {"Watchwolf", "Colossal Dreadmaw"}
    remaining = [state.name for state in scenario.player("bob").hand]
    assert remaining == ["Grizzly Bears"]
