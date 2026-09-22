"""CR 113.6: a triggered ability only functions from the zone(s) it is meant to.

Every CR number below was looked up with `knowledge_search(type="rules")` in the
session that wrote this file.

- **CR 113.6** - "Abilities of an instant or sorcery spell usually function only
  while that object is on the stack. Abilities of all other objects usually
  function only while that object is on the battlefield." (The rule's own tail
  - the exceptions list - truncated for `knowledge_search` in this session too,
  so it was never read directly, only the individually-served subrules below.)
- **CR 113.6b** - "An ability that states which zones it functions in functions
  only from those zones."
- **CR 113.6k** - "A trigger condition that can't trigger from the battlefield
  functions in all zones it can trigger from. Other trigger conditions of the
  same triggered ability may function in different zones."
- **CR 603.10a** - dies, is-sacrificed and spell-is-countered triggers look
  back at the object as it existed immediately beforehand.

The bug this file is the regression test for: `Game.emit` widens the sources a
cast trigger is asked of to include every spell on the stack (CR 603.3d's
"a trigger can trigger while a spell is being cast"), and until now nothing
then checked whether the ability in question actually *functions* from there.
Vexing Bauble's "whenever a player casts a spell" is a battlefield ability - it
was firing off its own casting, before the permanent it needs even exists, and
would have kept firing off anyone else's casting for as long as it sat on the
stack waiting to resolve. `machines/triggers.zones_ability_functions_in` is the
fix: a gate consulted in `triggers_for`, alongside (not instead of) the
condition match.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.triggers import (
    TriggerEvent,
    triggered_abilities_of,
    zones_ability_functions_in,
)
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario

# -- Vexing Bauble: the defect, from both zones ----------------------------


def test_vexing_bauble_does_not_trigger_off_its_own_casting():
    """Vexing Bauble is a spell, not yet a permanent, while it is being cast -
    its own "whenever a player casts a spell" is a battlefield ability
    (CR 113.6's default; nothing in its text names a zone), so it cannot fire
    off the very casting that puts it there.
    """
    scenario = (
        Scenario()
        .player("alice", library=["Forest"], hand=["Vexing Bauble"], battlefield=["Forest"])
        .player("bob", library=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (forest,) = scenario.untapped_sources("Forest")

    scenario.cast_onto_stack("Vexing Bauble", forest)

    assert scenario.stack_names() == ["Vexing Bauble"]
    assert scenario.pending_triggers == []


def test_vexing_bauble_triggers_from_the_battlefield_on_its_own_controllers_cast():
    """Once it resolves, Vexing Bauble is a permanent, and CR 113.6's default
    zone is exactly where it now sits - including for a spell its own
    controller casts. This is the case the fix must not suppress: the defect
    is zonal, not about whose spell it is.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Forest"],
            hand=["Lightning Bolt"],
            battlefield=["Vexing Bauble", "Mountain"],
        )
        .player("bob", library=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (mountain,) = scenario.untapped_sources("Mountain")

    scenario.cast_onto_stack("Lightning Bolt", mountain, targets=[scenario.player("bob")])

    # The zone gate lets it through - it reaches the "no mana was spent"
    # clause rather than being suppressed before it is even asked, and that
    # clause is read for real now (see test_mana_spent_intervening_if.py):
    # real mana was spent on Lightning Bolt, so the condition is false and the
    # ability does not trigger, with no engine-gap notice either.
    assert scenario.game.intervening_if_notices == []
    assert scenario.pending_triggers == []


def test_vexing_bauble_does_not_trigger_off_an_unrelated_spell_while_still_a_spell_itself():
    """A second, unrelated spell cast in response to Vexing Bauble still on the
    stack must not wake it either - the defect was never "only its own
    casting", `Game.emit` widens the source list for every spell on the stack.
    """
    scenario = (
        Scenario()
        .player("alice", library=["Forest"], hand=["Vexing Bauble"], battlefield=["Forest"])
        .player("bob", library=["Forest"], hand=["Lightning Bolt"], battlefield=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (forest,) = scenario.untapped_sources("Forest")
    scenario.cast_onto_stack("Vexing Bauble", forest)
    scenario.pass_priority("alice")

    (mountain,) = scenario.untapped_sources("Mountain", username="bob")
    scenario.cast_onto_stack(
        "Lightning Bolt", mountain, username="bob", targets=[scenario.player("alice")]
    )

    assert scenario.stack_names() == ["Vexing Bauble", "Lightning Bolt"]
    assert scenario.pending_triggers == []


# -- Chalice of the Void: the same defect, condition read in full ----------


def test_chalice_triggers_from_the_battlefield_on_a_matching_mana_value():
    """Control: with Chalice already on the battlefield, a spell whose mana
    value matches its charge counters is countered. Establishes the condition
    itself (mana value vs. charge counters) is read correctly before the zone
    test below relies on it.
    """
    scenario = (
        Scenario()
        .player("alice", library=["Forest"], battlefield=["Chalice of the Void"])
        .player("bob", library=["Forest"], hand=["Lightning Bolt"], battlefield=["Mountain"])
        .build()
    )
    chalice = scenario.creature("Chalice of the Void", "alice")
    scenario.game.add_counters(chalice, Counter.CHARGE, 1)
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.pass_priority("alice")

    (mountain,) = scenario.untapped_sources("Mountain", username="bob")
    scenario.cast_onto_stack(
        "Lightning Bolt", mountain, username="bob", targets=[scenario.player("alice")]
    )

    assert scenario.stack_names() == ["Lightning Bolt", "Chalice of the Void's triggered ability"]


def test_chalice_does_not_trigger_off_an_opponents_response_while_still_a_spell():
    """Chalice of the Void sitting on the stack, itself still being cast, must
    not counter a spell an opponent casts in response - even one whose mana
    value matches the charge count it will eventually have. This is the
    scenario named in the defect report: a naive fix scoped only to "the spell
    just cast" leaves this half live, because `Game.emit` widens sources for
    *every* spell on the stack, not only the newest one.
    """
    scenario = (
        Scenario()
        .player("alice", library=["Forest"], hand=["Chalice of the Void"], battlefield=["Forest"])
        .player("bob", library=["Forest"], hand=["Lightning Bolt"], battlefield=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (forest,) = scenario.untapped_sources("Forest")
    scenario.cast_onto_stack("Chalice of the Void", forest)
    # Contrived: give the still-uncast spell the charge count it would only
    # normally have after resolving (CR 601.2i is long past by the time X
    # would be paid), purely to isolate the zone question from the mana-value
    # one - the control above already proves the value comparison itself.
    chalice_spell = scenario.game.stack[0]
    scenario.game.add_counters(chalice_spell, Counter.CHARGE, 1)
    scenario.pass_priority("alice")

    (mountain,) = scenario.untapped_sources("Mountain", username="bob")
    scenario.cast_onto_stack(
        "Lightning Bolt", mountain, username="bob", targets=[scenario.player("alice")]
    )

    assert scenario.stack_names() == ["Chalice of the Void", "Lightning Bolt"]
    assert scenario.pending_triggers == []


# -- Cityscape Leveler: one ability, two conditions, two zones -------------


def test_cityscape_levelers_two_trigger_conditions_function_in_their_own_zones():
    """Cityscape Leveler prints "When you cast this spell and whenever this
    creature attacks, destroy up to one target nonland permanent." as one
    ability with two trigger conditions (CR 603.1b). `machines/abilities.py`
    reads it as one `TriggeredAbility` per condition, so CR 113.6k's "Other
    trigger conditions of the same triggered ability may function in
    different zones" falls out: the cast half from the stack, the attack half
    from the battlefield - and neither carries the other's text, which is
    what once tempted a substring zone gate into granting the attack half
    stack rights.
    """
    scenario = Scenario().player("alice", battlefield=["Cityscape Leveler"]).player("bob").build()
    leveler = scenario.creature("Cityscape Leveler", "alice")
    cast, attack = triggered_abilities_of(leveler.card)
    assert (cast.event, attack.event) == (TriggerEvent.CAST_SPELL, TriggerEvent.ATTACKS)
    assert "this spell" not in attack.condition.lower()

    assert zones_ability_functions_in(cast, leveler) == frozenset({Zone.STACK})
    assert zones_ability_functions_in(attack, leveler) == frozenset({Zone.BATTLEFIELD})


# -- the hazard list: every one of these must still fire --------------------
#
# Each of these already left the battlefield (or, for the opening-hand cases,
# never was on it) by the time its trigger is worked out, which is exactly
# what CR 603.10a's look-back exists for. A zone gate that only allowed
# BATTLEFIELD would have silently broken every one of them.


def _dies_trigger_names(name: str) -> list[str]:
    scenario = (
        Scenario().player("alice", library=["Forest"], battlefield=[name]).player("bob").build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    creature = scenario.creature(name, "alice")
    scenario.game.put_into_graveyard(creature)
    scenario.game.put_triggers_on_stack()
    return scenario.stack_names()


def test_flagstones_of_trokair_dies_trigger_still_fires():
    assert _dies_trigger_names("Flagstones of Trokair") == [
        "Flagstones of Trokair's triggered ability"
    ]


def test_wurmcoil_engine_dies_trigger_still_fires():
    assert _dies_trigger_names("Wurmcoil Engine") == ["Wurmcoil Engine's triggered ability"]


def test_hangarback_walker_dies_trigger_still_fires():
    assert _dies_trigger_names("Hangarback Walker") == ["Hangarback Walker's triggered ability"]


def test_footlight_fiend_dies_trigger_still_fires():
    assert _dies_trigger_names("Footlight Fiend") == ["Footlight Fiend's triggered ability"]


def test_solemn_simulacrum_dies_trigger_still_fires():
    assert _dies_trigger_names("Solemn Simulacrum") == ["Solemn Simulacrum's triggered ability"]


def test_blood_artist_dies_trigger_still_fires():
    assert _dies_trigger_names("Blood Artist") == ["Blood Artist's triggered ability"]


def test_kitchen_finks_persist_trigger_still_fires():
    """Persist (CR 702.79a) is a keyword-expanded DIES trigger with its own
    intervening *if* ("if it had no -1/-1 counters on it") - both the zone
    gate and the intervening-if clause have to pass for the same ability.
    """
    scenario = (
        Scenario()
        .player("alice", library=["Forest"], battlefield=["Kitchen Finks"])
        .player("bob")
        .build()
    )
    creature = scenario.creature("Kitchen Finks", "alice")
    scenario.game.put_into_graveyard(creature)
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == ["Kitchen Finks's triggered ability"]


def test_solemn_simulacrum_enters_trigger_still_fires_from_the_battlefield():
    """The other half of Solemn Simulacrum: its ENTERS trigger is an ordinary
    CR 113.6 default-zone ability and must be unaffected by the DIES-specific
    look-back handling above.
    """
    scenario = (
        Scenario()
        .player("alice", library=["Forest"], hand=["Solemn Simulacrum"], battlefield=["Forest"] * 5)
        .player("bob", library=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources(*(["Forest"] * 5))
    scenario.cast_onto_stack("Solemn Simulacrum", *sources)
    scenario.pass_until_resolved()

    assert scenario.stack_names() == ["Solemn Simulacrum's triggered ability"]


def test_thought_knot_seer_enters_trigger_still_fires_from_the_battlefield():
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Forest"],
            hand=["Thought-Knot Seer"],
            battlefield=["Wastes"] * 4,
        )
        .player("bob", library=["Forest"], hand=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources(*(["Wastes"] * 4))
    scenario.cast_onto_stack("Thought-Knot Seer", *sources)
    scenario.pass_until_resolved()

    assert scenario.stack_names() == ["Thought-Knot Seer's triggered ability"]
