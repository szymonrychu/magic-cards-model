"""Scenario: every amount sentence is read once (`machines/amount_sentences.py`).

EP-02 R1's task readers each carried their own copy of the same printed
wordings - "<who> loses life equal to <expr>", "<who> mills X cards, where X
is <expr>", "add {M} for each <count>", "put a counter on this permanent for
each <count>", "you gain X life and draw X cards, where X is <stat>" - and
their own resolver for the player a subject names. They now share one reader
per wording and one recipient resolver; two readers both applying one
instruction would double it. Each test below pins the exact delta of one
reconciled wording, and that nothing beyond it moved.

CR numbers were looked up with `mise run rules:find`: 608.2h (an amount is
taken once, as the effect is applied), 119.3 (life gained or lost adjusts the
total), 701.17a (mill), 106.4 (mana into the pool), 122.1 (counters).
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Color
from magic_cards_model.models.card_state import Counter

from .harness import Scenario

BEARS = "Grizzly Bears"


def _board(*, alice=(), hand=(), graveyard=(), bob=(), bob_graveyard=(), step=Step.PRECOMBAT_MAIN):
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=list(alice),
            hand=list(hand),
            graveyard=list(graveyard),
            library=["Forest"] * 12,
        )
        .player(
            "bob",
            battlefield=list(bob),
            graveyard=list(bob_graveyard),
            library=["Island"] * 12,
        )
        .build()
    )
    scenario.start_at(step)
    return scenario


def _settle(scenario, limit=12):
    for _ in range(limit):
        scenario.game.put_triggers_on_stack()
        if not scenario.stack_names():
            return
        scenario.pass_until_resolved()
    raise AssertionError(f"stack never emptied: {scenario.stack_names()}")


def _life(scenario, name):
    return scenario.player(name).life


def test_a_life_loss_for_each_counted_permanent_is_lost_once():
    """Gruesome Fate: "Each opponent loses 1 life for each creature you
    control." - the life sentence `parse_life_clause` reads."""
    scenario = _board(
        alice=[BEARS, BEARS, BEARS, "Swamp", "Swamp", "Swamp"], hand=["Gruesome Fate"], bob=[BEARS]
    )
    scenario.cast_and_resolve("Gruesome Fate", auto=True)
    assert _life(scenario, "bob") == 20 - 3
    assert _life(scenario, "alice") == 20


def test_that_player_is_the_damaged_player_once():
    """Graveblade Marauder: "that player loses life equal to the number of
    creature cards in your graveyard" - the recipient `resolve_recipients`
    names is the event's player, alone."""
    scenario = _board(
        alice=["Graveblade Marauder"], graveyard=[BEARS] * 3, step=Step.DECLARE_ATTACKERS
    )
    scenario.attack_with(scenario.creature("Graveblade Marauder", "alice"))
    scenario.no_blocks()
    scenario.combat_damage()
    _settle(scenario)
    assert _life(scenario, "bob") == 20 - 1 - 3
    assert _life(scenario, "alice") == 20


def test_a_mill_x_where_x_counts_the_targets_graveyard_mills_once():
    """Keening Stone: "Target player mills X cards, where X is the number of
    cards in that player's graveyard" - the one mill-X reader."""
    scenario = _board(alice=["Keening Stone", *["Mountain"] * 5], bob_graveyard=[BEARS, BEARS])
    stone = scenario.find("Keening Stone", Zone.BATTLEFIELD)
    scenario.activate(stone, targets=[scenario.player("bob")], auto=True)
    scenario.resolve_top()
    assert len(scenario.player("bob").library) == 12 - 2
    assert len(scenario.player("bob").graveyard) == 2 + 2
    assert len(scenario.player("alice").library) == 12


def test_add_mana_for_each_adds_once_per_counted_card():
    """Rite of Flame: "Add {R}{R}, then add {R} for each card named Rite of
    Flame in each graveyard." - the one add-mana-for-each reader."""
    scenario = _board(alice=["Mountain"], hand=["Rite of Flame"], bob_graveyard=["Rite of Flame"])
    scenario.cast_and_resolve("Rite of Flame", auto=True)
    assert scenario.player("alice").mana_pool.floating == {Color.RED: 2 + 1}


def test_counters_on_this_permanent_for_each_are_put_once():
    """Huatli, Radiant Champion: "+1: Put a loyalty counter on Huatli for each
    creature you control." - the self-counters-for-each reader, no longer a
    rewrite read a second time."""
    scenario = _board(alice=["Huatli, Radiant Champion", BEARS, BEARS, BEARS])
    huatli = scenario.find("Huatli, Radiant Champion", Zone.BATTLEFIELD, "alice")
    before = huatli.counter_count(Counter.LOYALTY)
    scenario.activate(huatli, index=0)
    _settle(scenario)
    assert huatli.counter_count(Counter.LOYALTY) == before + 1 + 3


def test_a_stat_sized_gain_and_draw_pair_happens_once():
    """Disciple of Bolas: "sacrifice another creature. You gain X life and
    draw X cards, where X is that creature's power." - the X pair read by
    `parse_life_clause` and `parse_cards_clause`."""
    scenario = _board(alice=[BEARS], hand=["Disciple of Bolas"])
    scenario.put_onto_battlefield("Disciple of Bolas", "alice")
    hand_before = len(scenario.player("alice").hand)
    _settle(scenario)
    assert scenario.find(BEARS, Zone.GRAVEYARD, "alice").zone is Zone.GRAVEYARD
    assert _life(scenario, "alice") == 20 + 2
    assert len(scenario.player("alice").hand) == hand_before + 2
    assert _life(scenario, "bob") == 20


def test_a_where_x_measured_once_is_written_in_and_applied_once():
    """Kyoshi Island Plaza ("Search your library for up to X basic land cards,
    where X is the number of Shrines you control") and Kotis, the Fangkeeper
    ("exile the top X cards of that player's library, where X is the damage
    dealt") - both read by `amount_sentences.find_where_x`. X is measured as the
    object resolves (CR 608.2h) and written in as a number (CR 107.3a): with three
    Shrines exactly three lands are fetched, and with the damage dealt exactly that
    many cards are exiled - neither is doubled."""
    scenario = _board(
        alice=["Forest"] * 4 + ["Honden of Life's Web", "Honden of Night's Reach"],
        hand=["Kyoshi Island Plaza"],
    )
    library_before = len(scenario.player("alice").library)
    scenario.cast_onto_stack("Kyoshi Island Plaza", auto=True, username="alice")
    _settle(scenario)
    lands_after = [
        p
        for p in scenario.game.permanents_controlled_by("alice")
        if scenario.game.characteristics_of(p).is_land
    ]
    assert len(lands_after) == 4 + 3  # X = 3 Shrines (the plaza is one): three fetched
    assert len(scenario.player("alice").library) == library_before - 3

    scenario = _board(alice=["Kotis, the Fangkeeper"], step=Step.DECLARE_ATTACKERS)
    kotis = scenario.creature("Kotis, the Fangkeeper", "alice")
    kotis.summoning_sick = False
    scenario.attack_with(kotis)
    _settle(scenario)
    scenario.no_blocks()
    scenario.combat_damage()
    _settle(scenario)
    damage = 20 - scenario.player("bob").life
    assert damage == 2
    assert len(scenario.player("bob").library) == 12 - damage
