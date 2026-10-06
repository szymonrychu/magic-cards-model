"""Scenario: a damage spell whose next clause refers back to the damage's
target - "that creature", "that permanent", "that player", "it".

CR 608.2c reads a spell's text in order and lets later text modify the meaning
of earlier text; the referent of "that creature" is the one target announced
under CR 115.1. Four shapes, each on a listed card and on a second printing
that is not a listed card and not in any deck:

- **"If <the target has a quality>, <src> deals M damage [to it] instead."**
  (CR 614.1a: "instead" replaces the base instruction; exactly one amount is
  dealt, chosen as the spell resolves.) Bring Low (a +1/+1 counter), Burning
  Hands (green); second printings Electrostatic Bolt ("If it's an artifact
  creature") and Hexgold Slash (toxic).
- **"<src> deals M damage to that creature's controller"**, conditional
  (Burn the Impure: infect; Rending Flame: a Spirit, with "also") or not
  (Fodder Launch after a -5/-5; Carnival's "and 1 damage to that permanent's
  controller"). The controller is the one when the spell began to resolve: a
  target that dies to the first half still has a last-known controller
  (CR 608.2h).
- **"That player [or that planeswalker's controller] discards N cards."**
  Carnage, Blightning; second printings Ozai's Cruelty and Rakdos's Return.
- **"If that permanent is a Chandra planeswalker, you may discard a card. If
  you do, draw a card."** (Chandra's Defeat) - the "if you do" is CR 608.2d's
  optional discard.

Rules looked up with `mise run rules:find` in the session that wrote this:

- CR 608.2b - the only target illegal: the spell doesn't resolve, so no
  damage to the controller, no discard.
- CR 608.2c, CR 608.2d, CR 608.2h, CR 614.1a - as above.
- CR 702.90b - infect (Burn the Impure's condition is the keyword, read off
  the creature as the spell resolves).
- CR 702.164a - toxic is a static ability "toxic N" (Hexgold Slash says only
  "has toxic").
- CR 701.9a - to discard a card is to move it from hand to graveyard.
- CR 118.8a - Fodder Launch's sacrificed Goblin is an additional cost.
- CR 120.3c - damage dealt to a planeswalker removes loyalty counters.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.support import card_support
from tests.cards import card
from tests.scenarios.harness import Scenario

LISTED = (
    "Bring Low",
    "Burning Hands",
    "Burn the Impure",
    "Carnival // Carnage",
    "Blightning",
    "Chandra's Defeat",
    "Fodder Launch",
)
SECOND_PRINTINGS = (
    "Electrostatic Bolt",
    "Hexgold Slash",
    "Rending Flame",
    "Ozai's Cruelty",
    "Rakdos's Return",
)


@pytest.mark.parametrize("name", LISTED + SECOND_PRINTINGS)
def test_every_printing_is_fully_handled(name):
    bad = [c for c in card_support(card(name)).clauses if c.outcome != "handled"]
    assert not bad, (name, bad)


def _scenario(*, hand, lands, alice_battlefield=(), bob_battlefield=(), bob_hand=()) -> Scenario:
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Mountain"] * 3,
            hand=list(hand),
            battlefield=list(lands) + list(alice_battlefield),
        )
        .player(
            "bob", library=["Mountain"] * 3, hand=list(bob_hand), battlefield=list(bob_battlefield)
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _cast(scenario: Scenario, name: str, target, **kwargs):
    return scenario.cast_and_resolve(name, targets=[target], auto=True, **kwargs)


def _red(*extra: str) -> list[str]:
    return ["Mountain"] * 6 + list(extra)


# -- "... deals M damage instead" -----------------------------------------------------


def test_bring_low_deals_three_without_a_counter_and_five_with_one():
    plain = _scenario(hand=["Bring Low"], lands=_red(), bob_battlefield=["Craw Wurm"])
    wurm = plain.creature("Craw Wurm", "bob")
    _cast(plain, "Bring Low", wurm)
    assert wurm.damage == 3 and wurm.zone is Zone.BATTLEFIELD, "3 of the Wurm's 4 toughness"

    grown = _scenario(hand=["Bring Low"], lands=_red(), bob_battlefield=["Craw Wurm"])
    big = grown.creature("Craw Wurm", "bob")
    big.add_counters("+1/+1", 1)
    _cast(grown, "Bring Low", big)
    assert big.zone is Zone.GRAVEYARD, "5 damage is exactly lethal to a 7/5: instead of 3"


def test_a_counter_on_some_other_creature_does_not_upgrade_the_damage():
    scenario = _scenario(
        hand=["Bring Low"], lands=_red(), bob_battlefield=["Craw Wurm", "Grizzly Bears"]
    )
    scenario.creature("Grizzly Bears", "bob").add_counters("+1/+1", 1)
    wurm = scenario.creature("Craw Wurm", "bob")

    _cast(scenario, "Bring Low", wurm)

    assert wurm.damage == 3, "that creature has no counter"


def test_burning_hands_deals_six_to_a_green_permanent_and_two_to_any_other():
    green = _scenario(hand=["Burning Hands"], lands=_red(), bob_battlefield=["Craw Wurm"])
    wurm = green.creature("Craw Wurm", "bob")
    _cast(green, "Burning Hands", wurm)
    assert wurm.zone is Zone.GRAVEYARD, "6 damage instead of 2"

    red = _scenario(hand=["Burning Hands"], lands=_red(), bob_battlefield=["Hill Giant"])
    giant = red.creature("Hill Giant", "bob")
    _cast(red, "Burning Hands", giant)
    assert giant.damage == 2


def test_burning_hands_on_a_planeswalker_reads_that_permanents_color():
    scenario = _scenario(
        hand=["Burning Hands"], lands=_red(), bob_battlefield=["Chandra, Flame's Fury"]
    )
    walker = next(c for c in scenario.game.battlefield if c.name == "Chandra, Flame's Fury")

    _cast(scenario, "Burning Hands", walker)

    assert walker.counter_count("loyalty") == 2, "red: the base 2, loyalty 4 -> 2"


def test_electrostatic_bolt_deals_four_to_an_artifact_creature_two_to_the_rest():
    scenario = _scenario(
        hand=["Electrostatic Bolt", "Electrostatic Bolt"],
        lands=_red(),
        bob_battlefield=["Sliver Construct", "Craw Wurm"],
    )
    construct = scenario.creature("Sliver Construct", "bob")
    wurm = scenario.creature("Craw Wurm", "bob")

    scenario.cast_and_resolve("Electrostatic Bolt", targets=[wurm], auto=True)
    scenario.cast_and_resolve("Electrostatic Bolt", targets=[construct], auto=True)

    assert wurm.damage == 2
    assert construct.zone is Zone.GRAVEYARD, "an artifact creature: 4 instead of 2"


def test_hexgold_slash_deals_four_to_a_creature_with_toxic():
    scenario = _scenario(
        hand=["Hexgold Slash", "Hexgold Slash"],
        lands=_red(),
        bob_battlefield=["Myr Convert", "Craw Wurm"],
    )
    convert = scenario.creature("Myr Convert", "bob")
    convert.add_counters("+1/+1", 2)  # a 4/3: 2 damage would not kill it
    wurm = scenario.creature("Craw Wurm", "bob")

    scenario.cast_and_resolve("Hexgold Slash", targets=[wurm], auto=True)
    scenario.cast_and_resolve("Hexgold Slash", targets=[convert], auto=True)

    assert wurm.damage == 2, "no toxic: the base 2"
    assert convert.zone is Zone.GRAVEYARD, "toxic: 4 instead of 2"


# -- damage to that creature's controller --------------------------------------------


def test_burn_the_impure_hits_the_controller_of_an_infect_creature_too():
    scenario = _scenario(hand=["Burn the Impure"], lands=_red(), bob_battlefield=["Glistener Elf"])
    elf = scenario.creature("Glistener Elf", "bob")

    _cast(scenario, "Burn the Impure", elf)

    assert elf.zone is Zone.GRAVEYARD
    assert scenario.player("bob").life == 17, "the controller is read though the elf died"


def test_burn_the_impure_spares_the_controller_of_a_creature_without_infect():
    scenario = _scenario(hand=["Burn the Impure"], lands=_red(), bob_battlefield=["Grizzly Bears"])

    _cast(scenario, "Burn the Impure", scenario.creature("Grizzly Bears", "bob"))

    assert scenario.player("bob").life == 20


def test_burn_the_impure_on_your_own_infect_creature_hurts_you():
    scenario = _scenario(
        hand=["Burn the Impure"], lands=_red(), alice_battlefield=["Glistener Elf"]
    )

    _cast(scenario, "Burn the Impure", scenario.creature("Glistener Elf", "alice"))

    assert scenario.player("alice").life == 17


def test_rending_flame_adds_two_to_the_controller_of_a_spirit():
    scenario = _scenario(
        hand=["Rending Flame", "Rending Flame"],
        lands=_red(),
        bob_battlefield=["Spirit of the Labyrinth", "Craw Wurm"],
    )
    spirit = scenario.creature("Spirit of the Labyrinth", "bob")
    wurm = scenario.creature("Craw Wurm", "bob")

    scenario.cast_and_resolve("Rending Flame", targets=[wurm], auto=True)
    assert scenario.player("bob").life == 20, "not a Spirit: no extra damage"
    scenario.cast_and_resolve("Rending Flame", targets=[spirit], auto=True)

    assert spirit.zone is Zone.GRAVEYARD
    assert scenario.player("bob").life == 18


def test_carnival_hits_the_creature_and_its_controller():
    scenario = _scenario(
        hand=["Carnival // Carnage"],
        lands=["Mountain"],
        bob_battlefield=["Grizzly Bears", "Chandra, Flame's Fury"],
    )
    bears = scenario.creature("Grizzly Bears", "bob")

    scenario.cast_and_resolve("Carnival", targets=[bears], auto=True)

    assert bears.damage == 1
    assert scenario.player("bob").life == 19


def test_carnival_on_a_planeswalker_hits_that_permanents_controller():
    scenario = _scenario(
        hand=["Carnival // Carnage"], lands=["Mountain"], bob_battlefield=["Chandra, Flame's Fury"]
    )
    walker = next(c for c in scenario.game.battlefield if c.name == "Chandra, Flame's Fury")

    scenario.cast_and_resolve("Carnival", targets=[walker], auto=True)

    assert walker.counter_count("loyalty") == 3
    assert scenario.player("bob").life == 19


def test_fodder_launch_shrinks_the_creature_and_damages_its_controller():
    scenario = _scenario(
        hand=["Fodder Launch"],
        lands=["Swamp"] * 4,
        alice_battlefield=["Goblin Guide"],
        bob_battlefield=["Craw Wurm"],
    )
    goblin = scenario.creature("Goblin Guide", "alice")
    wurm = scenario.creature("Craw Wurm", "bob")

    _cast(scenario, "Fodder Launch", wurm, sacrificing=[goblin])
    scenario.game.check_state_based_actions()

    assert goblin.zone is Zone.GRAVEYARD, "the additional cost"
    assert wurm.zone is Zone.GRAVEYARD, "-5/-5 kills the 6/4"
    assert scenario.player("bob").life == 15, "5 to its controller, read after it died"


def test_fodder_launch_with_the_creature_gone_does_nothing_to_the_controller():
    """CR 608.2b: the only target is illegal, so the spell doesn't resolve."""
    scenario = _scenario(
        hand=["Fodder Launch", "Lightning Bolt"],
        lands=["Swamp"] * 4,
        alice_battlefield=["Goblin Guide", "Mountain"],
        bob_battlefield=["Grizzly Bears"],
    )
    goblin = scenario.creature("Goblin Guide", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    swamps = scenario.untapped_sources(*(["Swamp"] * 4), username="alice")
    scenario.cast_onto_stack("Fodder Launch", *swamps, targets=[bears], sacrificing=[goblin])
    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    scenario.cast_onto_stack("Lightning Bolt", mountain, targets=[bears])
    scenario.pass_until_resolved()
    scenario.pass_until_resolved()

    assert scenario.player("bob").life == 20


# -- "That player discards ..." ---------------------------------------------------


def test_carnage_damages_the_opponent_and_makes_them_discard_two():
    scenario = _scenario(
        hand=["Carnival // Carnage"],
        lands=["Swamp", "Swamp", "Mountain", "Mountain"],
        bob_hand=["Forest", "Island", "Plains"],
    )
    keep, drop_a, drop_b = scenario.player("bob").hand
    scenario.will_discard(drop_a, drop_b, username="bob")

    casting = scenario.cast("Carnival", targets=None)
    casting.cast_as_split_half("Carnage")
    casting.choose_targets(["bob"])
    scenario.auto_pay(casting.begin_paying(), username="alice")
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert scenario.player("bob").life == 17
    assert scenario.player("bob").hand == [keep]
    assert drop_a.zone is Zone.GRAVEYARD and drop_b.zone is Zone.GRAVEYARD


def test_blightning_makes_a_targeted_player_discard():
    scenario = _scenario(
        hand=["Blightning"],
        lands=["Swamp", "Mountain", "Mountain"],
        bob_hand=["Forest", "Island"],
    )
    forest, island = scenario.player("bob").hand
    scenario.will_discard(forest, island, username="bob")

    _cast(scenario, "Blightning", "bob")

    assert scenario.player("bob").life == 17
    assert scenario.player("bob").hand == []


def test_blightning_on_a_planeswalker_makes_its_controller_discard():
    scenario = _scenario(
        hand=["Blightning"],
        lands=["Swamp", "Mountain", "Mountain"],
        bob_battlefield=["Chandra, Flame's Fury"],
        bob_hand=["Forest", "Island"],
    )
    walker = next(c for c in scenario.game.battlefield if c.name == "Chandra, Flame's Fury")
    forest, island = scenario.player("bob").hand
    scenario.will_discard(forest, island, username="bob")

    _cast(scenario, "Blightning", walker)

    assert walker.counter_count("loyalty") == 1, "3 damage from 4 loyalty"
    assert scenario.player("bob").life == 20, "the planeswalker took it, not the player"
    assert scenario.player("bob").hand == [], "that planeswalker's controller discards"


def test_blightning_with_a_short_hand_discards_what_there_is():
    scenario = _scenario(
        hand=["Blightning"], lands=["Swamp", "Mountain", "Mountain"], bob_hand=["Forest"]
    )

    _cast(scenario, "Blightning", "bob")

    assert scenario.player("bob").hand == []


def test_ozais_cruelty_is_the_same_pair_over_a_different_amount():
    scenario = _scenario(
        hand=["Ozai's Cruelty"], lands=["Swamp"] * 3, bob_hand=["Forest", "Island", "Plains"]
    )
    first, second, third = scenario.player("bob").hand
    scenario.will_discard(first, second, username="bob")

    _cast(scenario, "Ozai's Cruelty", "bob")

    assert scenario.player("bob").life == 18
    assert scenario.player("bob").hand == [third]


def test_rakdos_return_discards_as_many_as_x_damage():
    scenario = _scenario(
        hand=["Rakdos's Return"],
        lands=["Swamp", "Mountain", "Swamp", "Mountain", "Swamp"],
        bob_hand=["Forest", "Island", "Plains"],
    )
    first, second, third = scenario.player("bob").hand
    scenario.will_discard(first, second, third, username="bob")

    casting = scenario.cast("Rakdos's Return", targets=["bob"])
    casting.x_value = 3
    casting.determine_cost(x_value=3)
    scenario.auto_pay(casting.begin_paying(), username="alice")
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert scenario.player("bob").life == 17
    assert scenario.player("bob").hand == []


# -- Chandra's Defeat -----------------------------------------------------------------


def test_chandras_defeat_on_a_chandra_offers_a_discard_and_a_draw():
    scenario = _scenario(
        hand=["Chandra's Defeat", "Forest"],
        lands=["Mountain"],
        bob_battlefield=["Chandra, Flame's Fury"],
    )
    walker = next(c for c in scenario.game.battlefield if c.name == "Chandra, Flame's Fury")
    forest = scenario.find("Forest", Zone.HAND, "alice")
    library_top = scenario.player("alice").library[0]
    scenario.will_take_the_may(True, username="alice")
    scenario.will_discard(forest, username="alice")

    _cast(scenario, "Chandra's Defeat", walker)

    assert walker.zone is Zone.GRAVEYARD
    assert forest.zone is Zone.GRAVEYARD
    assert library_top.zone is Zone.HAND, "drew for the discard"


def test_chandras_defeat_declined_discards_and_draws_nothing():
    scenario = _scenario(
        hand=["Chandra's Defeat", "Forest"],
        lands=["Mountain"],
        bob_battlefield=["Chandra, Flame's Fury"],
    )
    forest = scenario.find("Forest", Zone.HAND, "alice")
    walker = next(c for c in scenario.game.battlefield if c.name == "Chandra, Flame's Fury")
    scenario.will_take_the_may(False, username="alice")

    _cast(scenario, "Chandra's Defeat", walker)

    assert forest.zone is Zone.HAND
    assert len(scenario.player("alice").hand) == 1


def test_chandras_defeat_on_a_red_creature_that_is_no_chandra_asks_nothing():
    scenario = _scenario(
        hand=["Chandra's Defeat", "Forest"], lands=["Mountain"], bob_battlefield=["Hill Giant"]
    )
    giant = scenario.creature("Hill Giant", "bob")
    forest = scenario.find("Forest", Zone.HAND, "alice")

    _cast(scenario, "Chandra's Defeat", giant)

    assert giant.zone is Zone.GRAVEYARD
    assert forest.zone is Zone.HAND
    assert not scenario.questions_asked()
