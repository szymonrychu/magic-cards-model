"""EP-02 R2 F6: the overloaded side of eleven overload spells (CR 702.96).

Rules, each read in full with `mise run rules:find` in this session:

- CR 702.96a - overload is two static abilities: "You may choose to pay [cost]
  rather than pay this spell's mana cost" and "If you chose to pay this spell's
  overload cost, change its text by replacing all instances of the word 'target'
  with the word 'each.'"
- CR 702.96b - an overloaded spell has no targets, so hexproof and protection
  (CR 115.1) do not stop it.
- CR 608.2f / CR 608.2c - an "each" instruction is followed for every object it
  describes, in the order the text prints.

Listed cards: Break the Ice, Blustersquall, Scale Up, Downsize, Rise and Shine,
Counterflux, Fangs of Kalonia, Damn, Dragonshift, Cyclonic Rift, Chemister's
Trick.
"""

import pytest

from magic_cards_model.models import Zone
from magic_cards_model.models.card import Color, Type
from magic_cards_model.support import card_support
from tests.cards import card

from .test_ep02_r2_revealed_this_way import (
    _battlefield_of,
    _board,
    _cast,
    _cast_with,
    _names,
)

LISTED = [
    "Break the Ice",
    "Blustersquall",
    "Scale Up",
    "Downsize",
    "Rise and Shine",
    "Counterflux",
    "Fangs of Kalonia",
    "Damn",
    "Dragonshift",
    "Cyclonic Rift",
    "Chemister's Trick",
]


@pytest.mark.parametrize("name", LISTED)
def test_every_listed_card_reads_handled(name):
    outcomes = {clause.outcome for clause in card_support(card(name)).clauses}
    assert outcomes == {"handled"}, name


def _stats(scenario, state):
    chars = scenario.game.characteristics_of(state)
    return chars.power, chars.toughness


def _land_names(scenario, username):
    return sorted(
        state.name
        for state in scenario.game.battlefield
        if state.controller == username and "Land" in str(state.card.type_line)
    )


def _on_stack(scenario, name, username, targets=None):
    casting = scenario.cast(name, username=username)
    if targets is not None:
        casting.choose_targets(targets)
    payment = casting.begin_paying()
    scenario.auto_pay(payment, username=username)
    return scenario.put_on_stack(casting)


# -- Break the Ice: destroy each land that is snow or could produce {C} ------------


def test_break_the_ice_destroys_the_one_target_when_cast_normally():
    scenario = _board(
        alice_hand=["Break the Ice"],
        alice_battlefield=["Wastes"],
        bob_battlefield=["Wastes", "Snow-Covered Forest"],
    )
    wastes = scenario.find("Wastes", Zone.BATTLEFIELD, "bob")
    _cast(scenario, "Break the Ice", targets=[wastes])
    assert wastes.zone is Zone.GRAVEYARD
    assert "Snow-Covered Forest" in _land_names(scenario, "bob")
    assert "Wastes" in _land_names(scenario, "alice")


def test_break_the_ice_overloaded_destroys_every_snow_or_colorless_land():
    scenario = _board(
        alice_hand=["Break the Ice"],
        alice_battlefield=["Wastes", "Forest"],
        bob_battlefield=["Wastes", "Snow-Covered Forest", "Forest"],
    )
    _cast_with(scenario, "Break the Ice", "Overload")
    assert _land_names(scenario, "bob") == ["Forest", "Swamp", "Swamp"]
    assert "Wastes" not in _land_names(scenario, "alice")
    assert "Forest" in _land_names(scenario, "alice")


# -- Blustersquall: tap each creature you don't control ----------------------------


def test_blustersquall_overloaded_taps_only_creatures_you_dont_control():
    scenario = _board(
        alice_hand=["Blustersquall"],
        alice_battlefield=["Grizzly Bears"],
        bob_battlefield=["Hill Giant", "Serra Angel"],
    )
    _cast_with(scenario, "Blustersquall", "Overload")
    assert scenario.creature("Hill Giant", "bob").tapped
    assert scenario.creature("Serra Angel", "bob").tapped
    assert not scenario.creature("Grizzly Bears", "alice").tapped


def test_blustersquall_normal_taps_one_target():
    scenario = _board(alice_hand=["Blustersquall"], bob_battlefield=["Hill Giant", "Serra Angel"])
    giant = scenario.creature("Hill Giant", "bob")
    _cast(scenario, "Blustersquall", targets=[giant])
    assert giant.tapped
    assert not scenario.creature("Serra Angel", "bob").tapped


# -- Scale Up: each creature you control becomes a green Wurm 6/4 -------------------


def test_scale_up_overloaded_makes_each_of_your_creatures_a_6_4_green_wurm():
    scenario = _board(
        alice_hand=["Scale Up"],
        alice_battlefield=["Grizzly Bears", "Llanowar Elves"],
        bob_battlefield=["Hill Giant"],
    )
    _cast_with(scenario, "Scale Up", "Overload")
    for name in ("Grizzly Bears", "Llanowar Elves"):
        creature = scenario.creature(name, "alice")
        assert _stats(scenario, creature) == (6, 4), name
        chars = scenario.game.characteristics_of(creature)
        assert chars.colors == (Color.GREEN,), name
        assert "Wurm" in chars.subtypes, name
    assert _stats(scenario, scenario.creature("Hill Giant", "bob")) == (3, 3)


def test_scale_up_normal_changes_only_the_target():
    scenario = _board(
        alice_hand=["Scale Up"], alice_battlefield=["Grizzly Bears", "Llanowar Elves"]
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    _cast(scenario, "Scale Up", targets=[bears])
    assert _stats(scenario, bears) == (6, 4)
    assert _stats(scenario, scenario.creature("Llanowar Elves", "alice")) == (1, 1)


# -- Downsize: each creature you don't control gets -4/-0 ---------------------------


def test_downsize_overloaded_shrinks_every_opposing_creature():
    scenario = _board(
        alice_hand=["Downsize"],
        alice_battlefield=["Grizzly Bears"],
        bob_battlefield=["Hill Giant", "Serra Angel"],
    )
    _cast_with(scenario, "Downsize", "Overload")
    assert _stats(scenario, scenario.creature("Hill Giant", "bob")) == (-1, 3)
    assert _stats(scenario, scenario.creature("Serra Angel", "bob")) == (0, 4)
    assert _stats(scenario, scenario.creature("Grizzly Bears", "alice")) == (2, 2)


# -- Rise and Shine: each noncreature artifact you control becomes a 4/4 ------------


def test_rise_and_shine_normal_animates_the_target_artifact_with_four_counters():
    scenario = _board(alice_hand=["Rise and Shine"], alice_battlefield=["Sol Ring", "Mind Stone"])
    ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "alice")
    _cast(scenario, "Rise and Shine", targets=[ring])
    assert Type.CREATURE in scenario.game.characteristics_of(ring).types
    assert _stats(scenario, ring) == (4, 4)
    stone = scenario.find("Mind Stone", Zone.BATTLEFIELD, "alice")
    assert Type.CREATURE not in scenario.game.characteristics_of(stone).types


def test_rise_and_shine_overloaded_animates_each_noncreature_artifact_you_control():
    scenario = _board(
        alice_hand=["Rise and Shine"],
        alice_battlefield=["Sol Ring", "Mind Stone", "Ornithopter"],
        bob_battlefield=["Sol Ring"],
    )
    _cast_with(scenario, "Rise and Shine", "Overload")
    for name in ("Sol Ring", "Mind Stone"):
        artifact = scenario.find(name, Zone.BATTLEFIELD, "alice")
        assert Type.CREATURE in scenario.game.characteristics_of(artifact).types, name
        assert _stats(scenario, artifact) == (4, 4), name
    ornithopter = scenario.find("Ornithopter", Zone.BATTLEFIELD, "alice")
    assert _stats(scenario, ornithopter) == (0, 2), "already a creature: no counters"
    theirs = scenario.find("Sol Ring", Zone.BATTLEFIELD, "bob")
    assert Type.CREATURE not in scenario.game.characteristics_of(theirs).types


# -- Counterflux: counter each spell you don't control ------------------------------


def test_counterflux_overloaded_counters_every_opposing_spell_and_not_yours():
    scenario = _board(
        alice_hand=["Counterflux", "Lightning Bolt"],
        alice_lands=("Island", "Island", "Mountain", "Mountain", "Island"),
        bob_hand=["Lightning Bolt", "Shock"],
        bob_battlefield=["Mountain", "Mountain"],
    )
    own = _on_stack(scenario, "Lightning Bolt", "alice", targets=["bob"])
    scenario.pass_priority("alice")
    bolt = _on_stack(scenario, "Lightning Bolt", "bob", targets=["alice"])
    shock = _on_stack(scenario, "Shock", "bob", targets=["alice"])
    scenario.pass_priority("bob")
    _cast_with(scenario, "Counterflux", "Overload")
    assert bolt.zone is Zone.GRAVEYARD
    assert shock.zone is Zone.GRAVEYARD
    assert own.zone is Zone.STACK


# -- Fangs of Kalonia: a counter on each creature, then double them -----------------


def _plus_one(state):
    return state.counter_count("+1/+1")


def test_fangs_of_kalonia_normal_puts_one_counter_then_doubles_that_creature():
    scenario = _board(
        alice_hand=["Fangs of Kalonia"], alice_battlefield=["Grizzly Bears", "Llanowar Elves"]
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    bears.add_counters("+1/+1", 1)
    elves = scenario.creature("Llanowar Elves", "alice")
    elves.add_counters("+1/+1", 3)
    _cast(scenario, "Fangs of Kalonia", targets=[bears])
    assert _plus_one(bears) == 4
    assert _plus_one(elves) == 3


def test_fangs_of_kalonia_overloaded_adds_and_doubles_on_each_creature_you_control():
    scenario = _board(
        alice_hand=["Fangs of Kalonia"],
        alice_battlefield=["Grizzly Bears", "Llanowar Elves"],
        bob_battlefield=["Hill Giant"],
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    bears.add_counters("+1/+1", 1)
    _cast_with(scenario, "Fangs of Kalonia", "Overload")
    assert _plus_one(bears) == 4
    assert _plus_one(scenario.creature("Llanowar Elves", "alice")) == 2
    assert _plus_one(scenario.creature("Hill Giant", "bob")) == 0


# -- Damn: destroy each creature, which can't be regenerated -------------------------


def test_damn_normal_destroys_the_target_creature():
    scenario = _board(
        alice_hand=["Damn"],
        alice_battlefield=["Grizzly Bears"],
        bob_battlefield=["Hill Giant", "Serra Angel"],
    )
    giant = scenario.creature("Hill Giant", "bob")
    _cast(scenario, "Damn", targets=[giant])
    assert giant.zone is Zone.GRAVEYARD
    assert "Serra Angel" in _battlefield_of(scenario, "bob")
    assert "Grizzly Bears" in _battlefield_of(scenario, "alice")


def test_damn_overloaded_destroys_every_creature():
    scenario = _board(
        alice_hand=["Damn"],
        alice_battlefield=["Grizzly Bears"],
        bob_battlefield=["Hill Giant", "Serra Angel", "Sol Ring"],
    )
    _cast_with(scenario, "Damn", "Overload")
    assert _battlefield_of(scenario, "bob") == ["Sol Ring"]
    assert _battlefield_of(scenario, "alice") == []


# -- Dragonshift: each creature you control becomes a 4/4 flying Dragon --------------


def test_dragonshift_normal_turns_the_target_into_a_4_4_flying_dragon():
    scenario = _board(
        alice_hand=["Dragonshift"], alice_battlefield=["Llanowar Elves", "Grizzly Bears"]
    )
    elves = scenario.creature("Llanowar Elves", "alice")
    _cast(scenario, "Dragonshift", targets=[elves])
    chars = scenario.game.characteristics_of(elves)
    assert (chars.power, chars.toughness) == (4, 4)
    assert set(chars.colors) == {Color.BLUE, Color.RED}
    assert "Dragon" in chars.subtypes
    assert any("flying" in ability.lower() for ability in chars.abilities)
    assert not any("add" in ability.lower() for ability in chars.abilities)
    assert _stats(scenario, scenario.creature("Grizzly Bears", "alice")) == (2, 2)


def test_dragonshift_overloaded_changes_each_creature_you_control():
    scenario = _board(
        alice_hand=["Dragonshift"],
        alice_battlefield=["Llanowar Elves", "Grizzly Bears"],
        alice_lands=("Island", "Island", "Island", "Mountain", "Mountain", "Island", "Mountain"),
        bob_battlefield=["Hill Giant"],
    )
    _cast_with(scenario, "Dragonshift", "Overload")
    for name in ("Llanowar Elves", "Grizzly Bears"):
        chars = scenario.game.characteristics_of(scenario.creature(name, "alice"))
        assert (chars.power, chars.toughness) == (4, 4), name
        assert "Dragon" in chars.subtypes, name
        assert any("flying" in ability.lower() for ability in chars.abilities), name
    assert _stats(scenario, scenario.creature("Hill Giant", "bob")) == (3, 3)


# -- Cyclonic Rift: return each nonland permanent you don't control ------------------


def test_cyclonic_rift_overloaded_returns_every_opposing_nonland_permanent():
    scenario = _board(
        alice_hand=["Cyclonic Rift"],
        alice_battlefield=["Grizzly Bears"],
        alice_lands=("Island",) * 4,
        bob_battlefield=["Hill Giant", "Sol Ring"],
    )
    _cast_with(scenario, "Cyclonic Rift", "Overload")
    assert _battlefield_of(scenario, "bob") == []
    assert _names(scenario, "bob", Zone.HAND) == ["Hill Giant", "Sol Ring"]
    assert "Swamp" in _land_names(scenario, "bob")
    assert _battlefield_of(scenario, "alice") == ["Grizzly Bears"]


def test_cyclonic_rift_normal_returns_one_permanent():
    scenario = _board(
        alice_hand=["Cyclonic Rift"],
        alice_lands=("Island",) * 2,
        bob_battlefield=["Hill Giant", "Sol Ring"],
    )
    giant = scenario.creature("Hill Giant", "bob")
    _cast(scenario, "Cyclonic Rift", targets=[giant])
    assert _names(scenario, "bob", Zone.HAND) == ["Hill Giant"]
    assert "Sol Ring" in _battlefield_of(scenario, "bob")


# -- Chemister's Trick: each creature you don't control gets -2/-0 and must attack --


def test_chemisters_trick_overloaded_shrinks_and_forces_every_opposing_creature():
    scenario = _board(
        alice_hand=["Chemister's Trick"],
        alice_battlefield=["Grizzly Bears"],
        bob_battlefield=["Hill Giant", "Serra Angel"],
    )
    _cast_with(scenario, "Chemister's Trick", "Overload")
    giant = scenario.creature("Hill Giant", "bob")
    angel = scenario.creature("Serra Angel", "bob")
    assert _stats(scenario, giant) == (1, 3)
    assert _stats(scenario, angel) == (2, 4)
    assert _stats(scenario, scenario.creature("Grizzly Bears", "alice")) == (2, 2)
    for creature in (giant, angel):
        chars = scenario.game.characteristics_of(creature)
        assert any("attacks each combat if able" in a.lower() for a in chars.abilities)


def test_chemisters_trick_normal_affects_only_the_target():
    scenario = _board(
        alice_hand=["Chemister's Trick"], bob_battlefield=["Hill Giant", "Serra Angel"]
    )
    giant = scenario.creature("Hill Giant", "bob")
    _cast(scenario, "Chemister's Trick", targets=[giant])
    assert _stats(scenario, giant) == (1, 3)
    assert _stats(scenario, scenario.creature("Serra Angel", "bob")) == (4, 4)


# -- Rules the readers must keep ------------------------------------------------------


def test_break_the_ice_cannot_target_a_land_that_is_neither_snow_nor_colorless():
    scenario = _board(alice_hand=["Break the Ice"], bob_battlefield=["Wastes"])
    swamp = scenario.find("Swamp", Zone.BATTLEFIELD, "bob")
    casting = scenario.cast("Break the Ice", username="alice")
    with pytest.raises(ValueError):
        casting.choose_targets([swamp])


@pytest.mark.parametrize("overload", [False, True])
def test_damn_destroys_through_a_regeneration_shield(overload):
    scenario = _board(alice_hand=["Damn"], alice_battlefield=["Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.game.regenerate(bears)  # CR 701.19c: "can't be regenerated" ignores the shield
    if overload:
        _cast_with(scenario, "Damn", "Overload")
    else:
        _cast(scenario, "Damn", targets=[bears])
    assert bears.zone is Zone.GRAVEYARD


def test_an_overloaded_spell_reaches_a_hexproof_permanent():
    """CR 702.96b: no target is chosen, so hexproof (CR 702.11b) has nothing to refuse."""
    scenario = _board(
        alice_hand=["Cyclonic Rift"],
        alice_lands=("Island",) * 4,
        bob_battlefield=["Carnage Tyrant"],
    )
    _cast_with(scenario, "Cyclonic Rift", "Overload")
    assert _names(scenario, "bob", Zone.HAND) == ["Carnage Tyrant"]
