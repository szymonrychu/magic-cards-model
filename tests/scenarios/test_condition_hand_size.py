"""Hand-size conditions: "you have no cards in hand", "that player has two or
fewer cards in hand", "exactly seven", "more cards in hand than each
opponent" - as an intervening "if" and as an "Activate only if".

Rules verified with `mise run rules:find` in the session that wrote this file:

- **CR 402.1** - "The hand is where a player holds cards that have been
  drawn." Every count here is of that zone, read as the condition is asked.
- **CR 603.4** - an intervening "if" is checked as the trigger event occurs:
  false then, and the ability never triggers.
- **CR 608.2a** - checked again as the ability resolves: false by then, and
  "the ability is removed from the stack and does nothing".
- **CR 602.5b** - "Activate only if <condition>" is a restriction that
  "continues to apply to that object even if its controller changes".
- **CR 109.5** - "you" is the controller of the triggered ability's source,
  or the player who activated the ability.
- **CR 506.2** - during combat in a two-player game, the nonactive player is
  the defending player.

`machines/conditions/player.py` reads every one of these shapes as one
template - a subject ("you", "that player", "defending player", "an
opponent", "a player", "each player"), a count ("no", "a", "exactly N [or
M]", "N or more", "N or fewer", "fewer than N") or a comparison ("more ...
than each opponent"), and a zone. Before it, each failed closed with an
`InterveningIfNotice`, or refused the activation as unread.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _next_upkeep(scenario) -> None:
    """Run the rest of this turn out and stop in the next one's upkeep."""
    scenario.turn.advance_to(Step.CLEANUP)
    scenario.advance()  # the new turn's untap step
    scenario.advance()  # its upkeep


def _to_declare_attackers(scenario) -> None:
    scenario.advance()  # beginning of combat
    scenario.advance()  # declare attackers


# -- "that player has N or fewer cards in hand" ------------------------------


def _muse_board(bob_hand: list[str]):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Lavaborn Muse"], library=["Plains"] * 5)
        .player("bob", hand=bob_hand, library=["Plains"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_that_player_with_two_cards_triggers_and_resolves():
    """Lavaborn Muse: "At the beginning of each opponent's upkeep, if that
    player has two or fewer cards in hand, this creature deals 3 damage to
    that player." - "that player" is the one whose upkeep began."""
    scenario = _muse_board(["Plains", "Plains"])
    _next_upkeep(scenario)
    assert scenario.turn.active_player == "bob"
    assert scenario.stack_names() == ["Lavaborn Muse's triggered ability"]
    scenario.pass_until_resolved()
    assert scenario.player("bob").life == 17
    assert scenario.game.intervening_if_notices == []


def test_that_player_with_three_cards_never_triggers():
    """CR 603.4: three cards is not "two or fewer" - nothing, and no notice."""
    scenario = _muse_board(["Plains", "Plains", "Plains"])
    _next_upkeep(scenario)
    assert scenario.stack_names() == []
    assert scenario.player("bob").life == 20
    assert scenario.game.intervening_if_notices == []


def test_that_player_drawing_before_resolution_removes_the_ability():
    """CR 608.2a: true at bob's upkeep, then bob draws a third card with the
    ability waiting - the recheck is false and it does nothing."""
    scenario = _muse_board(["Plains", "Plains"])
    _next_upkeep(scenario)
    (trigger,) = scenario.game.stack
    assert scenario.game._intervening_if_still_true(trigger)  # noqa: SLF001
    scenario.draw(username="bob")
    assert len(scenario.player("bob").hand) == 3
    assert not scenario.game._intervening_if_still_true(trigger)  # noqa: SLF001
    scenario.pass_until_resolved()
    assert scenario.game.stack_is_empty
    assert scenario.player("bob").life == 20
    assert scenario.game.intervening_if_notices == []


def test_that_player_is_not_the_controller_on_the_controllers_own_upkeep():
    """ "Each opponent's upkeep": alice's own upkeep is no trigger event at
    all, whatever alice holds."""
    scenario = _muse_board(["Plains"] * 5)
    _next_upkeep(scenario)  # bob's
    _next_upkeep(scenario)  # alice's, with an empty hand
    assert scenario.turn.active_player == "alice"
    assert scenario.player("alice").hand == []
    assert scenario.stack_names() == []


@pytest.mark.parametrize(("cards", "triggers"), [(0, True), (1, True), (2, False)])
def test_one_or_fewer_on_a_second_printing(cards, triggers):
    """Shrieking Affliction: "At the beginning of each opponent's upkeep, if
    that player has one or fewer cards in hand, they lose 3 life." - the
    boundary on both sides, zero included."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Shrieking Affliction"], library=["Plains"] * 5)
        .player("bob", hand=["Plains"] * cards, library=["Plains"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _next_upkeep(scenario)
    scenario.pass_until_resolved()
    assert scenario.player("bob").life == (17 if triggers else 20)
    assert scenario.game.intervening_if_notices == []


# -- "you have no cards in hand" / "that player has no cards in hand" --------


def _barghest_board(alice_hand: list[str], bob_hand: list[str]):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice", battlefield=["Hollowborn Barghest"], hand=alice_hand, library=["Plains"] * 5
        )
        .player("bob", hand=bob_hand, library=["Plains"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_you_have_no_cards_in_hand_on_your_upkeep():
    """Hollowborn Barghest: "At the beginning of your upkeep, if you have no
    cards in hand, each opponent loses 2 life." - "you" is alice."""
    scenario = _barghest_board([], ["Plains"])
    _next_upkeep(scenario)  # bob's: he holds a card, so its second ability is quiet
    assert scenario.stack_names() == []
    _next_upkeep(scenario)  # alice's
    assert scenario.stack_names() == ["Hollowborn Barghest's triggered ability"]
    scenario.pass_until_resolved()
    assert scenario.player("bob").life == 18
    assert scenario.player("alice").life == 20


def test_you_holding_a_card_does_not_trigger():
    scenario = _barghest_board(["Plains"], ["Plains"])
    _next_upkeep(scenario)
    _next_upkeep(scenario)
    assert scenario.stack_names() == []
    assert scenario.game.intervening_if_notices == []


def test_that_player_has_no_cards_on_an_opponents_upkeep():
    """ "At the beginning of each opponent's upkeep, if that player has no
    cards in hand, they lose 2 life." - bob's empty hand, whatever alice has."""
    scenario = _barghest_board(["Plains"], [])
    _next_upkeep(scenario)
    assert scenario.stack_names() == ["Hollowborn Barghest's triggered ability"]
    scenario.pass_until_resolved()
    assert scenario.player("bob").life == 18


# -- "you have a card in hand" ------------------------------------------------


@pytest.mark.parametrize(("hand", "returns"), [(["Plains"], True), ([], False)])
def test_you_have_a_card_in_hand(hand, returns):
    """Imaginary Pet: "At the beginning of your upkeep, if you have a card in
    hand, return this creature to its owner's hand." - "a card" is one or
    more."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Imaginary Pet"], hand=hand, library=["Plains"] * 5)
        .player("bob", library=["Plains"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _next_upkeep(scenario)
    _next_upkeep(scenario)
    scenario.pass_until_resolved()
    pet = scenario.find("Imaginary Pet", Zone.HAND if returns else Zone.BATTLEFIELD, "alice")
    assert pet.zone is (Zone.HAND if returns else Zone.BATTLEFIELD)
    assert scenario.game.intervening_if_notices == []


# -- "defending player has ..." -----------------------------------------------


def _attack_with(scenario, name: str) -> None:
    _to_declare_attackers(scenario)
    scenario.attack_with(scenario.creature(name, "alice"))


@pytest.mark.parametrize(("cards", "triggers"), [(2, True), (3, False)])
def test_defending_player_has_two_or_fewer(cards, triggers):
    """Reaper of Night: "Whenever this creature attacks, if defending player
    has two or fewer cards in hand, it gains flying until end of turn."
    (CR 506.2: bob, the nonactive player, is the defending player.)"""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Reaper of Night"], library=["Plains"] * 5)
        .player("bob", hand=["Plains"] * cards, library=["Plains"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _attack_with(scenario, "Reaper of Night")
    assert scenario.stack_names() == (["Reaper of Night's triggered ability"] if triggers else [])
    assert scenario.game.intervening_if_notices == []


@pytest.mark.parametrize(("alice", "bob", "triggers"), [(1, 2, True), (2, 2, False)])
def test_defending_player_has_more_cards_than_you(alice, bob, triggers):
    """Robber of the Rich: "Whenever this creature attacks, if defending
    player has more cards in hand than you, ..." - a tie is not more."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=["Robber of the Rich"],
            hand=["Plains"] * alice,
            library=["Plains"] * 5,
        )
        .player("bob", hand=["Plains"] * bob, library=["Plains"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _attack_with(scenario, "Robber of the Rich")
    assert len(scenario.stack_names()) == (1 if triggers else 0)
    assert scenario.game.intervening_if_notices == []


# -- "a player has more cards in hand than each other player" ---------------


@pytest.mark.parametrize(("alice", "bob", "holds"), [(1, 3, True), (3, 1, True), (2, 2, False)])
def test_a_player_has_more_than_each_other_player(alice, bob, holds):
    """Sokenzan Renegade's "if a player has more cards in hand than each other
    player" - either player can be that one, and a tie for the most makes it
    false. (Sokenzan Renegade itself is not in the pool: its bushido has no
    machine yet, so the clause is read here on a board of its own.)"""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Plains"] * alice, library=["Plains"] * 5)
        .player("bob", hand=["Plains"] * bob, library=["Plains"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    clause = "a player has more cards in hand than each other player"
    assert scenario.game.condition_holds("alice", clause) is holds
    assert scenario.game.condition_holds("bob", clause) is holds


# -- "Activate only if you have no cards in hand" ----------------------------


def test_hellbent_activation_is_refused_with_a_card_in_hand_and_allowed_without():
    """Ragamuffyn: "Hellbent - {T}, Sacrifice a creature or land: Draw a card.
    Activate only if you have no cards in hand." """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=["Ragamuffyn", "Swamp"],
            hand=["Plains"],
            library=["Island"] * 3,
        )
        .player("bob", library=["Plains"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ragamuffyn = scenario.creature("Ragamuffyn", "alice")
    refusal = scenario.why_cannot_activate(ragamuffyn)
    assert refusal == "Ragamuffyn's activation restriction is not met (CR 602.5b)"

    scenario.play_land("Plains")
    assert scenario.why_cannot_activate(ragamuffyn) is None
    scenario.activate(ragamuffyn, sacrificing=[scenario.creature("Swamp", "alice")])
    scenario.pass_until_resolved()
    assert [card.name for card in scenario.player("alice").hand] == ["Island"]
    # A card in hand again: refused again.
    assert scenario.why_cannot_activate(ragamuffyn) is not None


def test_hellbent_follows_the_activating_player_after_a_control_change():
    """CR 602.5b and CR 109.5: bob takes Ragamuffyn with Soul Ransom ("You
    control enchanted creature."). Alice's empty hand no longer matters -
    "you" is bob, and he still holds a card."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Ragamuffyn"], library=["Plains"] * 6)
        .player(
            "bob",
            hand=["Soul Ransom", "Plains"],
            battlefield=["Island", "Island", "Swamp", "Swamp"],
            library=["Plains"] * 6,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ragamuffyn = scenario.creature("Ragamuffyn", "alice")
    assert scenario.why_cannot_activate(ragamuffyn) is None  # alice: empty hand

    _next_upkeep(scenario)  # bob's turn
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve(
        "Soul Ransom",
        *scenario.untapped_sources("Island", "Island", "Swamp", "Swamp", username="bob"),
        targets=[ragamuffyn],
        username="bob",
    )
    assert scenario.game.controller_of(ragamuffyn).username == "bob"
    assert [card.name for card in scenario.player("bob").hand] == ["Plains"]
    refusal = scenario.why_cannot_activate(ragamuffyn, username="bob")
    assert refusal == "Ragamuffyn's activation restriction is not met (CR 602.5b)"

    scenario.play_land("Plains", username="bob")
    assert scenario.why_cannot_activate(ragamuffyn, username="bob") is None


def test_hellbent_activation_on_a_second_printing_resolves_when_met():
    """Keldon Megaliths: "Hellbent - {1}{R}, {T}: This land deals 1 damage to
    any target. Activate only if you have no cards in hand." """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=["Keldon Megaliths", "Mountain", "Mountain", "Mountain"],
            hand=["Lightning Bolt"],
            library=["Plains"] * 3,
        )
        .player("bob", library=["Plains"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    megaliths = scenario.creature("Keldon Megaliths", "alice")
    refusal = scenario.why_cannot_activate(megaliths, index=1)
    assert refusal == "Keldon Megaliths's activation restriction is not met (CR 602.5b)"

    scenario.cast_and_resolve(
        "Lightning Bolt", scenario.untapped_sources("Mountain")[0], targets=["bob"]
    )
    assert scenario.player("alice").hand == []
    assert scenario.why_cannot_activate(megaliths, index=1) is None
    scenario.activate(
        megaliths, *scenario.untapped_sources("Mountain", "Mountain"), index=1, targets=["bob"]
    )
    scenario.pass_until_resolved()
    assert scenario.player("bob").life == 16


# -- "exactly N [or M] cards in hand" -----------------------------------------


def test_exactly_seven_cards_in_hand():
    """Magus of the Library: "{T}: Draw a card. Activate only if you have
    exactly seven cards in hand." - six refused, seven allowed, and the draw
    that makes it eight refuses it again."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=["Magus of the Library"],
            hand=["Plains"] * 6,
            library=["Island"] * 5,
        )
        .player("bob", library=["Plains"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    magus = scenario.creature("Magus of the Library", "alice")
    assert scenario.why_cannot_activate(magus, index=1) is not None

    scenario.draw(username="alice")
    assert scenario.why_cannot_activate(magus, index=1) is None
    scenario.activate(magus, index=1)
    scenario.pass_until_resolved()
    assert len(scenario.player("alice").hand) == 8
    magus.tapped = False
    refusal = scenario.why_cannot_activate(magus, index=1)
    assert refusal == "Magus of the Library's activation restriction is not met (CR 602.5b)"


@pytest.mark.parametrize(("cards", "allowed"), [(0, True), (7, True), (1, False), (6, False)])
def test_exactly_zero_or_seven_cards_in_hand(cards, allowed):
    """The Biblioplex: "... Activate only if you have exactly zero or seven
    cards in hand." - either count, and nothing in between."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=["The Biblioplex", "Plains", "Plains"],
            hand=["Island"] * cards,
            library=["Island"] * 3,
        )
        .player("bob", library=["Plains"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    biblioplex = scenario.creature("The Biblioplex", "alice")
    refusal = scenario.why_cannot_activate(biblioplex, index=1)
    assert (refusal is None) == allowed
    if not allowed:
        assert refusal == "The Biblioplex's activation restriction is not met (CR 602.5b)"


# -- "more cards in hand than each opponent" ----------------------------------


@pytest.mark.parametrize(("alice", "bob", "allowed"), [(3, 2, True), (2, 2, False), (1, 2, False)])
def test_more_cards_in_hand_than_each_opponent(alice, bob, allowed):
    """Kitsune Bonesetter: "{T}: Prevent the next 3 damage ... Activate only if
    you have more cards in hand than each opponent." - a tie is not more."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=["Kitsune Bonesetter"],
            hand=["Plains"] * alice,
            library=["Plains"] * 3,
        )
        .player("bob", hand=["Plains"] * bob, library=["Plains"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bonesetter = scenario.creature("Kitsune Bonesetter", "alice")
    assert (scenario.why_cannot_activate(bonesetter) is None) == allowed


# -- the template, read directly -----------------------------------------------


def test_every_subject_and_count_form_is_read_against_the_live_hands():
    """The one template on a board where alice holds one card and bob three:
    each subject, count and comparison form answers, and none is unread."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Lavaborn Muse"], hand=["Plains"], library=["Plains"] * 3)
        .player("bob", hand=["Plains"] * 3, library=["Plains"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    game = scenario.game
    muse = scenario.creature("Lavaborn Muse", "alice")
    expected = {
        "you have no cards in hand": False,
        "you have a card in hand": True,
        "you have exactly one card in hand": True,
        "you have fewer than two cards in hand": True,
        "you have one or fewer cards in your hand": True,
        "an opponent has no cards in hand": False,
        "an opponent has three or more cards in hand": True,
        "each opponent has two or fewer cards in hand": False,
        "a player has one or fewer cards in hand": True,
        "each player has one or more cards in hand": True,
        "you have more cards in hand than each opponent": False,
        "an opponent has more cards in hand than you": True,
        "a player has more cards in hand than each other player": True,
        # No combat, so no defending player, and no event, so no "that player".
        "defending player has two or fewer cards in hand": False,
        "that player has no cards in hand": False,
    }
    for clause, holds in expected.items():
        assert game.condition_holds("alice", clause, muse) is holds, clause
