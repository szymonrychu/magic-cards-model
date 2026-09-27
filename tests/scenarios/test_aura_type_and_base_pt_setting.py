"""An Aura that sets its creature's creature type and base power and
toughness, strips its abilities, and restricts it - Retro-Mutation:
"Enchanted creature is a Turtle with base power and toughness 0/1. It can't
attack and loses all abilities. (It also loses all other creature types.)"

One static ability in several layers (CR 613.1):

- Layer 4 (CR 613.1d): "is a Turtle" sets the creature type. CR 205.1a:
  "when an effect sets one or more of an object's subtypes, the new
  subtype(s) replaces any existing subtypes from the appropriate set" - the
  other creature types go, the card types stay.
- Layer 6 (CR 613.1f): "loses all abilities" - a printed keyword, trigger or
  activated ability goes with it.
- Sublayer 7b (CR 613.4b): "base power and toughness 0/1" is a set; a +1/+1
  counter or an anthem still lands on top of it in 7c (CR 613.4c).
- "It can't attack" is CR 508.1c's restriction - an effect of the Aura, not
  an ability of the creature, so the Aura's own "loses all abilities" does
  not remove it.

Off-set proofs (legal, in no deck list):

- Spider-Man No More: "Enchanted creature is a Citizen with base power and
  toughness 1/1. It has defender and loses all other abilities." - the same
  two-sentence shape with a keyword grant as the rider.
- Lignify: "Enchanted creature is a Treefolk with base power and toughness
  0/4 and loses all abilities." - one sentence, no rider.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Type, Zone

from .harness import Scenario


def _chars(scenario, permanent):
    return scenario.game.computed_board().of(permanent)


def _enchant(scenario, aura, creature, *lands):
    return scenario.cast_and_resolve(
        aura, *scenario.untapped_sources(*lands, username="alice"), targets=[creature]
    )


def _board(aura, *theirs, extra_hand=(), lands=("Island",) * 3):
    return (
        Scenario()
        .player("alice", hand=[aura, *extra_hand], battlefield=list(lands))
        .player("bob", battlefield=list(theirs), library=["Island"] * 5)
        .build()
    )


def test_retro_mutation_makes_a_0_1_turtle():
    scenario = _board("Retro-Mutation", "Grizzly Bears")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")

    _enchant(scenario, "Retro-Mutation", bears, "Island", "Island", "Island")

    chars = _chars(scenario, bears)
    assert (chars.power, chars.toughness) == (0, 1)
    assert "Turtle" in chars.subtypes
    # CR 205.1a: the new creature type replaces the old ones.
    assert "Bear" not in chars.subtypes
    assert Type.CREATURE in chars.types


def test_retro_mutation_strips_printed_keywords():
    """CR 613.1f: Serra Angel's printed flying and vigilance are gone."""
    scenario = _board("Retro-Mutation", "Serra Angel")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.creature("Serra Angel", "bob")

    _enchant(scenario, "Retro-Mutation", angel, "Island", "Island", "Island")

    chars = _chars(scenario, angel)
    assert "Flying" not in chars.abilities
    assert "Vigilance" not in chars.abilities
    assert (chars.power, chars.toughness) == (0, 1)


def test_retro_mutation_strips_a_printed_activated_ability():
    """Birds of Paradise's mana ability is an ability too (CR 613.1f)."""
    scenario = _board("Retro-Mutation", "Birds of Paradise")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    birds = scenario.creature("Birds of Paradise", "bob")

    _enchant(scenario, "Retro-Mutation", birds, "Island", "Island", "Island")

    chars = _chars(scenario, birds)
    assert not any("Add one mana" in line for line in chars.abilities)
    assert "Flying" not in chars.abilities


def test_retro_mutation_keeps_card_types_but_not_other_creature_types():
    """An artifact creature stays an artifact: only the creature-type set is
    replaced (CR 205.1a), and Ornithopter loses its Thopter type."""
    scenario = _board("Retro-Mutation", "Ornithopter")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    thopter = scenario.creature("Ornithopter", "bob")

    _enchant(scenario, "Retro-Mutation", thopter, "Island", "Island", "Island")

    chars = _chars(scenario, thopter)
    assert Type.ARTIFACT in chars.types
    assert Type.CREATURE in chars.types
    assert "Thopter" not in chars.subtypes
    assert "Turtle" in chars.subtypes
    assert "Flying" not in chars.abilities


def test_the_enchanted_creature_cannot_attack():
    """CR 508.1c: the restriction makes the declaration illegal."""
    scenario = (
        Scenario()
        .player("alice", hand=["Retro-Mutation"], battlefield=["Island"] * 3 + ["Grizzly Bears"])
        .player("bob", library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    _enchant(scenario, "Retro-Mutation", bears, "Island", "Island", "Island")

    scenario.start_at(Step.DECLARE_ATTACKERS)
    assert not scenario.can_attack(bears)
    with pytest.raises(ValueError, match="can't attack"):
        scenario.attack_with(bears)


def test_the_enchanted_creature_can_still_block():
    """Only attacking is restricted - a 0/1 Turtle is still a legal blocker."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Retro-Mutation"],
            battlefield=["Island"] * 3 + ["Grizzly Bears"],
            library=["Island"] * 5,
        )
        .player("bob", battlefield=["Hill Giant"], library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    giant = scenario.creature("Hill Giant", "bob")
    _enchant(scenario, "Retro-Mutation", giant, "Island", "Island", "Island")
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(bears)
    scenario.advance()
    scenario.block(bears, giant)

    assert giant in scenario.blockers()


def test_a_counter_still_applies_on_top_of_the_set_base():
    """CR 613.4c: a +1/+1 counter modifies after 7b's set."""
    scenario = _board("Retro-Mutation", "Grizzly Bears")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    _enchant(scenario, "Retro-Mutation", bears, "Island", "Island", "Island")

    bears.add_counters("+1/+1", 2)

    chars = _chars(scenario, bears)
    assert (chars.power, chars.toughness) == (2, 3)


def test_an_anthem_still_applies_on_top_of_the_set_base():
    """Glorious Anthem's +1/+1 is 7c too, whatever its timestamp."""
    scenario = _board("Retro-Mutation", "Grizzly Bears", "Glorious Anthem")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")

    _enchant(scenario, "Retro-Mutation", bears, "Island", "Island", "Island")

    chars = _chars(scenario, bears)
    assert (chars.power, chars.toughness) == (1, 2)


def test_a_later_pump_still_applies():
    """Giant Growth after the Aura: 0/1 plus +3/+3 in 7c."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Retro-Mutation", "Giant Growth"],
            battlefield=["Island"] * 3 + ["Forest"],
        )
        .player("bob", battlefield=["Grizzly Bears"], library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    _enchant(scenario, "Retro-Mutation", bears, "Island", "Island", "Island")

    scenario.cast_and_resolve(
        "Giant Growth", *scenario.untapped_sources("Forest", username="alice"), targets=[bears]
    )

    chars = _chars(scenario, bears)
    assert (chars.power, chars.toughness) == (3, 4)


def test_the_creature_is_restored_when_the_aura_leaves():
    scenario = _board("Retro-Mutation", "Serra Angel")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.creature("Serra Angel", "bob")
    aura = _enchant(scenario, "Retro-Mutation", angel, "Island", "Island", "Island")

    scenario.game.destroy(aura)

    assert aura.zone is Zone.GRAVEYARD
    chars = _chars(scenario, angel)
    assert (chars.power, chars.toughness) == (4, 4)
    assert "Flying" in chars.abilities
    assert "Turtle" not in chars.subtypes


# -- Spider-Man No More ------------------------------------------------------


def test_spider_man_no_more_makes_a_1_1_citizen_with_defender_only():
    scenario = _board("Spider-Man No More", "Serra Angel", lands=("Island",) * 2)
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.creature("Serra Angel", "bob")

    _enchant(scenario, "Spider-Man No More", angel, "Island", "Island")

    chars = _chars(scenario, angel)
    assert (chars.power, chars.toughness) == (1, 1)
    assert "Citizen" in chars.subtypes
    assert "Angel" not in chars.subtypes
    assert "Flying" not in chars.abilities
    assert "Vigilance" not in chars.abilities
    assert "Defender" in chars.abilities


def test_spider_man_no_more_defender_stops_the_attack():
    """CR 702.3b: the granted defender outlives the Aura's own "loses all
    other abilities" - it is not one of the *other* abilities."""
    scenario = (
        Scenario()
        .player(
            "alice", hand=["Spider-Man No More"], battlefield=["Island"] * 2 + ["Grizzly Bears"]
        )
        .player("bob", library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    _enchant(scenario, "Spider-Man No More", bears, "Island", "Island")

    scenario.start_at(Step.DECLARE_ATTACKERS)
    assert not scenario.can_attack(bears)


# -- Lignify -------------------------------------------------------------------


def test_lignify_makes_a_0_4_treefolk_without_abilities():
    scenario = _board("Lignify", "Serra Angel", lands=("Forest",) * 2)
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.creature("Serra Angel", "bob")

    _enchant(scenario, "Lignify", angel, "Forest", "Forest")

    chars = _chars(scenario, angel)
    assert (chars.power, chars.toughness) == (0, 4)
    assert "Treefolk" in chars.subtypes
    assert "Angel" not in chars.subtypes
    assert "Flying" not in chars.abilities


def test_lignify_does_not_restrict_attacking():
    """No rider: a Lignified creature still attacks (it was a 0/4 body)."""
    scenario = (
        Scenario()
        .player("alice", hand=["Lignify"], battlefield=["Forest"] * 2 + ["Grizzly Bears"])
        .player("bob", library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    _enchant(scenario, "Lignify", bears, "Forest", "Forest")

    scenario.start_at(Step.DECLARE_ATTACKERS)
    assert scenario.can_attack(bears)
