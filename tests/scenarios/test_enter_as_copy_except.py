"""Entering as a copy "except it has changeling" - Omni-Changeling: "You may
have this creature enter as a copy of any creature on the battlefield, except
it has changeling."

Every CR number here was read whole with `mise run rules:find` in the session
that wrote this file:

- **CR 614.12** / **CR 614.12a** a replacement effect that modifies how a
  permanent enters; its choice is made before it enters.
- **CR 707.2** the copy takes the copiable values (as modified by other copy
  effects); **CR 707.9a** an ability gained as part of the copying process
  is itself a copiable value; **CR 707.9b** so is a modified characteristic
  (a supertype added "in addition to its other types"); **CR 707.9e** an
  exception that is an additional effect ("it enters with two additional
  +1/+1 counters"); **CR 707.9f** an exception that applies only "if it's a
  creature" is judged on the copy without that exception.
- **CR 702.73a** changeling is a characteristic-defining ability: "This
  object is every creature type"; **CR 613.3** it applies first in layer 4,
  so a later "loses all abilities" (layer 6) leaves every creature type in
  place (the card's own ruling).

Second printing (legal in Modern and Pioneer, in no deck list, Scryfall
printing read 2026-09-27): Moritte of the Frost - "You may have Moritte enter
as a copy of a permanent you control, except it's legendary and snow in
addition to its other types and, if it's a creature, it enters with two
additional +1/+1 counters on it and has changeling." - "has changeling" as
the tail of a conditional (CR 707.9f) exception.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import Keyword, has_keyword
from magic_cards_model.models import Supertype, Type, Zone
from tests.scenarios.harness import Scenario

OMNI = "Omni-Changeling"
MORITTE = "Moritte of the Frost"


def _chars(scenario: Scenario, permanent):
    return scenario.game.characteristics_of(permanent)


def _omni(*, alice=(), bob=("Grizzly Bears",), hand=()):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=[OMNI, *hand],
            battlefield=["Island"] * 7 + list(alice),
            library=["Island"] * 5,
        )
        .player("bob", battlefield=list(bob), library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _cast_omni(scenario: Scenario, copied=None):
    if copied is None:
        scenario.will_take_the_may(False, source=OMNI)
    else:
        scenario.will_choose_cards(copied, username="alice", source=OMNI)
    return scenario.cast_and_resolve(OMNI, *scenario.untapped_sources(*["Island"] * 5))


def test_omni_changeling_copies_a_creature_and_has_changeling():
    scenario = _omni()
    bears = scenario.creature("Grizzly Bears", "bob")

    omni = _cast_omni(scenario, bears)

    chars = _chars(scenario, omni)
    assert chars.name == "Grizzly Bears"
    assert (chars.power, chars.toughness) == (2, 2)
    assert "Changeling" in chars.abilities
    # CR 702.73a: every creature type, not just Bear.
    for kind in ("Bear", "Goblin", "Kithkin", "Shapeshifter"):
        assert kind in chars.subtypes
    assert scenario.game.unreadable_copy_exception_notices == []


def test_the_copied_creature_gains_nothing():
    scenario = _omni()
    bears = scenario.creature("Grizzly Bears", "bob")

    _cast_omni(scenario, bears)

    chars = _chars(scenario, bears)
    assert "Changeling" not in chars.abilities
    assert "Goblin" not in chars.subtypes


def test_declining_leaves_a_0_0_that_dies():
    """The card's own ruling: without a copy it is a 0/0 Shapeshifter and
    state-based actions put it into the graveyard (CR 704.5f)."""
    scenario = _omni()

    omni = _cast_omni(scenario)
    scenario.state_based_actions()

    assert omni.zone is Zone.GRAVEYARD


def test_copying_a_creature_with_an_enters_trigger_triggers_it():
    """CR 614.12: it enters already a copy, so Kitchen Finks' enters ability
    is its own and triggers."""
    scenario = _omni(bob=("Kitchen Finks",))
    finks = scenario.creature("Kitchen Finks", "bob")
    life = scenario.player("alice").life

    _cast_omni(scenario, finks)
    scenario.pass_until_resolved()

    assert scenario.player("alice").life == life + 2


def test_losing_all_abilities_leaves_every_creature_type():
    """The card's ruling: changeling applied first in layer 4 (CR 613.3), so
    Abigale's later "loses all abilities" (layer 6) cannot take its creature
    types away, even though the copy no longer has changeling."""
    scenario = _omni(hand=("Abigale, Eloquent First-Year",), alice=("Plains", "Plains"))
    bears = scenario.creature("Grizzly Bears", "bob")
    omni = _cast_omni(scenario, bears)

    scenario.will_choose_targets(omni, username="alice", source="Abigale, Eloquent First-Year")
    scenario.cast_and_resolve(
        "Abigale, Eloquent First-Year", *scenario.untapped_sources("Plains", "Plains")
    )
    scenario.pass_until_resolved()

    chars = _chars(scenario, omni)
    assert "Changeling" not in chars.abilities
    assert "Goblin" in chars.subtypes


def test_copying_a_clone_copies_what_the_clone_copied_plus_changeling():
    """CR 707.2: copiable values as modified by other copy effects."""
    scenario = _omni(hand=("Clone",), alice=("Island",) * 2)
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.will_choose_cards(bears, username="alice", source="Clone")
    clone = scenario.cast_and_resolve("Clone", *scenario.untapped_sources(*["Island"] * 4))

    scenario.will_choose_cards(clone, username="alice", source=OMNI)
    omni = scenario.cast_and_resolve(OMNI, *scenario.untapped_sources(*["Island"] * 5))

    chars = _chars(scenario, omni)
    assert chars.name == "Grizzly Bears"
    assert "Changeling" in chars.abilities


def test_a_copy_of_omni_changeling_has_changeling_too():
    """CR 707.9a: the gained changeling is a copiable value."""
    scenario = _omni(hand=("Clone",), alice=("Island",) * 2)
    bears = scenario.creature("Grizzly Bears", "bob")
    omni = _cast_omni(scenario, bears)

    scenario.will_choose_cards(omni, username="alice", source="Clone")
    clone = scenario.cast_and_resolve("Clone", *scenario.untapped_sources(*["Island"] * 4))

    chars = _chars(scenario, clone)
    assert chars.name == "Grizzly Bears"
    assert "Changeling" in chars.abilities
    assert "Merfolk" in chars.subtypes


def test_only_creatures_are_offered():
    """ "Any creature on the battlefield": a board with only a Sol Ring offers
    nothing, and Omni-Changeling enters as itself."""
    scenario = _omni(bob=("Sol Ring",))

    omni = scenario.cast_and_resolve(OMNI, *scenario.untapped_sources(*["Island"] * 5))

    assert _chars(scenario, omni).name == OMNI


# --------------------------------------------------------------------------
# Moritte of the Frost
# --------------------------------------------------------------------------


def _moritte(*permanents):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=[MORITTE],
            battlefield=["Forest", "Island", "Island", "Island", "Island", *permanents],
            library=["Island"] * 5,
        )
        .player("bob", library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _cast_moritte(scenario, copied):
    scenario.will_choose_cards(copied, username="alice", source=MORITTE)
    return scenario.cast_and_resolve(
        MORITTE, *scenario.untapped_sources("Forest", "Island", "Island", "Island", "Island")
    )


def test_moritte_copying_a_creature_is_a_legendary_snow_changeling_with_two_counters():
    scenario = _moritte("Serra Angel")
    angel = scenario.creature("Serra Angel", "alice")

    moritte = _cast_moritte(scenario, angel)

    chars = _chars(scenario, moritte)
    assert chars.name == "Serra Angel"
    assert Supertype.LEGENDARY in chars.supertypes
    assert Supertype.SNOW in chars.supertypes
    assert "Changeling" in chars.abilities
    assert "Goblin" in chars.subtypes
    assert moritte.counters["+1/+1"] == 2
    assert (chars.power, chars.toughness) == (6, 6)
    assert has_keyword(moritte, Keyword.FLYING, scenario.game)


def test_moritte_copying_a_noncreature_gets_no_counters_and_no_changeling():
    """CR 707.9f: the "if it's a creature" half is judged on the copy
    without it - a Sol Ring copy is not a creature."""
    scenario = _moritte("Sol Ring")
    ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "alice")

    moritte = _cast_moritte(scenario, ring)

    chars = _chars(scenario, moritte)
    assert chars.name == "Sol Ring"
    assert Type.CREATURE not in chars.types
    assert Supertype.LEGENDARY in chars.supertypes
    assert "Changeling" not in chars.abilities
    assert moritte.counters["+1/+1"] == 0


@pytest.mark.parametrize("name", [OMNI, MORITTE])
def test_the_sweep_handles_every_clause(name):
    from magic_cards_model.support import HANDLED, card_support
    from tests.cards import card

    support = card_support(card(name))
    assert support.effect_outcome == HANDLED, support.effect_detail
