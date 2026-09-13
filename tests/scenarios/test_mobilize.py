"""Mobilize (CR 702.181): an attack trigger that makes tapped and attacking Warriors.

Every rule below was read whole with `mise run rules:find` in the session that
wrote this file:

- **CR 702.181a** - "Mobilize is a triggered ability. "Mobilize N" means
  "Whenever this creature attacks, create N 1/1 red Warrior creature tokens.
  Those tokens enter tapped and attacking. Sacrifice them at the beginning of
  the next end step.""
- **CR 508.4** - a creature put onto the battlefield attacking: "its controller
  chooses which defending player, planeswalker a defending player controls, or
  battle a defending player protects it's attacking as it enters", and "for the
  purposes of trigger events and effects, they never 'attacked.'"
- **CR 508.4c** - such a creature "isn't affected by requirements or
  restrictions that apply to the declaration of attackers", so a token that
  arrived this turn attacks anyway.
- **CR 603.7c** - a delayed triggered ability that refers to a particular
  object still affects it only while it is in the zone it was expected in.
- **CR 608.2h** - "Mobilize X, where X is ..." is a value the effect determines
  once, as it is applied.
- **CR 113.7a** - once a triggered ability triggers it exists independently of
  its source, so the tokens are made even if the attacker has left.

Voice of Victory (Mobilize 2) is the card the battle report named. Dragonback
Lancer (Mobilize 1, singular reminder text) and Avenger of the Fallen
(Mobilize X) are in no deck pool: they prove the count is read off the keyword
line, not off a card.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.abilities import TriggerEvent
from magic_cards_model.machines.decisions import DecisionKind
from magic_cards_model.machines.keywords import keyword_triggered_abilities
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Color
from magic_cards_model.models.card_state import TargetRef
from magic_cards_model.models.token import is_token
from tests.cards import card
from tests.scenarios.harness import Scenario


def board(attacker: str = "Voice of Victory", *, graveyard=None, opposing=None) -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            library=["Plains"] * 3,
            battlefield=[attacker, "Grizzly Bears", "Plains"],
            graveyard=list(graveyard or []),
        )
        .player("bob", library=["Plains"] * 3, battlefield=list(opposing or []))
    )


def warriors(scenario, username: str = "alice") -> list:
    return [
        state
        for state in scenario.game.permanents_controlled_by(username)
        if is_token(state) and "Warrior" in state.subtypes
    ]


def attack_and_resolve(scenario, name: str = "Voice of Victory"):
    scenario.start_at(Step.DECLARE_ATTACKERS)
    attacker = scenario.creature(name)
    attacker.summoning_sick = False
    scenario.attack_with(attacker)
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()
    return attacker


def defender_of(scenario, creature) -> TargetRef | None:
    for attack in scenario.game.combat.attacks:
        if attack.attacker_id == creature.id:
            return attack.defender
    return None


# --------------------------------------------------------------------------
# The trigger (CR 702.181a, CR 603.2)
# --------------------------------------------------------------------------


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


# --------------------------------------------------------------------------
# The tokens (CR 702.181a, CR 508.4)
# --------------------------------------------------------------------------


def test_voice_of_victory_creates_two_tapped_and_attacking_red_warriors():
    """The battle report's own repro: Voice attacks, the trigger resolves, and
    two 1/1 red Warrior creature tokens are on the battlefield, tapped and
    attacking the player Voice is attacking."""
    scenario = board().build()
    attack_and_resolve(scenario)

    tokens = warriors(scenario)
    assert len(tokens) == 2
    board_now = scenario.game.computed_board()
    for token in tokens:
        computed = board_now.of(token)
        assert (computed.power, computed.toughness) == (1, 1)
        assert list(computed.colors) == [Color.RED]
        assert computed.is_creature
        assert token.tapped
        assert scenario.game.is_attacking(token)
        assert defender_of(scenario, token) == TargetRef.coerce("bob")


def test_the_tokens_attack_although_they_arrived_this_turn():
    """CR 508.4c: a creature put onto the battlefield attacking ignores the
    declaration's restrictions - summoning sickness (CR 302.6) among them."""
    scenario = board().build()
    attack_and_resolve(scenario)

    tokens = warriors(scenario)
    assert tokens
    assert all(token.summoning_sick for token in tokens)
    assert all(scenario.game.is_attacking(token) for token in tokens)


def test_the_tokens_never_attacked_so_nothing_triggers_off_them():
    """CR 508.4: "for the purposes of trigger events and effects, they never
    'attacked.'" Two more attackers arriving puts nothing new on the stack."""
    scenario = board().build()
    attack_and_resolve(scenario)
    scenario.game.put_triggers_on_stack()

    assert scenario.game.stack_is_empty


def test_the_trigger_makes_its_tokens_even_after_voice_has_left():
    """CR 113.7a: the ability exists independently of its source once it has
    triggered. Voice is destroyed in response; the Warriors still arrive."""
    scenario = board().build()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    voice = scenario.creature("Voice of Victory")
    voice.summoning_sick = False
    scenario.attack_with(voice)
    scenario.game.put_triggers_on_stack()

    scenario.game.destroy(voice)
    assert voice.zone is Zone.GRAVEYARD
    scenario.resolve_top()

    assert len(warriors(scenario)) == 2


def test_a_mobilize_1_card_outside_the_pool_makes_exactly_one_token():
    """Dragonback Lancer prints the singular reminder text ("create a tapped and
    attacking 1/1 red Warrior creature token. Sacrifice it ..."). The count comes
    off "Mobilize 1", not off the reminder text or the card's name."""
    scenario = board("Dragonback Lancer").build()
    attack_and_resolve(scenario, "Dragonback Lancer")

    tokens = warriors(scenario)
    assert len(tokens) == 1
    assert scenario.game.is_attacking(tokens[0])


def test_mobilize_x_counts_its_definition_as_the_trigger_resolves():
    """Avenger of the Fallen: "Mobilize X, where X is the number of creature
    cards in your graveyard." CR 608.2h fixes X once, when the effect is applied
    - so a creature card that reaches the graveyard while the trigger waits on
    the stack is counted."""
    scenario = board("Avenger of the Fallen", graveyard=["Grizzly Bears", "Plains"]).build()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    avenger = scenario.creature("Avenger of the Fallen")
    avenger.summoning_sick = False
    scenario.attack_with(avenger)
    scenario.game.put_triggers_on_stack()

    scenario.game.destroy(scenario.creature("Grizzly Bears"))
    scenario.resolve_top()

    assert len(warriors(scenario)) == 2


def test_mobilize_x_with_no_creature_cards_in_the_graveyard_makes_nothing():
    """X is 0, and creating zero tokens is a real answer, not a failure - no
    token and no notice."""
    scenario = board("Avenger of the Fallen", graveyard=["Plains"]).build()
    attack_and_resolve(scenario, "Avenger of the Fallen")

    assert warriors(scenario) == []
    assert scenario.game.unmodeled_trigger_effect_notices == []
    assert scenario.game.delayed_clause_notices == []


# --------------------------------------------------------------------------
# What each token attacks (CR 508.4)
# --------------------------------------------------------------------------


def test_the_controller_chooses_what_each_token_attacks():
    """CR 508.4: with a planeswalker on bob's side there are two things each
    Warrior could attack, and nothing printed chooses - so alice is asked, once
    per token, and her answers stand."""
    scenario = board(opposing=["Ugin, Eye of the Storms"]).build()
    ugin = scenario.find("Ugin, Eye of the Storms", Zone.BATTLEFIELD, username="bob")
    scenario.will_choose_targets(ugin, username="alice")
    scenario.will_choose_targets("bob", username="alice")
    attack_and_resolve(scenario)

    tokens = warriors(scenario)
    assert len(tokens) == 2
    assert sorted(str(defender_of(scenario, token)) for token in tokens) == sorted(
        [str(TargetRef.coerce(ugin)), str(TargetRef.coerce("bob"))]
    )
    assert [q.kind for q in scenario.questions_asked()].count(DecisionKind.CHOOSE_TARGETS) == 2


def test_with_only_one_thing_to_attack_nothing_is_asked():
    """One defending player and no planeswalker or battle: there is no choice
    to put to anyone."""
    scenario = board().build()
    attack_and_resolve(scenario)

    assert DecisionKind.CHOOSE_TARGETS not in [q.kind for q in scenario.questions_asked()]


# --------------------------------------------------------------------------
# Sacrifice them at the beginning of the next end step (CR 603.7)
# --------------------------------------------------------------------------


def _to_the_end_step(scenario) -> None:
    scenario.start_at(Step.POSTCOMBAT_MAIN)
    scenario.advance()  # the end step begins
    assert scenario.step is Step.END_STEP


def test_the_tokens_are_sacrificed_by_one_delayed_trigger_at_the_end_step():
    """ "Sacrifice **them**" is one delayed triggered ability for every token the
    trigger made, not one per token: at the end step exactly one object goes on
    the stack, and resolving it takes both Warriors away."""
    scenario = board().build()
    attack_and_resolve(scenario)
    assert len(warriors(scenario)) == 2

    _to_the_end_step(scenario)
    assert len(scenario.game.stack) == 1
    scenario.resolve_top()

    assert warriors(scenario) == []
    assert scenario.find("Voice of Victory", Zone.BATTLEFIELD, username="alice")


def test_a_token_already_gone_is_not_affected_and_the_other_is_still_sacrificed():
    """CR 603.7c: one Warrior dies before the end step; the delayed trigger
    finds only the one still on the battlefield, and sacrifices it."""
    scenario = board().build()
    attack_and_resolve(scenario)
    first, second = warriors(scenario)
    scenario.game.destroy(first)

    _to_the_end_step(scenario)
    while scenario.game.stack:
        scenario.resolve_top()

    assert warriors(scenario) == []
    assert second.zone is not Zone.BATTLEFIELD
