"""Scenario: life gained or lost as an amount read off the game - "for each <count>",
"equal to <stat>", "twice X", "X is your life total" - and the sentences that
exchange or set a life total.

CR 119.3: a life gain or loss adjusts the life total. CR 608.2h: an amount is taken once,
as the instruction is applied. CR 107.3f: an X the text defines is that expression.
Every CR number here was looked up with `mise run rules:find`.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

FOREST10 = ["Forest"] * 10
WHITE = ["Plains"] * 6


def _build(alice=(), bob=(), *, hand=(), bob_hand=(), library=None, bob_library=None, life=20):
    return (
        Scenario()
        .player(
            "alice",
            life=life,
            hand=list(hand),
            battlefield=list(alice),
            library=list(FOREST10 if library is None else library),
        )
        .player(
            "bob",
            hand=list(bob_hand),
            battlefield=list(bob),
            library=list(FOREST10 if bob_library is None else bob_library),
        )
        .build()
    )


def _main(scenario):
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _life(scenario, who="alice"):
    return scenario.player(who).life


def _tokens(scenario, token_name, username="alice"):
    return [
        state
        for state in scenario.game.battlefield
        if state.name == token_name and scenario.game.controller_of(state).username == username
    ]


def _settle(scenario, limit=12):
    """Put triggers on the stack and resolve until the stack is empty."""
    for _ in range(limit):
        scenario.game.put_triggers_on_stack()
        if not scenario.stack_names():
            return
        scenario.pass_until_resolved()
    raise AssertionError(f"stack never emptied: {scenario.stack_names()}")


def _advance_to(scenario, step):
    """Walk the turn through `Game.advance`, so beginning-of-step triggers fire."""
    while scenario.turn.step is not step:
        scenario.advance()
    _settle(scenario)


def _cast_kicked(scenario, name, *, times=1, which=None):
    """Cast `name`, paying its kicker `times` (or the named kicker costs)."""
    casting = scenario.cast(name)
    for cost in which if which is not None else [None] * times:
        casting.pay_kicker(which=cost)
    scenario.auto_pay(casting.begin_paying())
    scenario.put_on_stack(casting)
    return scenario.resolve_top()


def _creature_etb(scenario, name):
    scenario.cast_and_resolve(name, auto=True, username="alice")
    _settle(scenario)


# --------------------------------------------------------------------------
# "gain N life for each <count>": player (Benediction of Moons), creature attacking
# you (Blessed Reversal), <type> that player controls (Emissary of Hope), creature
# that died this turn (Canopy Stalker, Silent-Chant Zubera), time kicked
# (Lightkeeper of Emeria, Stronghold Arena)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("attackers", [1, 3])
def test_blessed_reversal_gains_three_per_creature_attacking_you(attackers):
    bob = ["Grizzly Bears", "Hill Giant", "Serra Angel"][:attackers] + ["Savannah Lions"]
    scenario = (
        Scenario()
        .player("bob", battlefield=bob)
        .player("alice", hand=["Blessed Reversal"], battlefield=["Plains"] * 2)
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(*scenario.creatures(*bob[:attackers], username="bob"))
    scenario.pass_priority("bob")
    scenario.cast_and_resolve("Blessed Reversal", auto=True, username="alice")
    assert _life(scenario) == 20 + 3 * attackers  # the idle Savannah Lions is not counted


def test_blessed_reversal_with_no_attackers_gains_nothing():
    scenario = _main(_build(["Plains"] * 2, hand=["Blessed Reversal"]))
    scenario.cast_and_resolve("Blessed Reversal", auto=True, username="alice")
    assert _life(scenario) == 20


def test_benediction_of_moons_gains_one_life_per_player():
    scenario = _main(_build(["Plains"], hand=["Benediction of Moons"]))
    scenario.cast_and_resolve("Benediction of Moons", auto=True, username="alice")
    assert _life(scenario) == 22


def test_emissary_of_hope_gains_one_life_per_artifact_the_damaged_player_controls():
    scenario = _build(["Emissary of Hope"], ["Sol Ring", "Sol Ring", "Mountain", "Grizzly Bears"])
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(scenario.creature("Emissary of Hope", "alice"))
    scenario.no_blocks()
    scenario.combat_damage()
    _settle(scenario)
    assert _life(scenario) == 20 + 2
    assert _life(scenario, "bob") == 20 - 2


def test_canopy_stalker_counts_every_creature_that_died_this_turn_including_itself():
    scenario = _main(_build(["Canopy Stalker", "Grizzly Bears"], ["Hill Giant"]))
    scenario.game.destroy(scenario.creature("Grizzly Bears", "alice"))
    scenario.game.destroy(scenario.creature("Hill Giant", "bob"))
    scenario.game.destroy(scenario.creature("Canopy Stalker", "alice"))
    _settle(scenario)
    assert _life(scenario) == 20 + 3


def test_silent_chant_zubera_counts_only_zubera_that_died_this_turn():
    scenario = _main(
        _build(["Silent-Chant Zubera", "Rushing-Tide Zubera", "Grizzly Bears"], ["Hill Giant"])
    )
    scenario.game.destroy(scenario.creature("Grizzly Bears", "alice"))
    scenario.game.destroy(scenario.creature("Rushing-Tide Zubera", "alice"))
    scenario.game.destroy(scenario.creature("Silent-Chant Zubera", "alice"))
    _settle(scenario)
    assert _life(scenario) == 20 + 2 * 2


@pytest.mark.parametrize("kicks", [0, 1, 3])
def test_lightkeeper_of_emeria_gains_two_per_time_kicked(kicks):
    scenario = _main(_build(["Plains"] * (4 + kicks), hand=["Lightkeeper of Emeria"]))
    _cast_kicked(scenario, "Lightkeeper of Emeria", times=kicks)
    _settle(scenario)
    assert _life(scenario) == 20 + 2 * kicks


@pytest.mark.parametrize("which", [[], ["{G}"], ["{G}", "{W}"]])
def test_stronghold_arena_gains_three_per_kicker_paid(which):
    scenario = _main(_build(["Swamp", "Swamp", "Forest", "Plains"], hand=["Stronghold Arena"]))
    _cast_kicked(scenario, "Stronghold Arena", which=which)
    _settle(scenario)
    assert _life(scenario) == 20 + 3 * len(which)


def _cast_x(scenario, name, x, *, targets=None, username="alice"):
    casting = scenario.cast(name, targets=targets, username=username)
    casting.determine_cost(x_value=x)
    scenario.auto_pay(casting.begin_paying(), username)
    scenario.put_on_stack(casting)
    return scenario.resolve_top()


# --------------------------------------------------------------------------
# "gain life equal to <stat>" - the greatest toughness among other creatures you
# control (Flourishing Hunter), the cards in that player's hand (Search Warrant),
# twice X (Sanguine Sacrament)
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("others", "expected"),
    [([], 0), (["Grizzly Bears"], 2), (["Grizzly Bears", "Serra Angel", "Hill Giant"], 4)],
)
def test_flourishing_hunter_gains_the_greatest_toughness_among_other_creatures(others, expected):
    """The Hunter (6/6) is not "other", so its own toughness is never the answer."""
    scenario = _main(_build(["Forest"] * 6 + others, hand=["Flourishing Hunter"]))
    _creature_etb(scenario, "Flourishing Hunter")
    assert _life(scenario) == 20 + expected


def test_search_warrant_gains_life_equal_to_the_cards_in_the_targeted_hand():
    scenario = _main(
        _build(
            ["Plains", "Island"],
            hand=["Search Warrant"],
            bob_hand=["Grizzly Bears", "Hill Giant", "Forest"],
        )
    )
    scenario.cast_and_resolve("Search Warrant", auto=True, username="alice", targets=["bob"])
    assert _life(scenario) == 23


def test_search_warrant_on_an_empty_hand_gains_nothing():
    scenario = _main(_build(["Plains", "Island"], hand=["Search Warrant"]))
    scenario.cast_and_resolve("Search Warrant", auto=True, username="alice", targets=["bob"])
    assert _life(scenario) == 20


@pytest.mark.parametrize("x", [0, 1, 4])
def test_sanguine_sacrament_gains_twice_x_then_goes_to_the_library_bottom(x):
    scenario = _main(_build(["Plains"] * (2 + x), hand=["Sanguine Sacrament"]))
    spell = _cast_x(scenario, "Sanguine Sacrament", x)
    assert _life(scenario) == 20 + 2 * x
    assert spell.zone is Zone.LIBRARY
    assert scenario.player("alice").library[-1] is spell


# --------------------------------------------------------------------------
# "where X is your life total" (Storm Herd, Loxodon Lifechanter) and "where X is your
# speed" (The Speed Demon, Momentum Breaker)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("life", [1, 7, 20])
def test_storm_herd_makes_a_pegasus_per_point_of_life(life):
    scenario = _main(_build(["Plains"] * 10, hand=["Storm Herd"], life=life))
    scenario.cast_and_resolve("Storm Herd", auto=True, username="alice")
    pegasi = _tokens(scenario, "Pegasus Token")
    assert len(pegasi) == life
    assert all(scenario.game.power_of(token) == 1 for token in pegasi)


@pytest.mark.parametrize("life", [3, 20])
def test_loxodon_lifechanter_pump_is_your_life_total(life):
    scenario = _main(_build(["Plains"] * 6 + ["Loxodon Lifechanter"], life=life))
    lifechanter = scenario.creature("Loxodon Lifechanter", "alice")
    scenario.activate(lifechanter, *scenario.untapped_sources(*["Plains"] * 6), index=0)
    scenario.pass_until_resolved()
    assert scenario.game.power_of(lifechanter) == 4 + life
    assert scenario.game.toughness_of(lifechanter) == 6 + life


@pytest.mark.parametrize(("speed", "drawn"), [(None, 1), (1, 1), (3, 3), (4, 4)])
def test_the_speed_demon_draws_and_loses_by_speed(speed, drawn):
    """A player with no speed starts at 1 while they control a permanent with start your
    engines! (CR 702.179a), so the Demon itself gives the None row its one card."""
    scenario = _main(_build(["The Speed Demon"]))
    scenario.player("alice").speed = speed
    _advance_to(scenario, Step.END_STEP)
    assert len(scenario.player("alice").hand) == drawn
    assert _life(scenario) == 20 - drawn


def test_momentum_breaker_sacrifice_gains_life_equal_to_speed():
    scenario = _main(_build(["Momentum Breaker", "Swamp", "Swamp"]))
    scenario.player("alice").speed = 3
    breaker = scenario.find("Momentum Breaker", Zone.BATTLEFIELD, "alice")
    scenario.activate(breaker, *scenario.untapped_sources("Swamp", "Swamp"))
    scenario.pass_until_resolved()
    assert _life(scenario) == 23
    assert breaker.zone is Zone.GRAVEYARD


# --------------------------------------------------------------------------
# "Exchange your life total with this creature's toughness|power" (Tree of Redemption,
# Tree of Perdition, Evra, Halcyon Witness) - CR 701.12g
# --------------------------------------------------------------------------


def _toughness(scenario, card):
    return scenario.game.toughness_of(card)


@pytest.mark.parametrize("life", [1, 20, 35])
def test_tree_of_redemption_swaps_your_life_with_its_toughness(life):
    scenario = _main(_build(["Tree of Redemption"], life=life))
    tree = scenario.creature("Tree of Redemption", "alice")
    toughness = _toughness(scenario, tree)
    scenario.activate(tree, index=0)
    scenario.pass_until_resolved()
    assert _life(scenario) == toughness
    assert _toughness(scenario, tree) == life


def test_tree_of_perdition_swaps_the_targeted_opponents_life():
    scenario = _main(_build(["Tree of Perdition"], life=20))
    scenario.player("bob").life = 3
    tree = scenario.creature("Tree of Perdition", "alice")
    toughness = _toughness(scenario, tree)
    scenario.activate(tree, index=0, targets=["bob"])
    scenario.pass_until_resolved()
    assert _life(scenario, "bob") == toughness
    assert _life(scenario) == 20
    assert _toughness(scenario, tree) == 3


def test_a_player_who_cannot_gain_life_cannot_make_an_exchange_that_raises_the_total():
    """CR 119.7 with CR 701.12a: no part of the exchange occurs."""
    scenario = _main(_build(["Tree of Redemption"], life=2))
    scenario.player("alice").cannot_gain_life = True
    tree = scenario.creature("Tree of Redemption", "alice")
    toughness = _toughness(scenario, tree)
    scenario.activate(tree, index=0)
    scenario.pass_until_resolved()
    assert _life(scenario) == 2
    assert _toughness(scenario, tree) == toughness


@pytest.mark.parametrize("life", [3, 12])
def test_evra_swaps_your_life_total_with_its_power(life):
    scenario = _main(_build(["Evra, Halcyon Witness"] + ["Plains"] * 4, life=life))
    evra = scenario.creature("Evra, Halcyon Witness", "alice")
    power = scenario.game.power_of(evra)
    scenario.activate(evra, *scenario.untapped_sources(*["Plains"] * 4), index=0)
    scenario.pass_until_resolved()
    assert _life(scenario) == power
    assert scenario.game.power_of(evra) == life


# --------------------------------------------------------------------------
# "sacrifice half the non-Demon permanents you control, rounded up" (Rakdos the Defiler)
# and "you may have your life total become the total toughness of creatures you control"
# (Loxodon Lifechanter)
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("others", "kept_others"),
    [(0, 0), (1, 0), (4, 2), (5, 2)],
)
def test_rakdos_attack_sacrifices_half_the_non_demons_rounded_up(others, kept_others):
    """Rakdos is a Demon, so it is never counted and never sacrificed (CR 701.21a)."""
    scenario = _build(["Rakdos the Defiler"] + ["Grizzly Bears"] * others, ["Hill Giant"])
    scenario.start_at(Step.DECLARE_ATTACKERS)
    rakdos = scenario.creature("Rakdos the Defiler", "alice")
    scenario.attack_with(rakdos)
    scenario.game.put_triggers_on_stack()
    if others > kept_others:
        bears = scenario.creatures(*["Grizzly Bears"] * others, username="alice")
        scenario.will_choose_cards(*bears[: others - kept_others])
    scenario.pass_until_resolved()
    assert rakdos.zone is Zone.BATTLEFIELD
    assert len([s for s in scenario.game.battlefield if s.name == "Grizzly Bears"]) == kept_others


@pytest.mark.parametrize("take", [True, False])
def test_loxodon_lifechanter_may_set_life_to_total_toughness(take):
    scenario = _main(
        _build(["Plains"] * 6 + ["Grizzly Bears", "Serra Angel"], hand=["Loxodon Lifechanter"])
    )
    scenario.will_take_the_may(take)
    _creature_etb(scenario, "Loxodon Lifechanter")
    assert _life(scenario) == (6 + 2 + 4 if take else 20)


# --------------------------------------------------------------------------
# Haunt (Benediction of Moons) - CR 702.55a, 702.55b, 702.55c
# --------------------------------------------------------------------------


def _haunted_benediction():
    """alice casts Benediction of Moons while bob controls a lone Grizzly Bears."""
    scenario = _main(_build(["Plains"], ["Grizzly Bears"], hand=["Benediction of Moons"]))
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.will_choose_targets(bears, source="Benediction of Moons")
    scenario.cast_and_resolve("Benediction of Moons", auto=True, username="alice")
    _settle(scenario)
    return scenario, bears


def test_benediction_haunts_the_creature_it_targets_when_it_resolves():
    """CR 702.55a: put into a graveyard during resolution, it is exiled haunting a creature."""
    scenario, bears = _haunted_benediction()
    card = next(c for c in scenario.game.exile if c.name == "Benediction of Moons")
    assert card.exile_annotation.marker.value == "haunting"
    assert card.exile_annotation.linked_permanent_id == bears.id
    assert _life(scenario) == 22  # the spell itself gained 1 per player first
    assert not [c for c in scenario.player("alice").graveyard if c.name == "Benediction of Moons"]


def test_the_haunting_card_triggers_from_exile_when_its_creature_dies():
    """CR 702.55b-c: "the creature this card haunts" dies, and the exiled card still triggers."""
    scenario, bears = _haunted_benediction()
    scenario.game.destroy(bears)
    _settle(scenario)
    assert _life(scenario) == 24


def test_another_creature_dying_does_not_trigger_the_haunting_card():
    scenario = _main(
        _build(["Plains"], ["Grizzly Bears", "Hill Giant"], hand=["Benediction of Moons"])
    )
    bears = scenario.creature("Grizzly Bears", "bob")
    giant = scenario.creature("Hill Giant", "bob")
    scenario.will_choose_targets(bears, source="Benediction of Moons")
    scenario.cast_and_resolve("Benediction of Moons", auto=True, username="alice")
    _settle(scenario)
    scenario.game.destroy(giant)
    _settle(scenario)
    assert _life(scenario) == 22


def test_benediction_with_no_creature_to_haunt_stays_in_the_graveyard():
    scenario = _main(_build(["Plains"], hand=["Benediction of Moons"]))
    scenario.cast_and_resolve("Benediction of Moons", auto=True, username="alice")
    _settle(scenario)
    assert [c for c in scenario.player("alice").graveyard if c.name == "Benediction of Moons"]
    assert _life(scenario) == 22


# --------------------------------------------------------------------------
# "target creature with power greater than or equal to your life total" (Blazing Hope)
# --------------------------------------------------------------------------


def test_blazing_hope_exiles_a_creature_whose_power_reaches_your_life_total():
    scenario = _main(
        _build(["Plains"] * 2, ["Hill Giant", "Grizzly Bears"], hand=["Blazing Hope"], life=3)
    )
    giant = scenario.creature("Hill Giant", "bob")
    scenario.cast_and_resolve("Blazing Hope", targets=[giant], auto=True, username="alice")
    assert giant.zone is Zone.EXILE


def test_blazing_hope_cannot_target_a_creature_with_less_power_than_your_life_total():
    scenario = _main(
        _build(["Plains"] * 2, ["Hill Giant", "Grizzly Bears"], hand=["Blazing Hope"], life=4)
    )
    bears = scenario.creature("Grizzly Bears", "bob")
    with pytest.raises(Exception, match="power"):
        scenario.cast("Blazing Hope", targets=[bears])


# --------------------------------------------------------------------------
# Chained "Then if creatures you control have total toughness N or greater" (Betor, Kin to All)
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("angels", "drawn", "untapped", "opponent_life"),
    [
        (0, 0, False, 21),  # toughness 7: the trigger's own condition fails
        (1, 1, False, 21),  # 11
        (4, 1, True, 21),  # 23
        (9, 1, True, 10),  # 43: half of 21 rounded up is 11
    ],
)
def test_betor_end_step_chain_applies_every_threshold_reached(
    angels, drawn, untapped, opponent_life
):
    scenario = _main(_build(["Betor, Kin to All"] + ["Serra Angel"] * angels))
    scenario.player("bob").life = 21
    for angel in scenario.creatures(*["Serra Angel"] * angels, username="alice"):
        angel.tapped = True
    hand = len(scenario.player("alice").hand)
    _advance_to(scenario, Step.END_STEP)
    assert len(scenario.player("alice").hand) == hand + drawn
    assert all(
        (not angel.tapped) is untapped
        for angel in scenario.creatures(*["Serra Angel"] * angels, username="alice")
    )
    assert _life(scenario, "bob") == opponent_life
