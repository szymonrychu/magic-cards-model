"""Mobilize: an attack trigger that makes tokens (CR 702.181).

CR 702.181a: "Mobilize is a triggered ability. 'Mobilize N' means "Whenever this
creature attacks, create N 1/1 red Warrior creature tokens. Those tokens enter
tapped and attacking. Sacrifice them at the beginning of the next end step.""

Like ward, prowess, cascade and persist, mobilize is a triggered ability the card
prints as one word, so `machines/triggers.py` had nothing to read. The expansion
in `machines/keywords.keyword_triggered_abilities` gives it one, and the trigger
now fires off a real attack declaration (CR 508.1).

Its *effect* is a different matter, and one this file does not xfail past: the
whole effect is creating tokens, and nothing in this engine creates one. The
trigger being on the stack is what is asserted here - it can be responded to, it
is ordered by CR 603.3b, and CR 608.2n removes it - and the tokens are named in
`docs/engine-coverage.md` as the gap they are.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.abilities import TriggerEvent
from magic_cards_model.machines.keywords import keyword_triggered_abilities
from tests.cards import card
from tests.scenarios.harness import Scenario


def board() -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Voice of Victory", "Grizzly Bears", "Plains"])
        .player("bob")
    )


def test_mobilize_is_a_triggered_ability_the_engine_can_produce():
    """CR 702.181a: "Mobilize is a triggered ability", and N is read off the line."""
    (ability,) = keyword_triggered_abilities(card("Voice of Victory"))
    assert ability.keyword == "mobilize"
    assert ability.event is TriggerEvent.ATTACKS
    assert ability.condition == "this creature attacks"
    assert ability.effect.startswith("create 2 1/1 red Warrior creature tokens")


def test_attacking_puts_the_mobilize_trigger_on_the_stack():
    """CR 508.1 declares the attack; CR 603.2 and CR 603.3 do the rest."""
    scenario = board().build()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    voice = scenario.creature("Voice of Victory")
    voice.summoning_sick = False

    scenario.attack_with(voice)
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == ["Voice of Victory's triggered ability"]


def test_another_creature_attacking_does_not_trigger_it():
    """ "**This creature** attacks" - the source has to be the attacker."""
    scenario = board().build()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    bears = scenario.creature("Grizzly Bears")
    bears.summoning_sick = False

    scenario.attack_with(bears)
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == []


def test_the_trigger_resolves_and_creates_nothing():
    """The honest state of it: no tokens, and CR 608.2n still removes the ability.

    A trigger with no effect entry behaves exactly like a card with none - it
    triggers, it can be responded to, and it does nothing on resolution. Asserted
    rather than xfailed, because the gap is tokens and not mobilize.
    """
    scenario = board().build()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    voice = scenario.creature("Voice of Victory")
    voice.summoning_sick = False

    scenario.attack_with(voice)
    scenario.game.put_triggers_on_stack()
    before = list(scenario.battlefield_names())
    scenario.resolve_top()

    assert scenario.game.stack_is_empty  # CR 608.2n
    assert scenario.battlefield_names() == before
