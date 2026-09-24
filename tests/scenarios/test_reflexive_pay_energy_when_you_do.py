"""Scenario: "you may pay `<energy>`. When you do, `<consequence>`." - the
reflexive energy payment (CR 603.12) whose consequence used to go unread.

CR 603.12: a resolving ability may "allow or instruct a player to take an
action and create a triggered ability that triggers 'when [a player] [does or
doesn't]' take that action". The reflexive ability is a second stack object,
put on the stack the next time a player would receive priority, and its
choices - targets (CR 603.3d) and, for a modal one, its mode (CR 603.3c, CR
700.2b) - are made then, not when the parent resolved. CR 107.14 pays {E} by
removing energy counters; CR 118.3 refuses a payment the player cannot make
in full, and a declined or unaffordable payment creates nothing.

Oracle text, pulled with `scripts/add_card.py` and verified against the
printings pool (every card Modern-legal):

- **Voltstorm Angel**: "At the beginning of combat on your turn, you may pay
  {E}{E}. When you do, choose one - / - This creature gains vigilance and
  lifelink until end of turn. / - Other creatures you control get +1/+1
  until end of turn."
- **Cyclops Superconductor**: "Prowess / ... / When this creature dies, you
  may pay {E}{E}{E}. When you do, this creature deals damage equal to its
  power to any target." The power is the creature's last known information
  (CR 608.2h, CR 113.7a): the dies trigger looks back in time (CR 603.10a),
  and so does the source that deals the damage.
- **Riddle Gate Gargoyle** (a second printing of the reflexive energy reader,
  not in the api deck pool): "Whenever you attack, you may pay {E}{E}. When
  you do, target creature you control gains lifelink until end of turn."
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import Keyword, has_keyword
from magic_cards_model.machines.decisions import DecisionKind
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter

from .harness import Scenario

ANGEL = "Voltstorm Angel"
CYCLOPS = "Cyclops Superconductor"
GARGOYLE = "Riddle Gate Gargoyle"
VIGILANCE_MODE = "This creature gains vigilance and lifelink until end of turn."
ANTHEM_MODE = "Other creatures you control get +1/+1 until end of turn."


def _questions(scenario: Scenario, kind: DecisionKind) -> list:
    return [q for q in scenario.questions_asked() if q.kind is kind]


# --------------------------------------------------------------------------
# Voltstorm Angel: a reflexive *modal* consequence
# --------------------------------------------------------------------------


def _angel_board(energy: int) -> Scenario:
    scenario = (
        Scenario()
        .player("alice", battlefield=[ANGEL, "Grizzly Bears"])
        .player("bob", battlefield=["Hill Giant"])
        .build()
    )
    scenario.player("alice").add_counters(Counter.ENERGY, energy)
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _mode_text(decision) -> list[str]:
    return [option for option in decision.options]


def test_voltstorm_angel_first_mode_grants_itself_vigilance_and_lifelink():
    scenario = _angel_board(2)
    angel = scenario.creature(ANGEL, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.will_pay_the_energy(True)
    scenario.will_choose_mode(VIGILANCE_MODE)

    scenario.advance()  # beginning of combat: the outer trigger
    scenario.resolve_top()  # pays {E}{E}, creates the reflexive ability
    assert scenario.player("alice").energy == 0
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == [f"{ANGEL}'s triggered ability"]
    scenario.resolve_top()

    assert has_keyword(angel, Keyword.VIGILANCE, scenario.game)
    assert has_keyword(angel, Keyword.LIFELINK, scenario.game)
    assert not has_keyword(bears, Keyword.LIFELINK, scenario.game)
    assert scenario.game.power_of(bears) == 2


def test_voltstorm_angel_second_mode_pumps_the_other_creatures_only():
    scenario = _angel_board(2)
    angel = scenario.creature(ANGEL, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "bob")
    scenario.will_pay_the_energy(True)
    scenario.will_choose_mode(ANTHEM_MODE)

    scenario.advance()
    scenario.resolve_top()
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()

    assert (scenario.game.power_of(bears), scenario.game.toughness_of(bears)) == (3, 3)
    assert scenario.game.power_of(angel) == 4, '"Other creatures" excludes the Angel'
    assert scenario.game.power_of(giant) == 3, "only creatures you control"
    assert not has_keyword(angel, Keyword.LIFELINK, scenario.game)


def test_voltstorm_angel_mode_is_chosen_as_the_reflexive_ability_goes_on_the_stack():
    """CR 603.3c / CR 700.2b: the mode is chosen as the reflexive ability is
    put on the stack - after the parent's payment, and recorded on the stack
    object before it resolves, never asked again at resolution."""
    scenario = _angel_board(2)
    scenario.will_pay_the_energy(True)
    scenario.will_choose_mode(ANTHEM_MODE)

    scenario.advance()
    scenario.resolve_top()
    scenario.game.put_triggers_on_stack()

    kinds = [q.kind for q in scenario.questions_asked()]
    assert kinds.index(DecisionKind.PAY_ENERGY) < kinds.index(DecisionKind.CHOOSE_A_MODE)
    (asked,) = _questions(scenario, DecisionKind.CHOOSE_A_MODE)
    assert set(_mode_text(asked)) >= {VIGILANCE_MODE, ANTHEM_MODE}
    (reflexive,) = scenario.game.stack
    assert reflexive.modes == [2]

    scenario.resolve_top()

    assert len(_questions(scenario, DecisionKind.CHOOSE_A_MODE)) == 1


def test_voltstorm_angel_declining_creates_no_reflexive_ability():
    scenario = _angel_board(2)
    scenario.will_pay_the_energy(False)

    scenario.advance()
    scenario.resolve_top()
    scenario.game.put_triggers_on_stack()

    assert scenario.player("alice").energy == 2
    assert scenario.stack_names() == []
    assert _questions(scenario, DecisionKind.CHOOSE_A_MODE) == []


def test_voltstorm_angel_with_one_energy_cannot_pay_and_nothing_happens():
    scenario = _angel_board(1)
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.advance()
    scenario.resolve_top()
    scenario.game.put_triggers_on_stack()

    (question,) = _questions(scenario, DecisionKind.PAY_ENERGY)
    assert question.affirmative_is_legal is False
    assert scenario.player("alice").energy == 1
    assert scenario.stack_names() == []
    assert scenario.game.power_of(bears) == 2


# --------------------------------------------------------------------------
# Cyclops Superconductor: a dies trigger, damage equal to its last known power
# --------------------------------------------------------------------------


def _cyclops_board(energy: int) -> Scenario:
    scenario = (
        Scenario()
        .player("alice", hand=["Lightning Bolt"], battlefield=[CYCLOPS, "Mountain"])
        .player("bob", battlefield=["Hill Giant"])
        .build()
    )
    scenario.player("alice").add_counters(Counter.ENERGY, energy)
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _bolt_own_cyclops(scenario: Scenario) -> None:
    """Alice bolts her own Cyclops: prowess resolves first (+1/+1 until end
    of turn, a 3/3), then the Bolt's 3 damage kills it."""
    cyclops = scenario.creature(CYCLOPS, "alice")
    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    scenario.cast_onto_stack("Lightning Bolt", mountain, username="alice", targets=[cyclops])
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names()[-1] == f"{CYCLOPS}'s triggered ability", "prowess, on top"
    scenario.resolve_top()  # prowess: a 3/3 until end of turn
    assert scenario.game.power_of(cyclops) == 3
    scenario.resolve_top()  # the Bolt
    scenario.state_based_actions()
    assert cyclops.zone is Zone.GRAVEYARD
    scenario.game.put_triggers_on_stack()  # the dies trigger


def test_cyclops_superconductor_deals_its_last_known_power_to_any_target():
    """CR 608.2h / CR 113.7a: the Cyclops died a 3/3 (prowess), and it is
    the object as it last existed on the battlefield that deals the damage -
    not the 2/2 card in the graveyard."""
    scenario = _cyclops_board(3)
    scenario.will_pay_the_energy(True, source=CYCLOPS)

    _bolt_own_cyclops(scenario)
    assert scenario.stack_names() == [f"{CYCLOPS}'s triggered ability"]
    scenario.choose_trigger_targets(CYCLOPS, ["bob"])
    scenario.resolve_top()  # the dies trigger: pays, creates the reflexive ability
    assert scenario.player("alice").energy == 0
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == [f"{CYCLOPS}'s triggered ability"]
    scenario.resolve_top()

    assert scenario.player("bob").life == 17


def test_cyclops_superconductor_can_hit_a_creature():
    scenario = _cyclops_board(3)
    giant = scenario.creature("Hill Giant", "bob")
    scenario.will_pay_the_energy(True, source=CYCLOPS)

    _bolt_own_cyclops(scenario)
    scenario.choose_trigger_targets(CYCLOPS, [giant])
    scenario.resolve_top()
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()
    scenario.state_based_actions()

    assert giant.zone is Zone.GRAVEYARD, "3 damage to a 3/3"


def test_cyclops_superconductor_declined_deals_nothing():
    scenario = _cyclops_board(3)
    scenario.will_pay_the_energy(False, source=CYCLOPS)

    _bolt_own_cyclops(scenario)
    scenario.resolve_top()
    scenario.game.put_triggers_on_stack()

    assert scenario.player("alice").energy == 3
    assert scenario.stack_names() == []
    assert scenario.player("bob").life == 20


def test_cyclops_superconductor_with_two_energy_cannot_pay_three():
    scenario = _cyclops_board(2)

    _bolt_own_cyclops(scenario)
    scenario.resolve_top()
    scenario.game.put_triggers_on_stack()

    (question,) = _questions(scenario, DecisionKind.PAY_ENERGY)
    assert question.amount == 3
    assert question.affirmative_is_legal is False
    assert scenario.player("alice").energy == 2
    assert scenario.stack_names() == []


def test_cyclops_superconductor_target_gone_before_the_reflexive_resolves():
    """CR 608.2b: the reflexive ability's only target has left the
    battlefield, so it does not resolve; the energy stays paid (a cost is not
    refunded)."""
    scenario = (
        Scenario()
        .player("alice", hand=["Lightning Bolt"], battlefield=[CYCLOPS, "Mountain"])
        .player("bob", hand=["Lightning Bolt"], battlefield=["Grizzly Bears", "Mountain"])
        .build()
    )
    scenario.player("alice").add_counters(Counter.ENERGY, 3)
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.will_pay_the_energy(True, source=CYCLOPS)
    _bolt_own_cyclops(scenario)
    scenario.choose_trigger_targets(CYCLOPS, [bears])
    scenario.resolve_top()
    scenario.game.put_triggers_on_stack()

    (mountain,) = scenario.untapped_sources("Mountain", username="bob")
    scenario.pass_priority("alice")
    scenario.cast_and_resolve("Lightning Bolt", mountain, username="bob", targets=[bears])
    scenario.state_based_actions()
    assert bears.zone is Zone.GRAVEYARD
    scenario.pass_until_resolved()

    assert scenario.stack_names() == []
    assert scenario.player("alice").energy == 0
    assert scenario.player("bob").life == 20


# --------------------------------------------------------------------------
# Riddle Gate Gargoyle: a second printing of the reflexive energy reader
# --------------------------------------------------------------------------


@pytest.mark.parametrize("paid", [True, False])
def test_riddle_gate_gargoyle_grants_lifelink_only_when_paid(paid: bool):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=[GARGOYLE, "Grizzly Bears"])
        .player("bob", battlefield=[])
        .build()
    )
    scenario.player("alice").add_counters(Counter.ENERGY, 2)
    scenario.start_at(Step.DECLARE_ATTACKERS)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.will_pay_the_energy(paid, source=GARGOYLE)

    scenario.attack_with(bears)
    scenario.game.put_triggers_on_stack()
    # CR 603.3d: the reflexive ability's target is chosen as it goes on the
    # stack, right after the parent resolves - queued after the parent's own
    # batch so the parent does not consume it.
    scenario.choose_trigger_targets(GARGOYLE, [bears])
    scenario.pass_until_resolved()  # the parent: pays, creates the reflexive ability
    scenario.pass_until_resolved()  # the reflexive ability, if it exists

    assert scenario.player("alice").energy == (0 if paid else 2)
    assert has_keyword(bears, Keyword.LIFELINK, scenario.game) is paid
