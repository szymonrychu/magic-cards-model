"""Scenario: "Until end of turn, `<creatures>` get +N/+N and gain [<keyword>
and] "`<ability>`"." - a one-shot pump that also grants a quoted ability
until end of turn, aimed at several targets or at a whole group.

Two readers in `machines/layers.py`:

- `_PUMP_AND_QUOTED_GRANT_RE`, widened from a single target to a plural one
  ("any number of target creatures [you control] each get ... and gain
  "..."") - Rabid Attack is the reported card ("... each get +1/+0 and gain
  "When this creature dies, draw a card.""), Setessan Tactics the second
  printing (no "you control", a +1/+1 pump, an *activated* quoted ability
  and a strive cost).
- `_MASS_PUMP_AND_QUOTED_GRANT_RE`, the group form "creatures you control get
  +N/+N and gain [<keyword> and] "..."" - Root Manipulation is the reported
  card (+2/+2, menace, "Whenever this creature attacks, you gain 1 life."),
  Storm the Citadel the second printing (no keyword, a combat-damage trigger
  with its own target).

Setessan Tactics and Storm the Citadel are legal in Modern and Pioneer
(Scryfall legalities, 2026-09-26) and in no deck under
`magic-cards-model-api/decks/`.

Every CR number below was looked up with `mise run rules:find` in the session
that wrote this file:

- **CR 113.10** - an effect that adds an ability says the object "gains" it.
- **CR 613.1f** - layer 6: ability-adding effects - each keyword and the
  quoted ability.
- **CR 611.2a** - "until end of turn" lasts as stated.
- **CR 611.2c** - the set of objects a resolving effect changes is fixed as
  it begins; a creature that enters later is not in it.
- **CR 603.10a** - a leaves-the-battlefield trigger looks back in time, so a
  creature that dies with the granted "When this creature dies" ability
  triggers it.
- **CR 702.111b** - a creature with menace can't be blocked except by two or
  more creatures.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import Keyword, has_keyword
from magic_cards_model.models import Zone
from magic_cards_model.support import HANDLED, classify_clauses
from tests.cards import card
from tests.scenarios.harness import Scenario

DIES_DRAW = "When this creature dies, draw a card."
ATTACKS_GAIN = "Whenever this creature attacks, you gain 1 life."
FIGHT = "{T}: This creature fights another target creature."
CITADEL = (
    "Whenever this creature deals combat damage to a player or planeswalker, destroy target "
    "artifact or enchantment defending player controls."
)


def computed(scenario):
    return scenario.game.continuous_effects.board(scenario.game.battlefield)


def notices(scenario) -> list[object]:
    game = scenario.game
    found: list[object] = list(game.continuous_effects.layer_notices)
    for name in type(game).model_fields:
        if name.endswith("_notices"):
            found.extend(getattr(game, name))
    return found


def _resolve_stack(scenario) -> None:
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()


def test_every_card_is_handled() -> None:
    for name in ("Rabid Attack", "Setessan Tactics", "Root Manipulation", "Storm the Citadel"):
        clauses = [c for c in classify_clauses(card(name)) if c.text]
        assert {c.category for c in clauses} == {HANDLED}, name


# -- Rabid Attack: any number of target creatures you control ---------------


def _rabid_board():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Rabid Attack", "Lightning Bolt"],
            battlefield=["Grizzly Bears", "Savannah Lions", "Swamp", "Swamp", "Mountain"],
            library=["Forest"] * 10,
        )
        .player("bob", battlefield=["Runeclaw Bear"], library=["Forest"] * 10)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _cast_rabid(scenario, *targets) -> None:
    sources = scenario.untapped_sources("Swamp", "Swamp", username="alice")
    scenario.cast_and_resolve("Rabid Attack", *sources, targets=list(targets))


def test_rabid_attack_pumps_and_grants_each_target() -> None:
    scenario = _rabid_board()
    bears = scenario.creature("Grizzly Bears")
    lions = scenario.creature("Savannah Lions")

    _cast_rabid(scenario, bears, lions)

    board = computed(scenario)
    assert (board.of(bears).power, board.of(bears).toughness) == (3, 2)
    assert (board.of(lions).power, board.of(lions).toughness) == (3, 1)
    assert board.of(bears).has_ability(DIES_DRAW)
    assert board.of(lions).has_ability(DIES_DRAW)
    assert notices(scenario) == []


def test_rabid_attack_leaves_an_untargeted_creature_alone() -> None:
    scenario = _rabid_board()
    bears = scenario.creature("Grizzly Bears")
    lions = scenario.creature("Savannah Lions")

    _cast_rabid(scenario, bears)

    board = computed(scenario)
    assert (board.of(lions).power, board.of(lions).toughness) == (2, 1)
    assert not board.of(lions).has_ability(DIES_DRAW)


def test_rabid_attack_cannot_target_an_opponents_creature() -> None:
    """ "target creatures you control"."""
    scenario = _rabid_board()
    runeclaw = scenario.creature("Runeclaw Bear", "bob")

    with pytest.raises(ValueError):
        scenario.cast("Rabid Attack", targets=[runeclaw])


def test_the_granted_dies_trigger_draws_a_card() -> None:
    """CR 603.10a: the ability is looked back at as the creature dies."""
    scenario = _rabid_board()
    bears = scenario.creature("Grizzly Bears")
    _cast_rabid(scenario, bears)
    hand_before = len(scenario.player().hand)

    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    scenario.cast_and_resolve("Lightning Bolt", mountain, targets=[bears])
    scenario.state_based_actions()
    _resolve_stack(scenario)

    assert bears.zone is Zone.GRAVEYARD
    # The Bolt left the hand, the trigger drew one back.
    assert len(scenario.player().hand) == hand_before


def test_a_creature_without_the_grant_draws_nothing_when_it_dies() -> None:
    scenario = _rabid_board()
    bears = scenario.creature("Grizzly Bears")
    lions = scenario.creature("Savannah Lions")
    _cast_rabid(scenario, bears)
    hand_before = len(scenario.player().hand)

    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    scenario.cast_and_resolve("Lightning Bolt", mountain, targets=[lions])
    scenario.state_based_actions()
    _resolve_stack(scenario)

    assert lions.zone is Zone.GRAVEYARD
    assert len(scenario.player().hand) == hand_before - 1


def test_rabid_attack_s_grant_ends_in_the_cleanup_step() -> None:
    scenario = _rabid_board()
    bears = scenario.creature("Grizzly Bears")
    _cast_rabid(scenario, bears)

    scenario.start_at(Step.END_STEP)
    scenario.advance()  # cleanup

    board = computed(scenario).of(bears)
    assert (board.power, board.toughness) == (2, 2)
    assert not board.has_ability(DIES_DRAW)


# -- Setessan Tactics: the second printing, an activated quoted ability -----


def test_setessan_tactics_pumps_and_grants_the_fight_ability() -> None:
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Setessan Tactics"],
            battlefield=["Grizzly Bears", "Savannah Lions", "Forest", "Forest", "Forest"],
        )
        .player("bob", battlefield=["Runeclaw Bear"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears")
    lions = scenario.creature("Savannah Lions")
    runeclaw = scenario.creature("Runeclaw Bear", "bob")
    forests = scenario.untapped_sources("Forest", "Forest", "Forest", username="alice")

    # Strive: {1}{G} plus {G} for the second target.
    scenario.cast_and_resolve("Setessan Tactics", *forests, targets=[bears, lions])

    board = computed(scenario)
    assert (board.of(bears).power, board.of(bears).toughness) == (3, 3)
    assert (board.of(lions).power, board.of(lions).toughness) == (3, 2)
    assert board.of(bears).has_ability(FIGHT)
    assert not board.of(runeclaw).has_ability(FIGHT)
    assert notices(scenario) == []

    bears.summoning_sick = False
    (index,) = [
        i
        for i, ability in enumerate(scenario.game.activated_abilities(bears))
        if ability.effect.startswith("This creature fights")
    ]
    scenario.activate(bears, index=index, targets=[runeclaw])
    _resolve_stack(scenario)
    scenario.state_based_actions()

    assert runeclaw.zone is Zone.GRAVEYARD, "the 3/3 Bears dealt 3 to the 2/2"
    assert bears.zone is Zone.BATTLEFIELD, "the Bears took 2 and has toughness 3"


# -- Root Manipulation: the whole group ------------------------------------


def _root_board(*, spell: str = "Root Manipulation", lands=None, bob=("Runeclaw Bear",)):
    lands = lands or ["Swamp", "Forest", "Forest", "Forest", "Forest"]
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[spell, "Llanowar Elves"],
            battlefield=["Grizzly Bears", "Savannah Lions", *lands],
            library=["Forest"] * 10,
        )
        .player("bob", battlefield=list(bob), library=["Forest"] * 10)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    for name in ("Grizzly Bears", "Savannah Lions"):
        scenario.creature(name).summoning_sick = False
    sources = scenario.untapped_sources(*lands, username="alice")
    scenario.cast_and_resolve(spell, *sources)
    return scenario


def test_root_manipulation_pumps_and_grants_every_creature_you_control() -> None:
    scenario = _root_board()
    bears = scenario.creature("Grizzly Bears")
    lions = scenario.creature("Savannah Lions")

    board = computed(scenario)
    assert (board.of(bears).power, board.of(bears).toughness) == (4, 4)
    assert (board.of(lions).power, board.of(lions).toughness) == (4, 3)
    for creature in (bears, lions):
        assert has_keyword(creature, Keyword.MENACE, scenario.game)
        assert board.of(creature).has_ability(ATTACKS_GAIN)
    assert notices(scenario) == []


def test_root_manipulation_leaves_an_opponents_creature_alone() -> None:
    scenario = _root_board()
    runeclaw = scenario.creature("Runeclaw Bear", "bob")

    board = computed(scenario).of(runeclaw)
    assert (board.power, board.toughness) == (2, 2)
    assert not has_keyword(runeclaw, Keyword.MENACE, scenario.game)
    assert not board.has_ability(ATTACKS_GAIN)


def test_a_creature_that_enters_afterwards_is_not_affected() -> None:
    """CR 611.2c: the group is fixed as the spell resolves."""
    scenario = _root_board()

    elves = scenario.put_onto_battlefield("Llanowar Elves", "alice")

    board = computed(scenario).of(elves)
    assert (board.power, board.toughness) == (1, 1)
    assert not has_keyword(elves, Keyword.MENACE, scenario.game)
    assert not board.has_ability(ATTACKS_GAIN)


def test_each_attacking_creature_gains_its_controller_a_life() -> None:
    scenario = _root_board()
    bears = scenario.creature("Grizzly Bears")
    lions = scenario.creature("Savannah Lions")

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(bears, lions)
    scenario.pass_until_resolved()
    _resolve_stack(scenario)

    assert scenario.player().life == 22


def test_menace_refuses_a_lone_blocker() -> None:
    """CR 702.111b."""
    scenario = _root_board()
    bears = scenario.creature("Grizzly Bears")
    runeclaw = scenario.creature("Runeclaw Bear", "bob")

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(bears)
    _resolve_stack(scenario)
    scenario.start_at(Step.DECLARE_BLOCKERS)

    with pytest.raises(ValueError):
        scenario.block(bears, runeclaw)


def test_root_manipulation_s_grants_end_in_the_cleanup_step() -> None:
    scenario = _root_board()
    bears = scenario.creature("Grizzly Bears")

    scenario.start_at(Step.END_STEP)
    scenario.advance()  # cleanup

    board = computed(scenario).of(bears)
    assert (board.power, board.toughness) == (2, 2)
    assert not has_keyword(bears, Keyword.MENACE, scenario.game)
    assert not board.has_ability(ATTACKS_GAIN)


# -- Storm the Citadel: the second printing, a targeted combat-damage trigger


def test_storm_the_citadel_destroys_an_artifact_on_combat_damage() -> None:
    scenario = _root_board(
        spell="Storm the Citadel",
        lands=["Forest"] * 5,
        bob=("Sol Ring",),
    )
    bears = scenario.creature("Grizzly Bears")
    ring = scenario.creature("Sol Ring", "bob")

    board = computed(scenario).of(bears)
    assert (board.power, board.toughness) == (4, 4)
    assert board.has_ability(CITADEL)
    assert not has_keyword(bears, Keyword.MENACE, scenario.game)
    assert notices(scenario) == []

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(bears)
    _resolve_stack(scenario)
    scenario.start_at(Step.DECLARE_BLOCKERS)
    scenario.no_blocks()
    scenario.choose_trigger_targets("Grizzly Bears", [ring])
    scenario.combat_damage()
    scenario.pass_until_resolved()
    _resolve_stack(scenario)

    assert scenario.player("bob").life == 16
    assert ring.zone is Zone.GRAVEYARD
