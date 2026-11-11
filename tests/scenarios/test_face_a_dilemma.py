"""Scenario: facing a dilemma (CR 700.17), the trk "Face a dilemma" cards, and
the readers they needed.

Every CR number here was read in full with `mise run rules:find` in the
session that wrote this file:

- CR 700.17: "A player faces a dilemma whenever they choose one or more modes
  for a spell or ability. Some effects refer to whether a player has 'faced a
  dilemma this turn.' This means that player has chosen one or more modes for
  a spell or ability this turn. An effect that refers to the number of
  dilemmas a player has faced in a turn counts the number of spells and/or
  abilities the player has chosen one or more modes for that turn."
- CR 700.2a: the controller of a modal spell or activated ability chooses the
  modes as part of casting or activating it; CR 700.2b: a modal triggered
  ability's controller chooses as it is put on the stack.
- CR 700.2g: "A copy of a modal spell or ability copies the mode(s) chosen for
  it. The controller of the copy can't choose a different mode." - so a copy
  is nobody's dilemma.
- CR 608.2d: a player other than the controller can be the one who makes a
  resolution-time choice (Tell Me What You See, Terrapact Intimidator).
- CR 608.2g: a spell cast during the resolution of another (Captain Benjamin
  Sisko, The Caretaker, Chaos Wand, Etali, Primal Storm).
- CR 603.4: the intervening "if" of The Caretaker's end-step trigger.
- CR 113.6m: Gabriel Lorca's "return this card from your graveyard" works
  from the graveyard.

"Choose one at random" (Outlaws' Merriment) is not a dilemma: the game picks
the mode, nobody chooses one (CR 700.17's "whenever they choose").

Proof cards, real printings from other sets, worded differently from the trk
card that needed the reader:

- Chaos Wand (activated, "an instant or sorcery card", a bottom-the-rest
  rider) for The Caretaker's exile-until-then-cast-that-card reader.
- Terrapact Intimidator ("create two Lander tokens" / "put two +1/+1
  counters") for Tell Me What You See's "target opponent may have you"
  reader.
- Etali, Primal Storm ("from among those cards", no mana value bound) for
  Captain Benjamin Sisko's widened cast-any-number reader.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.conditions.history import DILEMMAS_FACED
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from magic_cards_model.models.game import Game

from .harness import Scenario

COMMAND = "Kolaghan's Command"
DISCARD = 2  # "Target player discards a card."
TWO_DAMAGE = 4  # "Kolaghan's Command deals 2 damage to any target."


def dilemmas(game: Game, player: str = "alice") -> int:
    return game.turn_count(DILEMMAS_FACED, player)


def resolve_all(scenario: Scenario) -> None:
    while scenario.stack_names():
        scenario.resolve_top()


def cast_command(scenario: Scenario, *, username: str = "alice", at: str = "bob") -> None:
    """Kolaghan's Command with two modes chosen (CR 601.2b): one spell, one
    dilemma however many modes."""
    casting = scenario.cast(COMMAND, username)
    casting.choose_modes([DISCARD, TWO_DAMAGE])
    casting.choose_targets([at, at])
    sources = scenario.untapped_sources("Swamp", "Mountain", "Mountain", username=username)
    scenario.pay_with(casting.begin_paying(), *sources)
    scenario.put_on_stack(casting)


def command_board(watcher: str, *, commands: int = 1, watcher_owner: str = "alice") -> Scenario:
    lands = ["Swamp", "Mountain", "Mountain"] * commands
    alice_battlefield = [*lands, watcher] if watcher_owner == "alice" else lands
    bob_battlefield = [watcher] if watcher_owner == "bob" else []
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[COMMAND] * commands,
            battlefield=alice_battlefield,
            library=["Island"] * 5,
        )
        .player("bob", hand=["Island"] * 3, battlefield=bob_battlefield, library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def activate_kargan(scenario: Scenario) -> None:
    """Kargan Intimidator's "{1}: Choose one that hasn't been chosen this turn -"
    - a modal activated ability (CR 700.2a). The unscripted answer is its
    first mode, "This creature gets +1/+1 until end of turn"."""
    kargan = scenario.creature("Kargan Intimidator", "alice")
    (mountain,) = scenario.untapped_sources("Mountain")
    scenario.activate(kargan, mountain)


def controlled_names(scenario: Scenario, username: str) -> list[str]:
    return [state.name for state in scenario.game.permanents_controlled_by(username)]


def to_end_step(scenario: Scenario) -> None:
    while scenario.step is not Step.END_STEP:
        scenario.advance()


# --------------------------------------------------------------------------
# What is, and is not, a dilemma
# --------------------------------------------------------------------------


def test_two_modes_of_one_spell_are_one_dilemma() -> None:
    scenario = command_board("Melkotian Adjudicator")
    cast_command(scenario)

    assert dilemmas(scenario.game) == 1
    assert scenario.stack_names() == [COMMAND, "Melkotian Adjudicator's triggered ability"]
    resolve_all(scenario)
    adjudicator = scenario.creature("Melkotian Adjudicator", "alice")
    assert adjudicator.counter_count(Counter.PLUS_ONE) == 1
    assert scenario.player("bob").life == 18


def test_a_spell_with_no_modes_is_no_dilemma() -> None:
    scenario = (
        Scenario()
        .player("alice", hand=["Lightning Bolt"], battlefield=["Mountain", "Seven of Nine"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (mountain,) = scenario.untapped_sources("Mountain")
    scenario.cast_onto_stack("Lightning Bolt", mountain, targets=["bob"])

    assert scenario.stack_names() == ["Lightning Bolt"]
    assert dilemmas(scenario.game) == 0


def test_a_modal_activated_ability_is_a_dilemma() -> None:
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Kargan Intimidator", "Mountain", "Obsidian Order Operative"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    activate_kargan(scenario)

    assert dilemmas(scenario.game) == 1
    resolve_all(scenario)
    assert scenario.player("bob").life == 19
    assert scenario.player("alice").life == 21
    kargan = scenario.creature("Kargan Intimidator", "alice")
    assert scenario.game.power_of(kargan) == 4, "the chosen mode resolved too"


def test_a_modal_triggered_ability_is_a_dilemma_as_it_goes_on_the_stack() -> None:
    """Casting Ainok Guide chooses no mode; its enters trigger does, as it is
    put on the stack (CR 700.2b) - that is the dilemma."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Ainok Guide"],
            battlefield=["Forest", "Forest", "Seven of Nine"],
            library=["Island"] * 5,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    hand_before = len(scenario.player("alice").hand)
    scenario.cast_and_resolve("Ainok Guide", *scenario.untapped_sources("Forest", "Forest"))

    assert dilemmas(scenario.game) == 1
    assert scenario.stack_names() == [
        "Ainok Guide's triggered ability",
        "Seven of Nine's triggered ability",
    ]
    resolve_all(scenario)
    assert len(scenario.player("alice").hand) == hand_before  # Guide left, one card drawn
    guide = scenario.creature("Ainok Guide", "alice")
    assert guide.counter_count(Counter.PLUS_ONE) == 1


def test_an_opponents_modal_spell_is_not_your_dilemma() -> None:
    scenario = command_board("Elim Garak, Simple Tailor", watcher_owner="bob")
    cast_command(scenario)

    assert dilemmas(scenario.game, "alice") == 1
    assert dilemmas(scenario.game, "bob") == 0
    assert scenario.stack_names() == [COMMAND], "bob's Elim Garak watches only bob"


def test_a_copy_of_a_modal_spell_is_no_dilemma() -> None:
    """CR 700.2g: the copy copies the modes; its controller chooses none."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[COMMAND, "Reverberate"],
            battlefield=["Swamp", "Mountain", "Mountain", "Mountain", "Mountain"],
        )
        .player("bob", hand=["Island"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    cast_command(scenario)
    command = scenario.find(COMMAND, Zone.STACK, "alice")
    scenario.cast_onto_stack(
        "Reverberate", *scenario.untapped_sources("Mountain", "Mountain"), targets=[command]
    )
    scenario.resolve_top()  # Reverberate: the copy goes on the stack

    assert len(scenario.game.stack) == 2
    assert dilemmas(scenario.game) == 1
    resolve_all(scenario)
    assert scenario.player("bob").life == 16, "the copy kept both modes"
    assert dilemmas(scenario.game) == 1


def test_a_mode_chosen_at_random_is_no_dilemma() -> None:
    scenario = (
        Scenario()
        .player("alice", battlefield=["Outlaws' Merriment", "Seven of Nine"], library=["Island"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.UNTAP)
    scenario.advance()
    assert scenario.step is Step.UPKEEP
    assert scenario.stack_names() == ["Outlaws' Merriment's triggered ability"]
    assert dilemmas(scenario.game) == 0


def test_each_dilemma_triggers_once_and_the_count_resets_next_turn() -> None:
    scenario = command_board("Elim Garak, Simple Tailor", commands=2)
    cast_command(scenario)
    resolve_all(scenario)
    cast_command(scenario)
    resolve_all(scenario)

    assert dilemmas(scenario.game) == 2
    assert scenario.player("bob").life == 20 - 2 * 2 - 2 * 2
    assert scenario.player("alice").life == 24
    while scenario.turn.active_player == "alice":
        scenario.advance()
        resolve_all(scenario)
    assert dilemmas(scenario.game) == 0


# --------------------------------------------------------------------------
# One test per trk card
# --------------------------------------------------------------------------


def test_captain_benjamin_sisko_creates_an_officer_for_each_dilemma() -> None:
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Captain Benjamin Sisko", "Kargan Intimidator", "Mountain", "Mountain"],
            library=["Island"] * 5,
        )
        .player("bob", library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    activate_kargan(scenario)
    resolve_all(scenario)
    activate_kargan(scenario)
    resolve_all(scenario)
    assert dilemmas(scenario.game) == 2

    to_end_step(scenario)
    resolve_all(scenario)
    officers = [
        state
        for state in scenario.game.permanents_controlled_by("alice")
        if state.token and "Officer" in state.subtypes
    ]
    assert len(officers) == 2
    assert all((o.power, o.toughness) == (1, 1) for o in officers)


def test_captain_benjamin_sisko_casts_spells_up_to_the_officer_count_for_free() -> None:
    """Two Officers (Sisko and Obsidian Order Operative): Memnite (0) and
    Grizzly Bears (2) may be cast for free, Hill Giant (4) may not."""
    lands = ["Plains", "Island", "Swamp", "Mountain", "Forest", "Forest", "Forest"]
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Captain Benjamin Sisko", "Obsidian Order Operative", *lands],
            library=["Hill Giant", "Grizzly Bears", "Forest", "Memnite", "Island", "Plains"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sisko = scenario.creature("Captain Benjamin Sisko", "alice")
    scenario.will_take_the_may(True, times=None)
    scenario.activate(sisko, *scenario.untapped_sources(*lands))
    resolve_all(scenario)

    names = controlled_names(scenario, "alice")
    assert "Grizzly Bears" in names
    assert "Memnite" in names
    giant = scenario.find("Hill Giant", Zone.EXILE, "alice")
    assert giant.zone is Zone.EXILE
    assert scenario.find("Plains", Zone.LIBRARY, "alice").zone is Zone.LIBRARY


def test_the_caretaker_casts_an_opponents_card_after_a_dilemma() -> None:
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["The Caretaker", "Kargan Intimidator", "Mountain"],
            library=["Island"] * 5,
        )
        .player("bob", library=["Forest", "Grizzly Bears", "Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    activate_kargan(scenario)
    resolve_all(scenario)
    scenario.will_take_the_may(True, times=None)
    to_end_step(scenario)
    assert scenario.stack_names() == ["The Caretaker's triggered ability"]
    resolve_all(scenario)

    bears = scenario.creature("Grizzly Bears", "alice")
    assert bears.controller == "alice"
    assert bears.owner == "bob"
    assert scenario.find("Forest", Zone.EXILE, "bob").zone is Zone.EXILE
    assert [card.name for card in scenario.player("bob").library] == ["Island"]


def test_the_caretaker_does_nothing_without_a_dilemma() -> None:
    scenario = (
        Scenario()
        .player("alice", battlefield=["The Caretaker"], library=["Island"] * 5)
        .player("bob", library=["Forest", "Grizzly Bears", "Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    to_end_step(scenario)

    assert scenario.stack_names() == []
    assert len(scenario.player("bob").library) == 3


def test_jett_reno_grows_with_each_dilemma() -> None:
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Jett Reno, Problem Solver", "Kargan Intimidator", "Mountain"],
            library=["Island"] * 5,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    activate_kargan(scenario)
    resolve_all(scenario)

    jett = scenario.creature("Jett Reno, Problem Solver", "alice")
    assert jett.counter_count(Counter.PLUS_ONE) == 1


_HER_POWER = (
    "'If her power is 4 or greater' is pronoun self-reference, the T-110 B4 reader; "
    "this batch rebases on B4 for it (docs/plans T-110 implementation, B2)"
)


@pytest.mark.xfail(strict=True, reason=_HER_POWER)
def test_jett_reno_surveils_when_she_becomes_tapped() -> None:
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Jett Reno, Problem Solver"],
            library=["Island", "Plains", "Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    top = scenario.top_of_library(1)
    scenario.surveil_to_graveyard(top[0], username="alice")
    scenario.attack_with(scenario.creature("Jett Reno, Problem Solver", "alice"))
    resolve_all(scenario)

    assert top[0].zone is Zone.GRAVEYARD


@pytest.mark.xfail(strict=True, reason=_HER_POWER)
def test_jett_reno_draws_instead_at_power_four() -> None:
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Jett Reno, Problem Solver"],
            library=["Island", "Plains", "Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    jett = scenario.creature("Jett Reno, Problem Solver", "alice")
    jett.add_counters(Counter.PLUS_ONE, 3)
    top = scenario.top_of_library(1)
    scenario.attack_with(jett)
    resolve_all(scenario)

    assert top[0].zone is Zone.HAND


def test_melkotian_adjudicator_gets_a_counter_for_each_dilemma() -> None:
    scenario = command_board("Melkotian Adjudicator", commands=2)
    cast_command(scenario)
    resolve_all(scenario)
    cast_command(scenario)
    resolve_all(scenario)

    adjudicator = scenario.creature("Melkotian Adjudicator", "alice")
    assert adjudicator.counter_count(Counter.PLUS_ONE) == 2


def test_elim_garak_drains_two_for_a_dilemma() -> None:
    scenario = command_board("Elim Garak, Simple Tailor")
    cast_command(scenario)
    assert scenario.stack_names() == [COMMAND, "Elim Garak, Simple Tailor's triggered ability"]
    scenario.resolve_top()

    assert scenario.player("bob").life == 18
    assert scenario.player("alice").life == 22


def test_gabriel_lorca_returns_from_the_graveyard_when_you_pay_black() -> None:
    scenario = (
        Scenario()
        .player(
            "alice",
            graveyard=["Gabriel Lorca, Mirror Menace"],
            battlefield=["Kargan Intimidator", "Mountain", "Swamp"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_take_the_may(True, source="Gabriel Lorca, Mirror Menace")
    activate_kargan(scenario)
    assert "Gabriel Lorca, Mirror Menace's triggered ability" in scenario.stack_names()
    resolve_all(scenario)

    lorca = scenario.find("Gabriel Lorca, Mirror Menace", Zone.HAND, "alice")
    assert lorca.zone is Zone.HAND
    assert scenario.find("Swamp", Zone.BATTLEFIELD, "alice").tapped, "{B} was paid"


def test_gabriel_lorca_does_nothing_on_the_battlefield() -> None:
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Gabriel Lorca, Mirror Menace", "Kargan Intimidator", "Mountain", "Swamp"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    activate_kargan(scenario)

    assert dilemmas(scenario.game) == 1
    assert not any("Gabriel Lorca" in name for name in scenario.stack_names()), (
        "the ability returns this card from the graveyard, so it works only there (CR 113.6m)"
    )


def test_obsidian_order_operative_drains_one_for_a_dilemma() -> None:
    scenario = command_board("Obsidian Order Operative")
    cast_command(scenario)
    resolve_all(scenario)

    assert scenario.player("bob").life == 20 - 2 - 1
    assert scenario.player("alice").life == 21


def test_tell_me_what_you_see_opponent_lets_you_draw() -> None:
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Tell Me What You See"],
            battlefield=["Swamp", "Swamp"],
            library=["Island", "Plains", "Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    library = scenario.top_of_library(1)
    scenario.will_take_the_may(True, username="bob")
    scenario.cast_and_resolve("Tell Me What You See", *scenario.untapped_sources("Swamp", "Swamp"))
    resolve_all(scenario)

    assert library[0].zone is Zone.HAND
    assert scenario.player("bob").life == 20


def test_tell_me_what_you_see_opponent_refuses_and_loses_four() -> None:
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Tell Me What You See"],
            battlefield=["Swamp", "Swamp"],
            library=["Island", "Plains", "Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    top = scenario.top_of_library(1)
    scenario.will_take_the_may(False, username="bob")
    scenario.surveil_to_graveyard(top[0], username="alice")
    hand_before = len(scenario.player("alice").hand)
    scenario.cast_and_resolve("Tell Me What You See", *scenario.untapped_sources("Swamp", "Swamp"))
    resolve_all(scenario)

    assert scenario.player("bob").life == 16
    assert top[0].zone is Zone.GRAVEYARD, "surveil 1 put it into the graveyard"
    assert len(scenario.player("alice").hand) == hand_before - 1


def test_tell_me_what_you_see_returns_to_hand_on_a_dilemma() -> None:
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Tell Me What You See", "Kargan Intimidator", "Mountain"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_take_the_may(True, source="Tell Me What You See")
    activate_kargan(scenario)
    resolve_all(scenario)

    enchantment = scenario.find("Tell Me What You See", Zone.HAND, "alice")
    assert enchantment.zone is Zone.HAND


def test_seven_of_nine_draws_for_a_dilemma() -> None:
    scenario = command_board("Seven of Nine")
    hand_before = len(scenario.player("alice").hand)
    cast_command(scenario)
    resolve_all(scenario)

    assert len(scenario.player("alice").hand) == hand_before - 1 + 1


# --------------------------------------------------------------------------
# Proof cards for the readers
# --------------------------------------------------------------------------


def test_chaos_wand_casts_the_instant_and_bottoms_the_rest() -> None:
    scenario = (
        Scenario()
        .player("alice", battlefield=["Chaos Wand", "Mountain", "Mountain", "Mountain", "Mountain"])
        .player("bob", library=["Forest", "Grizzly Bears", "Lightning Bolt", "Island", "Plains"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    wand = scenario.find("Chaos Wand", Zone.BATTLEFIELD, "alice")
    scenario.will_take_the_may(True, times=None)
    scenario.will_choose_targets("bob", source="Lightning Bolt")
    scenario.activate(wand, *scenario.untapped_sources(*["Mountain"] * 4), targets=["bob"])
    resolve_all(scenario)

    bolt = scenario.find("Lightning Bolt", Zone.GRAVEYARD, "bob")
    assert bolt.zone is Zone.GRAVEYARD
    assert scenario.player("bob").life == 17
    library = [card.name for card in scenario.player("bob").library]
    assert library[:2] == ["Island", "Plains"]
    assert sorted(library[2:]) == ["Forest", "Grizzly Bears"]


def test_terrapact_intimidator_opponent_gives_landers() -> None:
    scenario = (
        Scenario()
        .player("alice", hand=["Terrapact Intimidator"], battlefield=["Mountain", "Mountain"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_take_the_may(True, username="bob")
    scenario.cast_and_resolve(
        "Terrapact Intimidator", *scenario.untapped_sources("Mountain", "Mountain")
    )
    resolve_all(scenario)

    landers = [s for s in scenario.game.permanents_controlled_by("alice") if "Lander" in s.name]
    assert len(landers) == 2
    kavu = scenario.creature("Terrapact Intimidator", "alice")
    assert kavu.counter_count(Counter.PLUS_ONE) == 0


def test_terrapact_intimidator_opponent_refuses_and_it_grows() -> None:
    scenario = (
        Scenario()
        .player("alice", hand=["Terrapact Intimidator"], battlefield=["Mountain", "Mountain"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_take_the_may(False, username="bob")
    scenario.cast_and_resolve(
        "Terrapact Intimidator", *scenario.untapped_sources("Mountain", "Mountain")
    )
    resolve_all(scenario)

    kavu = scenario.creature("Terrapact Intimidator", "alice")
    assert kavu.counter_count(Counter.PLUS_ONE) == 2
    assert not [s for s in scenario.game.permanents_controlled_by("alice") if "Lander" in s.name]


def test_etali_primal_storm_casts_from_among_those_cards() -> None:
    scenario = (
        Scenario()
        .player("alice", battlefield=["Etali, Primal Storm"], library=["Grizzly Bears", "Island"])
        .player("bob", library=["Memnite", "Island"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.will_take_the_may(True, times=None)
    scenario.attack_with(scenario.creature("Etali, Primal Storm", "alice"))
    resolve_all(scenario)

    assert "Grizzly Bears" in controlled_names(scenario, "alice")
    assert "Memnite" in controlled_names(scenario, "alice")
