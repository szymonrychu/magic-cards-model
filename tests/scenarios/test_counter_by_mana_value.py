"""Scenario: a counterspell whose legal targets are bounded by mana value.

Two shapes, both a restriction on the *target* rather than on what the spell
does when it resolves, so both are settled at announcement (CR 601.2c: "the
player announces their choice of an appropriate object or player for each
target the spell requires") and rechecked on resolution (CR 608.2b).

- **Spell Snare** - "Counter target spell with mana value 2." A fixed number
  (CR 202.3: "the mana value of an object is a number equal to the total
  amount of mana in its mana cost, regardless of color").
- **Drown in the Loch** - "Counter target spell with mana value less than or
  equal to the number of cards in its controller's graveyard." The same
  restriction with the bound *computed* off the game state instead of printed:
  CR 404.1's discard pile, counted right now. It is knowable at CR 601.2c, so
  unlike Prismatic Ending's converge count (which is not fixed until CR 601.2h
  pays the cost, after targets are announced) it genuinely restricts what may
  be targeted.

Every CR number here was looked up with `knowledge_search(q="...",
type="rules")` in the session that wrote this file: CR 115.1 (targets are
declared as part of putting the spell on the stack), CR 601.2c, CR 601.2h,
CR 608.2b, CR 202.3, CR 404.1, CR 404.2, CR 108.4a.

**Not covered here, and not this file's gap:** neither Spell Snare nor Drown
in the Loch's counter mode has a spell *effect* - `effect_for("Spell Snare",
...)` is `None`, measured - so a legally targeted spell is not actually
removed from the stack. That is the counter-qualifier family in
`machines/effects.py` (plan task 1.13); the xfail at the bottom holds the
place for it.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone

from .harness import Scenario


def _snare_board(graveyard: list[str] | None = None) -> Scenario:
    """Bob is the active player casting creatures in his own main phase
    (CR 117.1a); alice holds the counterspells and answers at instant speed."""
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "bob",
            hand=["Grizzly Bears", "Hill Giant"],
            battlefield=["Forest", "Forest", "Forest", "Mountain"],
            graveyard=graveyard,
        )
        .player(
            "alice",
            hand=["Spell Snare", "Drown in the Loch"],
            battlefield=["Island", "Island", "Swamp"],
        )
    )


# -- Spell Snare: a printed number ------------------------------------------


def test_spell_snare_accepts_a_mana_value_2_spell():
    """CR 202.3: Grizzly Bears' {1}{G} is a mana value of exactly 2."""
    scenario = _snare_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    forests = scenario.untapped_sources("Forest", "Forest", username="bob")
    bears = scenario.cast_onto_stack("Grizzly Bears", *forests, username="bob")
    assert bears.zone is Zone.STACK
    scenario.pass_priority("bob")

    (island,) = scenario.untapped_sources("Island", username="alice")
    snare = scenario.cast_onto_stack("Spell Snare", island, username="alice", targets=[bears])

    assert snare.zone is Zone.STACK


def test_spell_snare_refuses_a_mana_value_3_spell_at_announcement():
    """Hill Giant is {3}{R}, mana value 4 - not 2, so CR 601.2c refuses it."""
    scenario = _snare_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    sources = scenario.untapped_sources("Forest", "Forest", "Forest", "Mountain", username="bob")
    giant = scenario.cast_onto_stack("Hill Giant", *sources, username="bob")
    scenario.pass_priority("bob")

    with pytest.raises(ValueError, match="mana value"):
        scenario.cast("Spell Snare", username="alice", targets=[giant])


# -- Drown in the Loch: a bound computed from the graveyard ------------------


def test_drown_in_the_loch_refuses_a_spell_the_graveyard_cannot_cover():
    """ "mana value less than or equal to the number of cards in its
    controller's graveyard" - bob's graveyard holds one card, so a mana value
    2 spell is out of reach and the announcement is refused (CR 601.2c).

    "Its controller" is the *target's* controller, not the caster's: CR 108.4a
    only redirects to the owner for a card with no controller at all, and a
    spell on the stack has one.
    """
    scenario = _snare_board(graveyard=["Lightning Bolt"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    assert len(scenario.player("bob").graveyard) == 1

    forests = scenario.untapped_sources("Forest", "Forest", username="bob")
    bears = scenario.cast_onto_stack("Grizzly Bears", *forests, username="bob")
    scenario.pass_priority("bob")

    casting = scenario.cast("Drown in the Loch", username="alice")
    casting.choose_modes([1])
    with pytest.raises(ValueError, match="mana value"):
        casting.choose_targets([bears])


def test_drown_in_the_loch_accepts_a_spell_the_graveyard_covers():
    """Two cards in bob's graveyard is exactly enough for a mana value 2 spell."""
    scenario = _snare_board(graveyard=["Lightning Bolt", "Grizzly Bears"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    assert len(scenario.player("bob").graveyard) == 2

    forests = scenario.untapped_sources("Forest", "Forest", username="bob")
    bears = scenario.cast_onto_stack("Grizzly Bears", *forests, username="bob")
    scenario.pass_priority("bob")

    casting = scenario.cast("Drown in the Loch", username="alice")
    casting.choose_modes([1])
    casting.choose_targets([bears])  # no refusal


def test_drown_in_the_loch_creature_mode_is_bounded_by_the_same_count():
    """The second mode restricts a creature on the battlefield the same way,
    and the count is read off *that* creature's controller's graveyard."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Drown in the Loch"], battlefield=["Island", "Swamp"])
        .player("bob", battlefield=["Hill Giant"], graveyard=["Lightning Bolt"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    giant = scenario.creature("Hill Giant", "bob")

    casting = scenario.cast("Drown in the Loch", username="alice")
    casting.choose_modes([2])
    with pytest.raises(ValueError, match="mana value"):
        casting.choose_targets([giant])


def test_drown_in_the_loch_creature_mode_accepts_a_creature_within_the_count():
    """Four cards in the graveyard reach Hill Giant's mana value of 4."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Drown in the Loch"], battlefield=["Island", "Swamp"])
        .player(
            "bob",
            battlefield=["Hill Giant"],
            graveyard=["Lightning Bolt", "Grizzly Bears", "Forest", "Mountain"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    giant = scenario.creature("Hill Giant", "bob")

    casting = scenario.cast("Drown in the Loch", username="alice")
    casting.choose_modes([2])
    casting.choose_targets([giant])  # no refusal


def test_spell_snare_actually_counters_the_spell_it_legally_targeted():
    """CR 701.6a's counter: the targeted spell leaves the stack unresolved.

    Written as a strict xfail when the targeting half landed - the effect half
    was measured as `None` at the time, and named as the counter-qualifier
    family's job. That family landed in the same wave, so the marker came off
    rather than the test: both halves are real now, and Spell Snare needed
    both to do anything at all.
    """
    scenario = _snare_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    forests = scenario.untapped_sources("Forest", "Forest", username="bob")
    bears = scenario.cast_onto_stack("Grizzly Bears", *forests, username="bob")
    scenario.pass_priority("bob")
    (island,) = scenario.untapped_sources("Island", username="alice")
    scenario.cast_onto_stack("Spell Snare", island, username="alice", targets=[bears])

    scenario.resolve_top()

    assert bears.zone is Zone.GRAVEYARD
