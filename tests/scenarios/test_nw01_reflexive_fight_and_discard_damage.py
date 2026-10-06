"""Reflexive "When you do" abilities (CR 603.12) on a *spell*: a fight whose
first fighter is the object the spell's first sentence acted on, and a
damage-to-each-creature consequence gated on an optional discard or sacrifice.

Rules verified with `mise run rules:find`:

- **CR 603.12** - a resolving spell may instruct a player to take an action
  and create a triggered ability that triggers "when [a player] [does]" it;
  the reflexive ability is its own stack object, checked immediately.
- **CR 603.12a** - paying a cost several times still triggers it once.
- **CR 603.3d / CR 601.2c** - the reflexive ability's own targets are chosen as
  it goes on the stack, not when the spell was cast.
- **CR 701.14a / CR 701.14b** - fight; one or both creatures gone or no longer
  creatures, or an illegal target, means neither fights.
- **CR 303.7a / CR 704.5z** - a second Role you control on the same permanent
  puts every Role but the newest into its owner's graveyard.
- **CR 608.2b** - a target that is illegal on resolution is not affected.
- **CR 107.3a** - X in the reflexive ability's text is the number worked out
  when the ability was created ("the greatest mana value among cards
  discarded this way").

Reported cards: Curse of the Werefox, Ill-Timed Explosion. Off-set second
printings: Back for More ("it fights", the returned creature) and Lithobraking
("sacrifice an artifact", a fixed amount).
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _all_notices(scenario) -> list[object]:
    game = scenario.game
    found: list[object] = list(game.continuous_effects.layer_notices)
    for name in type(game).model_fields:
        if name.endswith("_notices"):
            found.extend(getattr(game, name))
    return found


def _unexpected_notices(scenario) -> list[object]:
    """Every notice except CR 115.6's own "up to one target, and there is none"
    record - a legal game state `Game._ask_trigger_targets` logs on purpose."""
    return [
        notice
        for notice in _all_notices(scenario)
        if getattr(getattr(notice, "kind", None), "value", None) != "no_legal_targets"
    ]


def _power_toughness(scenario, card):
    return (
        scenario.game.continuous_effects.board(scenario.game.battlefield).of(card).power_toughness
    )


def _roles_on(scenario, creature):
    return [
        permanent
        for permanent in scenario.game.battlefield
        if permanent.card.subtypes
        and "Role" in permanent.card.subtypes
        and permanent.attached_to == creature.id
    ]


# --------------------------------------------------------------------------
# Curse of the Werefox: Role token, then "When you do, that creature fights"
# --------------------------------------------------------------------------


def _curse(alice_bf, bob_bf, *, copies=1, forests=3):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Curse of the Werefox"] * copies,
            battlefield=["Forest"] * forests + alice_bf,
            library=["Forest"],
        )
        .player("bob", battlefield=bob_bf, library=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_curse_of_the_werefox_role_pump_applies_before_the_reflexive_fight():
    scenario = _curse(["Grizzly Bears"], ["Llanowar Elves"])
    bears = scenario.creature("Grizzly Bears", "alice")
    elves = scenario.creature("Llanowar Elves", "bob")
    sources = scenario.untapped_sources("Forest", "Forest", "Forest")
    scenario.choose_trigger_targets("Curse of the Werefox", [elves])
    scenario.cast_and_resolve("Curse of the Werefox", *sources, targets=[bears])

    assert len(_roles_on(scenario, bears)) == 1, "the Monster Role is attached to the bear"
    assert "Curse of the Werefox's triggered ability" in scenario.stack_names(), (
        "the reflexive ability is its own object"
    )
    scenario.resolve_top()

    assert _power_toughness(scenario, bears) == (3, 3), "Monster Role: +1/+1"
    assert elves.zone is Zone.GRAVEYARD
    assert bears.damage == 1
    assert _all_notices(scenario) == []


def test_curse_of_the_werefox_fights_with_the_roles_power_not_the_printed_one():
    scenario = _curse(["Grizzly Bears"], ["Wall of Omens"])
    bears = scenario.creature("Grizzly Bears", "alice")
    wall = scenario.creature("Wall of Omens", "bob")
    sources = scenario.untapped_sources("Forest", "Forest", "Forest")
    scenario.choose_trigger_targets("Curse of the Werefox", [wall])
    scenario.cast_and_resolve("Curse of the Werefox", *sources, targets=[bears])
    scenario.resolve_top()

    assert wall.damage == 3


def test_curse_of_the_werefox_up_to_one_with_no_opposing_creature_still_makes_the_role():
    scenario = _curse(["Grizzly Bears"], [])
    bears = scenario.creature("Grizzly Bears", "alice")
    sources = scenario.untapped_sources("Forest", "Forest", "Forest")
    scenario.cast_and_resolve("Curse of the Werefox", *sources, targets=[bears])
    scenario.resolve_top()

    assert len(_roles_on(scenario, bears)) == 1
    assert bears.damage == 0
    assert _unexpected_notices(scenario) == []


def test_curse_of_the_werefox_fighter_gone_before_the_reflexive_ability_resolves_means_no_fight():
    scenario = _curse(["Grizzly Bears"], ["Llanowar Elves"])
    bears = scenario.creature("Grizzly Bears", "alice")
    elves = scenario.creature("Llanowar Elves", "bob")
    sources = scenario.untapped_sources("Forest", "Forest", "Forest")
    scenario.choose_trigger_targets("Curse of the Werefox", [elves])
    scenario.cast_and_resolve("Curse of the Werefox", *sources, targets=[bears])
    scenario.game.exile_permanent(bears)
    scenario.resolve_top()

    assert elves.damage == 0
    assert elves.zone is Zone.BATTLEFIELD


def test_curse_of_the_werefox_a_second_role_replaces_the_first():
    """CR 303.7a / CR 704.5z: two Roles you control on one creature - only the
    newest stays."""
    scenario = _curse(["Grizzly Bears"], [], copies=2, forests=6)
    bears = scenario.creature("Grizzly Bears", "alice")
    first = scenario.untapped_sources("Forest", "Forest", "Forest")
    scenario.cast_and_resolve("Curse of the Werefox", *first, targets=[bears])
    scenario.resolve_top()
    second = scenario.untapped_sources("Forest", "Forest", "Forest")
    scenario.cast_and_resolve("Curse of the Werefox", *second, targets=[bears])
    scenario.resolve_top()

    assert len(_roles_on(scenario, bears)) == 1
    assert _power_toughness(scenario, bears) == (3, 3)


def test_curse_of_the_werefox_you_cannot_aim_the_fight_at_your_own_creature():
    scenario = _curse(["Grizzly Bears", "Llanowar Elves"], ["Wall of Omens"])
    bears = scenario.creature("Grizzly Bears", "alice")
    elves = scenario.creature("Llanowar Elves", "alice")
    wall = scenario.creature("Wall of Omens", "bob")
    sources = scenario.untapped_sources("Forest", "Forest", "Forest")
    scenario.choose_trigger_targets("Curse of the Werefox", [elves])
    scenario.cast_and_resolve("Curse of the Werefox", *sources, targets=[bears])
    scenario.resolve_top()

    assert elves.damage == 0, "'you don't control' rejects the elves as the fight target"
    assert wall.damage == 0


# --------------------------------------------------------------------------
# Back for More: the same shape, "it" is the creature the first sentence returned
# --------------------------------------------------------------------------


def _back_for_more(bob_bf):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Back for More"],
            battlefield=["Swamp", "Forest", "Forest", "Forest", "Forest", "Swamp"],
            graveyard=["Elder Gargaroth"],
            library=["Forest"],
        )
        .player("bob", battlefield=bob_bf, library=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_back_for_more_the_returned_creature_fights():
    scenario = _back_for_more(["Serra Angel"])
    angel = scenario.creature("Serra Angel", "bob")
    gargaroth = scenario.find("Elder Gargaroth", Zone.GRAVEYARD, "alice")
    sources = scenario.untapped_sources("Swamp", "Forest", "Forest", "Forest", "Forest", "Swamp")
    scenario.choose_trigger_targets("Back for More", [angel])
    scenario.cast_and_resolve("Back for More", *sources, targets=[gargaroth])
    assert gargaroth.zone is Zone.BATTLEFIELD
    scenario.resolve_top()

    assert angel.zone is Zone.GRAVEYARD, "a 6/6 kills a 4/4"
    assert gargaroth.damage == 4
    assert _all_notices(scenario) == []


def test_back_for_more_with_no_opposing_creature_just_returns():
    scenario = _back_for_more([])
    gargaroth = scenario.find("Elder Gargaroth", Zone.GRAVEYARD, "alice")
    sources = scenario.untapped_sources("Swamp", "Forest", "Forest", "Forest", "Forest", "Swamp")
    scenario.cast_and_resolve("Back for More", *sources, targets=[gargaroth])
    scenario.resolve_top()

    assert gargaroth.zone is Zone.BATTLEFIELD
    assert gargaroth.damage == 0


# --------------------------------------------------------------------------
# Ill-Timed Explosion: "you may discard two cards. When you do, X damage ..."
# --------------------------------------------------------------------------


def _explosion(hand_extra, library, alice_bf, bob_bf):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Ill-Timed Explosion", *hand_extra],
            battlefield=["Island", "Island", "Mountain", "Mountain", *alice_bf],
            library=library,
        )
        .player("bob", battlefield=bob_bf, library=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_ill_timed_explosion_deals_the_greatest_mana_value_discarded_to_each_creature():
    scenario = _explosion(
        ["Elder Gargaroth", "Lightning Bolt"],
        ["Forest", "Forest"],
        ["Grizzly Bears"],
        ["Elder Gargaroth"],
    )
    gargaroth_in_hand = scenario.find("Elder Gargaroth", Zone.HAND, "alice")
    forest = scenario.find("Forest", Zone.LIBRARY, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    big = scenario.creature("Elder Gargaroth", "bob")
    sources = scenario.untapped_sources("Island", "Island", "Mountain", "Mountain")
    scenario.will_take_the_may(True)
    scenario.will_discard(gargaroth_in_hand, forest)
    scenario.cast_and_resolve("Ill-Timed Explosion", *sources)
    assert "Ill-Timed Explosion's triggered ability" in scenario.stack_names(), (
        "the reflexive ability is on the stack"
    )
    scenario.resolve_top()

    assert big.damage == 5, "X is the greatest mana value among the discarded cards (5 and 0)"
    assert bears.zone is Zone.GRAVEYARD, "each creature, yours included"
    assert gargaroth_in_hand.zone is Zone.GRAVEYARD
    assert _all_notices(scenario) == []


def test_ill_timed_explosion_x_ignores_the_high_cost_card_you_kept():
    scenario = _explosion(
        ["Elder Gargaroth", "Lightning Bolt"],
        ["Forest", "Forest"],
        [],
        ["Elder Gargaroth"],
    )
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "alice")
    forest = scenario.find("Forest", Zone.LIBRARY, "alice")
    big = scenario.creature("Elder Gargaroth", "bob")
    sources = scenario.untapped_sources("Island", "Island", "Mountain", "Mountain")
    scenario.will_take_the_may(True)
    scenario.will_discard(bolt, forest)
    scenario.cast_and_resolve("Ill-Timed Explosion", *sources)
    scenario.resolve_top()

    assert big.damage == 1, "Bolt (1) and a Forest (0) were discarded; the Gargaroth stayed"


def test_ill_timed_explosion_declining_the_discard_does_nothing_more():
    scenario = _explosion(
        ["Lightning Bolt"], ["Forest", "Forest"], ["Grizzly Bears"], ["Elder Gargaroth"]
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    sources = scenario.untapped_sources("Island", "Island", "Mountain", "Mountain")
    scenario.will_take_the_may(False)
    scenario.cast_and_resolve("Ill-Timed Explosion", *sources)

    assert "Ill-Timed Explosion" not in scenario.stack_names()
    assert bears.zone is Zone.BATTLEFIELD
    assert len(scenario.player("alice").hand) == 3, "two drawn cards, one Bolt, nothing discarded"
    assert _all_notices(scenario) == []


def test_ill_timed_explosion_zero_mana_value_discards_deal_zero_damage():
    scenario = _explosion([], ["Forest", "Forest"], ["Grizzly Bears"], [])
    bears = scenario.creature("Grizzly Bears", "alice")
    sources = scenario.untapped_sources("Island", "Island", "Mountain", "Mountain")
    scenario.will_take_the_may(True)
    scenario.cast_and_resolve("Ill-Timed Explosion", *sources)
    scenario.resolve_top()

    assert bears.zone is Zone.BATTLEFIELD
    assert bears.damage == 0
    assert len(scenario.player("alice").graveyard) == 3, "the spell and the two discarded Forests"


# --------------------------------------------------------------------------
# Lithobraking: the sacrifice flavour of the same spell-level reflexive shape
# --------------------------------------------------------------------------


def _lithobraking():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Lithobraking"],
            battlefield=["Mountain", "Mountain", "Mountain", "Grizzly Bears"],
            library=["Forest"],
        )
        .player("bob", battlefield=["Wall of Omens", "Llanowar Elves"], library=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_lithobraking_sacrificing_the_artifact_it_made_deals_two_to_each_creature():
    scenario = _lithobraking()
    bears = scenario.creature("Grizzly Bears", "alice")
    wall = scenario.creature("Wall of Omens", "bob")
    elves = scenario.creature("Llanowar Elves", "bob")
    sources = scenario.untapped_sources("Mountain", "Mountain", "Mountain")
    scenario.will_take_the_may(True)
    scenario.cast_and_resolve("Lithobraking", *sources)
    assert "Lithobraking's triggered ability" in scenario.stack_names(), (
        "the reflexive ability waits on the stack"
    )
    scenario.resolve_top()

    assert "Lander Token" not in scenario.battlefield_names()
    assert wall.damage == 2
    assert elves.zone is Zone.GRAVEYARD
    assert bears.zone is Zone.GRAVEYARD
    assert _all_notices(scenario) == []


def test_lithobraking_declining_the_sacrifice_keeps_the_lander_and_deals_nothing():
    scenario = _lithobraking()
    wall = scenario.creature("Wall of Omens", "bob")
    sources = scenario.untapped_sources("Mountain", "Mountain", "Mountain")
    scenario.will_take_the_may(False)
    scenario.cast_and_resolve("Lithobraking", *sources)

    assert "Lander Token" in scenario.battlefield_names()
    assert wall.damage == 0
    assert "Lithobraking" not in scenario.stack_names()
