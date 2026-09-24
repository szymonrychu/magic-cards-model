"""Scenario: "<this> gets +N/+N until end of turn and deals N damage to each
opponent." - one sentence, two instructions sharing one subject.

Gandalf, Goblins' Bane prints it on a cast trigger ("Whenever you cast a
noncreature spell, ..."); off-set Penregon Strongbull prints the same
sentence on an activated ability ("{1}, Sacrifice an artifact: This creature
gets +1/+1 until end of turn and deals 1 damage to each opponent.") - a
different ability kind and a different self-reference (CR 201.5's own name
against CR 700.7's "this creature"), which proves the reader is the template.

The pump is a layer 7c effect (CR 613.4c) lasting until end of turn (CR
611.2a); the damage is dealt by the creature itself (CR 608.2h: "If an
ability states that an object does something, it's the object as it exists
- or as it most recently existed - that does it"), so a source that left the
battlefield in response still deals it, using its last known information,
while the pump has nothing left to apply to. Damage to a player without
infect is life loss (CR 120.3a). A triggered ability triggers on the event
(CR 603.2).

CR numbers verified with `mise run rules:find`: 201.5, 700.7, 613.4c,
611.2a, 608.2h, 120.3a, 603.2.
"""

from magic_cards_model.machines import Step
from magic_cards_model.support import card_support
from tests.cards import card

from .harness import Scenario

GANDALF = "Gandalf, Goblins' Bane // Flameshape"


def test_both_printings_read_the_pump_and_damage_clause():
    gandalf = [c for c in card_support(card(GANDALF)).clauses if c.kind == "triggered"]
    assert [c.outcome for c in gandalf] == ["handled"]
    assert card_support(card("Penregon Strongbull")).status == "handled"


def _gandalf_board(*, opponents: int = 1, hand=("Opt",)) -> Scenario:
    scenario = Scenario().player(
        "alice",
        hand=list(hand),
        battlefield=[GANDALF, "Island", "Island", "Mountain", "Mountain"],
        library=["Island"] * 5,
    )
    for name in ("bob", "carol")[:opponents]:
        scenario = scenario.player(name, library=["Island"] * 5)
    return scenario


def test_a_noncreature_spell_pumps_gandalf_and_pings_the_opponent():
    scenario = _gandalf_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    gandalf = scenario.creature("Gandalf, Goblins' Bane", "alice")
    bob = scenario.player("bob")
    scenario.cast_onto_stack("Opt", *scenario.untapped_sources("Island"))
    assert scenario.stack_names() == ["Opt", "Gandalf, Goblins' Bane's triggered ability"]
    scenario.resolve_top()
    chars = scenario.game.characteristics_of(gandalf)
    assert (chars.power, chars.toughness) == (3, 4)
    assert bob.life == 19


def test_the_pump_ends_at_end_of_turn_and_stacks_per_spell():
    scenario = _gandalf_board(hand=("Opt", "Opt")).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    gandalf = scenario.creature("Gandalf, Goblins' Bane", "alice")
    bob = scenario.player("bob")
    for island in scenario.untapped_sources("Island", "Island"):
        scenario.cast_onto_stack("Opt", island)
        scenario.resolve_top()  # the trigger
        scenario.resolve_top()  # Opt
    chars = scenario.game.characteristics_of(gandalf)
    assert (chars.power, chars.toughness) == (4, 5)
    assert bob.life == 18
    while scenario.step is not Step.CLEANUP:
        scenario.advance()
    chars = scenario.game.characteristics_of(gandalf)
    assert (chars.power, chars.toughness) == (2, 3)


def test_a_creature_spell_does_not_trigger_it():
    scenario = _gandalf_board(hand=("Goblin Guide",)).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_onto_stack("Goblin Guide", *scenario.untapped_sources("Mountain"))
    assert scenario.stack_names() == ["Goblin Guide"]


def test_each_opponent_takes_the_damage_in_a_three_player_game():
    scenario = _gandalf_board(opponents=2).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_onto_stack("Opt", *scenario.untapped_sources("Island"))
    scenario.resolve_top()
    assert scenario.player("bob").life == 19
    assert scenario.player("carol").life == 19
    assert scenario.player("alice").life == 20


def test_gandalf_gone_in_response_still_deals_the_damage_from_last_known_information():
    """CR 608.2h: the opponent Bolts Gandalf in response to the trigger - the
    damage is still dealt, by Gandalf as he last existed; the pump has no
    object left to apply to."""
    scenario = (
        Scenario()
        .player("alice", hand=["Opt"], battlefield=[GANDALF, "Island"], library=["Island"] * 5)
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    gandalf = scenario.creature("Gandalf, Goblins' Bane", "alice")
    scenario.cast_onto_stack("Opt", *scenario.untapped_sources("Island"))
    scenario.pass_priority("alice")
    scenario.cast_onto_stack(
        "Lightning Bolt",
        *scenario.untapped_sources("Mountain", username="bob"),
        username="bob",
        targets=[gandalf],
    )
    scenario.resolve_top()  # Bolt: Gandalf (2/3) dies
    scenario.state_based_actions()
    assert gandalf.zone.value == "graveyard"
    scenario.resolve_top()  # the trigger
    assert scenario.player("bob").life == 19


def test_strongbull_activation_pumps_itself_and_pings_each_opponent():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Penregon Strongbull", "Ornithopter", "Mountain"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bull = scenario.creature("Penregon Strongbull", "alice")
    thopter = scenario.creature("Ornithopter", "alice")
    scenario.activate(bull, *scenario.untapped_sources("Mountain"), sacrificing=[thopter])
    scenario.resolve_top()
    chars = scenario.game.characteristics_of(bull)
    assert (chars.power, chars.toughness) == (3, 4)
    assert scenario.player("bob").life == 19


def test_strongbull_sacrificed_in_response_still_deals_its_damage():
    """CR 608.2h: the damage is dealt by the creature as it last existed;
    the pump has no object left to apply to."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Penregon Strongbull", "Ornithopter", "Mountain", "Mountain"],
            hand=["Lightning Bolt"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bull = scenario.creature("Penregon Strongbull", "alice")
    thopter = scenario.creature("Ornithopter", "alice")
    mountain_a, mountain_b = scenario.untapped_sources("Mountain", "Mountain")
    scenario.activate(bull, mountain_a, sacrificing=[thopter])
    scenario.cast_and_resolve("Lightning Bolt", mountain_b, targets=[bull])
    assert bull not in scenario.game.battlefield
    scenario.resolve_top()
    assert scenario.player("bob").life == 19
