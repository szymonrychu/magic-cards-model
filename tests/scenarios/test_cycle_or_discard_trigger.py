""" "Whenever you cycle or discard another card, `<effect>`" - one trigger per
card discarded, and a cycled card counted once (CR 702.29d).

CR 702.29d: "Some cards have abilities that trigger whenever a player "cycles
or discards" a card. These abilities trigger only once when a card is
cycled." A cycling ability's cost is a discard (CR 702.29a: "Cycling [cost]"
means "[Cost], Discard this card: Draw a card."), so the one discard event is
the whole of "cycles or discards" - the rulings on both printings say the same:
"The ability "Whenever you discard a card" is functionally identical to this
ability; cycling is mentioned for clarity."

CR 701.9a: "To discard a card, move it from its owner's hand to that player's
graveyard." CR 603.2c: "An ability triggers only once each time its trigger
event occurs. However, it can trigger repeatedly if one event contains
multiple occurrences." - so a single instruction discarding two cards triggers
a "discard a card" ability twice, once for each card.

CR 514.1 / CR 514.3a: the cleanup step's discard to maximum hand size is a
discard too, and a trigger it sets off reopens the step.

Curator of Mysteries is the listed card (scry 1); Archfiend of Ifnir (a -1/-1
counter on each opposing creature) is the proof printing - Modern and Pioneer
legal, in no api deck.

Every CR number here was looked up with `mise run rules:find` in the session
that wrote it.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.abilities import TriggerEvent
from magic_cards_model.machines.keywords import cycling_activation
from magic_cards_model.machines.triggers import triggered_abilities_of
from magic_cards_model.models import Zone
from magic_cards_model.support import card_support
from tests.cards import card
from tests.scenarios.harness import Scenario, mana_from

CURATOR = "Curator of Mysteries"
ARCHFIEND = "Archfiend of Ifnir"


def _cycle_onto_stack(scenario, cycled, *mana, username: str = "alice"):
    """Activate a cycling ability and leave it (and whatever it set off) on
    the stack - CR 702.29a's ability uses the stack and can be responded to."""
    activation = cycling_activation(scenario.game, cycled, username)
    payment = activation.begin_paying()
    for source in mana:
        payment.tap_for_mana(source, mana_from(source))
    payment.pay()
    activation.activate()
    return activation


def _triggers_named(scenario, name: str) -> list:
    return [item for item in scenario.game.stack if item.name == f"{name}'s triggered ability"]


def test_the_condition_reads_as_a_discard_event() -> None:
    """The trigger is parsed onto CR 701.9a's discard event, not dropped."""
    (ability,) = [
        a for a in triggered_abilities_of(card(CURATOR)) if "cycle or discard" in a.condition
    ]
    assert ability.event is TriggerEvent.DISCARDS_A_CARD
    assert ability.effect.lower().startswith("scry 1")


def test_both_printings_are_fully_supported() -> None:
    for name in (CURATOR, ARCHFIEND):
        statuses = {clause.status for clause in card_support(card(name)).clauses}
        assert statuses == {"handled"}, (name, card_support(card(name)).clauses)


def test_cycling_another_card_triggers_curator_once() -> None:
    """CR 702.29d: a cycled card is cycled *and* discarded, but the ability
    triggers only once - and it resolves before the cycling draw."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Censor"],
            library=["Lightning Bolt", "Grizzly Bears"],
            battlefield=[CURATOR, "Island"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    censor = scenario.find("Censor", Zone.HAND, "alice")
    bolt = scenario.find("Lightning Bolt", Zone.LIBRARY, "alice")

    _cycle_onto_stack(scenario, censor, *scenario.untapped_sources("Island"))

    assert censor.zone is Zone.GRAVEYARD
    assert len(_triggers_named(scenario, CURATOR)) == 1
    assert scenario.stack_names()[-1] == f"{CURATOR}'s triggered ability"

    # Scry 1 bottoms the Bolt, so the cycling draw finds the Bears.
    scenario.scry_bottoming(bolt)
    scenario.resolve_top()
    assert scenario.player("alice").library[-1] is bolt
    scenario.resolve_top()
    assert scenario.find("Grizzly Bears", Zone.HAND, "alice").zone is Zone.HAND


def test_one_discard_of_two_cards_triggers_twice() -> None:
    """CR 603.2c: Faithless Looting discards two cards in one instruction -
    one event with two occurrences, so the ability triggers twice."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Faithless Looting", "Grizzly Bears", "Memnite"],
            library=["Island", "Island", "Island", "Island"],
            battlefield=[CURATOR, "Mountain"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.HAND, "alice")
    memnite = scenario.find("Memnite", Zone.HAND, "alice")
    scenario.will_discard(bears, memnite)

    scenario.cast_and_resolve("Faithless Looting", *scenario.untapped_sources("Mountain"))
    scenario.game.put_triggers_on_stack()

    assert bears.zone is Zone.GRAVEYARD and memnite.zone is Zone.GRAVEYARD
    assert len(_triggers_named(scenario, CURATOR)) == 2


def test_an_opponents_discard_does_not_trigger_it() -> None:
    """ "Whenever *you* cycle or discard" - the ability's controller only."""
    scenario = (
        Scenario()
        .player("alice", battlefield=[CURATOR])
        .player("bob", hand=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.HAND, "bob")

    scenario.game.discard_cards("bob", [bears])
    scenario.game.put_triggers_on_stack()

    assert bears.zone is Zone.GRAVEYARD
    assert _triggers_named(scenario, CURATOR) == []


def test_it_functions_only_on_the_battlefield() -> None:
    """A Curator in hand has the ability but it does nothing there - cycling
    Curator itself sets off no trigger of its own (CR 113.6)."""
    scenario = (
        Scenario()
        .player("alice", hand=[CURATOR], library=["Island"], battlefield=["Island"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    curator = scenario.find(CURATOR, Zone.HAND, "alice")

    _cycle_onto_stack(scenario, curator, *scenario.untapped_sources("Island"))

    assert curator.zone is Zone.GRAVEYARD
    assert _triggers_named(scenario, CURATOR) == []


def test_cycling_a_second_curator_triggers_the_one_on_the_battlefield() -> None:
    """ "another card" means any card but this object - a second copy of the
    same card cycled from hand is another card (CR 400.7's objects, not names)."""
    scenario = (
        Scenario()
        .player("alice", hand=[CURATOR], library=["Island"], battlefield=[CURATOR, "Island"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    in_hand = scenario.find(CURATOR, Zone.HAND, "alice")

    _cycle_onto_stack(scenario, in_hand, *scenario.untapped_sources("Island"))

    assert len(_triggers_named(scenario, CURATOR)) == 1


def test_the_cleanup_discard_triggers_it() -> None:
    """CR 514.1: discarding to maximum hand size is a discard, and the
    ruling on both printings says the ability triggers there too."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Island"] * 8,
            battlefield=[CURATOR],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    extra = scenario.player("alice").hand[-1]
    scenario.will_discard(extra)

    discarded = scenario.player("alice").discard_to_maximum_hand_size()
    scenario.game.put_triggers_on_stack()

    assert discarded == [extra]
    assert len(_triggers_named(scenario, CURATOR)) == 1


def test_archfiend_puts_a_counter_on_each_opposing_creature_per_card() -> None:
    """The proof printing: a differently worded effect off the same trigger.
    Two cards discarded at once is two -1/-1 counters on each of bob's
    creatures, and none on alice's own."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Faithless Looting", "Island", "Island"],
            library=["Island", "Island"],
            battlefield=[ARCHFIEND, "Mountain", "Grizzly Bears"],
        )
        .player("bob", battlefield=["Grizzly Bears", "Ornithopter"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    hand = scenario.player("alice").hand
    first, second = hand[1], hand[2]
    scenario.will_discard(first, second)
    bob_bears = scenario.creature("Grizzly Bears", "bob")
    thopter = scenario.creature("Ornithopter", "bob")
    alice_bears = scenario.creature("Grizzly Bears", "alice")

    scenario.cast_and_resolve("Faithless Looting", *scenario.untapped_sources("Mountain"))
    scenario.game.put_triggers_on_stack()
    assert len(_triggers_named(scenario, ARCHFIEND)) == 2
    scenario.resolve_top()
    scenario.state_based_actions()
    assert bob_bears.counter_count("-1/-1") == 1
    assert thopter.counter_count("-1/-1") == 1
    scenario.resolve_top()
    scenario.state_based_actions()

    # CR 704.5f: the second counter leaves both at toughness 0.
    assert bob_bears.zone is Zone.GRAVEYARD
    assert thopter.zone is Zone.GRAVEYARD
    assert alice_bears.counter_count("-1/-1") == 0


def test_archfiend_triggers_once_off_a_cycled_card() -> None:
    """CR 702.29d on the proof printing: one counter per creature for one
    cycled card, never two."""
    scenario = (
        Scenario()
        .player("alice", hand=["Censor"], library=["Island"], battlefield=[ARCHFIEND, "Island"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")

    _cycle_onto_stack(
        scenario, scenario.find("Censor", Zone.HAND, "alice"), *scenario.untapped_sources("Island")
    )
    assert len(_triggers_named(scenario, ARCHFIEND)) == 1
    scenario.resolve_top()

    assert bears.counter_count("-1/-1") == 1
