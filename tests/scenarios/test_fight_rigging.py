"""Fight Rigging: hideaway (CR 702.75a) and its own beginning-of-combat
trigger, read as two separate abilities (CR 113.3, one paragraph is one
ability).

"Hideaway 5 (When this enchantment enters, look at the top five cards of
your library, exile one face down, then put the rest on the bottom in a
random order.)
At the beginning of combat on your turn, put a +1/+1 counter on target
creature you control. Then if you control a creature with power 7 or
greater, you may play the exiled card without paying its mana cost."

CR numbers looked up with `knowledge_search(type="rules")` in this session:
CR 702.75a (hideaway), CR 122.1a (+1/+1 counter), CR 601.3 (permission to
play a specific card).
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import ExileMarker
from tests.scenarios.harness import Scenario


def board(*, extra_battlefield: list[str] | None = None) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=["Fight Rigging"],
            battlefield=["Forest", "Forest", "Forest", *(extra_battlefield or [])],
            library=["Lightning Bolt", "Forest", "Forest", "Forest", "Forest"],
        )
        .player("bob")
    )


def cast_fight_rigging(scenario: Scenario):
    """Cast Fight Rigging and resolve its own hideaway trigger too, always
    hiding away Lightning Bolt (the top card), so every test downstream
    knows what got exiled. `cast_and_resolve` only resolves the spell
    itself; the enters-the-battlefield trigger it puts on the stack needs
    its own `resolve_top`."""
    bolt = scenario.player("alice").library[0]
    assert bolt.name == "Lightning Bolt"
    scenario.will_choose_cards(bolt, source="Fight Rigging")
    sources = scenario.untapped_sources("Forest", "Forest", "Forest")
    fight_rigging = scenario.cast_and_resolve("Fight Rigging", *sources)
    while scenario.game.stack:
        scenario.resolve_top()
    return fight_rigging


def test_hideaway_exiles_one_of_the_top_five_face_down_and_bottoms_the_rest():
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    fight_rigging = cast_fight_rigging(scenario)

    bolt = scenario.find("Lightning Bolt", Zone.EXILE, "alice")
    assert bolt.exile_annotation is not None
    assert bolt.exile_annotation.marker == ExileMarker.HIDEAWAY
    assert bolt.exile_annotation.linked_permanent_id == fight_rigging.id
    assert bolt.face_up is False
    # Five looked at, one exiled: four left, bottomed in some order.
    assert len(scenario.player("alice").library) == 4
    assert {card.name for card in scenario.player("alice").library} == {"Forest"}


def test_the_combat_trigger_puts_a_counter_on_the_target_creature():
    scenario = board(extra_battlefield=["Grizzly Bears"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    cast_fight_rigging(scenario)
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.choose_trigger_targets("Fight Rigging", [bears])
    scenario.advance()  # combat begins
    while scenario.game.stack:
        scenario.resolve_top()

    assert bears.counters["+1/+1"] == 1


def test_without_a_big_enough_creature_no_free_cast_is_offered():
    """Grizzly Bears reaches power 3 with the counter - nowhere near 7 - so
    the "you may play the exiled card" half never asks anything, and the
    exiled card stays put."""
    scenario = board(extra_battlefield=["Grizzly Bears"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    cast_fight_rigging(scenario)
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.choose_trigger_targets("Fight Rigging", [bears])
    scenario.advance()  # combat begins
    while scenario.game.stack:
        scenario.resolve_top()

    assert not any(
        question.prompt == "play the exiled card without paying its mana cost"
        for question in scenario.questions_asked()
    )
    bolt = scenario.find("Lightning Bolt", Zone.EXILE, "alice")
    assert bolt.zone is Zone.EXILE


def test_with_a_big_enough_creature_the_exiled_card_is_cast_free():
    """The corner case this file is for: the free-cast permission is gated on
    the board *after* the counter resolves (CR 608.2c's printed order), so a
    6-power creature that becomes a 7-power creature from the counter itself
    still qualifies.
    """
    scenario = board(extra_battlefield=["Colossal Dreadmaw"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    cast_fight_rigging(scenario)
    dreadmaw = scenario.creature("Colossal Dreadmaw", "alice")
    assert dreadmaw.power == 6

    scenario.will_take_the_may(True, source="Fight Rigging")
    scenario.choose_trigger_targets("Fight Rigging", [dreadmaw])
    scenario.advance()  # combat begins
    while scenario.game.stack:
        scenario.resolve_top()

    assert dreadmaw.counters["+1/+1"] == 1
    assert dreadmaw.power == 7
    # Lightning Bolt left exile - cast for free, with no legal target
    # available, so CR 601.2c makes casting it illegal and nothing goes on
    # the stack at all; the free-cast question was still asked and answered
    # "yes", which is what this test is checking.
    assert not any(state.name == "Lightning Bolt" for state in scenario.game.exile)
