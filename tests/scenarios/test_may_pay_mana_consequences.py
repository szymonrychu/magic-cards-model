"""Scenario: the consequence readers of "you may pay `<cost>`. If/When you
do, `<consequence>`." proven on an ordinary-mana payment.

The energy family (`test_may_pay_energy_if_you_do.py`,
`test_reflexive_pay_energy_when_you_do.py`) and the mana family share one
consequence reader: CR 118.12 ("If you do": the cost is paid as the ability
resolves and the consequence runs on that same ability) and CR 603.12 ("When
you do": a reflexive triggered ability, its target chosen as it goes on the
stack, CR 603.3d). These printings carry the two widened consequences on a
mana cost instead of {E}, so the readers are proven on wording the energy
cards that exposed them do not print. None is in the api deck pool; oracle
text pulled with `scripts/add_card.py` and verified against the pool.

- **Skyline Scout** (Modern, Pioneer): "Whenever this creature attacks, you
  may pay {1}{W}. If you do, it gains flying until end of turn." - the
  source anaphor "it".
- **Frenzied Goblin** (Modern, Pioneer, Standard): "Whenever this creature
  attacks, you may pay {R}. If you do, target creature can't block this
  turn." - CR 509.1b's blocking restriction, on a one-symbol payment.
- **Labyrinth Adversary** (Modern): "Whenever you attack, you may pay {1}{R}.
  When you do, target creature can't block this turn." - the same
  restriction as a reflexive consequence.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import Keyword, has_keyword

from .harness import Scenario


def _untapped(scenario: Scenario, name: str) -> int:
    return sum(
        1
        for state in scenario.game.permanents_controlled_by("alice")
        if state.name == name and state.untapped
    )


def _board(attacker: str, lands: list[str], bob: list[str]) -> Scenario:
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=[attacker, *lands])
        .player("bob", battlefield=bob)
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    return scenario


def test_skyline_scout_paid_gains_flying():
    scenario = _board("Skyline Scout", ["Plains", "Plains"], [])
    scout = scenario.creature("Skyline Scout", "alice")
    scenario.will_pay_the_mana_cost(True)

    scenario.attack_with(scout)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert has_keyword(scout, Keyword.FLYING, scenario.game)
    assert _untapped(scenario, "Plains") == 0


def test_skyline_scout_declined_stays_on_the_ground():
    scenario = _board("Skyline Scout", ["Plains", "Plains"], [])
    scout = scenario.creature("Skyline Scout", "alice")
    scenario.will_pay_the_mana_cost(False)

    scenario.attack_with(scout)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert not has_keyword(scout, Keyword.FLYING, scenario.game)
    assert _untapped(scenario, "Plains") == 2


def test_skyline_scout_without_the_mana_cannot_pay():
    """CR 118.3: one Plains cannot pay {1}{W}."""
    scenario = _board("Skyline Scout", ["Plains"], [])
    scout = scenario.creature("Skyline Scout", "alice")

    scenario.attack_with(scout)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert not has_keyword(scout, Keyword.FLYING, scenario.game)


def test_frenzied_goblin_paid_stops_the_target_blocking():
    scenario = _board("Frenzied Goblin", ["Mountain"], ["Hill Giant"])
    goblin = scenario.creature("Frenzied Goblin", "alice")
    giant = scenario.creature("Hill Giant", "bob")
    scenario.will_pay_the_mana_cost(True)

    scenario.choose_trigger_targets("Frenzied Goblin", [giant])
    scenario.attack_with(goblin)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert scenario.game.why_cannot_block(giant, goblin) is not None


def test_frenzied_goblin_declined_lets_the_target_block():
    scenario = _board("Frenzied Goblin", ["Mountain"], ["Hill Giant"])
    goblin = scenario.creature("Frenzied Goblin", "alice")
    giant = scenario.creature("Hill Giant", "bob")
    scenario.will_pay_the_mana_cost(False)

    scenario.choose_trigger_targets("Frenzied Goblin", [giant])
    scenario.attack_with(goblin)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert scenario.game.why_cannot_block(giant, goblin) is None


def test_labyrinth_adversary_reflexive_restriction_on_the_chosen_target():
    scenario = _board("Labyrinth Adversary", ["Mountain", "Mountain"], ["Hill Giant"])
    adversary = scenario.creature("Labyrinth Adversary", "alice")
    giant = scenario.creature("Hill Giant", "bob")
    scenario.will_pay_the_mana_cost(True)

    scenario.attack_with(adversary)
    scenario.game.put_triggers_on_stack()
    scenario.choose_trigger_targets("Labyrinth Adversary", [giant])
    scenario.pass_until_resolved()  # the parent: pays, creates the reflexive ability
    assert scenario.stack_names() == ["Labyrinth Adversary's triggered ability"]
    scenario.pass_until_resolved()

    assert scenario.game.why_cannot_block(giant, adversary) is not None


def test_labyrinth_adversary_declined_creates_no_reflexive_ability():
    scenario = _board("Labyrinth Adversary", ["Mountain", "Mountain"], ["Hill Giant"])
    adversary = scenario.creature("Labyrinth Adversary", "alice")
    giant = scenario.creature("Hill Giant", "bob")
    scenario.will_pay_the_mana_cost(False)

    scenario.attack_with(adversary)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert scenario.stack_names() == []
    assert scenario.game.why_cannot_block(giant, adversary) is None
