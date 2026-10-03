"""Turn-long delayed triggered abilities a spell creates beside a mass pump
or -X/-X: Death Frenzy's "Whenever a creature dies this turn, you gain 1
life.", Gnawing Crescendo's "Whenever a nontoken creature you control dies
this turn, create a 1/1 black Rat creature token with "This token can't
block."", Warhost's Frenzy's "If this spell was kicked, whenever a creature
you control dies this turn, draw a card." and Noxious Assault's "Whenever a
creature blocks this turn, its controller gets a poison counter."

Every CR number here was read in full with `mise run rules:find` in the
session that wrote this file:

- **CR 603.7b** - a delayed triggered ability with a stated duration such
  as "this turn" triggers every time its event occurs, not only once.
- **CR 700.4** - "dies" means put into a graveyard from the battlefield.
- **CR 702.33d** - a spell whose kicker cost was paid "has been kicked".
- **CR 122.1f** - poison counters are a kind of counter a player gets.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _settle(scenario) -> None:
    """State-based actions, then every trigger they put on the stack."""
    for _ in range(20):
        scenario.state_based_actions()
        if scenario.game.stack_is_empty and not scenario.pending_triggers:
            return
        scenario.pass_until_resolved()
    raise AssertionError("the stack never emptied")


def _next_turn(scenario) -> None:
    turns = scenario.turn.turns_taken
    while scenario.turn.turns_taken == turns:
        scenario.advance()
        _settle(scenario)


def _bolt(scenario, target, username="alice") -> None:
    (mountain, *_) = scenario.untapped_sources("Mountain", username=username)
    scenario.cast_onto_stack("Lightning Bolt", mountain, username=username, targets=[target])
    scenario.pass_until_resolved()
    _settle(scenario)


def _cast(scenario, spell, *lands) -> None:
    scenario.cast_onto_stack(spell, *scenario.untapped_sources(*lands))
    scenario.pass_until_resolved()
    _settle(scenario)


# -- Death Frenzy: "Whenever a creature dies this turn, you gain 1 life." ----


def _frenzy_board(*, alice=(), bob=(), bob_hand=()):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Death Frenzy", "Lightning Bolt"],
            battlefield=["Swamp", "Swamp", "Swamp", "Forest", "Forest", "Mountain", *alice],
            library=["Swamp"] * 10,
        )
        .player(
            "bob",
            hand=list(bob_hand),
            battlefield=["Mountain", *bob],
            library=["Mountain"] * 10,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_death_frenzy_gains_a_life_for_every_creature_its_minus_two_kills():
    scenario = _frenzy_board(alice=["Grizzly Bears"], bob=["Grizzly Bears", "Llanowar Elves"])
    _cast(scenario, "Death Frenzy", "Swamp", "Swamp", "Swamp", "Forest", "Forest")

    assert scenario.player("alice").life == 23
    assert scenario.player("bob").life == 20


def test_death_frenzy_triggers_on_a_creature_dying_later_this_turn():
    scenario = _frenzy_board(bob=["Hill Giant"])
    giant = scenario.creature("Hill Giant", "bob")
    _cast(scenario, "Death Frenzy", "Swamp", "Swamp", "Swamp", "Forest", "Forest")
    assert scenario.player("alice").life == 20

    _bolt(scenario, giant)

    assert giant.zone is Zone.GRAVEYARD
    assert scenario.player("alice").life == 21


def test_death_frenzy_does_not_trigger_next_turn():
    scenario = _frenzy_board(bob=["Hill Giant"], bob_hand=["Lightning Bolt"])
    giant = scenario.creature("Hill Giant", "bob")
    _cast(scenario, "Death Frenzy", "Swamp", "Swamp", "Swamp", "Forest", "Forest")
    _next_turn(scenario)
    scenario.start_at(Step.PRECOMBAT_MAIN)

    _bolt(scenario, giant, username="bob")

    assert giant.zone is Zone.GRAVEYARD
    assert scenario.player("alice").life == 20


# -- Gnawing Crescendo ------------------------------------------------------


def _crescendo_board(*, alice=(), bob=()):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Gnawing Crescendo", "Raise the Alarm", "Lightning Bolt", "Lightning Bolt"],
            battlefield=["Mountain"] * 5 + ["Plains"] * 2 + list(alice),
            library=["Mountain"] * 10,
        )
        .player("bob", battlefield=list(bob), library=["Forest"] * 10)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _rats(scenario):
    return [card for card in scenario.game.permanents_controlled_by("alice") if card.name.startswith("Rat")]


def test_crescendo_makes_a_rat_that_cannot_block_when_a_nontoken_creature_dies():
    scenario = _crescendo_board(alice=["Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears", "alice")
    _cast(scenario, "Gnawing Crescendo", "Mountain", "Mountain", "Mountain")
    assert scenario.game.characteristics_of(bears).power == 4

    _bolt(scenario, bears)

    (rat,) = _rats(scenario)
    assert "This token can't block." in scenario.game.characteristics_of(rat).abilities


def test_crescendo_makes_no_rat_for_a_token_or_an_opponents_creature():
    scenario = _crescendo_board(bob=["Grizzly Bears"])
    _cast(scenario, "Raise the Alarm", "Plains", "Plains")
    _cast(scenario, "Gnawing Crescendo", "Mountain", "Mountain", "Mountain")
    soldier = next(c for c in scenario.game.permanents_controlled_by("alice") if c.name.startswith("Soldier"))

    _bolt(scenario, soldier)
    _bolt(scenario, scenario.creature("Grizzly Bears", "bob"))

    assert _rats(scenario) == []


# -- Warhost's Frenzy: kicked vs unkicked -----------------------------------


def _warhost_board():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Warhost's Frenzy", "Lightning Bolt"],
            battlefield=["Mountain"] * 4 + ["Swamp", "Grizzly Bears"],
            library=["Island"] * 10,
        )
        .player("bob", battlefield=["Grizzly Bears"], library=["Forest"] * 10)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_kicked_warhosts_frenzy_draws_when_a_creature_you_control_dies():
    scenario = _warhost_board()
    bears = scenario.creature("Grizzly Bears", "alice")
    casting = scenario.cast("Warhost's Frenzy")
    casting.pay_kicker()
    scenario.pay_with(
        casting.begin_paying(), *scenario.untapped_sources("Mountain", "Mountain", "Mountain", "Swamp")
    )
    scenario.put_on_stack(casting)
    scenario.pass_until_resolved()
    _settle(scenario)
    hand_before = len(scenario.player("alice").hand)

    _bolt(scenario, scenario.creature("Grizzly Bears", "bob"))
    assert len(scenario.player("alice").hand) == hand_before - 1

    scenario.game.destroy(bears)
    _settle(scenario)
    assert len(scenario.player("alice").hand) == hand_before


def test_unkicked_warhosts_frenzy_draws_nothing():
    scenario = _warhost_board()
    bears = scenario.creature("Grizzly Bears", "alice")
    _cast(scenario, "Warhost's Frenzy", "Mountain", "Mountain", "Mountain")
    hand_before = len(scenario.player("alice").hand)

    scenario.game.destroy(bears)
    _settle(scenario)

    assert bears.zone is Zone.GRAVEYARD
    assert len(scenario.player("alice").hand) == hand_before


# -- Noxious Assault: "Whenever a creature blocks this turn, ..." -----------


def _assault_board():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Noxious Assault"],
            battlefield=["Forest"] * 5 + ["Grizzly Bears", "Hill Giant"],
            library=["Forest"] * 10,
        )
        .player("bob", battlefield=["Llanowar Elves", "Grizzly Bears"], library=["Forest"] * 10)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    for creature in scenario.game.permanents_controlled_by("alice"):
        creature.summoning_sick = False
    return scenario


def test_noxious_assault_poisons_the_controller_of_each_blocking_creature():
    scenario = _assault_board()
    _cast(scenario, "Noxious Assault", *["Forest"] * 5)
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "alice")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(bears, giant)
    scenario.start_at(Step.DECLARE_BLOCKERS)
    scenario.block(bears, scenario.creature("Grizzly Bears", "bob"))
    scenario.block(giant, scenario.creature("Llanowar Elves", "bob"))
    _settle(scenario)

    assert scenario.player("bob").poison == 2
    assert scenario.player("alice").poison == 0


def test_noxious_assault_does_not_poison_next_turn():
    scenario = _assault_board()
    _cast(scenario, "Noxious Assault", *["Forest"] * 5)
    _next_turn(scenario)
    bob_bears = scenario.creature("Grizzly Bears", "bob")
    bob_bears.summoning_sick = False
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(bob_bears)
    scenario.start_at(Step.DECLARE_BLOCKERS)
    scenario.block(bob_bears, scenario.creature("Hill Giant", "alice"))
    _settle(scenario)

    assert scenario.player("alice").poison == 0
