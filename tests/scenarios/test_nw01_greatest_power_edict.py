"""The greatest-power edict: "each opponent sacrifices a creature with the
greatest power among creatures that player controls."

Listed card (NW-01, task T3): **Crackling Doom** - "deals 2 damage to each
opponent. Each opponent sacrifices a creature with the greatest power among
creatures that player controls."

Second printing that proves the reader is a template, not a card (legal in
Modern, in no deck list): **Consumed by Greed** (the targeted wording,
"target opponent sacrifices a creature with the greatest power among
creatures they control").

Rules, each read with `mise run rules:find` in the session that wrote this
file:

- **CR 701.21a** - to sacrifice a permanent, its controller moves it from the
  battlefield directly to its owner's graveyard; sacrificing is not
  destroying, so regeneration and indestructible do nothing about it.
- **CR 115.10a** - the permanent is not "target", so hexproof, shroud and
  protection do not stop the edict.
- **CR 608.2h** - the greatest power is read as the effect applies, per
  player.
- **CR 101.4** - with several choosing players, APNAP order, every choice made
  before anything leaves.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def _board(*, hand=(), alice_battlefield=(), bob_battlefield=(), alice_graveyard=()) -> Scenario:
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=list(hand),
            battlefield=list(alice_battlefield),
            graveyard=list(alice_graveyard),
        )
        .player("bob", battlefield=list(bob_battlefield))
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


_DOOM_MANA = ["Mountain", "Plains", "Swamp"]


def _doom(*, bob, alice=()):
    return _board(
        hand=["Crackling Doom"], alice_battlefield=[*_DOOM_MANA, *alice], bob_battlefield=bob
    )


def test_crackling_doom_deals_two_and_the_opponent_sacrifices_their_biggest_creature():
    scenario = _doom(bob=["Grizzly Bears", "Hill Giant", "Colossal Dreadmaw"])

    scenario.cast_and_resolve("Crackling Doom", auto=True)

    assert scenario.player("bob").life == 18
    assert scenario.find("Colossal Dreadmaw", Zone.GRAVEYARD, "bob") is not None
    assert scenario.creature("Hill Giant", "bob").zone is Zone.BATTLEFIELD
    assert scenario.creature("Grizzly Bears", "bob").zone is Zone.BATTLEFIELD


def test_crackling_doom_leaves_the_casters_own_creatures_alone():
    scenario = _doom(bob=["Grizzly Bears"], alice=["Colossal Dreadmaw"])

    scenario.cast_and_resolve("Crackling Doom", auto=True)

    assert scenario.find("Grizzly Bears", Zone.GRAVEYARD, "bob") is not None
    assert scenario.creature("Colossal Dreadmaw", "alice").zone is Zone.BATTLEFIELD
    assert scenario.player("alice").life == 20


def test_crackling_doom_with_no_creature_only_deals_the_damage():
    scenario = _doom(bob=[])

    scenario.cast_and_resolve("Crackling Doom", auto=True)

    assert scenario.player("bob").life == 18


def test_crackling_doom_a_tie_for_greatest_power_is_the_opponents_choice():
    scenario = _doom(bob=["Hill Giant", "Hill Giant", "Grizzly Bears"])
    giants = [c for c in scenario.game.battlefield if c.name == "Hill Giant"]
    scenario.will_choose_cards(giants[1], username="bob")

    scenario.cast_and_resolve("Crackling Doom", auto=True)

    assert giants[1].zone is Zone.GRAVEYARD
    assert giants[0].zone is Zone.BATTLEFIELD
    assert scenario.creature("Grizzly Bears", "bob").zone is Zone.BATTLEFIELD


def test_crackling_doom_a_lone_greatest_creature_is_not_a_question():
    scenario = _doom(bob=["Hill Giant", "Grizzly Bears"])

    scenario.cast_and_resolve("Crackling Doom", auto=True)

    assert scenario.questions_asked() == []
    assert scenario.find("Hill Giant", Zone.GRAVEYARD, "bob") is not None


def test_crackling_doom_greatest_power_is_read_as_it_resolves():
    """CR 608.2h: four +1/+1 counters make Hill Giant a 7/7, past the 6/6
    Dreadmaw, so the Giant is the one sacrificed."""
    scenario = _doom(bob=["Hill Giant", "Colossal Dreadmaw"])
    giant = scenario.creature("Hill Giant", "bob")
    giant.add_counters(Counter.PLUS_ONE, 4)

    scenario.cast_and_resolve("Crackling Doom", auto=True)

    assert giant.zone is Zone.GRAVEYARD
    assert scenario.creature("Colossal Dreadmaw", "bob").zone is Zone.BATTLEFIELD


def test_crackling_doom_indestructible_does_not_stop_a_sacrifice():
    """CR 701.21a: sacrificing is not destroying."""
    scenario = _doom(bob=["Darksteel Gargoyle", "Grizzly Bears"])

    scenario.cast_and_resolve("Crackling Doom", auto=True)

    assert scenario.find("Darksteel Gargoyle", Zone.GRAVEYARD, "bob") is not None


def test_crackling_doom_ignores_noncreature_permanents():
    scenario = _doom(bob=["Glorious Anthem", "Grizzly Bears"])

    scenario.cast_and_resolve("Crackling Doom", auto=True)

    assert scenario.find("Grizzly Bears", Zone.GRAVEYARD, "bob") is not None
    assert scenario.find("Glorious Anthem", Zone.BATTLEFIELD, "bob") is not None


# -- Consumed by Greed: the targeted wording --------------------------------------


def test_consumed_by_greed_target_opponent_sacrifices_their_biggest_creature():
    scenario = _board(
        hand=["Consumed by Greed"],
        alice_battlefield=["Swamp"] * 3,
        alice_graveyard=["Runeclaw Bear"],
        bob_battlefield=["Grizzly Bears", "Colossal Dreadmaw"],
    )
    bear = scenario.find("Runeclaw Bear", Zone.GRAVEYARD, "alice")

    scenario.cast_and_resolve("Consumed by Greed", auto=True, targets=["bob", bear])

    assert scenario.find("Colossal Dreadmaw", Zone.GRAVEYARD, "bob") is not None
    assert scenario.creature("Grizzly Bears", "bob").zone is Zone.BATTLEFIELD
