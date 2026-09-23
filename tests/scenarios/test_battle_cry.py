"""Scenario: Battle cry (CR 702.91), an attack trigger that pumps allies.

Every rule below was read whole with `mise run rules:find` in the session that
wrote this file:

- **CR 702.91a** - "Battle cry is a triggered ability. 'Battle cry' means
  'Whenever this creature attacks, each other attacking creature gets +1/+0
  until end of turn.'"
- **CR 702.91b** - "If a creature has multiple instances of battle cry, each
  triggers separately."
- **CR 611.2c** - the set of objects a resolving ability's continuous effect
  applies to is fixed "when that continuous effect begins" and never
  recomputed - which is what decides both of the negative cases below: a
  creature no longer attacking by the moment battle cry resolves is not in
  that set, and neither is one that starts attacking only afterwards.
- **CR 508.4 / 508.4c** - a creature "put onto the battlefield attacking"
  never "attacked" for trigger purposes and is not subject to the
  declare-attackers restrictions - the mechanism `create_tokens(...,
  attacking=...)` models, reused here (the same primitive Mobilize's own
  tokens go through) to prove the "after resolution" half without inventing
  a second card.

Signal Pest and Accorder Paladin are the two Modern-legal battle cry
printings in the pool; both print exactly "Battle cry (Whenever this
creature attacks, each other attacking creature gets +1/+0 until end of
turn.)" with no rider, so either can stand in for the other. Both entries are
`_TRIGGER_EXPANSIONS['battle cry']`'s own text, not read off either card -
CR 702.91b's "each instance triggers separately" is inherited for free from
the same per-`KeywordAbility`-instance loop `keyword_triggered_abilities`
already runs for every other keyword in that registry (ward, prowess,
persist, mobilize, ...), proven generically by `test_mobilize.py` and the
rest; no Modern/Pioneer/Standard-legal printing repeats battle cry on one
card to prove the multi-instance count itself, so this file does not
special-case it.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.abilities import TriggerEvent
from magic_cards_model.machines.keywords import keyword_triggered_abilities
from magic_cards_model.models import Zone
from magic_cards_model.models.token import TokenDefinition, create_tokens
from tests.cards import card

from .harness import Scenario


def board(*attackers: str, opposing: list[str] | None = None) -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", library=["Plains"] * 3, battlefield=list(attackers))
        .player("bob", library=["Plains"] * 3, battlefield=list(opposing or []))
    )


def attack_and_resolve_all(scenario, *names: str):
    """Declare every named creature as an attacker and resolve every trigger
    that goes on the stack because of it, in whatever order the engine puts
    them there."""
    scenario.start_at(Step.DECLARE_ATTACKERS)
    attackers = [scenario.creature(name) for name in names]
    for attacker in attackers:
        attacker.summoning_sick = False
    scenario.attack_with(*attackers)
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()
    return attackers


# --------------------------------------------------------------------------
# The trigger itself (CR 702.91a, CR 603.2)
# --------------------------------------------------------------------------


def test_signal_pest_battle_cry_expands_to_the_cr_702_91a_trigger():
    (ability,) = keyword_triggered_abilities(card("Signal Pest"))
    assert ability.keyword == "battle cry"
    assert ability.event is TriggerEvent.ATTACKS
    assert ability.condition == "this creature attacks"
    assert ability.effect == "each other attacking creature gets +1/+0 until end of turn"


def test_accorder_paladin_battle_cry_expands_to_the_same_trigger():
    """Two different printings, the same rule's own words - not read off
    either card's reminder text."""
    (ability,) = keyword_triggered_abilities(card("Accorder Paladin"))
    assert ability.keyword == "battle cry"
    assert ability.effect == "each other attacking creature gets +1/+0 until end of turn"


# --------------------------------------------------------------------------
# Other attackers get it, the battle cry creature itself does not
# --------------------------------------------------------------------------


def test_battle_cry_pumps_the_other_attacker_but_not_itself():
    scenario = board("Accorder Paladin", "Grizzly Bears", opposing=["Watchwolf"]).build()
    paladin, bears = attack_and_resolve_all(scenario, "Accorder Paladin", "Grizzly Bears")

    game = scenario.game
    assert game.characteristics_of(bears).power_toughness == (3, 2), "pumped +1/+0"
    assert game.characteristics_of(paladin).power_toughness == (3, 1), "battle cry excludes self"


def test_signal_pest_battle_cry_also_excludes_itself():
    """Same proof, off the other Modern-legal printing - not read off
    Accorder Paladin's own text."""
    scenario = board("Signal Pest", "Grizzly Bears", opposing=["Watchwolf"]).build()
    pest, bears = attack_and_resolve_all(scenario, "Signal Pest", "Grizzly Bears")

    game = scenario.game
    assert game.characteristics_of(bears).power_toughness == (3, 2)
    assert game.characteristics_of(pest).power_toughness == (0, 1)


# --------------------------------------------------------------------------
# Two battle cry attackers pump each other
# --------------------------------------------------------------------------


def test_two_battle_cry_attackers_pump_each_other():
    """Accorder Paladin's own trigger pumps Signal Pest, and Signal Pest's
    own trigger pumps Accorder Paladin - two separate triggers (CR 702.91a),
    each excluding only its own source."""
    scenario = board("Accorder Paladin", "Signal Pest", opposing=["Watchwolf"]).build()
    paladin, pest = attack_and_resolve_all(scenario, "Accorder Paladin", "Signal Pest")

    game = scenario.game
    assert game.characteristics_of(paladin).power_toughness == (4, 1), "pumped once, by the Pest"
    assert game.characteristics_of(pest).power_toughness == (1, 1), "pumped once, by the Paladin"


# --------------------------------------------------------------------------
# CR 611.2c: the pumped set is fixed when battle cry resolves
# --------------------------------------------------------------------------


def test_a_creature_that_stops_attacking_before_battle_cry_resolves_is_not_pumped():
    """Grizzly Bears is sacrificed after the trigger goes on the stack but
    before it resolves - CR 506.4 takes it out of combat, so `Game.
    attacking_creatures()` no longer includes it when the effect is actually
    fixed (CR 611.2c), and nothing pumps it."""
    scenario = board("Accorder Paladin", "Grizzly Bears", opposing=["Watchwolf"]).build()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    paladin = scenario.creature("Accorder Paladin")
    bears = scenario.creature("Grizzly Bears")
    paladin.summoning_sick = False
    bears.summoning_sick = False
    scenario.attack_with(paladin, bears)
    scenario.game.put_triggers_on_stack()

    assert scenario.game.is_attacking(bears)
    scenario.game.sacrifice(bears)
    assert not scenario.game.is_attacking(bears), "CR 506.4: sacrificing removed it from combat"

    while scenario.game.stack:
        scenario.resolve_top()

    assert bears.zone is Zone.GRAVEYARD
    assert scenario.game.continuous_effects.effects == [], "nothing left to pump"
    assert scenario.game.characteristics_of(paladin).power_toughness == (3, 1)


def test_a_creature_put_onto_the_battlefield_attacking_after_resolution_is_not_pumped():
    """A token created attacking (CR 508.4) once battle cry has already
    resolved is not part of the fixed set (CR 611.2c) - the mechanism itself
    is `models.token.create_tokens(..., attacking=...)`, the same one
    Mobilize's own tokens use, run by hand here rather than through a second
    keyword ability so only battle cry's own timing is on trial."""
    scenario = board("Accorder Paladin", opposing=["Watchwolf"]).build()
    (paladin,) = attack_and_resolve_all(scenario, "Accorder Paladin")

    assert scenario.game.continuous_effects.effects == [], "battle cry already resolved, alone"

    (token,) = create_tokens(
        scenario.game,
        TokenDefinition(power=1, toughness=1, subtypes=("Warrior",)),
        "alice",
        tapped=True,
        attacking="bob",
    )

    assert scenario.game.is_attacking(token)
    assert scenario.game.characteristics_of(token).power_toughness == (1, 1), "never touched"
    assert scenario.game.characteristics_of(paladin).power_toughness == (3, 1), "still just itself"
