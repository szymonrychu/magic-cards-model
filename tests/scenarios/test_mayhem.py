"""Mayhem: casting a discarded card from the graveyard (CR 702.187).

CR 702.187a: "Mayhem is a static ability that functions while the card with
mayhem is in a player's graveyard." CR 702.187b: "'Mayhem [cost]' means 'As
long as you discarded this card this turn, you may cast it from your
graveyard by paying [cost] rather than paying its mana cost.'"

Structurally flashback (CR 702.34a) - the graveyard zone permission and the
alternative cost are one clause - with the added "discarded this turn"
condition `test_madness.py` also exercises for a different keyword. Electro's
Bolt (`resolve_cards` confirmed: Sorcery, `{2}{R}`, "deals 4 damage to target
creature", `Mayhem {1}{R}`) is the regression fixture: its face cost `{2}{R}`
(mana value 3) is *dearer* than its mayhem cost `{1}{R}` (mana value 2), the
mirror image of Faithful Mending's flashback undercharge in `test_flashback.py`
- here an unclaimed zone permission would let the graveyard cast go through
for the wrong (higher) cost instead of a lower one, but the actual defect is
the same: CR 702.187a's graveyard permission does not exist apart from
mayhem's own cost, and `Casting.keyword_used` has to be set by
`use_keyword("Mayhem")`, not merely offered by `KeywordCastOption`'s
existence, before a graveyard cast may proceed at all (CR 601.2b, 118.9a).

Every CR number here was looked up with `knowledge_search(q="...",
type="rules")` in the session that wrote this file: CR 702.187a, CR 702.187b,
CR 601.2b, CR 118.9a, CR 601.6, CR 733.1.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import CardState
from tests.scenarios.harness import Scenario


def _discard_electros_bolt(scenario: Scenario) -> CardState:
    bolt = scenario.find("Electro's Bolt", Zone.HAND, "alice")
    mongrel = scenario.creature("Wild Mongrel")
    scenario.activate(mongrel, discarding=[bolt])
    # Mayhem's reminder: "Timing rules still apply." Electro's Bolt is a
    # sorcery (CR 307.1), so Wild Mongrel's ability resolves first.
    scenario.pass_until_resolved()
    return bolt


def board() -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Electro's Bolt"],
            battlefield=["Wild Mongrel", "Forest", "Mountain", "Mountain"],
        )
        .player("bob", battlefield=["Grizzly Bears"])
    )


def test_casting_from_the_graveyard_without_announcing_mayhem_is_refused():
    """The `test_flashback.py` live-game defect, generalized to mayhem: a
    graveyard cast with no `use_keyword("Mayhem")` call must be refused - the
    existence of the option is not CR 601.2b's announced choice. CR 601.6/
    CR 733.1's rewind leaves the card in the graveyard and the mana untapped.
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bolt = _discard_electros_bolt(scenario)
    assert bolt.zone is Zone.GRAVEYARD

    bears = scenario.creature("Grizzly Bears", "bob")
    sources = scenario.untapped_sources("Mountain", "Mountain", "Forest")
    casting = scenario.cast("Electro's Bolt", from_zone=Zone.GRAVEYARD, targets=[bears])
    scenario.pay_with(casting.begin_paying(), *sources)

    with pytest.raises(ValueError, match="Mayhem"):
        casting.cast()
    casting.cancel()

    assert scenario.find("Electro's Bolt", Zone.GRAVEYARD, "alice").zone is Zone.GRAVEYARD
    assert all(source.untapped for source in sources)


def test_announcing_mayhem_charges_the_mayhem_cost_not_the_face_cost():
    """The assertion that would have caught a mayhem-shaped version of the
    report: once Mayhem is announced, the cost is the printed `{1}{R}`, not
    the face cost `{2}{R}`."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _discard_electros_bolt(scenario)
    bears = scenario.creature("Grizzly Bears", "bob")

    casting = scenario.cast("Electro's Bolt", from_zone=Zone.GRAVEYARD)
    casting.use_keyword("Mayhem")
    casting.choose_targets([bears])

    assert str(casting.total_cost.mana) == "{1}{R}"
    sources = scenario.untapped_sources("Mountain", "Mountain")
    scenario.pay_with(casting.begin_paying(), *sources)
    bolt = scenario.put_on_stack(casting)

    assert bolt.zone is Zone.STACK


def test_mayhem_cannot_cast_a_card_not_discarded_this_turn():
    """CR 702.187b's own condition - "as long as you discarded this card this
    turn" - is not satisfied by a card that reached the graveyard some other
    way."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", graveyard=["Electro's Bolt"], battlefield=["Mountain", "Mountain"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    casting = scenario.cast("Electro's Bolt", from_zone=Zone.GRAVEYARD)

    with pytest.raises(ValueError, match="did not discard"):
        casting.use_keyword("Mayhem")
