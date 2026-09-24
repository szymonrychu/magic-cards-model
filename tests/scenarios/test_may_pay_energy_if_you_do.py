"""Scenario: "you may pay `<energy>`. If you do, `<consequence>`." - every
in-format printing of the shape whose consequence used to go unread.

CR 118.12: "[A player] may [do something]. If [that player] [does ...],
[effect]." The action is a cost, paid when the ability resolves, and the
consequence runs on that same ability - no second stack object (that is CR
603.12's "When you do", `test_reflexive_pay_energy_when_you_do.py`). CR
107.14: "To pay {E}, a player removes one energy counter from themselves."
CR 118.3: "A player can't pay a cost without having the necessary resources
to pay it fully", so with too few energy counters the payment is not
offered and nothing happens. Declining does nothing either.

Before this, each of these cards crashed with `ValueError: unsupported mana
symbol: {E}`: the energy reader declined an unread consequence and the
ordinary-mana twin, whose symbol group accepted {E}, took the text.

Oracle text, pulled with `scripts/add_card.py` and verified against the
printings pool (every card Modern-legal):

- **Hexgold Slith**: "Whenever this creature attacks, you may pay {E}{E}. If
  you do, it gains first strike until end of turn."
- **Aetherstream Leopard**: "... you may pay {E}. If you do, it gets +2/+0
  until end of turn."
- **Voltaic Brawler**: "... you may pay {E}. If you do, it gets +1/+1 and
  gains trample until end of turn."
- **Riparian Tiger**: "... you may pay {E}{E}. If you do, it gets +2/+2 until
  end of turn."
- **Conduit Goblin**: "At the beginning of combat on your turn, you may pay
  {E}. If you do, another target creature you control gets +1/+0 and gains
  haste until end of turn."
- **Smelted Chargebug**: "Whenever this creature attacks, you may pay {E}. If
  you do, another target attacking creature gets +1/+0 and gains menace until
  end of turn."
- **Maulfist Doorbuster**: "Whenever this creature attacks, you may pay {E}.
  If you do, target creature can't block this turn."

Second printings proving the energy reader beyond the cards that exposed it
(none of them in the api deck pool):

- **Eddytrail Hawk**: "... you may pay {E}. If you do, another target
  attacking creature gains flying until end of turn."
- **Consul's Shieldguard**: "... you may pay {E}. If you do, another target
  attacking creature gains indestructible until end of turn."
- **Aetherstorm Roc**: "... you may pay {E}{E}. If you do, put a +1/+1
  counter on it and tap up to one target creature defending player controls."

The same consequence readers on an ordinary-mana payment are proven in
`test_may_pay_mana_consequences.py`.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import Keyword, has_keyword
from magic_cards_model.machines.decisions import DecisionKind
from magic_cards_model.machines.keywords import is_indestructible
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter

from .harness import Scenario


def _energy_questions(scenario: Scenario) -> list:
    return [q for q in scenario.questions_asked() if q.kind is DecisionKind.PAY_ENERGY]


def _attack_board(attacker: str, energy: int, *others: str, bob: tuple[str, ...] = ()) -> Scenario:
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=[attacker, *others])
        .player("bob", battlefield=list(bob))
        .build()
    )
    scenario.player("alice").add_counters(Counter.ENERGY, energy)
    scenario.start_at(Step.DECLARE_ATTACKERS)
    return scenario


# --------------------------------------------------------------------------
# "it gets/gains ..." - the source anaphor (CR 603.2: "it" is the creature the
# trigger event names, here the attacking source itself)
# --------------------------------------------------------------------------


def test_aetherstream_leopard_pays_and_gets_plus_two_plus_zero():
    scenario = _attack_board("Aetherstream Leopard", 1)
    leopard = scenario.creature("Aetherstream Leopard", "alice")
    scenario.will_pay_the_energy(True)

    scenario.attack_with(leopard)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert scenario.player("alice").energy == 0
    assert scenario.game.power_of(leopard) == 4
    assert scenario.game.toughness_of(leopard) == 3
    assert scenario.stack_names() == [], "CR 118.12: no second stack object"


def test_aetherstream_leopard_declining_spends_nothing_and_changes_nothing():
    scenario = _attack_board("Aetherstream Leopard", 1)
    leopard = scenario.creature("Aetherstream Leopard", "alice")
    scenario.will_pay_the_energy(False)

    scenario.attack_with(leopard)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert scenario.player("alice").energy == 1
    assert scenario.game.power_of(leopard) == 2


def test_aetherstream_leopard_with_no_energy_is_not_offered_the_payment():
    """CR 118.3: the affirmative is illegal with no energy counter, so the
    question's only legal answer is "no" and the pump never happens."""
    scenario = _attack_board("Aetherstream Leopard", 0)
    leopard = scenario.creature("Aetherstream Leopard", "alice")

    scenario.attack_with(leopard)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    (question,) = _energy_questions(scenario)
    assert question.affirmative_is_legal is False
    assert scenario.player("alice").energy == 0
    assert scenario.game.power_of(leopard) == 2


def test_the_pump_ends_at_end_of_turn():
    """CR 611.2a: "until end of turn" - the cleanup step ends it."""
    scenario = _attack_board("Aetherstream Leopard", 1)
    leopard = scenario.creature("Aetherstream Leopard", "alice")
    scenario.will_pay_the_energy(True)
    scenario.attack_with(leopard)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()
    assert scenario.game.power_of(leopard) == 4

    scenario.game.cleanup_step()

    assert scenario.game.power_of(leopard) == 2


def test_riparian_tiger_needs_both_energy_and_gets_plus_two_plus_two():
    scenario = _attack_board("Riparian Tiger", 2)
    tiger = scenario.creature("Riparian Tiger", "alice")
    scenario.will_pay_the_energy(True)

    scenario.attack_with(tiger)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert scenario.player("alice").energy == 0
    assert (scenario.game.power_of(tiger), scenario.game.toughness_of(tiger)) == (6, 6)


def test_riparian_tiger_with_one_energy_cannot_pay_two():
    """CR 118.3: one counter is not enough for {E}{E}, and it is not spent."""
    scenario = _attack_board("Riparian Tiger", 1)
    tiger = scenario.creature("Riparian Tiger", "alice")

    scenario.attack_with(tiger)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    (question,) = _energy_questions(scenario)
    assert question.amount == 2
    assert question.affirmative_is_legal is False
    assert scenario.player("alice").energy == 1
    assert scenario.game.power_of(tiger) == 4


def test_voltaic_brawler_gets_plus_one_plus_one_and_gains_trample():
    scenario = _attack_board("Voltaic Brawler", 1)
    brawler = scenario.creature("Voltaic Brawler", "alice")
    scenario.will_pay_the_energy(True)

    scenario.attack_with(brawler)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert (scenario.game.power_of(brawler), scenario.game.toughness_of(brawler)) == (4, 3)
    assert has_keyword(brawler, Keyword.TRAMPLE, scenario.game)


def test_voltaic_brawler_declined_gains_nothing():
    scenario = _attack_board("Voltaic Brawler", 1)
    brawler = scenario.creature("Voltaic Brawler", "alice")
    scenario.will_pay_the_energy(False)

    scenario.attack_with(brawler)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert scenario.player("alice").energy == 1
    assert not has_keyword(brawler, Keyword.TRAMPLE, scenario.game)


def test_hexgold_slith_pays_two_and_gains_first_strike():
    scenario = _attack_board("Hexgold Slith", 2)
    slith = scenario.creature("Hexgold Slith", "alice")
    scenario.will_pay_the_energy(True)

    scenario.attack_with(slith)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert scenario.player("alice").energy == 0
    assert has_keyword(slith, Keyword.FIRST_STRIKE, scenario.game)


def test_hexgold_slith_declined_keeps_its_energy():
    scenario = _attack_board("Hexgold Slith", 2)
    slith = scenario.creature("Hexgold Slith", "alice")
    scenario.will_pay_the_energy(False)

    scenario.attack_with(slith)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert scenario.player("alice").energy == 2
    assert not has_keyword(slith, Keyword.FIRST_STRIKE, scenario.game)


def test_the_source_gone_by_resolution_leaves_it_nothing_to_pump():
    """CR 118.12's cost is still offered and may still be paid, but "it" is
    the attacking creature, which has left the battlefield (CR 400.7), so the
    pump affects nothing."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Aetherstream Leopard"])
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .build()
    )
    scenario.player("alice").add_counters(Counter.ENERGY, 1)
    scenario.start_at(Step.DECLARE_ATTACKERS)
    leopard = scenario.creature("Aetherstream Leopard", "alice")
    scenario.attack_with(leopard)
    scenario.game.put_triggers_on_stack()
    scenario.pass_priority("alice")
    (mountain,) = scenario.untapped_sources("Mountain", username="bob")
    scenario.cast_and_resolve("Lightning Bolt", mountain, username="bob", targets=[leopard])
    assert leopard.zone is Zone.GRAVEYARD

    scenario.will_pay_the_energy(True)
    scenario.pass_until_resolved()

    assert scenario.stack_names() == []
    assert scenario.game.continuous_effects.layer_notices == []


# --------------------------------------------------------------------------
# "another target [attacking] creature [you control] gets +N/+N and gains ..."
# --------------------------------------------------------------------------


def test_smelted_chargebug_pumps_another_attacking_creature_and_grants_menace():
    scenario = _attack_board("Smelted Chargebug", 1, "Grizzly Bears")
    chargebug = scenario.creature("Smelted Chargebug", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.will_pay_the_energy(True)

    scenario.attack_with(chargebug, bears)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert scenario.player("alice").energy == 0
    assert scenario.game.power_of(bears) == 3
    assert has_keyword(bears, Keyword.MENACE, scenario.game)
    assert scenario.game.power_of(chargebug) == 1


def test_smelted_chargebug_attacking_alone_has_no_other_attacker_to_target():
    """CR 603.3d: "another" excludes the source, so with no other attacking
    creature the trigger has no legal target and is removed from the stack -
    the payment is never offered."""
    scenario = _attack_board("Smelted Chargebug", 1, "Grizzly Bears")
    chargebug = scenario.creature("Smelted Chargebug", "alice")

    scenario.attack_with(chargebug)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert _energy_questions(scenario) == []
    assert scenario.player("alice").energy == 1


def test_smelted_chargebug_cannot_target_a_creature_that_is_not_attacking():
    scenario = _attack_board("Smelted Chargebug", 1, "Grizzly Bears")
    chargebug = scenario.creature("Smelted Chargebug", "alice")

    scenario.attack_with(chargebug)  # the Bears stay home
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == []
    assert _energy_questions(scenario) == []


def test_smelted_chargebug_target_killed_in_response_does_not_resolve():
    """CR 608.2b: its only target is illegal on resolution, so the ability
    does not resolve at all - the payment is never asked and nothing is
    spent."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Smelted Chargebug", "Grizzly Bears"])
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .build()
    )
    scenario.player("alice").add_counters(Counter.ENERGY, 1)
    scenario.start_at(Step.DECLARE_ATTACKERS)
    chargebug = scenario.creature("Smelted Chargebug", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.attack_with(chargebug, bears)
    scenario.game.put_triggers_on_stack()
    scenario.pass_priority("alice")
    (mountain,) = scenario.untapped_sources("Mountain", username="bob")
    scenario.cast_and_resolve("Lightning Bolt", mountain, username="bob", targets=[bears])

    scenario.pass_until_resolved()

    assert _energy_questions(scenario) == []
    assert scenario.player("alice").energy == 1
    assert scenario.stack_names() == []


def _combat_board(energy: int, *others: str) -> Scenario:
    scenario = (
        Scenario()
        .player("alice", battlefield=["Conduit Goblin", *others])
        .player("bob", battlefield=[])
        .build()
    )
    scenario.player("alice").add_counters(Counter.ENERGY, energy)
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_conduit_goblin_pumps_and_hastes_another_creature_at_beginning_of_combat():
    scenario = _combat_board(1, "Grizzly Bears")
    goblin = scenario.creature("Conduit Goblin", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.choose_trigger_targets("Conduit Goblin", [bears])
    scenario.will_pay_the_energy(True)

    scenario.advance()  # beginning of combat: the trigger goes on the stack
    assert scenario.stack_names() == ["Conduit Goblin's triggered ability"]
    scenario.pass_until_resolved()

    assert scenario.player("alice").energy == 0
    assert scenario.game.power_of(bears) == 3
    assert has_keyword(bears, Keyword.HASTE, scenario.game)
    assert scenario.game.power_of(goblin) == 2
    assert not has_keyword(goblin, Keyword.HASTE, scenario.game)


def test_conduit_goblin_alone_has_no_other_creature_to_target():
    """CR 603.3d: "another target creature you control" can never be the
    Goblin itself; with no other creature the trigger is removed."""
    scenario = _combat_board(1)

    scenario.advance()

    assert scenario.stack_names() == []
    assert _energy_questions(scenario) == []
    assert scenario.player("alice").energy == 1


def test_conduit_goblin_declined_leaves_the_target_as_it_was():
    scenario = _combat_board(1, "Grizzly Bears")
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.choose_trigger_targets("Conduit Goblin", [bears])
    scenario.will_pay_the_energy(False)

    scenario.advance()
    scenario.pass_until_resolved()

    assert scenario.player("alice").energy == 1
    assert scenario.game.power_of(bears) == 2
    assert not has_keyword(bears, Keyword.HASTE, scenario.game)


def test_conduit_goblin_without_energy_changes_nothing():
    scenario = _combat_board(0, "Grizzly Bears")
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.choose_trigger_targets("Conduit Goblin", [bears])

    scenario.advance()
    scenario.pass_until_resolved()

    (question,) = _energy_questions(scenario)
    assert question.affirmative_is_legal is False
    assert scenario.game.power_of(bears) == 2


# --------------------------------------------------------------------------
# "target creature can't block this turn" (CR 509.1b's blocking restriction)
# --------------------------------------------------------------------------


def test_maulfist_doorbuster_stops_the_target_from_blocking():
    scenario = _attack_board("Maulfist Doorbuster", 1, bob=("Hill Giant",))
    doorbuster = scenario.creature("Maulfist Doorbuster", "alice")
    giant = scenario.creature("Hill Giant", "bob")
    scenario.will_pay_the_energy(True)

    scenario.choose_trigger_targets("Maulfist Doorbuster", [giant])
    scenario.attack_with(doorbuster)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert scenario.player("alice").energy == 0
    assert scenario.game.why_cannot_block(giant, doorbuster) is not None


def test_maulfist_doorbuster_declined_lets_the_target_block():
    scenario = _attack_board("Maulfist Doorbuster", 1, bob=("Hill Giant",))
    doorbuster = scenario.creature("Maulfist Doorbuster", "alice")
    giant = scenario.creature("Hill Giant", "bob")
    scenario.will_pay_the_energy(False)

    scenario.choose_trigger_targets("Maulfist Doorbuster", [giant])
    scenario.attack_with(doorbuster)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert scenario.player("alice").energy == 1
    assert scenario.game.why_cannot_block(giant, doorbuster) is None
    scenario.block(doorbuster, giant)


def test_maulfist_doorbuster_restriction_is_enforced_at_declare_blockers():
    """CR 509.1b: a declaration disobeying the restriction is illegal."""
    scenario = _attack_board("Maulfist Doorbuster", 1, bob=("Hill Giant", "Grizzly Bears"))
    doorbuster = scenario.creature("Maulfist Doorbuster", "alice")
    giant = scenario.creature("Hill Giant", "bob")
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.will_pay_the_energy(True)
    scenario.choose_trigger_targets("Maulfist Doorbuster", [giant])
    scenario.attack_with(doorbuster)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    try:
        scenario.block(doorbuster, giant)
    except ValueError:
        pass
    else:
        raise AssertionError("the Giant can't block this turn")
    scenario.block(doorbuster, bears)  # the untargeted Bears still may


def test_maulfist_doorbuster_restriction_lasts_only_this_turn():
    scenario = _attack_board("Maulfist Doorbuster", 1, bob=("Hill Giant",))
    doorbuster = scenario.creature("Maulfist Doorbuster", "alice")
    giant = scenario.creature("Hill Giant", "bob")
    scenario.will_pay_the_energy(True)
    scenario.choose_trigger_targets("Maulfist Doorbuster", [giant])
    scenario.attack_with(doorbuster)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()
    assert scenario.game.why_cannot_block(giant, doorbuster) is not None

    scenario.game.cleanup_step()

    assert scenario.game.why_cannot_block(giant, doorbuster) is None


# --------------------------------------------------------------------------
# Second printings: Eddytrail Hawk, Consul's Shieldguard, Aetherstorm Roc
# --------------------------------------------------------------------------


def test_eddytrail_hawk_grants_flying_to_another_attacker():
    scenario = _attack_board("Eddytrail Hawk", 1, "Grizzly Bears")
    hawk = scenario.creature("Eddytrail Hawk", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.will_pay_the_energy(True)

    scenario.attack_with(hawk, bears)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert scenario.player("alice").energy == 0
    assert has_keyword(bears, Keyword.FLYING, scenario.game)


def test_consuls_shieldguard_grants_indestructible_to_another_attacker():
    scenario = _attack_board("Consul's Shieldguard", 1, "Grizzly Bears")
    shieldguard = scenario.creature("Consul's Shieldguard", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.will_pay_the_energy(True)

    scenario.attack_with(shieldguard, bears)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert is_indestructible(bears, scenario.game)
    assert not is_indestructible(shieldguard, scenario.game)


def test_aetherstorm_roc_counters_itself_and_taps_a_defender():
    scenario = _attack_board("Aetherstorm Roc", 2, bob=("Hill Giant",))
    roc = scenario.creature("Aetherstorm Roc", "alice")
    giant = scenario.creature("Hill Giant", "bob")
    scenario.will_pay_the_energy(True)

    scenario.choose_trigger_targets("Aetherstorm Roc", [giant])
    scenario.attack_with(roc)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert scenario.player("alice").energy == 0
    assert roc.counters[Counter.PLUS_ONE] == 1
    assert giant.tapped


def test_aetherstorm_roc_with_one_energy_does_nothing():
    scenario = _attack_board("Aetherstorm Roc", 1, bob=("Hill Giant",))
    roc = scenario.creature("Aetherstorm Roc", "alice")
    giant = scenario.creature("Hill Giant", "bob")

    scenario.choose_trigger_targets("Aetherstorm Roc", [giant])
    scenario.attack_with(roc)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert scenario.player("alice").energy == 1
    assert roc.counters[Counter.PLUS_ONE] == 0
    assert not giant.tapped
