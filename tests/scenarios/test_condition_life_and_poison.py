"""Life, poison and library conditions: "at least 7 life more than your
starting life total", "your life total is less than your starting life
total", "you have exactly 1 life", "each player has 10 or less life", "you
have more life than an opponent", "you have the most life or are tied for
most life", "defending player is poisoned", "you have 200 or more cards in
your library".

Rules verified with `mise run rules:find` in the session that wrote this file:

- **CR 103.4** - "Each player begins the game with a starting life total of
  20. Some variant games have different starting life totals." The starting
  life total is recorded on the player as it is made (`Player.
  starting_life`), never assumed: a player made at 30 life compares against
  30.
- **CR 122.1f** - 'A player is "poisoned" if they have one or more poison
  counters.'
- **CR 401.1** - each player's deck becomes their library.
- **CR 603.4** / **CR 608.2a** - an intervening "if" is checked as the
  trigger event occurs and again as the ability resolves.
- **CR 602.5b** - "Activate only if <condition>" keeps applying after a
  control change, and **CR 109.5** makes its "you" the activating player.
- **CR 506.2** - the nonactive player of a two-player combat is the defending
  player.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.keywords import has_keyword
from magic_cards_model.models import Player
from tests.scenarios.harness import Scenario


def _next_upkeep(scenario) -> None:
    scenario.turn.advance_to(Step.CLEANUP)
    scenario.advance()  # untap
    scenario.advance()  # upkeep


def _to_declare_attackers(scenario) -> None:
    scenario.advance()  # beginning of combat
    scenario.advance()  # declare attackers


# -- the starting life total is recorded, never assumed ---------------------


def test_the_starting_life_total_is_the_life_a_player_is_made_with():
    """CR 103.4: 20 by default, and whatever a variant starts the player at -
    a decoded player keeps the value it was recorded with."""
    assert Player(username="alice").starting_life == 20
    commander = Player(username="bob", life=40)
    assert commander.starting_life == 40
    commander.life = 12
    decoded = Player.model_validate(commander.model_dump(mode="json"))
    assert (decoded.life, decoded.starting_life) == (12, 40)


# -- "at least N life more than your starting life total" -------------------


def _speaker_board(*, alice_life: int = 20, bob_hand=()):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice", life=alice_life, battlefield=["Speaker of the Heavens"], library=["Plains"] * 6
        )
        .player(
            "bob",
            hand=list(bob_hand),
            battlefield=["Island", "Island", "Swamp", "Swamp"],
            library=["Plains"] * 6,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_seven_more_than_the_starting_life_total_unlocks_the_ability():
    """Speaker of the Heavens: "{T}: Create a 4/4 white Angel creature token
    with flying. Activate only if you have at least 7 life more than your
    starting life total and only as a sorcery." - 26 is six more, 27 seven."""
    scenario = _speaker_board()
    speaker = scenario.creature("Speaker of the Heavens", "alice")
    scenario.game.gain_life("alice", 6)
    refusal = scenario.why_cannot_activate(speaker)
    assert refusal == "Speaker of the Heavens's activation restriction is not met (CR 602.5b)"

    scenario.game.gain_life("alice", 1)
    assert scenario.why_cannot_activate(speaker) is None
    scenario.activate(speaker)
    scenario.pass_until_resolved()
    assert "Angel Token" in [
        state.name for state in scenario.game.permanents_controlled_by("alice")
    ]


def test_a_higher_starting_life_total_raises_the_bar():
    """Alice began at 30 (CR 103.4's variants): 37 is the bar, not 27."""
    scenario = _speaker_board(alice_life=30)
    speaker = scenario.creature("Speaker of the Heavens", "alice")
    scenario.game.gain_life("alice", 6)
    assert scenario.player("alice").life == 36
    assert scenario.why_cannot_activate(speaker) is not None
    scenario.game.gain_life("alice", 1)
    assert scenario.why_cannot_activate(speaker) is None


def test_the_starting_life_restriction_follows_the_activating_player():
    """CR 602.5b / CR 109.5: bob takes the Speaker with Soul Ransom. Alice's
    27 life is not his - "you" is bob, at his own starting 20."""
    scenario = _speaker_board(bob_hand=["Soul Ransom"])
    speaker = scenario.creature("Speaker of the Heavens", "alice")
    scenario.game.gain_life("alice", 7)
    assert scenario.why_cannot_activate(speaker) is None

    _next_upkeep(scenario)
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve(
        "Soul Ransom",
        *scenario.untapped_sources("Island", "Island", "Swamp", "Swamp", username="bob"),
        targets=[speaker],
        username="bob",
    )
    assert scenario.game.controller_of(speaker).username == "bob"
    refusal = scenario.why_cannot_activate(speaker, username="bob")
    assert refusal == "Speaker of the Heavens's activation restriction is not met (CR 602.5b)"
    scenario.game.gain_life("bob", 7)
    assert scenario.why_cannot_activate(speaker, username="bob") is None


# -- "your life total is less than your starting life total" -----------------


@pytest.mark.parametrize(
    ("made_at", "lost", "triggers"),
    [(20, 5, True), (20, 0, False), (10, 0, False), (10, 1, True)],
)
def test_life_total_less_than_the_starting_life_total(made_at, lost, triggers):
    """Resolute Archangel: "When this creature enters, if your life total is
    less than your starting life total, it becomes equal to your starting life
    total." - a player made at 10 life is not below *their* start at 10."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            life=made_at,
            hand=["Resolute Archangel"],
            battlefield=["Plains"] * 7,
            library=["Plains"] * 3,
        )
        .player("bob", library=["Plains"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.lose_life("alice", lost)
    scenario.cast_and_resolve("Resolute Archangel", *scenario.untapped_sources(*["Plains"] * 7))
    assert len(scenario.game.stack) + len(scenario.pending_triggers) == (1 if triggers else 0)
    assert scenario.game.intervening_if_notices == []


# -- "you have N or less / more / exactly N life" ---------------------------


@pytest.mark.parametrize(("life", "triggers"), [(5, True), (1, True), (6, False)])
def test_n_or_less_life(life, triggers):
    """Arguel's Blood Fast: "At the beginning of your upkeep, if you have 5 or
    less life, you may transform Arguel's Blood Fast." """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Arguel's Blood Fast"], library=["Plains"] * 4)
        .player("bob", library=["Plains"] * 4)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.lose_life("alice", 20 - life)
    _next_upkeep(scenario)
    _next_upkeep(scenario)
    assert len(scenario.stack_names()) == (1 if triggers else 0)
    assert scenario.game.intervening_if_notices == []


@pytest.mark.parametrize(("life", "triggers"), [(1, True), (2, False)])
def test_exactly_n_life(life, triggers):
    """Near-Death Experience: "At the beginning of your upkeep, if you have
    exactly 1 life, you win the game." """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Near-Death Experience"], library=["Plains"] * 4)
        .player("bob", library=["Plains"] * 4)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.lose_life("alice", 20 - life)
    _next_upkeep(scenario)
    _next_upkeep(scenario)
    assert len(scenario.stack_names()) == (1 if triggers else 0)
    assert scenario.game.intervening_if_notices == []


def test_a_life_total_falling_before_resolution_removes_the_ability():
    """CR 608.2a: Near-Death Experience's trigger is waiting at exactly 1
    life, then alice gains 1 - the recheck is false."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Near-Death Experience"], library=["Plains"] * 4)
        .player("bob", library=["Plains"] * 4)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.lose_life("alice", 19)
    _next_upkeep(scenario)
    _next_upkeep(scenario)
    (trigger,) = scenario.game.stack
    assert scenario.game._intervening_if_still_true(trigger)  # noqa: SLF001
    scenario.game.gain_life("alice", 1)
    assert not scenario.game._intervening_if_still_true(trigger)  # noqa: SLF001


@pytest.mark.parametrize(("alice", "bob", "triggers"), [(10, 10, True), (10, 11, False)])
def test_each_player_has_n_or_less_life(alice, bob, triggers):
    """Cryptolith Fragment: "At the beginning of your upkeep, if each player
    has 10 or less life, transform this artifact." - every player, not one."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Cryptolith Fragment"], library=["Plains"] * 4)
        .player("bob", library=["Plains"] * 4)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.lose_life("alice", 20 - alice)
    scenario.game.lose_life("bob", 20 - bob)
    _next_upkeep(scenario)
    _next_upkeep(scenario)
    assert len(scenario.stack_names()) == (1 if triggers else 0)
    assert scenario.game.intervening_if_notices == []


@pytest.mark.parametrize(("life", "triggers"), [(6, True), (7, False)])
def test_your_life_total_is_less_than_n(life, triggers):
    """Elderscale Wurm: "When this creature enters, if your life total is less
    than 7, your life total becomes 7." """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Elderscale Wurm"],
            battlefield=["Forest"] * 7,
            library=["Plains"] * 3,
        )
        .player("bob", library=["Plains"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.lose_life("alice", 20 - life)
    scenario.cast_and_resolve("Elderscale Wurm", *scenario.untapped_sources(*["Forest"] * 7))
    assert len(scenario.game.stack) + len(scenario.pending_triggers) == (1 if triggers else 0)
    assert scenario.game.intervening_if_notices == []


# -- "more life than an opponent" / "the most life or tied" ------------------


@pytest.mark.parametrize(("bob_loses", "triggers"), [(1, True), (0, False)])
def test_more_life_than_an_opponent(bob_loses, triggers):
    """Glorious Enforcer: "At the beginning of each combat, if you have more
    life than an opponent, this creature gains double strike until end of
    turn." - a tie is not more."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Glorious Enforcer"], library=["Plains"] * 3)
        .player("bob", library=["Plains"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.lose_life("bob", bob_loses)
    scenario.advance()  # beginning of combat
    assert scenario.stack_names() == (["Glorious Enforcer's triggered ability"] if triggers else [])
    scenario.pass_until_resolved()
    enforcer = scenario.creature("Glorious Enforcer", "alice")
    assert has_keyword(enforcer, "double strike", scenario.game) is triggers
    assert scenario.game.intervening_if_notices == []


@pytest.mark.parametrize(("alice_loses", "draws"), [(0, True), (1, False)])
def test_the_most_life_or_tied_for_most_life(alice_loses, draws):
    """Preacher of the Schism: "Whenever this creature attacks while you have
    the most life or are tied for most life, you draw a card and you lose 1
    life." - level at 20 is tied, and counts; one behind does not."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Preacher of the Schism"], library=["Plains"] * 3)
        .player("bob", library=["Plains"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.lose_life("alice", alice_loses)
    preacher = scenario.creature("Preacher of the Schism", "alice")
    game = scenario.game
    clause = "you have the most life or are tied for most life"
    assert game.condition_holds("alice", clause, preacher) is draws
    _to_declare_attackers(scenario)
    scenario.attack_with(preacher)
    scenario.pass_until_resolved()
    assert (len(scenario.player("alice").hand) == 1) is draws
    assert game.intervening_if_notices == []


# -- poison ---------------------------------------------------------------------


@pytest.mark.parametrize(("poison", "triggers"), [(1, True), (0, False)])
def test_defending_player_is_poisoned(poison, triggers):
    """Septic Rats: "Whenever this creature attacks, if defending player is
    poisoned, it gets +1/+1 until end of turn." - CR 122.1f: one counter is
    poisoned."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Septic Rats"], library=["Plains"] * 3)
        .player("bob", library=["Plains"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    if poison:
        scenario.game.add_player_counters("bob", "poison", poison)
    _to_declare_attackers(scenario)
    rats = scenario.creature("Septic Rats", "alice")
    scenario.attack_with(rats)
    assert scenario.stack_names() == (["Septic Rats's triggered ability"] if triggers else [])
    scenario.pass_until_resolved()
    assert scenario.game.power_of(rats) == (3 if triggers else 2)
    assert scenario.game.intervening_if_notices == []


def test_an_opponent_has_three_or_more_poison_counters():
    """Vivisection Evangelist's "if an opponent has three or more poison
    counters" - the count form, read the same way."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Vivisection Evangelist"], library=["Plains"] * 3)
        .player("bob", library=["Plains"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    game = scenario.game
    clause = "an opponent has three or more poison counters"
    assert game.condition_holds("alice", clause) is False
    game.add_player_counters("bob", "poison", 3)
    assert game.condition_holds("alice", clause) is True
    assert game.condition_holds("bob", clause) is False
    assert game.condition_holds("alice", "defending player is poisoned") is False


# -- the library ------------------------------------------------------------------


@pytest.mark.parametrize(("cards", "triggers"), [(200, True), (199, False)])
def test_n_or_more_cards_in_your_library(cards, triggers):
    """Battle of Wits: "At the beginning of your upkeep, if you have 200 or
    more cards in your library, you win the game." """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Battle of Wits"], library=["Plains"] * cards)
        .player("bob", library=["Plains"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _next_upkeep(scenario)
    _next_upkeep(scenario)
    assert len(scenario.stack_names()) == (1 if triggers else 0)
    assert scenario.game.intervening_if_notices == []


# -- the template, read directly -----------------------------------------------


def test_every_life_form_is_read_against_the_live_totals():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", life=30, battlefield=["Glorious Enforcer"], library=["Plains"] * 3)
        .player("bob", library=["Plains"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    game = scenario.game
    game.lose_life("alice", 4)  # 26, starting 30
    game.lose_life("bob", 5)  # 15, starting 20
    expected = {
        "your life total is less than your starting life total": True,
        "you have at least 1 life more than your starting life total": False,
        "you have 26 or more life": True,
        "you have exactly 26 life": True,
        "you have more life than an opponent": True,
        "an opponent has more life than you": False,
        "you have the most life": True,
        "each player has 26 or less life": True,
        "each opponent has 15 or less life": True,
        "a player has 30 or more life": False,
        "an opponent's life total is less than 16": True,
        "you are poisoned": False,
    }
    for clause, holds in expected.items():
        assert game.condition_holds("alice", clause) is holds, clause
