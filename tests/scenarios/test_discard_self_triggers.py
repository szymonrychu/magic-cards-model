""" "When you discard this card, ..." on a card that is not a permanent -
Edgar's Awakening, a sorcery whose second paragraph is its own triggered
ability rather than part of its resolution.

CR 701.9a: "To discard a card, move it from its owner's hand to that
player's graveyard."

CR 113.6: "Abilities of an instant or sorcery spell usually function only
while that object is on the stack." CR 113.6k is the exception that applies:
"A trigger condition that can't trigger from the battlefield functions in all
zones it can trigger from." A discard can never happen on the stack or the
battlefield, so the ability works from the graveyard the discard puts the
card in - and it is never part of the sorcery's own resolution.

CR 603.12: "A resolving spell or ability may allow or instruct a player to
take an action and create a triggered ability that triggers "when [a player]
[does or doesn't]" take that action" - Edgar's "you may pay {B}. When you do,
return target creature card ..." is that reflexive shape: the target is
chosen only once the payment has been made.

Before this, the trigger paragraph poisoned the sorcery's own text (the
whole "[spell]" clause read silent, so casting Edgar's Awakening did
nothing), and the sweep never judged the trigger at all because it only
reads triggered abilities of permanents.

Bartered Cow is the proof printing: Modern/Pioneer-legal, in no api deck,
and it prints the same "when you discard this card" condition as the second
half of a CR 603.1b compound on a creature.

Every CR number here was looked up with `mise run rules:find` in the session
that wrote it.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.support import classify_clauses
from tests.cards import card
from tests.scenarios.harness import Scenario

EDGAR = "Edgar's Awakening"
COW = "Bartered Cow"


def test_edgars_awakening_cast_returns_a_creature_card_to_the_battlefield() -> None:
    """The sorcery's own resolution: "Return target creature card from your
    graveyard to the battlefield." - read without the trigger paragraph."""
    scenario = (
        Scenario()
        .player("alice", hand=[EDGAR], graveyard=["Grizzly Bears"], battlefield=["Swamp"] * 5)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")

    awakening = scenario.cast_and_resolve(
        EDGAR, *scenario.untapped_sources(*["Swamp"] * 5), targets=[bears]
    )

    assert bears.zone is Zone.BATTLEFIELD
    assert awakening.zone is Zone.GRAVEYARD
    # Resolving as a sorcery is not discarding it: nothing triggered.
    assert scenario.stack_names() == []


def test_discarding_edgars_awakening_and_paying_returns_a_creature_card_to_hand() -> None:
    """The discard trigger, paid: {B} leaves the pool and the reflexive
    trigger (CR 603.12) returns the targeted creature card to the hand."""
    scenario = (
        Scenario()
        .player("alice", hand=[EDGAR], graveyard=["Grizzly Bears"], battlefield=["Swamp"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    awakening = scenario.find(EDGAR, Zone.HAND, "alice")
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")
    (swamp,) = scenario.untapped_sources("Swamp")
    scenario.will_pay_the_mana_cost(True, source=EDGAR)
    scenario.will_choose_targets(bears, source=EDGAR)

    scenario.game.discard_cards("alice", [awakening])
    scenario.game.put_triggers_on_stack()
    assert awakening.zone is Zone.GRAVEYARD
    assert scenario.stack_names() == [f"{EDGAR}'s triggered ability"]

    while scenario.game.stack:
        scenario.pass_until_resolved()

    assert swamp.tapped
    assert bears.zone is Zone.HAND


def test_declining_to_pay_returns_nothing() -> None:
    """ "you may pay {B}" - declined, the reflexive trigger never exists
    (CR 603.12: it triggers only on the action having been taken)."""
    scenario = (
        Scenario()
        .player("alice", hand=[EDGAR], graveyard=["Grizzly Bears"], battlefield=["Swamp"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    awakening = scenario.find(EDGAR, Zone.HAND, "alice")
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")
    (swamp,) = scenario.untapped_sources("Swamp")
    scenario.will_pay_the_mana_cost(False, source=EDGAR)

    scenario.game.discard_cards("alice", [awakening])
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.pass_until_resolved()

    assert not swamp.tapped
    assert bears.zone is Zone.GRAVEYARD


def test_discarding_it_to_pay_a_spells_cost_triggers_it() -> None:
    """A discard paid as a cost (Cathartic Reunion's "As an additional cost
    to cast this spell, discard two cards") is still a discard (CR 701.9a),
    and the trigger goes on the stack above the spell whose cost it paid."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Cathartic Reunion", EDGAR, "Lightning Bolt"],
            library=["Island", "Island", "Island"],
            graveyard=["Grizzly Bears"],
            battlefield=["Mountain", "Mountain"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    awakening = scenario.find(EDGAR, Zone.HAND, "alice")
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "alice")

    scenario.cast_onto_stack(
        "Cathartic Reunion",
        *scenario.untapped_sources("Mountain", "Mountain"),
        discarding=[awakening, bolt],
    )

    assert awakening.zone is Zone.GRAVEYARD
    assert scenario.stack_names() == ["Cathartic Reunion", f"{EDGAR}'s triggered ability"]


def test_an_opponents_discard_effect_still_triggers_it_for_its_owner() -> None:
    """Mind Rot is Bob's spell, but the discarding player is Alice, and CR
    701.9a's discard is hers - so "you discard" holds and the trigger is
    hers to control."""
    scenario = (
        Scenario()
        # Bob first: his turn, so his sorcery can be cast.
        .player("bob", hand=["Mind Rot"], battlefield=["Swamp", "Swamp", "Swamp"])
        .player("alice", hand=[EDGAR, "Lightning Bolt"], graveyard=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    awakening = scenario.find(EDGAR, Zone.HAND, "alice")
    scenario.will_pay_the_mana_cost(False, source=EDGAR)

    scenario.cast_and_resolve(
        "Mind Rot",
        *scenario.untapped_sources("Swamp", "Swamp", "Swamp", username="bob"),
        username="bob",
        targets=["alice"],
    )
    scenario.game.put_triggers_on_stack()

    assert awakening.zone is Zone.GRAVEYARD
    assert scenario.stack_names() == [f"{EDGAR}'s triggered ability"]
    assert scenario.game.stack[-1].controller == "alice"


def test_a_different_card_discarded_does_not_trigger_it() -> None:
    """ "this card" - Edgar's Awakening already sitting in the graveyard does
    not hear another card being discarded."""
    scenario = (
        Scenario()
        .player("alice", hand=["Lightning Bolt"], graveyard=[EDGAR, "Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "alice")

    scenario.game.discard_cards("alice", [bolt])
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == []


def test_bartered_cow_makes_a_food_when_discarded() -> None:
    """Proof printing: the discard half of Bartered Cow's CR 603.1b compound
    "When this creature dies and when you discard this card"."""
    scenario = Scenario().player("alice", hand=[COW]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    cow = scenario.find(COW, Zone.HAND, "alice")

    scenario.game.discard_cards("alice", [cow])
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == [f"{COW}'s triggered ability"]
    scenario.pass_until_resolved()

    foods = [p for p in scenario.game.permanents_controlled_by("alice") if "Food" in p.subtypes]
    assert len(foods) == 1


def test_bartered_cow_makes_a_food_when_it_dies_too() -> None:
    """The other half of the compound still works from the battlefield."""
    scenario = Scenario().player("alice", battlefield=[COW]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    cow = scenario.creature(COW, "alice")

    scenario.game.destroy(cow)
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == [f"{COW}'s triggered ability"]
    scenario.pass_until_resolved()

    foods = [p for p in scenario.game.permanents_controlled_by("alice") if "Food" in p.subtypes]
    assert len(foods) == 1


def test_the_sweep_judges_the_sorcery_and_its_discard_trigger_separately() -> None:
    """`support.classify_clauses`: Edgar's Awakening has two clauses - the
    sorcery's own resolution and the discard trigger - and both are read."""
    outcomes = classify_clauses(card(EDGAR))
    assert sorted(outcome.source for outcome in outcomes) == ["spell", "triggered"]
    assert {outcome.category for outcome in outcomes} == {"handled"}, outcomes
    assert {outcome.category for outcome in classify_clauses(card(COW))} == {"handled"}
