"""Scenario: an intervening "if" printed as a serial list of conditions.

Happily Ever After - "At the beginning of your upkeep, if there are five
colors among permanents you control, there are six or more card types among
permanents you control and/or cards in your graveyard, and your life total is
greater than or equal to your starting life total, you win the game."

The intervening "if" (CR 603.4) runs to the comma before the effect, so it is
the whole "A, B, and C" list, not just its first item; each item must hold,
both as the upkeep begins and as the ability resolves (CR 603.4 / 608.2a). The
effect left behind is the bare "you win the game." (CR 104.2b).

Rules verified with `mise run rules:find` in the session that wrote this file:

- **CR 603.4** - the intervening "if" clause rule.
- **CR 104.2b** - "An effect may state that a player wins the game."
- **CR 103.4** - "Each player begins the game with a starting life total of
  20. Some variant games have different starting life totals."
- **CR 300.1** - the card types; an artifact creature is two of them, and a
  type present among both the permanents and the graveyard counts once.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.triggers import triggered_abilities_of
from tests.cards import card

from .harness import Scenario

HAPPILY = "Happily Ever After"
#: Green/white, green/blue, red and black creatures: with the white
#: enchantment itself, all five colors.
FIVE_COLORS = ["Dawnhart Wardens", "Zegana, Utopian Speaker", "Goblin Bird-Grabber", "Ophiomancer"]
#: Artifact (and creature), instant, sorcery, land - with the enchantment and
#: the creatures on the battlefield, six card types.
GRAVEYARD = ["Memnite", "Lightning Bolt", "Divination", "Plains"]


def _board(*, battlefield=FIVE_COLORS, graveyard=GRAVEYARD, life=20):
    return (
        Scenario()
        .player(
            "alice",
            life=life,
            library=["Plains"] * 3,
            battlefield=[HAPPILY, *battlefield],
            graveyard=list(graveyard),
        )
        .player("bob", library=["Plains"] * 3)
        .build()
    )


def _to_upkeep(scenario) -> None:
    scenario.advance()  # untap -> upkeep
    assert scenario.step is Step.UPKEEP


def _resolve_all(scenario) -> None:
    """Ophiomancer's own upkeep trigger shares the stack."""
    while scenario.stack_names() and not scenario.game.is_over:
        scenario.pass_until_resolved()


def _triggered(scenario) -> bool:
    return any(HAPPILY in name for name in scenario.stack_names())


def test_the_intervening_if_is_the_whole_serial_list():
    """The clause runs to the comma before "you win the game", not to the
    first comma."""
    (win,) = [a for a in triggered_abilities_of(card(HAPPILY)) if a.intervening_if]
    assert win.intervening_if == (
        "there are five colors among permanents you control, there are six or more card "
        "types among permanents you control and/or cards in your graveyard, and your life "
        "total is greater than or equal to your starting life total"
    )
    assert win.effect == "you win the game."


def test_all_three_conditions_win_at_upkeep():
    scenario = _board()
    _to_upkeep(scenario)
    assert _triggered(scenario)

    _resolve_all(scenario)

    assert scenario.game.winner == "alice"


def test_four_colors_do_not_trigger():
    """Ophiomancer is the only black permanent."""
    scenario = _board(battlefield=FIVE_COLORS[:3])
    _to_upkeep(scenario)

    assert not _triggered(scenario)
    assert scenario.game.winner is None


def test_five_card_types_do_not_trigger():
    """Without Divination no sorcery is anywhere: five types."""
    scenario = _board(graveyard=["Memnite", "Lightning Bolt", "Plains"])
    _to_upkeep(scenario)

    assert not _triggered(scenario)
    assert scenario.game.winner is None


def test_card_types_are_counted_across_permanents_and_the_graveyard_together():
    """The land is on the battlefield and nowhere else, the artifact only in
    the graveyard; a creature in both counts once (CR 300.1)."""
    scenario = _board(
        battlefield=[*FIVE_COLORS, "Plains"],
        graveyard=["Memnite", "Lightning Bolt", "Divination", "Grizzly Bears"],
    )
    _to_upkeep(scenario)
    assert _triggered(scenario)
    _resolve_all(scenario)
    assert scenario.game.winner == "alice"


def test_only_your_own_graveyard_and_permanents_count():
    """Bob's graveyard sorcery is not alice's."""
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Plains"] * 3,
            battlefield=[HAPPILY, *FIVE_COLORS],
            graveyard=["Memnite", "Lightning Bolt", "Plains"],
        )
        .player("bob", library=["Plains"] * 3, graveyard=["Divination"])
        .build()
    )
    _to_upkeep(scenario)
    assert not _triggered(scenario)


@pytest.mark.parametrize(
    ("made_at", "change", "wins"),
    [(20, 0, True), (20, 3, True), (20, -1, False), (30, -10, False), (10, 0, True)],
)
def test_life_total_is_compared_with_the_starting_life_total(made_at, change, wins):
    """ "Greater than or equal to" includes equal; the bar is the player's own
    starting life total (CR 103.4), 30 for a player made at 30."""
    scenario = _board(life=made_at)
    if change > 0:
        scenario.game.gain_life("alice", change)
    elif change < 0:
        scenario.game.lose_life("alice", -change)
    _to_upkeep(scenario)

    assert _triggered(scenario) is wins
    _resolve_all(scenario)
    assert scenario.game.winner == ("alice" if wins else None)


def test_the_list_is_rechecked_on_resolution():
    """CR 603.4 / 608.2a: alice drops below her starting life total with the
    ability on the stack, so it does nothing as it resolves."""
    scenario = _board()
    _to_upkeep(scenario)
    assert _triggered(scenario)

    scenario.game.lose_life("alice", 1)
    _resolve_all(scenario)

    assert scenario.game.winner is None


def test_a_serial_list_is_read_as_every_item():
    """The shared compound reader takes "A, B, and C" as all three; one
    unread item leaves the whole list unread rather than true."""
    game = _board().game
    holds = (
        "there are five colors among permanents you control, your life total is "
        "equal to your starting life total, and you have 20 or more life"
    )
    assert game.condition_holds("alice", holds) is True
    fails = (
        "there are five colors among permanents you control, your life total is "
        "less than your starting life total, and you have 20 or more life"
    )
    assert game.condition_holds("alice", fails) is False
    unread = (
        "there are five colors among permanents you control, the moon is full, "
        "and you have 20 or more life"
    )
    assert game.condition_holds("alice", unread) is None
