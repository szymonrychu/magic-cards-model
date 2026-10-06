"""Scenario: "the number of cards named <this card's name> in your graveyard /
in all graveyards" as a damage or effect amount, with an "N plus" prefix.

Galvanic Bombardment: "Galvanic Bombardment deals X damage to target creature,
where X is 2 plus the number of cards named Galvanic Bombardment in your
graveyard." Feast of Flesh: "Feast of Flesh deals X damage to target creature
and you gain X life, where X is 1 plus the number of cards named Feast of Flesh
in all graveyards." The count is fixed once on resolution (CR 608.2c / CR 107.3a),
the same X for damage and life, and the resolving spell is on the stack, not in
the graveyard, so it never counts itself. A card is "named" by its printed name
(CR 201.2).

Kjeldoran War Cry ("Creatures you control get +X/+X until end of turn, where X
is 1 plus the number of cards named Kjeldoran War Cry in all graveyards.") is
the off-set proof of the same reader on a different effect shape.
"""

from magic_cards_model.machines import Step

from .harness import Scenario


def _scenario(hand, mana, *, alice_gy=(), bob_gy=(), bob_bf=("Colossal Dreadmaw",), alice_bf=()):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=list(hand),
            battlefield=list(mana) + list(alice_bf),
            graveyard=list(alice_gy),
        )
        .player("bob", battlefield=list(bob_bf), graveyard=list(bob_gy))
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_galvanic_bombardment_is_two_with_an_empty_graveyard():
    scenario = _scenario(["Galvanic Bombardment"], ["Mountain"])
    target = scenario.creature("Colossal Dreadmaw", "bob")
    scenario.cast_and_resolve("Galvanic Bombardment", auto=True, targets=[target])
    assert target.damage == 2


def test_galvanic_bombardment_adds_one_per_copy_in_your_graveyard():
    scenario = _scenario(
        ["Galvanic Bombardment"],
        ["Mountain"],
        alice_gy=["Galvanic Bombardment", "Galvanic Bombardment"],
    )
    target = scenario.creature("Colossal Dreadmaw", "bob")
    scenario.cast_and_resolve("Galvanic Bombardment", auto=True, targets=[target])
    assert target.damage == 4


def test_galvanic_bombardment_ignores_copies_in_other_graveyards():
    scenario = _scenario(["Galvanic Bombardment"], ["Mountain"], bob_gy=["Galvanic Bombardment"])
    target = scenario.creature("Colossal Dreadmaw", "bob")
    scenario.cast_and_resolve("Galvanic Bombardment", auto=True, targets=[target])
    assert target.damage == 2


def test_galvanic_bombardment_ignores_differently_named_cards_in_graveyard():
    scenario = _scenario(
        ["Galvanic Bombardment"], ["Mountain"], alice_gy=["Lightning Bolt", "Shock"]
    )
    target = scenario.creature("Colossal Dreadmaw", "bob")
    scenario.cast_and_resolve("Galvanic Bombardment", auto=True, targets=[target])
    assert target.damage == 2


def test_the_resolving_spell_does_not_count_itself():
    """CR 608.2n: the spell goes to the graveyard only after its instructions."""
    scenario = _scenario(["Galvanic Bombardment"], ["Mountain"], bob_bf=["Colossal Dreadmaw"])
    target = scenario.creature("Colossal Dreadmaw", "bob")
    scenario.cast_and_resolve("Galvanic Bombardment", auto=True, targets=[target])
    assert target.damage == 2


def test_feast_of_flesh_counts_every_graveyard_and_pays_the_same_x_as_life():
    scenario = _scenario(
        ["Feast of Flesh"],
        ["Swamp"],
        alice_gy=["Feast of Flesh"],
        bob_gy=["Feast of Flesh", "Feast of Flesh"],
        bob_bf=["Colossal Dreadmaw"],
    )
    target = scenario.creature("Colossal Dreadmaw", "bob")
    life = scenario.player("alice").life
    scenario.cast_and_resolve("Feast of Flesh", auto=True, targets=[target])
    assert target.damage == 4
    assert scenario.player("alice").life == life + 4


def test_feast_of_flesh_is_one_with_no_copies():
    scenario = _scenario(["Feast of Flesh"], ["Swamp"], bob_bf=["Colossal Dreadmaw"])
    target = scenario.creature("Colossal Dreadmaw", "bob")
    life = scenario.player("alice").life
    scenario.cast_and_resolve("Feast of Flesh", auto=True, targets=[target])
    assert target.damage == 1
    assert scenario.player("alice").life == life + 1


def test_kjeldoran_war_cry_pumps_by_one_plus_copies_in_all_graveyards():
    scenario = _scenario(
        ["Kjeldoran War Cry"],
        ["Plains", "Plains"],
        alice_gy=["Kjeldoran War Cry"],
        bob_gy=["Kjeldoran War Cry"],
        alice_bf=["Grizzly Bears"],
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.cast_and_resolve("Kjeldoran War Cry", auto=True)
    assert (bears.power, bears.toughness) == (5, 5)


def test_kjeldoran_war_cry_alone_is_plus_one():
    scenario = _scenario(["Kjeldoran War Cry"], ["Plains", "Plains"], alice_bf=["Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.cast_and_resolve("Kjeldoran War Cry", auto=True)
    assert (bears.power, bears.toughness) == (3, 3)


def test_goblin_gathering_makes_two_plus_one_per_copy_in_your_graveyard():
    """ "Create a number of 1/1 red Goblin creature tokens equal to two plus the
    number of cards named Goblin Gathering in your graveyard." - the resolving
    spell is still on the stack, so with one copy already there it is three."""
    scenario = _scenario(["Goblin Gathering"], ["Mountain"] * 3, alice_gy=["Goblin Gathering"])
    scenario.cast_and_resolve("Goblin Gathering", auto=True)
    goblins = [
        s for s in scenario.game.permanents_controlled_by("alice") if s.name == "Goblin Token"
    ]
    assert len(goblins) == 3


def test_goblin_gathering_alone_makes_two():
    scenario = _scenario(["Goblin Gathering"], ["Mountain"] * 3)
    scenario.cast_and_resolve("Goblin Gathering", auto=True)
    goblins = [
        s for s in scenario.game.permanents_controlled_by("alice") if s.name == "Goblin Token"
    ]
    assert len(goblins) == 2


def test_take_inventory_draws_one_plus_one_per_copy_in_your_graveyard():
    """ "Draw a card, then draw cards equal to the number of cards named Take
    Inventory in your graveyard." - the same named count on a draw amount."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Take Inventory"],
            library=["Forest"] * 6,
            battlefield=["Island", "Island"],
            graveyard=["Take Inventory", "Take Inventory"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve("Take Inventory", auto=True)
    assert len(scenario.player("alice").hand) == 3
