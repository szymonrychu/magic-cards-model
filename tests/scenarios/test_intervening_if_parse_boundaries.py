"""Where an intervening "if" clause ends: parse boundaries that cut a clause
short, ran it into its effect, or took a trigger event's own qualifier for one.

Rules verified with `mise run rules:find` in the session that wrote this file:

- **CR 603.4** - "A triggered ability may read 'When/Whenever/At [trigger
  event], if [condition], [effect].' ... this rule only applies to an 'if'
  that immediately follows a trigger condition." The clause is everything
  between that "if" and the comma before the effect - a comma inside a list
  ("a Giant, Wizard, or spell", "nonland, nontoken permanents") is not it.
- **CR 603.2** - a trigger event is what happened, including how: "while
  casting a spell with emerge" / "while scrying" describe the event and are
  not a condition CR 603.4 rechecks on resolution.
- **CR 608.2a** - the recheck on resolution.
- **CR 605.1a** - what makes an activated ability a mana ability.
- **CR 508.1f** - "attacking simply causes creatures to become tapped".
- **CR 120.1** - "An object that deals damage is the source of that damage."
- **CR 702.171b** - "Saddled is a designation".
"""

from magic_cards_model.machines import Step, conditions
from magic_cards_model.machines.abilities import TriggeredAbility, parse_abilities
from magic_cards_model.machines.conditions import ConditionContext
from magic_cards_model.machines.triggers import ExtraTriggerEvent, GameEvent, TriggerEvent
from magic_cards_model.models import Zone
from tests.cards import card
from tests.scenarios.harness import Scenario


def _triggered(name: str) -> list[TriggeredAbility]:
    return [a for a in parse_abilities(card(name)) if isinstance(a, TriggeredAbility)]


# -- a list inside the clause: "nonland, nontoken permanents" ----------------


def test_a_qualifier_list_stays_in_the_clause():
    (ability,) = _triggered("Chrome Replicator")
    assert ability.intervening_if == (
        "you control two or more nonland, nontoken permanents with the same name as one another"
    )
    assert ability.effect == "create a 4/4 colorless Construct artifact creature token."


def _replicator_board(battlefield: list[str], hand: list[str] | None = None):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Chrome Replicator", *(hand or [])],
            battlefield=[*battlefield, *["Plains"] * 5],
            library=["Plains"] * 3,
        )
        .player("bob", library=["Plains"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _cast_replicator(scenario):
    scenario.cast_and_resolve("Chrome Replicator", *scenario.untapped_sources(*["Plains"] * 5))


def test_two_nonland_nontoken_permanents_sharing_a_name_trigger_and_resolve():
    """Chrome Replicator: "When this creature enters, if you control two or
    more nonland, nontoken permanents with the same name as one another,
    create a 4/4 colorless Construct artifact creature token." """
    scenario = _replicator_board(["Grizzly Bears", "Grizzly Bears"])
    _cast_replicator(scenario)
    assert scenario.stack_names() == ["Chrome Replicator's triggered ability"]
    scenario.pass_until_resolved()
    assert "Construct Token" in [s.name for s in scenario.game.permanents_controlled_by("alice")]
    assert scenario.game.intervening_if_notices == []


def test_lands_sharing_a_name_are_not_nonland():
    """Five Plains share a name, but "nonland" excludes every one."""
    scenario = _replicator_board(["Grizzly Bears"])
    _cast_replicator(scenario)
    assert scenario.stack_names() == []
    assert scenario.game.intervening_if_notices == []


def test_the_replicator_counts_itself():
    """A second Chrome Replicator entering makes two nonland, nontoken
    permanents named Chrome Replicator."""
    scenario = _replicator_board(["Chrome Replicator"])
    _cast_replicator(scenario)
    assert scenario.stack_names() == ["Chrome Replicator's triggered ability"]


def test_a_shared_name_gone_by_resolution_removes_the_ability():
    """CR 608.2a: one of the two Bears dies before the trigger resolves."""
    scenario = _replicator_board(["Grizzly Bears", "Grizzly Bears"])
    _cast_replicator(scenario)
    (trigger,) = scenario.game.stack
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.game.destroy(bears)
    assert not scenario.game._intervening_if_still_true(trigger)  # noqa: SLF001
    scenario.pass_until_resolved()
    assert "Construct Token" not in [
        s.name for s in scenario.game.permanents_controlled_by("alice")
    ]


# -- a serial list: "a Giant, Wizard, or spell you controlled" ----------------


def test_a_serial_list_stays_in_the_clause():
    (ability,) = _triggered("Aegar, the Freezing Flame")
    assert ability.intervening_if == (
        "a Giant, Wizard, or spell you controlled dealt damage to it this turn"
    )
    assert ability.effect == "draw a card."


def test_a_source_you_controlled_is_read_off_the_damage_as_dealt():
    """The clause, read against real damage: a spell alice controlled (CR
    109.2b) dealt damage to bob's creature; a Grizzly Bears alice controlled
    is neither a Giant, a Wizard nor a spell. Aegar's own trigger event
    ("is dealt excess damage") is not raised by this engine yet, so the
    clause is asked the way that trigger would ask it: of the damaged
    creature, as the event's subject."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Mountain", "Grizzly Bears"], hand=["Lightning Bolt"])
        .player("bob", battlefield=["Serra Angel"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.creature("Serra Angel", "bob")
    clause = "a Giant, Wizard, or spell you controlled dealt damage to it this turn"
    about_the_angel = GameEvent(event=TriggerEvent.DEALS_DAMAGE, target_id=angel.id)
    alice = ConditionContext(scenario.game, "alice", event=about_the_angel)
    assert conditions.read_condition(alice, clause) is False

    scenario.game.deal_damage(angel, 1, source=scenario.creature("Grizzly Bears", "alice"))
    assert conditions.read_condition(alice, clause) is False

    scenario.cast_and_resolve(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=[angel]
    )
    assert conditions.read_condition(alice, clause) is True
    bob = ConditionContext(scenario.game, "bob", event=about_the_angel)
    assert conditions.read_condition(bob, clause) is False
    # No event naming "it": nothing to ask about.
    assert conditions.read_condition(ConditionContext(scenario.game, "alice"), clause) is False


# -- a clause that must not swallow its effect --------------------------------


def test_a_cast_this_turn_clause_ends_at_its_own_sentence():
    """Hurkyl, Master Wizard: "At the beginning of your end step, if you've
    cast a noncreature spell this turn, reveal the top five cards of your
    library. For each card type among noncreature spells you've cast this
    turn, ..." - the clause ends at the first comma, not the second
    sentence's "you've cast this turn,"."""
    (ability,) = _triggered("Hurkyl, Master Wizard")
    assert ability.intervening_if == "you've cast a noncreature spell this turn"
    assert ability.effect.startswith("reveal the top five cards of your library.")


def _hurkyl_board():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=["Hurkyl, Master Wizard", "Mountain"],
            hand=["Lightning Bolt"],
            library=["Plains"] * 6,
        )
        .player("bob", library=["Plains"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_a_noncreature_spell_cast_this_turn_triggers_at_the_end_step():
    scenario = _hurkyl_board()
    scenario.cast_and_resolve(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=["bob"]
    )
    scenario.start_at(Step.END_STEP)
    scenario.game.emit(
        GameEvent(event=TriggerEvent.BEGINNING_OF_STEP, step=Step.END_STEP, player="alice")
    )
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == ["Hurkyl, Master Wizard's triggered ability"]
    assert scenario.game.intervening_if_notices == []


def test_no_noncreature_spell_cast_this_turn_does_not_trigger():
    scenario = _hurkyl_board()
    scenario.start_at(Step.END_STEP)
    scenario.game.emit(
        GameEvent(event=TriggerEvent.BEGINNING_OF_STEP, step=Step.END_STEP, player="alice")
    )
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == []
    assert scenario.game.intervening_if_notices == []


# -- "while <doing something>" is the event, not an intervening "if" ----------


def test_while_casting_stays_part_of_the_trigger_event():
    """Foul Emissary: "When you sacrifice this creature while casting a spell
    with emerge, create a 3/2 ... token." - an intervening "if" would be
    rechecked on resolution, when the casting is long over (CR 608.2a)."""
    (_, sacrificed) = _triggered("Foul Emissary")
    assert sacrificed.intervening_if is None
    assert sacrificed.condition == "you sacrifice this creature while casting a spell with emerge"
    assert sacrificed.event is None


def test_a_sacrifice_not_while_casting_with_emerge_triggers_nothing():
    """Foul Emissary sacrificed to Hell's Caretaker's cost: no emerge spell is
    being cast, so nothing triggers - and nothing is recorded as an unread
    clause, which is what the old reading did."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=["Hell's Caretaker", "Foul Emissary"],
            graveyard=["Grizzly Bears"],
            library=["Plains"] * 3,
        )
        .player("bob", library=["Plains"] * 3)
        .build()
    )
    scenario.start_at(Step.UPKEEP)
    caretaker = scenario.creature("Hell's Caretaker", "alice")
    emissary = scenario.creature("Foul Emissary", "alice")
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")
    scenario.activate(caretaker, sacrificing=[emissary], targets=[bears])
    assert scenario.stack_names() == ["Hell's Caretaker's activated ability"]
    assert scenario.game.intervening_if_notices == []


def test_while_you_are_activating_stays_part_of_the_event():
    """Market Gnome's "... while you're activating a craft ability" is the
    same shape, with its subject spelled out."""
    (_, gnome) = _triggered("Market Gnome")
    assert gnome.intervening_if is None
    assert gnome.condition.endswith("while you're activating a craft ability")
    assert gnome.event is None


def test_while_saddled_is_the_permanents_own_state():
    """Brightfield Mustang's "Whenever this creature attacks while saddled" -
    a state of the permanent (CR 702.171b), kept as the intervening "if" and
    spelled as the clause its reader reads."""
    (ability,) = _triggered("Brightfield Mustang")
    assert ability.condition == "this creature attacks"
    assert ability.intervening_if == "it's saddled"


# -- "if it isn't a mana ability" on an activation trigger ---------------------


def test_harsh_mentors_list_and_its_mana_ability_clause_are_cut_apart():
    (ability,) = _triggered("Harsh Mentor")
    assert ability.condition == (
        "an opponent activates an ability of an artifact, creature, or land on the battlefield"
    )
    assert ability.intervening_if == "it isn't a mana ability"
    assert ability.effect == "this creature deals 2 damage to that player."


def _mentor_board():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Harsh Mentor"])
        .player("bob", battlefield=["Augur of Skulls", "Swamp", "Forest", "Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.pass_priority("alice")
    return scenario


def test_an_opponents_non_mana_ability_triggers_and_resolves():
    """Harsh Mentor: "Whenever an opponent activates an ability of an
    artifact, creature, or land on the battlefield, if it isn't a mana
    ability, this creature deals 2 damage to that player." - bob regenerates
    his Augur of Skulls."""
    scenario = _mentor_board()
    augur = scenario.creature("Augur of Skulls", "bob")
    scenario.activate(
        augur, *scenario.untapped_sources("Swamp", "Forest", username="bob"), username="bob"
    )
    assert scenario.stack_names() == [
        "Augur of Skulls's activated ability",
        "Harsh Mentor's triggered ability",
    ]
    scenario.resolve_top()
    assert scenario.player("bob").life == 18


def test_a_mana_ability_does_not_trigger():
    """Bob taps a Forest for mana - an ability of a land, but a mana ability
    (CR 605.1a): no trigger."""
    scenario = _mentor_board()
    (forest, _) = scenario.untapped_sources("Forest", "Forest", username="bob")
    scenario.activate(forest, username="bob")
    assert scenario.stack_names() == []
    assert scenario.game.intervening_if_notices == []


# -- "if it isn't being declared as an attacker" ------------------------------


def test_the_attack_declarations_own_tap_carries_that_it_was_one():
    """CR 508.1f: the event a declared attacker's tap raises says so, and the
    clause reads it off the event (Verity Circle). Gran-Gran's own "Whenever
    Gran-Gran becomes tapped" is what holds the real event here."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Gran-Gran"], library=["Plains"] * 3)
        .player("bob", battlefield=["Verity Circle"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(scenario.creature("Gran-Gran", "alice"))
    (trigger,) = [a for a in scenario.game.stack + scenario.game.pending_triggers]
    assert trigger.event is not None and trigger.event.declared_attacker
    clause = "it isn't being declared as an attacker"
    bob = ConditionContext(scenario.game, "bob", event=trigger.event)
    assert conditions.read_condition(bob, clause) is False
    another_tap = trigger.event.model_copy(update={"declared_attacker": False})
    assert (
        conditions.read_condition(ConditionContext(scenario.game, "bob", event=another_tap), clause)
        is True
    )
    assert conditions.read_condition(ConditionContext(scenario.game, "bob"), clause) is False


def test_the_mana_ability_clause_needs_an_activation_event():
    scenario = Scenario().player("alice").player("bob").build()
    context = ConditionContext(scenario.game, "alice")
    assert conditions.read_condition(context, "it isn't a mana ability") is False
    activation = GameEvent(event=ExtraTriggerEvent.ABILITY_ACTIVATED, mana_ability=False)
    assert (
        conditions.read_condition(
            ConditionContext(scenario.game, "alice", event=activation), "it isn't a mana ability"
        )
        is True
    )
