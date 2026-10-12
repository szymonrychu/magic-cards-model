"""EP-01-R3 T2: exert-event triggers and the combat/trigger keywords.

Every CR number below was read with `mise run rules:find` in the session that
wrote this file:

- CR 701.43 exert; CR 701.43d "you may exert [this creature] as it attacks".
- CR 702.45a bushido; CR 702.135a afterlife; CR 702.134a mentor.
- CR 702.66 graft is looked up where its tests live below.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import has_keyword
from magic_cards_model.machines.cost import exert_cost
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Color
from magic_cards_model.models.card_state import Counter
from magic_cards_model.support import card_support
from tests.cards import card

from .harness import Scenario


def _support_is_handled(name: str) -> None:
    support = card_support(card(name))
    assert support.status == "handled", [
        (c.text, c.status, c.reason) for c in support.clauses if c.status != "handled"
    ]


def _resolve_everything(scenario) -> None:
    scenario.game.put_triggers_on_stack()
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()


def _combat_board(alice, bob, *, hand=()):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=list(alice), hand=list(hand), library=["Plains"] * 5)
        .player("bob", battlefield=list(bob), library=["Plains"] * 5)
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    return scenario


# -- bushido (CR 702.45) -----------------------------------------------------


def test_bushido_attacker_becoming_blocked_gets_plus_one_plus_one():
    """CR 702.45a: 'becomes blocked' - Samurai of the Pale Curtain 2/2 -> 3/3."""
    scenario = _combat_board(["Samurai of the Pale Curtain"], ["Grizzly Bears"])
    samurai = scenario.creature("Samurai of the Pale Curtain", "alice")
    samurai.summoning_sick = False
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.attack_with(samurai)
    scenario.advance()
    scenario.block(samurai, bears)
    _resolve_everything(scenario)
    assert scenario.game.characteristics_of(samurai).power_toughness == (3, 3)


def test_bushido_blocker_gets_the_bonus_when_it_blocks():
    """CR 702.45a: 'blocks' - Kentaro 2/1 blocking becomes 3/2."""
    scenario = _combat_board(["Grizzly Bears"], ["Kentaro, the Smiling Cat"])
    bears = scenario.creature("Grizzly Bears", "alice")
    bears.summoning_sick = False
    kentaro = scenario.creature("Kentaro, the Smiling Cat", "bob")
    scenario.attack_with(bears)
    scenario.advance()
    scenario.block(bears, kentaro)
    _resolve_everything(scenario)
    assert scenario.game.characteristics_of(kentaro).power_toughness == (3, 2)


def test_bushido_does_nothing_when_unblocked():
    scenario = _combat_board(["Samurai of the Pale Curtain"], ["Grizzly Bears"])
    samurai = scenario.creature("Samurai of the Pale Curtain", "alice")
    samurai.summoning_sick = False
    scenario.attack_with(samurai)
    scenario.advance()
    scenario.no_blocks()
    _resolve_everything(scenario)
    assert scenario.game.characteristics_of(samurai).power_toughness == (2, 2)


def test_bushido_on_a_second_printing_devoted_retainer():
    """Second printing (a 1/1 for {W}): the same rule text, read off CR 702.45a."""
    scenario = _combat_board(["Devoted Retainer"], ["Llanowar Elves"])
    retainer = scenario.creature("Devoted Retainer", "alice")
    retainer.summoning_sick = False
    elves = scenario.creature("Llanowar Elves", "bob")
    scenario.attack_with(retainer)
    scenario.advance()
    scenario.block(retainer, elves)
    _resolve_everything(scenario)
    assert scenario.game.characteristics_of(retainer).power_toughness == (2, 2)
    scenario.combat_damage()
    assert retainer.zone is Zone.BATTLEFIELD
    assert elves.zone is Zone.GRAVEYARD


def test_bushido_cards_read_handled():
    for name in ("Kentaro, the Smiling Cat", "Samurai of the Pale Curtain"):
        support = card_support(card(name))
        assert not [c for c in support.clauses if c.kind == "keyword" and c.status != "handled"]


# -- afterlife (CR 702.135) --------------------------------------------------


def _spirits(scenario, username="alice"):
    return [c for c in scenario.game.permanents_controlled_by(username) if c.name == "Spirit Token"]


def test_afterlife_two_creates_two_flying_white_black_spirits():
    """CR 702.135a: Ministrant of Obligation (afterlife 2) dies."""
    scenario = _combat_board(["Ministrant of Obligation"], [])
    ministrant = scenario.creature("Ministrant of Obligation", "alice")
    scenario.game.destroy(ministrant)
    _resolve_everything(scenario)
    spirits = _spirits(scenario)
    assert len(spirits) == 2
    for spirit in spirits:
        chars = scenario.game.characteristics_of(spirit)
        assert chars.power_toughness == (1, 1)
        assert has_keyword(spirit, "flying", scenario.game)
        assert set(chars.colors) == {Color.WHITE, Color.BLACK}
        assert "Spirit" in chars.subtypes


def test_afterlife_one_creates_one_spirit_for_knight_of_sorrows():
    scenario = _combat_board(["Knight of Sorrows"], [])
    knight = scenario.creature("Knight of Sorrows", "alice")
    scenario.game.destroy(knight)
    _resolve_everything(scenario)
    assert len(_spirits(scenario)) == 1


def test_afterlife_does_not_trigger_when_the_creature_is_exiled():
    """CR 702.135a: only 'put into a graveyard from the battlefield'."""
    scenario = _combat_board(["Ministrant of Obligation"], [])
    ministrant = scenario.creature("Ministrant of Obligation", "alice")
    scenario.game.exile_permanent(ministrant)
    _resolve_everything(scenario)
    assert _spirits(scenario) == []


def test_afterlife_tokens_belong_to_the_dead_creatures_controller():
    scenario = _combat_board([], ["Ministrant of Obligation"])
    ministrant = scenario.creature("Ministrant of Obligation", "bob")
    scenario.game.destroy(ministrant)
    _resolve_everything(scenario)
    assert len(_spirits(scenario, "bob")) == 2
    assert _spirits(scenario, "alice") == []


# -- mentor (CR 702.134) -----------------------------------------------------


def test_mentor_puts_a_counter_on_an_attacker_with_lesser_power():
    """CR 702.134a: Barging Sergeant (power 4) mentors a 1-power attacker."""
    scenario = _combat_board(["Barging Sergeant", "Llanowar Elves"], [])
    sergeant = scenario.creature("Barging Sergeant", "alice")
    elves = scenario.creature("Llanowar Elves", "alice")
    sergeant.summoning_sick = elves.summoning_sick = False
    scenario.attack_with(sergeant, elves)
    scenario.game.put_triggers_on_stack()
    scenario.choose_trigger_targets("Barging Sergeant", [elves])
    _resolve_everything(scenario)
    assert elves.counter_count(Counter.PLUS_ONE) == 1
    assert sergeant.counter_count(Counter.PLUS_ONE) == 0


def test_mentor_cannot_target_an_attacker_with_equal_or_greater_power():
    scenario = _combat_board(["Wojek Bodyguard", "Hill Giant"], [])
    bodyguard = scenario.creature("Wojek Bodyguard", "alice")
    giant = scenario.creature("Hill Giant", "alice")
    bodyguard.summoning_sick = giant.summoning_sick = False
    scenario.attack_with(bodyguard, giant)
    scenario.game.put_triggers_on_stack()
    # Hill Giant (3) is not lesser than Wojek Bodyguard (3): no legal target.
    assert scenario.stack_names() == []
    _resolve_everything(scenario)
    assert giant.counter_count(Counter.PLUS_ONE) == 0


def test_wojek_bodyguard_cannot_attack_alone_but_can_with_a_partner():
    scenario = _combat_board(["Wojek Bodyguard", "Llanowar Elves"], [])
    bodyguard = scenario.creature("Wojek Bodyguard", "alice")
    elves = scenario.creature("Llanowar Elves", "alice")
    bodyguard.summoning_sick = elves.summoning_sick = False
    try:
        scenario.attack_with(bodyguard)
    except ValueError as error:
        assert "alone" in str(error).lower()
    else:
        raise AssertionError("Wojek Bodyguard attacked alone")
    scenario.attack_with(bodyguard, elves)


def test_mentor_and_bodyguard_read_handled():
    _support_is_handled("Wojek Bodyguard")


# -- "Whenever you exert a creature" (CR 701.43, CR 603.2) ------------------


def _attack_exerting(scenario, attacker, *others, exert=True):
    scenario.will_take_the_may(exert, source=attacker.name)
    scenario.attack_with(attacker, *others)
    scenario.game.put_triggers_on_stack()


def _exert_board(alice, bob=(), *, hand=()):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=list(alice), hand=list(hand), library=["Plains"] * 6)
        .player("bob", battlefield=list(bob), library=["Plains"] * 6)
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    for creature in scenario.game.permanents_controlled_by("alice"):
        creature.summoning_sick = False
    return scenario


def test_vizier_of_the_true_taps_an_opponents_creature_when_it_exerts_itself():
    scenario = _exert_board(["Vizier of the True"], ["Grizzly Bears"])
    vizier = scenario.creature("Vizier of the True", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    _attack_exerting(scenario, vizier)
    assert vizier.exerted
    scenario.choose_trigger_targets("Vizier of the True", [bears])
    _resolve_everything(scenario)
    assert bears.tapped


def test_resolute_survivors_pings_each_opponent_and_gains_life_per_exert():
    scenario = _exert_board(["Resolute Survivors"], [])
    survivors = scenario.creature("Resolute Survivors", "alice")
    life = scenario.player("alice").life
    opponent_life = scenario.player("bob").life
    _attack_exerting(scenario, survivors)
    _resolve_everything(scenario)
    assert scenario.player("bob").life == opponent_life - 1
    assert scenario.player("alice").life == life + 1


def test_trueheart_twins_pumps_every_creature_you_control():
    scenario = _exert_board(["Trueheart Twins", "Grizzly Bears"], ["Hill Giant"])
    twins = scenario.creature("Trueheart Twins", "alice")
    mine = scenario.creature("Grizzly Bears", "alice")
    theirs = scenario.creature("Hill Giant", "bob")
    _attack_exerting(scenario, twins)
    _resolve_everything(scenario)
    assert scenario.game.characteristics_of(twins).power_toughness == (5, 4)
    assert scenario.game.characteristics_of(mine).power_toughness == (3, 2)
    assert scenario.game.characteristics_of(theirs).power_toughness == (3, 3)


def test_battlefield_scavenger_loots_when_another_creature_exerts():
    scenario = _exert_board(["Battlefield Scavenger", "Tah-Crop Elite"], [], hand=["Island"])
    elite = scenario.creature("Tah-Crop Elite", "alice")
    hand_before = len(scenario.player("alice").hand)
    scenario.will_take_the_may(True, source="Battlefield Scavenger")
    scenario.will_discard(scenario.find("Island", Zone.HAND, "alice"))
    _attack_exerting(scenario, elite)
    _resolve_everything(scenario)
    assert len(scenario.player("alice").hand) == hand_before
    assert scenario.find("Island", Zone.GRAVEYARD, "alice")


def test_declining_to_exert_triggers_nothing():
    scenario = _exert_board(["Trueheart Twins"], [])
    twins = scenario.creature("Trueheart Twins", "alice")
    _attack_exerting(scenario, twins, exert=False)
    _resolve_everything(scenario)
    assert not twins.exerted
    assert scenario.game.characteristics_of(twins).power_toughness == (4, 4)


def test_an_opponents_exert_does_not_trigger_you_exert():
    scenario = _exert_board(["Trueheart Twins"], ["Vizier of the True"])
    twins = scenario.creature("Trueheart Twins", "alice")
    vizier = scenario.creature("Vizier of the True", "bob")
    scenario.game.exerted_this_turn.clear()
    from magic_cards_model.machines.exert_triggers import exert_permanent

    exert_permanent(scenario.game, vizier)
    _resolve_everything(scenario)
    assert scenario.game.characteristics_of(twins).power_toughness == (4, 4)


def test_two_payoffs_each_trigger_for_one_exert():
    scenario = _exert_board(["Trueheart Twins", "Resolute Survivors"], [])
    twins = scenario.creature("Trueheart Twins", "alice")
    _attack_exerting(scenario, twins)
    names = sorted(scenario.stack_names())
    assert names == [
        "Resolute Survivors's triggered ability",
        "Trueheart Twins's triggered ability",
    ]


def test_exerting_a_creature_as_a_cost_also_triggers_you_exert():
    """CR 701.43a: exert is the same keyword action as a cost component."""
    scenario = _exert_board(["Trueheart Twins", "Grizzly Bears"], [])
    twins = scenario.creature("Trueheart Twins", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    exert_cost(bears, payer="alice", description="Exert this creature").pay(scenario.game)
    assert bears.exerted
    _resolve_everything(scenario)
    assert scenario.game.characteristics_of(twins).power_toughness == (5, 4)


def test_exerting_a_land_is_not_exerting_a_creature():
    """Arena of Glory's exert cost exerts a land; "you exert a creature" ignores it."""
    scenario = _exert_board(["Arena of Glory", "Mountain", "Trueheart Twins"], [])
    twins = scenario.creature("Trueheart Twins", "alice")
    arena = scenario.find("Arena of Glory", Zone.BATTLEFIELD, "alice")
    mountain = scenario.find("Mountain", Zone.BATTLEFIELD, "alice")
    scenario.activate(arena, mountain, index=1)
    assert arena.exerted
    _resolve_everything(scenario)
    assert scenario.game.characteristics_of(twins).power_toughness == (4, 4)


def test_exert_payoff_cards_read_handled():
    for name in (
        "Battlefield Scavenger",
        "Resolute Survivors",
        "Trueheart Twins",
        "Vizier of the True",
        "Tah-Crop Elite",
    ):
        _support_is_handled(name)


# -- graft (CR 702.58) -------------------------------------------------------


def _main_board(alice, bob=(), *, hand=()):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=list(alice), hand=list(hand), library=["Plains"] * 6)
        .player("bob", battlefield=list(bob), library=["Plains"] * 6)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_graft_enters_with_its_counters_vigean_hydropon_is_a_five_five():
    """CR 702.58a, the static half: 'Graft 5' means enters with five +1/+1 counters."""
    scenario = _main_board([], hand=["Vigean Hydropon"])
    hydropon = scenario.put_onto_battlefield("Vigean Hydropon", "alice")
    assert hydropon.counter_count(Counter.PLUS_ONE) == 5
    assert scenario.game.characteristics_of(hydropon).power_toughness == (5, 5)


def test_graft_second_printing_simic_initiate_enters_with_one():
    scenario = _main_board([], hand=["Simic Initiate"])
    initiate = scenario.put_onto_battlefield("Simic Initiate", "alice")
    assert initiate.counter_count(Counter.PLUS_ONE) == 1


def test_graft_moves_a_counter_onto_a_creature_that_enters():
    """CR 702.58a, the triggered half."""
    scenario = _main_board([], hand=["Vigean Hydropon", "Grizzly Bears"])
    hydropon = scenario.put_onto_battlefield("Vigean Hydropon", "alice")
    scenario.will_take_the_may(True, source="Vigean Hydropon")
    bears = scenario.put_onto_battlefield("Grizzly Bears", "alice")
    _resolve_everything(scenario)
    assert bears.counter_count(Counter.PLUS_ONE) == 1
    assert hydropon.counter_count(Counter.PLUS_ONE) == 4
    assert scenario.game.characteristics_of(bears).power_toughness == (3, 3)


def test_graft_may_be_declined():
    scenario = _main_board([], hand=["Vigean Hydropon", "Grizzly Bears"])
    hydropon = scenario.put_onto_battlefield("Vigean Hydropon", "alice")
    scenario.will_take_the_may(False, source="Vigean Hydropon")
    bears = scenario.put_onto_battlefield("Grizzly Bears", "alice")
    _resolve_everything(scenario)
    assert bears.counter_count(Counter.PLUS_ONE) == 0
    assert hydropon.counter_count(Counter.PLUS_ONE) == 5


def test_graft_does_not_trigger_for_the_grafter_itself_or_with_no_counters():
    scenario = _main_board([], hand=["Simic Initiate", "Grizzly Bears"])
    initiate = scenario.put_onto_battlefield("Simic Initiate", "alice")
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == []  # "another creature" - not itself
    initiate.remove_counters(Counter.PLUS_ONE, 1)
    bears = scenario.put_onto_battlefield("Grizzly Bears", "alice")
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == []  # intervening if: no +1/+1 counter left
    assert bears.counter_count(Counter.PLUS_ONE) == 0


def test_graft_works_on_an_opponents_creature_too():
    """'another creature enters' - any controller's."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Vigean Hydropon"], library=["Plains"] * 6)
        .player("bob", hand=["Grizzly Bears"], library=["Plains"] * 6)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    hydropon = scenario.put_onto_battlefield("Vigean Hydropon", "alice")
    scenario.will_take_the_may(True, source="Vigean Hydropon")
    bears = scenario.put_onto_battlefield("Grizzly Bears", "bob")
    _resolve_everything(scenario)
    assert bears.counter_count(Counter.PLUS_ONE) == 1
    assert hydropon.counter_count(Counter.PLUS_ONE) == 4


def test_vigean_hydropon_cannot_attack_or_block():
    scenario = _combat_board(["Vigean Hydropon"], ["Grizzly Bears"])
    hydropon = scenario.creature("Vigean Hydropon", "alice")
    hydropon.summoning_sick = False
    assert not scenario.can_attack(hydropon)


def test_graft_cards_read_handled():
    for name in ("Vigean Hydropon", "Simic Initiate"):
        _support_is_handled(name)


# -- backup (CR 702.165) and the toughness-assigns-damage static -------------


def _cast_backup(scenario, name, target, *, lands):
    scenario.cast_and_resolve(name, *scenario.untapped_sources(*lands))
    scenario.game.put_triggers_on_stack()
    scenario.choose_trigger_targets(name, [target])
    _resolve_everything(scenario)


def test_backup_puts_a_counter_on_another_creature_and_grants_the_abilities_below():
    """CR 702.165a: Sigiled Sentinel's Vigilance goes to the target until end of turn."""
    scenario = _main_board(
        ["Forest", "Plains", "Plains", "Grizzly Bears"], hand=["Sigiled Sentinel"]
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    _cast_backup(scenario, "Sigiled Sentinel", bears, lands=["Plains", "Plains", "Forest"])
    assert bears.counter_count(Counter.PLUS_ONE) == 1
    assert has_keyword(bears, "vigilance", scenario.game)
    sentinel = scenario.creature("Sigiled Sentinel", "alice")
    assert sentinel.counter_count(Counter.PLUS_ONE) == 0


def test_backup_targeting_itself_only_gets_the_counter():
    scenario = _main_board(["Plains", "Plains", "Forest"], hand=["Sigiled Sentinel"])
    scenario.cast_and_resolve(
        "Sigiled Sentinel", *scenario.untapped_sources("Plains", "Plains", "Forest")
    )
    sentinel = scenario.creature("Sigiled Sentinel", "alice")
    scenario.game.put_triggers_on_stack()
    scenario.choose_trigger_targets("Sigiled Sentinel", [sentinel])
    _resolve_everything(scenario)
    assert sentinel.counter_count(Counter.PLUS_ONE) == 1
    assert scenario.game.characteristics_of(sentinel).power_toughness == (3, 3)


def test_backup_two_counters_on_a_second_printing_cragsmasher_yeti():
    scenario = _main_board(["Mountain"] * 6 + ["Grizzly Bears"], hand=["Cragsmasher Yeti"])
    bears = scenario.creature("Grizzly Bears", "alice")
    _cast_backup(scenario, "Cragsmasher Yeti", bears, lands=["Mountain"] * 6)
    assert bears.counter_count(Counter.PLUS_ONE) == 2
    assert has_keyword(bears, "trample", scenario.game)


def test_backup_grant_ends_with_the_turn():
    scenario = _main_board(
        ["Plains", "Plains", "Forest", "Grizzly Bears"], hand=["Sigiled Sentinel"]
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    _cast_backup(scenario, "Sigiled Sentinel", bears, lands=["Plains", "Plains", "Forest"])
    assert has_keyword(bears, "vigilance", scenario.game)
    scenario.game.cleanup_step()  # CR 514.2
    assert not has_keyword(bears, "vigilance", scenario.game)
    assert bears.counter_count(Counter.PLUS_ONE) == 1  # the counter stays


def test_streetwise_negotiator_grants_toughness_damage_to_another_creature():
    """Pillarfield Ox 2/4 + counter = 3/5 assigns 5, not 3, into a 0/4 wall."""
    scenario = _main_board(
        ["Forest", "Forest", "Pillarfield Ox"],
        ["Wall of Omens"],
        hand=["Streetwise Negotiator"],
    )
    ox = scenario.creature("Pillarfield Ox", "alice")
    ox.summoning_sick = False
    wall = scenario.creature("Wall of Omens", "bob")
    _cast_backup(scenario, "Streetwise Negotiator", ox, lands=["Forest", "Forest"])
    assert scenario.game.characteristics_of(ox).power_toughness == (3, 5)
    scenario.advance()  # beginning of combat
    while scenario.step is not Step.DECLARE_ATTACKERS:
        scenario.advance()
    scenario.attack_with(ox)
    scenario.advance()
    scenario.block(ox, wall)
    scenario.combat_damage()
    assert wall.zone is Zone.GRAVEYARD


def test_assigns_toughness_damage_without_the_grant_is_just_power():
    scenario = _combat_board(["Pillarfield Ox"], ["Wall of Omens"])
    ox = scenario.creature("Pillarfield Ox", "alice")
    ox.summoning_sick = False
    wall = scenario.creature("Wall of Omens", "bob")
    scenario.attack_with(ox)
    scenario.advance()
    scenario.block(ox, wall)
    scenario.combat_damage()
    assert wall.zone is Zone.BATTLEFIELD


def test_streetwise_negotiator_assigns_its_own_toughness_as_a_blocker():
    """The printed static: 1/3 (with a counter) blocks and deals 3 to a 3/3."""
    scenario = _combat_board(["Hill Giant"], ["Streetwise Negotiator"])
    giant = scenario.creature("Hill Giant", "alice")
    giant.summoning_sick = False
    negotiator = scenario.creature("Streetwise Negotiator", "bob")
    scenario.game.add_counters(negotiator, Counter.PLUS_ONE, 1)
    scenario.attack_with(giant)
    scenario.advance()
    scenario.block(giant, negotiator)
    scenario.combat_damage()
    assert giant.zone is Zone.GRAVEYARD


def test_streetwise_negotiator_without_the_counter_assigns_toughness_two():
    scenario = _combat_board(["Hill Giant"], ["Streetwise Negotiator"])
    giant = scenario.creature("Hill Giant", "alice")
    giant.summoning_sick = False
    negotiator = scenario.creature("Streetwise Negotiator", "bob")
    scenario.attack_with(giant)
    scenario.advance()
    scenario.block(giant, negotiator)
    scenario.combat_damage()
    assert giant.zone is Zone.BATTLEFIELD  # 2 damage on a 3/3
    assert negotiator.zone is Zone.GRAVEYARD


def test_backup_cards_read_handled():
    for name in ("Streetwise Negotiator", "Sigiled Sentinel", "Cragsmasher Yeti"):
        _support_is_handled(name)


# -- connive as a keyword on a granted trigger (CR 701.50), attacking alone --


def _aura_board(*, attackers, blockers=(), hand=("Security Bypass",)):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=["Island", "Island", *attackers],
            hand=[*hand, "Forest", "Grizzly Bears"],
            library=["Plains"] * 6,
        )
        .player("bob", battlefield=list(blockers), library=["Plains"] * 6)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    for creature in scenario.game.permanents_controlled_by("alice"):
        creature.summoning_sick = False
    return scenario


def _enchant(scenario, creature):
    scenario.cast_and_resolve(
        "Security Bypass", *scenario.untapped_sources("Island", "Island"), targets=[creature]
    )


def _to_attackers(scenario):
    while scenario.step is not Step.DECLARE_ATTACKERS:
        scenario.advance()


def test_security_bypass_attacking_alone_cannot_be_blocked():
    scenario = _aura_board(attackers=["Hill Giant"], blockers=["Grizzly Bears"])
    giant = scenario.creature("Hill Giant", "alice")
    _enchant(scenario, giant)
    _to_attackers(scenario)
    scenario.attack_with(giant)
    scenario.advance()
    bears = scenario.creature("Grizzly Bears", "bob")
    with pytest.raises(ValueError, match="(?i)block"):
        scenario.block(giant, bears)


def test_security_bypass_does_nothing_when_it_attacks_with_a_friend():
    scenario = _aura_board(attackers=["Hill Giant", "Llanowar Elves"], blockers=["Grizzly Bears"])
    giant = scenario.creature("Hill Giant", "alice")
    elves = scenario.creature("Llanowar Elves", "alice")
    _enchant(scenario, giant)
    _to_attackers(scenario)
    scenario.attack_with(giant, elves)
    scenario.advance()
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.block(giant, bears)  # legal: the enchanted creature is not attacking alone


def test_security_bypass_enchanted_creature_connives_on_combat_damage_to_a_player():
    scenario = _aura_board(attackers=["Hill Giant"])
    giant = scenario.creature("Hill Giant", "alice")
    _enchant(scenario, giant)
    _to_attackers(scenario)
    scenario.attack_with(giant)
    scenario.advance()
    scenario.no_blocks()
    hand_size = len(scenario.player("alice").hand)
    scenario.will_discard(scenario.find("Forest", Zone.HAND, "alice"))
    scenario.combat_damage()
    _resolve_everything(scenario)
    assert len(scenario.player("alice").hand) == hand_size  # drew one, discarded one
    assert scenario.find("Forest", Zone.GRAVEYARD, "alice")
    assert giant.counter_count(Counter.PLUS_ONE) == 0  # a land discarded: no counter


def test_connive_counter_for_a_nonland_discard_via_the_granted_trigger():
    scenario = _aura_board(attackers=["Hill Giant"])
    giant = scenario.creature("Hill Giant", "alice")
    _enchant(scenario, giant)
    _to_attackers(scenario)
    scenario.attack_with(giant)
    scenario.advance()
    scenario.no_blocks()
    scenario.will_discard(scenario.find("Grizzly Bears", Zone.HAND, "alice"))
    scenario.combat_damage()
    _resolve_everything(scenario)
    assert giant.counter_count(Counter.PLUS_ONE) == 1


def test_connive_keyword_on_security_bypass_and_raffines_informant_reads_handled():
    for name in ("Security Bypass", "Raffine's Informant"):
        _support_is_handled(name)


# -- champion (CR 702.72) ----------------------------------------------------


def _champion_board(on_battlefield, hand):
    return _main_board(on_battlefield, hand=hand)


def _cast_champion(scenario, name, lands):
    scenario.cast_and_resolve(name, *scenario.untapped_sources(*lands))
    _resolve_everything(scenario)


def test_champion_exiles_another_matching_creature_instead_of_being_sacrificed():
    """CR 702.72a: Changeling Hero is every creature type, so it is a Kithkin."""
    scenario = _champion_board(
        ["Plains", "Plains", "Plains", "Plains", "Changeling Hero"], ["Thoughtweft Trio"]
    )
    hero = scenario.creature("Changeling Hero", "alice")
    scenario.will_choose_cards(hero, source="Thoughtweft Trio")
    _cast_champion(scenario, "Thoughtweft Trio", ["Plains"] * 4)
    trio = scenario.creature("Thoughtweft Trio", "alice")
    assert trio.zone is Zone.BATTLEFIELD
    assert hero.zone is Zone.EXILE


def test_champion_sacrifices_itself_with_nothing_to_exile():
    scenario = _champion_board(["Plains"] * 4 + ["Grizzly Bears"], ["Thoughtweft Trio"])
    _cast_champion(scenario, "Thoughtweft Trio", ["Plains"] * 4)
    assert scenario.find("Thoughtweft Trio", Zone.GRAVEYARD, "alice")
    assert scenario.creature("Grizzly Bears", "alice").zone is Zone.BATTLEFIELD


def test_champion_may_decline_the_exile_and_sacrifice_instead():
    scenario = _champion_board(["Plains"] * 4 + ["Changeling Hero"], ["Thoughtweft Trio"])
    hero = scenario.creature("Changeling Hero", "alice")
    scenario.will_choose_cards(source="Thoughtweft Trio")
    _cast_champion(scenario, "Thoughtweft Trio", ["Plains"] * 4)
    assert scenario.find("Thoughtweft Trio", Zone.GRAVEYARD, "alice")
    assert hero.zone is Zone.BATTLEFIELD


def test_champion_returns_the_exiled_card_when_it_leaves_the_battlefield():
    """CR 702.72a's second ability, linked to the first by CR 702.72b."""
    scenario = _champion_board(["Mountain"] * 4 + ["Swab Goblin"], ["Lightning Crafter"])
    goblin = scenario.creature("Swab Goblin", "alice")
    scenario.will_choose_cards(goblin, source="Lightning Crafter")
    _cast_champion(scenario, "Lightning Crafter", ["Mountain"] * 4)
    crafter = scenario.creature("Lightning Crafter", "alice")
    assert goblin.zone is Zone.EXILE
    scenario.game.destroy(crafter)
    _resolve_everything(scenario)
    assert goblin.zone is Zone.BATTLEFIELD
    assert crafter.zone is Zone.GRAVEYARD


def test_a_returned_champion_target_is_a_new_object_that_can_champion_again():
    """Changeling Hero returns and, entering, must champion a creature itself (CR 702.72a)."""
    scenario = _champion_board(["Plains"] * 4 + ["Changeling Hero"], ["Thoughtweft Trio"])
    hero = scenario.creature("Changeling Hero", "alice")
    scenario.will_choose_cards(hero, source="Thoughtweft Trio")
    _cast_champion(scenario, "Thoughtweft Trio", ["Plains"] * 4)
    trio = scenario.creature("Thoughtweft Trio", "alice")
    scenario.game.destroy(trio)
    _resolve_everything(scenario)
    # Hero came back, had nothing to exile for its own champion, and was sacrificed.
    assert hero.zone is Zone.GRAVEYARD


def test_champion_sacrificed_with_nothing_exiled_returns_nothing():
    scenario = _champion_board(["Plains"] * 4 + ["Grizzly Bears"], ["Thoughtweft Trio"])
    _cast_champion(scenario, "Thoughtweft Trio", ["Plains"] * 4)
    assert scenario.creature("Grizzly Bears", "alice").zone is Zone.BATTLEFIELD
    assert scenario.game.exile == []


def test_champion_cannot_exile_itself_for_its_own_cost():
    scenario = _champion_board(["Plains"] * 4, ["Thoughtweft Trio"])
    _cast_champion(scenario, "Thoughtweft Trio", ["Plains"] * 4)
    assert scenario.find("Thoughtweft Trio", Zone.GRAVEYARD, "alice")


def test_champion_two_subtype_alternatives_goblin_or_shaman():
    """Lightning Crafter 'Champion a Goblin or Shaman': a Goblin qualifies."""
    scenario = _champion_board(["Mountain"] * 4 + ["Swab Goblin"], ["Lightning Crafter"])
    goblin = scenario.creature("Swab Goblin", "alice")
    scenario.will_choose_cards(goblin, source="Lightning Crafter")
    _cast_champion(scenario, "Lightning Crafter", ["Mountain"] * 4)
    assert scenario.creature("Lightning Crafter", "alice").zone is Zone.BATTLEFIELD
    assert goblin.zone is Zone.EXILE


def test_champion_alternatives_reject_a_creature_of_neither_type():
    scenario = _champion_board(["Mountain"] * 4 + ["Grizzly Bears"], ["Lightning Crafter"])
    _cast_champion(scenario, "Lightning Crafter", ["Mountain"] * 4)
    assert scenario.find("Lightning Crafter", Zone.GRAVEYARD, "alice")


def test_champion_creature_object_takes_any_creature_changeling_hero():
    scenario = _champion_board(["Plains"] * 5 + ["Grizzly Bears"], ["Changeling Hero"])
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.will_choose_cards(bears, source="Changeling Hero")
    _cast_champion(scenario, "Changeling Hero", ["Plains"] * 5)
    assert scenario.creature("Changeling Hero", "alice").zone is Zone.BATTLEFIELD
    assert bears.zone is Zone.EXILE


def test_champion_elemental_nova_chaser_with_a_changeling():
    scenario = _champion_board(["Mountain"] * 4 + ["Changeling Hero"], ["Nova Chaser"])
    hero = scenario.creature("Changeling Hero", "alice")
    scenario.will_choose_cards(hero, source="Nova Chaser")
    _cast_champion(scenario, "Nova Chaser", ["Mountain"] * 4)
    assert hero.zone is Zone.EXILE


def test_champion_cards_read_handled():
    for name in ("Thoughtweft Trio", "Nova Chaser", "Changeling Hero", "Lightning Crafter"):
        _support_is_handled(name)


# -- fateseal (CR 701.29) ----------------------------------------------------


def _sliver_board(hand_alice, hand_bob=()):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=list(hand_alice), library=["Plains", "Island", "Swamp", "Forest"])
        .player("bob", hand=list(hand_bob), library=["Mountain", "Forest", "Swamp", "Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_fateseal_puts_the_top_card_of_an_opponents_library_on_the_bottom():
    scenario = _sliver_board(["Mesmeric Sliver"])
    top = scenario.top_of_library(1, "bob")[0]
    scenario.will_take_the_may(True, source="Mesmeric Sliver")
    scenario.scry_bottoming(top, username="alice")
    scenario.put_onto_battlefield("Mesmeric Sliver", "alice")
    _resolve_everything(scenario)
    assert scenario.player("bob").library[-1] is top
    assert scenario.player("bob").library[0] is not top


def test_fateseal_may_keep_the_card_on_top():
    scenario = _sliver_board(["Mesmeric Sliver"])
    top = scenario.top_of_library(1, "bob")[0]
    scenario.will_take_the_may(True, source="Mesmeric Sliver")
    scenario.scry_keeping_everything_on_top(username="alice")
    scenario.put_onto_battlefield("Mesmeric Sliver", "alice")
    _resolve_everything(scenario)
    assert scenario.player("bob").library[0] is top


def test_fateseal_does_not_touch_the_controllers_own_library():
    scenario = _sliver_board(["Mesmeric Sliver"])
    mine = scenario.top_of_library(1, "alice")[0]
    scenario.will_take_the_may(True, source="Mesmeric Sliver")
    scenario.scry_bottoming(scenario.top_of_library(1, "bob")[0], username="alice")
    scenario.put_onto_battlefield("Mesmeric Sliver", "alice")
    _resolve_everything(scenario)
    assert scenario.player("alice").library[0] is mine


def test_fateseal_is_optional():
    scenario = _sliver_board(["Mesmeric Sliver"])
    top = scenario.top_of_library(1, "bob")[0]
    scenario.will_take_the_may(False, source="Mesmeric Sliver")
    scenario.put_onto_battlefield("Mesmeric Sliver", "alice")
    _resolve_everything(scenario)
    assert scenario.player("bob").library[0] is top
    assert all(question.kind.value != "scry" for question in scenario.questions_asked())


def test_all_slivers_have_the_fateseal_trigger_including_an_opponents():
    """'All Slivers' - bob's Sliver Construct fateseals alice's library."""
    scenario = _sliver_board(["Mesmeric Sliver"], ["Sliver Construct"])
    scenario.put_onto_battlefield("Mesmeric Sliver", "alice")
    scenario.will_take_the_may(False, source="Mesmeric Sliver")
    _resolve_everything(scenario)
    top = scenario.top_of_library(1, "alice")[0]
    scenario.will_take_the_may(True, source="Sliver Construct")
    scenario.scry_bottoming(top, username="bob")
    scenario.put_onto_battlefield("Sliver Construct", "bob")
    _resolve_everything(scenario)
    assert scenario.player("alice").library[-1] is top


def test_fateseal_two_on_a_second_printing_spin_into_myth():
    """Spin into Myth: 'then fateseal 2' - order two cards: one bottom, one top."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=["Island"] * 5,
            hand=["Spin into Myth"],
            library=["Plains"] * 4,
        )
        .player(
            "bob", battlefield=["Grizzly Bears"], library=["Mountain", "Forest", "Swamp", "Island"]
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    first, second = scenario.top_of_library(2, "bob")
    scenario.scry_bottoming(first, username="alice")
    scenario.cast_and_resolve(
        "Spin into Myth", *scenario.untapped_sources(*["Island"] * 5), targets=[bears]
    )
    library = scenario.player("bob").library
    assert library[-1] is first
    assert library[1] is second  # bears on top, the unbottomed card beneath it
    assert library[0].name == "Grizzly Bears"


def test_fateseal_cards_read_handled():
    for name in ("Mesmeric Sliver", "Spin into Myth", "Sliver Construct"):
        _support_is_handled(name)


# -- clash (CR 701.30) -------------------------------------------------------


def _clash_board(alice_library, bob_library, hand):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=list(hand), library=list(alice_library))
        .player("bob", library=list(bob_library))
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_winning_a_clash_puts_a_counter_on_nath_s_elite():
    """CR 701.30d: a greater mana value wins - Elite (alice) reveals Craw Wurm (6)."""
    scenario = _clash_board(["Craw Wurm"], ["Island"], ["Nath's Elite"])
    elite = scenario.put_onto_battlefield("Nath's Elite", "alice")
    _resolve_everything(scenario)
    assert elite.counter_count(Counter.PLUS_ONE) == 1


def test_losing_a_clash_does_nothing():
    scenario = _clash_board(["Island"], ["Craw Wurm"], ["Nath's Elite"])
    elite = scenario.put_onto_battlefield("Nath's Elite", "alice")
    _resolve_everything(scenario)
    assert elite.counter_count(Counter.PLUS_ONE) == 0


def test_a_tied_clash_is_not_a_win():
    """CR 701.30d: 'higher mana value than all other cards revealed'."""
    scenario = _clash_board(["Grizzly Bears"], ["Grizzly Bears"], ["Nath's Elite"])
    elite = scenario.put_onto_battlefield("Nath's Elite", "alice")
    _resolve_everything(scenario)
    assert elite.counter_count(Counter.PLUS_ONE) == 0


def test_a_clash_reveals_both_top_cards_and_each_may_bottom_theirs():
    scenario = _clash_board(["Craw Wurm", "Island"], ["Island", "Plains"], ["Nath's Elite"])
    wurm = scenario.top_of_library(1, "alice")[0]
    scenario.will_take_the_may(True, source="Nath's Elite", username="alice")
    scenario.will_take_the_may(False, source="Nath's Elite", username="bob")
    scenario.put_onto_battlefield("Nath's Elite", "alice")
    _resolve_everything(scenario)
    assert scenario.player("alice").library[-1] is wurm
    assert scenario.player("bob").library[0].name == "Island"


def test_an_opponent_with_an_empty_library_reveals_nothing_and_loses_the_clash():
    scenario = _clash_board(["Grizzly Bears"], [], ["Nath's Elite"])
    elite = scenario.put_onto_battlefield("Nath's Elite", "alice")
    _resolve_everything(scenario)
    assert elite.counter_count(Counter.PLUS_ONE) == 1


def test_oaken_brawler_second_printing_of_the_clash_template():
    scenario = _clash_board(["Craw Wurm"], ["Island"], ["Oaken Brawler"])
    brawler = scenario.put_onto_battlefield("Oaken Brawler", "alice")
    _resolve_everything(scenario)
    assert brawler.counter_count(Counter.PLUS_ONE) == 1


def test_clash_cards_read_handled():
    for name in ("Nath's Elite", "Oaken Brawler"):
        _support_is_handled(name)


# -- Brothers Yamazaki: the legend rule off for exactly two (CR 704.5j) ------


def _yamazaki_board(count):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=["Brothers Yamazaki"] * count,
            library=["Plains"] * 4,
        )
        .player("bob", library=["Plains"] * 4)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _yamazakis(scenario):
    return [
        c for c in scenario.game.permanents_controlled_by("alice") if c.name == "Brothers Yamazaki"
    ]


def test_two_brothers_yamazaki_both_survive_the_legend_rule():
    scenario = _yamazaki_board(2)
    scenario.state_based_actions()
    assert len(_yamazakis(scenario)) == 2


def test_the_other_brother_gets_plus_two_plus_two_and_haste():
    scenario = _yamazaki_board(2)
    scenario.state_based_actions()
    first, second = _yamazakis(scenario)
    # Each is "another creature named Brothers Yamazaki" to the other.
    assert scenario.game.characteristics_of(first).power_toughness == (4, 3)
    assert scenario.game.characteristics_of(second).power_toughness == (4, 3)
    assert has_keyword(first, "haste", scenario.game)


def test_three_brothers_yamazaki_fall_back_to_the_legend_rule():
    """CR 704.5j: 'exactly two' - with three, the player keeps one."""
    scenario = _yamazaki_board(3)
    scenario.state_based_actions()
    assert len(_yamazakis(scenario)) == 1


def test_one_brother_is_just_a_legend():
    scenario = _yamazaki_board(1)
    scenario.state_based_actions()
    assert len(_yamazakis(scenario)) == 1
    assert scenario.game.characteristics_of(_yamazakis(scenario)[0]).power_toughness == (2, 1)


def test_other_legends_still_obey_the_legend_rule_beside_two_brothers():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=["Brothers Yamazaki", "Brothers Yamazaki", "Kentaro, the Smiling Cat"] * 1
            + ["Kentaro, the Smiling Cat"],
            library=["Plains"] * 4,
        )
        .player("bob", library=["Plains"] * 4)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.state_based_actions()
    names = sorted(c.name for c in scenario.game.permanents_controlled_by("alice"))
    assert names == ["Brothers Yamazaki", "Brothers Yamazaki", "Kentaro, the Smiling Cat"]


def test_brothers_yamazaki_reads_handled():
    _support_is_handled("Brothers Yamazaki")


# -- assemble (CR 701.45) ----------------------------------------------------


def _boss_board(alice, bob=()):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=list(alice), library=["Plains"] * 4)
        .player("bob", battlefield=list(bob), library=["Plains"] * 4)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_a_rigger_assembles_two_contraptions_with_steamflogger_boss():
    """CR 701.45a + CR 614.1a: the Boss is a Rigger you control, so it assembles two."""
    scenario = _boss_board(["Steamflogger Boss"])
    boss = scenario.creature("Steamflogger Boss", "alice")
    assert scenario.game.assembling_count("alice", boss) == 2


def test_a_non_rigger_assembles_one_contraption():
    scenario = _boss_board(["Steamflogger Boss", "Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears", "alice")
    assert scenario.game.assembling_count("alice", bears) == 1


def test_an_opponents_boss_does_not_double_my_rigger():
    scenario = _boss_board(["Steamflogger Boss"], ["Steamflogger Boss"])
    mine = scenario.creature("Steamflogger Boss", "alice")
    theirs = scenario.creature("Steamflogger Boss", "bob")
    assert scenario.game.assembling_count("alice", mine) == 2
    assert scenario.game.assembling_count("bob", theirs) == 2
    scenario.game.destroy(theirs)
    assert scenario.game.assembling_count("alice", mine) == 2


def test_other_riggers_get_plus_one_plus_zero_and_haste():
    scenario = _boss_board(["Steamflogger Boss", "Steamflogger Boss"])
    first, second = scenario.creatures("Steamflogger Boss", "Steamflogger Boss", username="alice")
    assert scenario.game.characteristics_of(first).power_toughness == (4, 3)
    assert has_keyword(second, "haste", scenario.game)


def test_steamflogger_boss_reads_handled():
    _support_is_handled("Steamflogger Boss")


# -- the other statics on the listed cards -----------------------------------


def test_samurai_of_the_pale_curtain_exiles_permanents_headed_for_a_graveyard():
    scenario = _boss_board(["Samurai of the Pale Curtain", "Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.game.destroy(bears)
    assert bears.zone is Zone.EXILE


def test_kentaro_lets_you_pay_x_for_samurai_spells_with_x_their_mana_value():
    """Kentaro: pay {X} rather than the mana cost of a Samurai spell, X its mana value."""
    scenario = _main_board(
        ["Kentaro, the Smiling Cat", "Plains", "Plains", "Plains"],
        hand=["Samurai of the Pale Curtain"],
    )
    scenario.cast_and_resolve(
        "Samurai of the Pale Curtain", *scenario.untapped_sources("Plains", "Plains")
    )
    assert scenario.creature("Samurai of the Pale Curtain", "alice").zone is Zone.BATTLEFIELD


def test_knight_of_sorrows_can_block_an_additional_creature():
    scenario = _combat_board(["Grizzly Bears", "Hill Giant"], ["Knight of Sorrows"])
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "alice")
    bears.summoning_sick = giant.summoning_sick = False
    knight = scenario.creature("Knight of Sorrows", "bob")
    scenario.attack_with(bears, giant)
    scenario.advance()
    scenario.block(bears, knight)
    scenario.block(giant, knight)
    assert scenario.game.combat.attack_by(bears.id).blockers
    assert scenario.game.combat.attack_by(giant.id).blockers


def test_thoughtweft_trio_can_block_any_number_of_creatures():
    scenario = _combat_board(
        ["Grizzly Bears", "Hill Giant", "Llanowar Elves"], ["Thoughtweft Trio"]
    )
    attackers = [
        scenario.creature(n, "alice") for n in ("Grizzly Bears", "Hill Giant", "Llanowar Elves")
    ]
    for attacker in attackers:
        attacker.summoning_sick = False
    trio = scenario.creature("Thoughtweft Trio", "bob")
    scenario.attack_with(*attackers)
    scenario.advance()
    for attacker in attackers:
        scenario.block(attacker, trio)
    assert all(scenario.game.combat.attack_by(a.id).blockers for a in attackers)


def test_a_creature_without_the_ability_blocks_only_one():
    scenario = _combat_board(["Grizzly Bears", "Hill Giant"], ["Grizzly Bears"])
    bears, giant = (scenario.creature(n, "alice") for n in ("Grizzly Bears", "Hill Giant"))
    bears.summoning_sick = giant.summoning_sick = False
    blocker = scenario.creature("Grizzly Bears", "bob")
    scenario.attack_with(bears, giant)
    scenario.advance()
    scenario.block(bears, blocker)
    with pytest.raises(ValueError):
        scenario.block(giant, blocker)


def test_nath_s_elite_forces_every_able_creature_to_block_it():
    scenario = _combat_board(["Nath's Elite"], ["Grizzly Bears", "Hill Giant"])
    elite = scenario.creature("Nath's Elite", "alice")
    elite.summoning_sick = False
    scenario.attack_with(elite)
    scenario.advance()
    with pytest.raises(ValueError):
        scenario.no_blocks()
    bears = scenario.creature("Grizzly Bears", "bob")
    giant = scenario.creature("Hill Giant", "bob")
    scenario.block(elite, bears, giant)
    assert len(scenario.game.combat.attack_by(elite.id).blockers) == 2


def test_wojek_bodyguard_cannot_block_alone_either():
    scenario = _combat_board(["Grizzly Bears"], ["Wojek Bodyguard"])
    bears = scenario.creature("Grizzly Bears", "alice")
    bears.summoning_sick = False
    bodyguard = scenario.creature("Wojek Bodyguard", "bob")
    scenario.attack_with(bears)
    scenario.advance()
    with pytest.raises(ValueError):
        scenario.block(bears, bodyguard)


def test_listed_cards_all_read_handled():
    for name in (
        "Battlefield Scavenger",
        "Resolute Survivors",
        "Trueheart Twins",
        "Vizier of the True",
        "Brothers Yamazaki",
        "Kentaro, the Smiling Cat",
        "Samurai of the Pale Curtain",
        "Knight of Sorrows",
        "Wojek Bodyguard",
        "Vigean Hydropon",
        "Streetwise Negotiator",
        "Security Bypass",
        "Mesmeric Sliver",
        "Thoughtweft Trio",
        "Nath's Elite",
        "Steamflogger Boss",
    ):
        _support_is_handled(name)
