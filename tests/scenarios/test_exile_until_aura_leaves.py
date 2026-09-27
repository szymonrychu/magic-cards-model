"""Scenario: an Aura's own "exile until this Aura leaves the battlefield"
(CR 610.2/610.3), reusing the exile-until-leaves machinery Henchbots and
Prayer of Binding already exercise (`test_exile_until_leaves_the_battlefield.
py`, `test_exile_until_leaves_battlefield_variable_counts.py`), now off an
Aura's own self-reference.

Dimensional Exile: "Enchant basic land you control / When this Aura enters,
exile target creature an opponent controls until this Aura leaves the
battlefield." Before this fix, `_EXILE_UNTIL_THIS_LEAVES_BATTLEFIELD_RE`'s
type alternation named every CR 205.2a card type an "until this `<type>`
leaves the battlefield" clause is printed against (permanent, enchantment,
artifact, creature, planeswalker) but not "aura" - a subtype, not a card
type, yet the self-reference every Aura printing this exact shape uses. The
clause read as unrecognised text - silent, per the sweep - even though
`_watch_for_departure_and_return_exiled_card` already covers every departure
route an *enchantment* can take, which an Aura is one of (CR 303.4).

Proof printing (Modern/Pioneer/Standard-legal, added with
`scripts/add_card.py`, not Dimensional Exile and not in any deck list):
**Hardlight Containment** - "Enchant artifact you control / When this Aura
enters, exile target creature an opponent controls until this Aura leaves
the battlefield. / Enchanted permanent has ward {1}." The identical ETB
clause, enchanting a different permanent type (an artifact rather than a
basic land) and with an unrelated granted-ward rider after it, proving the
widened type alternation reads any Aura's own self-reference rather than one
fitted to Dimensional Exile's exact printed sentence.

CR numbers verified with `mise run rules:find` in the session that wrote
this file: 303.4 (an Aura is an enchantment with the Aura subtype, and
CR 303.4b names what it is attached to as "enchanted"), 608.3c (a resolving
Aura spell attaches to what it targeted), 610.2/610.3/610.3c (the delayed
return, under the exiled card's owner's control by default), 700.4 (destroy
and sacrifice both move a permanent to its owner's graveyard - the same
`DIES` event either route raises), 111.8 (a token that already left the
battlefield is not returned).
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.support import card_support
from tests.cards import card

from .harness import Scenario

DIMENSIONAL_EXILE = "Dimensional Exile"
HARDLIGHT_CONTAINMENT = "Hardlight Containment"


def test_listed_and_proof_printings_are_handled():
    for name in (DIMENSIONAL_EXILE, HARDLIGHT_CONTAINMENT):
        bad = [
            c
            for c in card_support(card(name)).clauses
            if c.outcome not in ("handled", "static_unaudited")
        ]
        assert not bad, (name, bad)


def test_dimensional_exile_attaches_and_exiles_the_chosen_creature():
    scenario = (
        Scenario()
        .player("alice", hand=[DIMENSIONAL_EXILE], battlefield=["Plains"] * 2 + ["Forest"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    forest = scenario.find("Forest", Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    plains = scenario.untapped_sources("Plains", "Plains")
    scenario.choose_trigger_targets(DIMENSIONAL_EXILE, [bears])
    aura = scenario.cast_and_resolve(DIMENSIONAL_EXILE, *plains, targets=[forest])
    scenario.pass_until_resolved()  # the ETB trigger: exile Grizzly Bears

    assert aura.zone is Zone.BATTLEFIELD and aura.attached_to == forest.id
    assert bears.zone is Zone.EXILE


def test_destroying_the_aura_returns_the_exiled_creature_under_its_owner():
    scenario = (
        Scenario()
        .player("alice", hand=[DIMENSIONAL_EXILE], battlefield=["Plains"] * 2 + ["Forest"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    forest = scenario.find("Forest", Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    plains = scenario.untapped_sources("Plains", "Plains")
    scenario.choose_trigger_targets(DIMENSIONAL_EXILE, [bears])
    aura = scenario.cast_and_resolve(DIMENSIONAL_EXILE, *plains, targets=[forest])
    scenario.pass_until_resolved()

    scenario.game.destroy(aura)
    scenario.pass_until_resolved()  # the delayed trigger: return Grizzly Bears

    returned = scenario.creature("Grizzly Bears", "bob")
    assert returned.zone is Zone.BATTLEFIELD
    assert returned.controller == "bob", "CR 610.3c: under its owner's control"


def test_sacrificing_the_enchanted_land_takes_the_aura_with_it_and_returns_the_creature():
    """CR 704.5m: an Aura attached to nothing legal goes to the graveyard as
    a state-based action, one of the three departure routes."""
    scenario = (
        Scenario()
        .player("alice", hand=[DIMENSIONAL_EXILE], battlefield=["Plains"] * 2 + ["Forest"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    forest = scenario.find("Forest", Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    plains = scenario.untapped_sources("Plains", "Plains")
    scenario.choose_trigger_targets(DIMENSIONAL_EXILE, [bears])
    scenario.cast_and_resolve(DIMENSIONAL_EXILE, *plains, targets=[forest])
    scenario.pass_until_resolved()

    scenario.game.sacrifice(forest)
    fallen = scenario.state_based_actions()  # CR 704.5m: the Aura falls off
    assert any(state.name == DIMENSIONAL_EXILE for state in fallen)
    scenario.pass_until_resolved()  # the delayed trigger: return Grizzly Bears

    assert scenario.creature("Grizzly Bears", "bob").zone is Zone.BATTLEFIELD


def test_a_creature_that_left_exile_before_the_aura_does_is_not_returned():
    """CR 603.7c: the delayed ability no longer finds its object in exile."""
    scenario = (
        Scenario()
        .player("alice", hand=[DIMENSIONAL_EXILE], battlefield=["Plains"] * 2 + ["Forest"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    forest = scenario.find("Forest", Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    plains = scenario.untapped_sources("Plains", "Plains")
    scenario.choose_trigger_targets(DIMENSIONAL_EXILE, [bears])
    aura = scenario.cast_and_resolve(DIMENSIONAL_EXILE, *plains, targets=[forest])
    scenario.pass_until_resolved()

    exiled = scenario.find("Grizzly Bears", Zone.EXILE)
    scenario.game.put_into_graveyard(exiled)
    scenario.game.destroy(aura)
    scenario.pass_until_resolved()

    assert not [c for c in scenario.game.battlefield if c.name == "Grizzly Bears"]


# -- proof printing: Hardlight Containment enchants an artifact instead -----


def test_hardlight_containment_exiles_until_it_leaves_an_enchanted_artifact():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[HARDLIGHT_CONTAINMENT],
            battlefield=["Plains"] * 2 + ["Mind Stone"],
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    stone = scenario.find("Mind Stone", Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    (plains,) = scenario.untapped_sources("Plains")
    scenario.choose_trigger_targets(HARDLIGHT_CONTAINMENT, [bears])
    aura = scenario.cast_and_resolve(HARDLIGHT_CONTAINMENT, plains, targets=[stone])
    scenario.pass_until_resolved()

    assert aura.attached_to == stone.id
    assert bears.zone is Zone.EXILE

    scenario.game.destroy(aura)
    scenario.pass_until_resolved()

    returned = scenario.creature("Grizzly Bears", "bob")
    assert returned.zone is Zone.BATTLEFIELD and returned.controller == "bob"
