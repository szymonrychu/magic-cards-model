"""Scenario: the trigger event's own subject as a printed condition - what a
cast spell targets, what was attached to a creature that died, how the
creatures that entered got there, what an attack is attacking.

Rules read whole with `mise run rules:find` in the session that wrote this:

- **CR 603.2** - the trigger event, whose own object "it", "that spell" and
  "those creatures" name.
- **CR 115.1** / **CR 115.3** - targets, and the same object chosen once per
  instance of the word "target".
- **CR 603.10a** - a dies trigger looks back at the creature as it last
  existed, attachments included.
- **CR 614.12a** - "as [this] enters, choose ..." is chosen before it
  enters; "the chosen colors" read that answer back.
- **CR 508.1b** - each attacking creature attacks a player,
  planeswalker or battle.
- **CR 107.3** - {X} in a mana cost or activation cost.
- **CR 603.4** / **CR 608.2a** - checked as the event occurs and again on
  resolution.
"""

import pytest

from magic_cards_model.machines import Step, conditions
from magic_cards_model.machines.abilities import TriggeredAbility, parse_abilities
from magic_cards_model.machines.conditions import ConditionContext
from magic_cards_model.machines.triggers import GameEvent, TriggerEvent
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Choice, ChoiceKind
from tests.cards import card
from tests.scenarios.harness import Scenario


def _board(alice=(), *, bob=(), hand=(), bob_hand=(), graveyard=()):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=list(alice),
            hand=list(hand),
            graveyard=list(graveyard),
            library=["Plains"] * 5,
        )
        .player("bob", battlefield=list(bob), hand=list(bob_hand), library=["Plains"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _read(scenario, clause, source, *, controller="alice", event=None, ability=None):
    return conditions.read_condition(
        ConditionContext(scenario.game, controller, source=source, event=event, ability=ability),
        clause,
    )


def _triggered(name: str) -> TriggeredAbility:
    (ability, *_rest) = [a for a in parse_abilities(card(name)) if isinstance(a, TriggeredAbility)]
    return ability


def _cast(scenario, name, *lands, targets, username="alice"):
    spell = scenario.cast_onto_stack(
        name,
        *scenario.untapped_sources(*lands, username=username),
        targets=targets,
        username=username,
    )
    return spell


# -- what a spell targets -----------------------------------------------------


def test_orvar_triggers_on_a_spell_targeting_another_permanent_you_control():
    scenario = _board(["Orvar, the All-Form", "Grizzly Bears", "Forest"], hand=["Giant Growth"])
    bears = scenario.creature("Grizzly Bears", "alice")
    _cast(scenario, "Giant Growth", "Forest", targets=[bears])
    scenario.game.put_triggers_on_stack()
    assert "Orvar, the All-Form's triggered ability" in scenario.stack_names()


def test_orvar_ignores_a_spell_targeting_only_itself():
    scenario = _board(["Orvar, the All-Form", "Forest"], hand=["Giant Growth"])
    orvar = scenario.creature("Orvar, the All-Form", "alice")
    _cast(scenario, "Giant Growth", "Forest", targets=[orvar])
    scenario.game.put_triggers_on_stack()
    assert "Orvar, the All-Form's triggered ability" not in scenario.stack_names()


def test_orvar_ignores_a_spell_targeting_an_opponents_creature():
    scenario = _board(["Orvar, the All-Form", "Mountain"], hand=["Lightning Bolt"], bob=["Memnite"])
    _cast(scenario, "Lightning Bolt", "Mountain", targets=[scenario.creature("Memnite", "bob")])
    scenario.game.put_triggers_on_stack()
    assert "Orvar, the All-Form's triggered ability" not in scenario.stack_names()


def test_ink_treader_nephilim_that_spell_targets_only_this_creature():
    scenario = _board(["Ink-Treader Nephilim", "Forest"], hand=["Giant Growth"])
    nephilim = scenario.creature("Ink-Treader Nephilim", "alice")
    _cast(scenario, "Giant Growth", "Forest", targets=[nephilim])
    scenario.game.put_triggers_on_stack()
    assert "Ink-Treader Nephilim's triggered ability" in scenario.stack_names()


def test_ink_treader_nephilim_other_target_does_not_trigger():
    scenario = _board(["Ink-Treader Nephilim", "Grizzly Bears", "Forest"], hand=["Giant Growth"])
    _cast(scenario, "Giant Growth", "Forest", targets=[scenario.creature("Grizzly Bears", "alice")])
    scenario.game.put_triggers_on_stack()
    assert "Ink-Treader Nephilim's triggered ability" not in scenario.stack_names()


def test_captured_by_the_consulate_reads_a_single_target():
    scenario = _board(["Captured by the Consulate"], bob=["Mountain"], bob_hand=["Lightning Bolt"])
    consulate = scenario.find("Captured by the Consulate", Zone.BATTLEFIELD)
    spell = scenario.find("Lightning Bolt", Zone.HAND, "bob")
    from magic_cards_model.models.card_state import TargetRef

    spell.targets = [TargetRef.to_player("alice")]
    event = GameEvent(event=TriggerEvent.CAST_SPELL, subject_id=spell.id, player="bob")
    assert _read(scenario, "it has a single target", consulate, event=event) is True
    spell.targets = []
    assert _read(scenario, "it has a single target", consulate, event=event) is False


def test_a_targetless_spell_has_no_single_target():
    scenario = _board(["Captured by the Consulate"], bob_hand=["Lightning Bolt"])
    consulate = scenario.find("Captured by the Consulate", Zone.BATTLEFIELD)
    spell = scenario.find("Lightning Bolt", Zone.HAND, "bob")
    event = GameEvent(event=TriggerEvent.CAST_SPELL, subject_id=spell.id, player="bob")
    assert _read(scenario, "it has a single target", consulate, event=event) is False


# -- what was attached to the creature that died ------------------------------


def test_dawn_evangel_an_aura_you_controlled_was_attached():
    scenario = _board(["Dawn Evangel", "Rancor"], bob=["Grizzly Bears"], graveyard=["Memnite"])
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.find("Rancor", Zone.BATTLEFIELD).attach_to(bears)
    scenario.choose_trigger_targets("Dawn Evangel", [scenario.find("Memnite", Zone.GRAVEYARD)])
    scenario.game.destroy(bears)
    scenario.game.put_triggers_on_stack()
    assert "Dawn Evangel's triggered ability" in scenario.stack_names()


def test_dawn_evangel_an_opponents_aura_does_not_count():
    scenario = _board(["Dawn Evangel"], bob=["Grizzly Bears", "Rancor"])
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.find("Rancor", Zone.BATTLEFIELD, "bob").attach_to(bears)
    scenario.game.destroy(bears)
    scenario.game.put_triggers_on_stack()
    assert "Dawn Evangel's triggered ability" not in scenario.stack_names()


def test_dawn_evangel_an_equipment_is_not_an_aura():
    scenario = _board(["Dawn Evangel", "Bonesplitter", "Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.find("Bonesplitter", Zone.BATTLEFIELD).attach_to(bears)
    scenario.game.destroy(bears)
    scenario.game.put_triggers_on_stack()
    assert "Dawn Evangel's triggered ability" not in scenario.stack_names()


# -- how the entering creatures got there -------------------------------------


def test_extraordinary_journey_from_exile():
    scenario = _board(["Extraordinary Journey"], hand=["Grizzly Bears"])
    journey = scenario.find("Extraordinary Journey", Zone.BATTLEFIELD)
    clause = "one or more of them entered from exile or was cast from exile"
    bears = scenario.find("Grizzly Bears", Zone.HAND, "alice")
    from_hand = GameEvent(
        event=TriggerEvent.ENTERS_THE_BATTLEFIELD, subject_id=bears.id, origin_zone=Zone.HAND
    )
    assert _read(scenario, clause, journey, event=from_hand) is False
    from_exile = GameEvent(
        event=TriggerEvent.ENTERS_THE_BATTLEFIELD, subject_id=bears.id, origin_zone=Zone.EXILE
    )
    assert _read(scenario, clause, journey, event=from_exile) is True


# -- those creatures: an attack ------------------------------------------------


def test_tomik_two_attackers_at_you_count():
    scenario = _board(["Grizzly Bears", "Memnite"], bob=["Tomik, Wielder of Law"])
    tomik = scenario.creature("Tomik, Wielder of Law", "bob")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.attack_with(bears, scenario.creature("Memnite", "alice"))
    event = GameEvent(event=TriggerEvent.ATTACKS, subject_id=bears.id, player="alice")
    clause = "two or more of those creatures are attacking you and/or planeswalkers you control"
    assert _read(scenario, clause, tomik, controller="bob", event=event) is True


def test_tomik_one_attacker_is_not_two():
    scenario = _board(["Grizzly Bears", "Memnite"], bob=["Tomik, Wielder of Law"])
    tomik = scenario.creature("Tomik, Wielder of Law", "bob")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.attack_with(bears)
    event = GameEvent(event=TriggerEvent.ATTACKS, subject_id=bears.id, player="alice")
    clause = "two or more of those creatures are attacking you and/or planeswalkers you control"
    assert _read(scenario, clause, tomik, controller="bob", event=event) is False


# -- the chosen colors --------------------------------------------------------


def test_tablet_of_the_guilds_asks_two_colors_as_it_enters():
    scenario = _board(["Plains", "Island"], hand=["Tablet of the Guilds"])
    scenario.will_choose("W")
    scenario.will_choose("U")
    scenario.cast_and_resolve(
        "Tablet of the Guilds", *scenario.untapped_sources("Plains", "Island")
    )
    tablet = scenario.find("Tablet of the Guilds", Zone.BATTLEFIELD)
    assert tablet.choice == Choice(kind=ChoiceKind.COLORS, value="WU")


def test_tablet_of_the_guilds_at_least_one_of_the_chosen_colors():
    scenario = _board(["Tablet of the Guilds"], hand=["Lightning Bolt", "Giant Growth"])
    tablet = scenario.find("Tablet of the Guilds", Zone.BATTLEFIELD)
    tablet.choice = Choice(kind=ChoiceKind.COLORS, value="WR")
    clause = "it's at least one of the chosen colors"
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "alice")
    growth = scenario.find("Giant Growth", Zone.HAND, "alice")
    assert _read(
        scenario, clause, tablet, event=GameEvent(event=TriggerEvent.CAST_SPELL, subject_id=bolt.id)
    )
    assert not _read(
        scenario,
        clause,
        tablet,
        event=GameEvent(event=TriggerEvent.CAST_SPELL, subject_id=growth.id),
    )


# -- {X} in the cost ------------------------------------------------------------


def test_unbound_flourishing_reads_x_in_a_spells_mana_cost():
    scenario = _board(["Unbound Flourishing"], hand=["Fireball", "Lightning Bolt"])
    flourishing = scenario.find("Unbound Flourishing", Zone.BATTLEFIELD)
    clause = "that spell's mana cost or that ability's activation cost contains {x}"
    fireball = scenario.find("Fireball", Zone.HAND, "alice")
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "alice")
    assert _read(
        scenario,
        clause,
        flourishing,
        event=GameEvent(event=TriggerEvent.CAST_SPELL, subject_id=fireball.id),
    )
    assert not _read(
        scenario,
        clause,
        flourishing,
        event=GameEvent(event=TriggerEvent.CAST_SPELL, subject_id=bolt.id),
    )


# -- the probes ---------------------------------------------------------------


@pytest.mark.parametrize(
    "clause",
    [
        "it has a single target",
        "an aura you controlled was attached to it",
        "one or more of them entered from exile or was cast from exile",
        "that spell targets only this creature",
        "two or more of those creatures are attacking you and/or planeswalkers you control",
        "it targets one or more other permanents you control",
        "it's at least one of the chosen colors",
        "that spell's mana cost or that ability's activation cost contains {x}",
    ],
)
def test_every_template_is_claimed(clause):
    assert conditions.claims(clause)


def test_the_parser_hands_each_clause_to_its_ability():
    assert _triggered("Orvar, the All-Form").intervening_if == (
        "it targets one or more other permanents you control"
    )
