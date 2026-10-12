"""EP-01-R3 T2: exert-event triggers and the combat/trigger keywords.

Every CR number below was read with `mise run rules:find` in the session that
wrote this file:

- CR 701.43 exert; CR 701.43d "you may exert [this creature] as it attacks".
- CR 702.45a bushido; CR 702.135a afterlife; CR 702.134a mentor.
- CR 702.66 graft is looked up where its tests live below.
"""

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


def test_bushido_two_reads_the_number_takeno_gets_plus_two_plus_two():
    """Second printing, a different N: Takeno, Samurai General (bushido 2)."""
    scenario = _combat_board(["Takeno, Samurai General"], ["Grizzly Bears"])
    takeno = scenario.creature("Takeno, Samurai General", "alice")
    takeno.summoning_sick = False
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.attack_with(takeno)
    scenario.advance()
    scenario.block(takeno, bears)
    _resolve_everything(scenario)
    assert scenario.game.characteristics_of(takeno).power_toughness == (5, 5)


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
    """CR 702.134a: Legion Warboss (2) mentors Grizzly Bears... power 2 is not
    less, so a 1-power Elvish Mystic is the target."""
    scenario = _combat_board(["Legion Warboss", "Llanowar Elves"], [])
    warboss = scenario.creature("Legion Warboss", "alice")
    elves = scenario.creature("Llanowar Elves", "alice")
    warboss.summoning_sick = elves.summoning_sick = False
    scenario.attack_with(warboss, elves)
    scenario.game.put_triggers_on_stack()
    scenario.choose_trigger_targets("Legion Warboss", [elves])
    _resolve_everything(scenario)
    assert elves.counter_count(Counter.PLUS_ONE) == 1
    assert warboss.counter_count(Counter.PLUS_ONE) == 0


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
