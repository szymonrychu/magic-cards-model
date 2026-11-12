"""An Aura whose one static sentence is a three-part list: a pump, a blocking
restriction and a creature type set - De-evolve: "Enchanted creature gets -4/-0,
can't block, and is a Salamander. (It loses all other creature types.)"

Rules, each read with `mise run rules:find` in the session that wrote this:

- CR 613.1d: "is a Salamander" is a layer 4 type change; CR 205.1a says an
  effect that sets a subtype replaces the existing subtypes of that set, so the
  Bear goes and the card types stay.
- CR 613.4c: the -4/-0 is a sublayer 7c modification (so power can go below
  zero and toughness is untouched).
- CR 509.1b: "can't block" is a restriction on declaring blockers, enforced at
  the declaration; the creature may still attack (CR 508.1c is not involved).
- CR 303.4b: "enchanted creature" is the object the Aura is attached to, and
  CR 611.3a: the effect is not locked in - it ends when the Aura leaves.

Second printings of the list reader, none of them De-evolve: Demonic Embrace
("gets +3/+1, has flying, and is a Demon in addition to its other types") and
Alien Symbiosis (menace, Symbiote) are the gets/has/is lists of the same
reader. No printing pairs a pump with "can't block" in a list, so the
restriction half is proven on the board: a different creature, other blockers,
an attacker already blocked.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Type, Zone
from magic_cards_model.support import card_support
from tests.cards import card
from tests.scenarios.harness import Scenario


def _board(*, bob=("Grizzly Bears", "Watchwolf"), alice_extra=(), aura="De-evolve", gy=0):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=[aura],
            battlefield=["Swamp", "Swamp", "Swamp", "Hill Giant", *alice_extra],
            graveyard=["Island"] * gy,
            library=["Island"] * 8,
        )
        .player("bob", battlefield=list(bob), library=["Island"] * 8)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _enchant(scenario, creature, aura="De-evolve", *lands):
    scenario.cast_and_resolve(
        aura,
        *scenario.untapped_sources(*(lands or ("Swamp", "Swamp")), username="alice"),
        targets=[creature],
    )


def _chars(scenario, permanent):
    return scenario.game.computed_board().of(permanent)


def test_de_evolve_is_fully_handled():
    bad = [c for c in card_support(card("De-evolve")).clauses if c.outcome != "handled"]
    assert not bad, bad


def test_the_enchanted_creature_gets_minus_four_zero():
    scenario = _board()
    bears = scenario.creature("Grizzly Bears", "bob")
    _enchant(scenario, bears)
    chars = _chars(scenario, bears)
    assert (chars.power, chars.toughness) == (-2, 2)


def test_the_enchanted_creature_is_only_a_salamander_and_stays_a_creature():
    scenario = _board()
    bears = scenario.creature("Grizzly Bears", "bob")
    _enchant(scenario, bears)
    chars = _chars(scenario, bears)
    assert chars.subtypes == ("Salamander",)
    assert Type.CREATURE in chars.types


def test_every_other_creature_type_goes_not_just_one():
    """Llanowar Elves is an Elf Druid; a creature with two types loses both."""
    scenario = _board(bob=("Llanowar Elves",))
    elves = scenario.creature("Llanowar Elves", "bob")
    assert len(_chars(scenario, elves).subtypes) == 2
    _enchant(scenario, elves)
    assert _chars(scenario, elves).subtypes == ("Salamander",)


def test_the_enchanted_creature_cannot_block_but_an_unenchanted_one_can():
    scenario = _board()
    bears = scenario.creature("Grizzly Bears", "bob")
    wolf = scenario.creature("Watchwolf", "bob")
    _enchant(scenario, bears)
    giant = scenario.creature("Hill Giant", "alice")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(giant, defending="bob")
    with pytest.raises(ValueError, match="can't block"):
        scenario.block(giant, bears)
    scenario.block(giant, wolf)
    assert wolf in scenario.blockers()


def test_the_enchanted_creature_may_still_attack():
    """The restriction names blocking only (CR 509.1b); attacking stays open."""
    scenario = _board()
    giant = scenario.creature("Hill Giant", "alice")
    _enchant(scenario, giant)
    scenario.start_at(Step.DECLARE_ATTACKERS)
    assert scenario.can_attack(giant, defending="bob")


def test_when_the_aura_leaves_the_creature_is_a_bear_again_and_can_block():
    scenario = _board()
    bears = scenario.creature("Grizzly Bears", "bob")
    _enchant(scenario, bears)
    aura = scenario.find("De-evolve", Zone.BATTLEFIELD, "alice")
    scenario.game.destroy(aura)
    chars = _chars(scenario, bears)
    assert (chars.power, chars.toughness) == (2, 2)
    assert chars.subtypes == ("Bear",)
    giant = scenario.creature("Hill Giant", "alice")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(giant, defending="bob")
    scenario.block(giant, bears)
    assert bears in scenario.blockers()


def test_enchanting_a_creature_that_already_has_a_plus_pump_nets_the_two():
    """Both are sublayer 7c modifications and add (CR 613.4c)."""
    scenario = _board(bob=("Grizzly Bears",))
    bears = scenario.creature("Grizzly Bears", "bob")
    _enchant(scenario, bears)
    bears.add_counters("+1/+1", 2)
    chars = _chars(scenario, bears)
    assert (chars.power, chars.toughness) == (0, 4)


# --------------------------------------------------------------------------
# The Threshold line of the same card
# --------------------------------------------------------------------------


def _to_next_upkeep(scenario) -> None:
    scenario.turn.advance_to(Step.CLEANUP)
    scenario.advance()  # untap
    scenario.advance()  # upkeep


def test_threshold_exiles_the_enchanted_creature_at_an_upkeep_with_seven_cards():
    scenario = _board(gy=7)
    bears = scenario.creature("Grizzly Bears", "bob")
    _enchant(scenario, bears)
    _to_next_upkeep(scenario)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()
    assert bears.zone is Zone.EXILE


def test_six_cards_in_the_graveyard_is_not_threshold():
    scenario = _board(gy=6)
    bears = scenario.creature("Grizzly Bears", "bob")
    _enchant(scenario, bears)
    _to_next_upkeep(scenario)
    scenario.game.put_triggers_on_stack()
    assert scenario.game.stack_is_empty
    assert bears.zone is Zone.BATTLEFIELD


# --------------------------------------------------------------------------
# The same list reader on its other printed shapes (regression proofs)
# --------------------------------------------------------------------------


def test_demonic_embrace_keeps_the_bear_and_adds_a_demon_with_flying():
    """ "gets +3/+1, has flying, and is a Demon in addition to its other types":
    the comma list is read whole, and "in addition" keeps the old types."""
    scenario = _board(aura="Demonic Embrace")
    bears = scenario.creature("Grizzly Bears", "bob")
    _enchant(scenario, bears, "Demonic Embrace", "Swamp", "Swamp", "Swamp")
    chars = _chars(scenario, bears)
    assert (chars.power, chars.toughness) == (5, 3)
    assert set(chars.subtypes) == {"Bear", "Demon"}
    assert "Flying" in chars.abilities


def test_alien_symbiosis_adds_a_symbiote_with_menace():
    scenario = _board(aura="Alien Symbiosis")
    bears = scenario.creature("Grizzly Bears", "bob")
    _enchant(scenario, bears, "Alien Symbiosis")
    chars = _chars(scenario, bears)
    assert (chars.power, chars.toughness) == (3, 3)
    assert set(chars.subtypes) == {"Bear", "Symbiote"}
    assert "Menace" in chars.abilities
