"""Improvise: tapping artifacts instead of spending mana (CR 702.126).

CR 702.126a: "Improvise is a static ability that functions while the spell with
improvise is on the stack. 'Improvise' means 'For each generic mana in this
spell's total cost, you may tap an untapped artifact you control rather than
pay that mana.'" Kappa Cannoneer prints the same thing as reminder text: "Your
artifacts can help cast this spell. Each artifact you tap after you're done
activating mana abilities pays for {1}."

Two corners shape the implementation, and both have their own test below:

- **CR 702.126a is generic-only.** There is no "of that color" half the way
  convoke has one (CR 702.51a), so an artifact never pays Metallic Rebuke's
  `{U}` - not even a blue artifact creature.
- **CR 702.126b**: improvise "isn't an additional or alternative cost and
  applies only after the total cost of the spell with improvise is
  determined". So it is not a cost reduction: Kappa Cannoneer still costs
  `{5}{U}` while five artifacts pay five of its symbols, which is what anything
  reading the spell's cost - a Chalice, a copy effect - has to see.

The board is the pinnacle-affinity list's own artifacts (see
`tests/scenarios/test_pinnacle_affinity_deck.py` for the registered decklist),
because improvise is that archetype's engine.

Every CR number here was looked up with `knowledge_search(type="rules")` in the
session that wrote this file.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.objects_as_costs import (
    has_improvise,
    improvise,
    improvise_payment,
)
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Color
from tests.cards import card
from tests.scenarios.harness import Scenario

#: Five artifacts off the registered affinity list, none of which taps for mana
#: or wants to be tapped for anything else.
ARTIFACTS = [
    "Mishra's Bauble",
    "Tormod's Crypt",
    "Claws of Gix",
    "Pithing Needle",
    "Welding Jar",
]


def board(artifacts: int = 5, islands: int = 1, hand: list[str] | None = None) -> Scenario:
    """Kappa Cannoneer is `{5}{U}`: five generic symbols improvise can cover,
    and one `{U}` it cannot."""
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=hand or ["Kappa Cannoneer"],
            battlefield=ARTIFACTS[:artifacts] + ["Island"] * islands,
        )
        .player("bob", battlefield=["Grizzly Bears"])
    )


def artifacts_of(scenario, count: int = 5):
    return scenario.creatures(*ARTIFACTS[:count], username="alice")


# -- reading the keyword off the card -------------------------------------


def test_the_printed_cards_carry_improvise():
    """No mocks: the keyword is read off the real Scryfall printings."""
    for name in ("Kappa Cannoneer", "Metallic Rebuke", "Whir of Invention"):
        printing = card(name)
        assert "Improvise" in (printing.oracle_text or "")
        assert has_improvise(printing)
        assert improvise_payment(printing) is not None


def test_a_card_without_the_keyword_offers_nothing():
    """CR 702.126a functions only "while the spell **with improvise**" is on
    the stack, so a card without it makes no offer at all."""
    assert not has_improvise(card("Lightning Bolt"))
    assert improvise_payment(card("Lightning Bolt")) is None


def test_the_offer_is_untapped_artifacts_you_control():
    """The whole of CR 702.126a's eligibility, read back off the offer."""
    offer = improvise_payment(card("Kappa Cannoneer"))

    assert offer is not None
    assert offer.rule == "CR 702.126a"
    assert offer.zone is Zone.BATTLEFIELD
    assert offer.untapped_only and offer.yours_only
    assert offer.pays_generic and not offer.pays_own_colors
    assert offer.noun == "an artifact"


# -- paying with it -------------------------------------------------------


def test_five_artifacts_and_one_island_cast_kappa_cannoneer():
    """The archetype's whole clock: `{5}{U}` for one blue mana."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    junk = artifacts_of(scenario)

    casting = scenario.cast("Kappa Cannoneer")
    payment = casting.begin_paying()
    improvise(payment, casting.spell, *junk)

    assert str(payment.mana_owed) == "{U}"
    scenario.pay_with(payment, *scenario.untapped_sources("Island"))
    spell = scenario.put_on_stack(casting)

    assert spell.zone is Zone.STACK
    assert all(artifact.tapped for artifact in junk)


def test_the_pool_is_untouched_beyond_the_coloured_symbol():
    """CR 702.126a says "rather than pay that mana": a tapped artifact adds
    nothing to the pool, so the one Island's `{U}` is spent exactly and nothing
    floats afterwards."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    junk = artifacts_of(scenario)

    casting = scenario.cast("Kappa Cannoneer")
    payment = casting.begin_paying()
    improvise(payment, casting.spell, *junk)
    scenario.pay_with(payment, *scenario.untapped_sources("Island"))

    assert payment.pool.total == 0
    assert scenario.player("alice").mana_pool.total == 0


def test_improvise_is_not_a_cost_reduction():
    """CR 702.126b: the total cost is still `{5}{U}` - improvise only changes
    what pays two of its symbols."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    junk = artifacts_of(scenario)

    casting = scenario.cast("Kappa Cannoneer")
    payment = casting.begin_paying()
    improvise(payment, casting.spell, junk[0], junk[1])

    assert str(payment.cost) == "{5}{U}"
    assert str(payment.mana_owed) == "{3}{U}"


def test_a_partial_board_improvises_only_as_far_as_it_goes():
    """Two artifacts take `{5}{U}` to `{3}{U}`, and no further."""
    scenario = board(artifacts=2).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    junk = artifacts_of(scenario, 2)

    casting = scenario.cast("Kappa Cannoneer")
    payment = casting.begin_paying()
    improvise(payment, casting.spell, *junk)

    assert str(payment.mana_owed) == "{3}{U}"


def test_an_empty_board_improvises_for_nothing():
    """With no artifacts the spell simply costs `{5}{U}` and one Island cannot
    pay it."""
    scenario = board(artifacts=0).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Kappa Cannoneer")
    payment = casting.begin_paying()
    improvise(payment, casting.spell)  # nothing to tap

    assert str(payment.mana_owed) == "{5}{U}"
    with pytest.raises(ValueError, match="cannot pay"):
        scenario.pay_with(payment, *scenario.untapped_sources("Island"))


# -- what improvise may not do --------------------------------------------


def test_improvise_cannot_be_offered_against_a_coloured_symbol():
    """CR 702.126a is generic-only: unlike convoke (CR 702.51a) it has no
    "of that color" half, so the offer refuses a coloured symbol outright
    rather than turning it down on the arithmetic."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    junk = artifacts_of(scenario)
    offer = improvise_payment(card("Kappa Cannoneer"))
    assert offer is not None

    with pytest.raises(ValueError, match="does not pay coloured mana"):
        offer.option_for(junk[0], Color.BLUE)


def test_a_blue_artifact_creature_pays_generic_and_never_the_blue_symbol():
    """A Kappa Cannoneer already on the battlefield is a *blue* artifact
    creature. It improvises - it is an artifact - but CR 702.126a still does
    not let it pay another one's `{U}`, whatever its colour."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Kappa Cannoneer"], battlefield=["Kappa Cannoneer", "Island"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    turtle = scenario.creature("Kappa Cannoneer", "alice")
    assert Color.BLUE in turtle.colors
    offer = improvise_payment(card("Kappa Cannoneer"))
    assert offer is not None

    with pytest.raises(ValueError, match="does not pay coloured mana"):
        offer.option_for(turtle, Color.BLUE)

    casting = scenario.cast("Kappa Cannoneer")
    payment = casting.begin_paying()
    improvise(payment, casting.spell, turtle)

    assert str(payment.mana_owed) == "{4}{U}"


def test_a_nonartifact_creature_cannot_improvise():
    """CR 702.126a taps "an untapped **artifact** you control" - the one place
    it is narrower than waterbend (CR 701.67a, "artifact or creature")."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Kappa Cannoneer"], battlefield=["Grizzly Bears", "Island"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bear = scenario.creature("Grizzly Bears", "alice")

    casting = scenario.cast("Kappa Cannoneer")
    payment = casting.begin_paying()

    with pytest.raises(ValueError, match="not an artifact"):
        improvise(payment, casting.spell, bear)

    assert str(payment.mana_owed) == "{5}{U}"
    assert not bear.tapped


def test_a_land_cannot_improvise():
    """An Island is not an artifact, however much the deck would like it."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    island = scenario.find("Island", Zone.BATTLEFIELD, "alice")

    casting = scenario.cast("Kappa Cannoneer")
    payment = casting.begin_paying()

    with pytest.raises(ValueError, match="not an artifact"):
        improvise(payment, casting.spell, island)


def test_an_already_tapped_artifact_cannot_improvise():
    """ "you may tap an **untapped** artifact" (CR 702.126a): one already tapped
    for mana, or for anything else, has nothing left to give."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    junk = artifacts_of(scenario)
    junk[0].tap()

    casting = scenario.cast("Kappa Cannoneer")
    payment = casting.begin_paying()

    with pytest.raises(ValueError, match="already tapped"):
        improvise(payment, casting.spell, junk[0])


def test_an_opponents_artifact_cannot_improvise():
    """CR 702.126a: "an untapped artifact **you control**"."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Kappa Cannoneer"], battlefield=["Island"])
        .player("bob", battlefield=["Welding Jar"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    theirs = scenario.creature("Welding Jar", "bob")

    casting = scenario.cast("Kappa Cannoneer")
    payment = casting.begin_paying()

    with pytest.raises(ValueError, match="does not control"):
        improvise(payment, casting.spell, theirs)

    assert not theirs.tapped


def test_an_artifact_in_hand_cannot_improvise():
    """The offer names the battlefield; an artifact still in hand is not an
    untapped permanent."""
    scenario = board(hand=["Kappa Cannoneer", "Mox Opal"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    in_hand = scenario.find("Mox Opal", Zone.HAND, "alice")

    casting = scenario.cast("Kappa Cannoneer")
    payment = casting.begin_paying()

    with pytest.raises(ValueError, match="improvise spends objects in the battlefield"):
        improvise(payment, casting.spell, in_hand)


def test_the_same_artifact_cannot_improvise_twice():
    """One artifact, one generic symbol: it is tapped after the first."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    junk = artifacts_of(scenario)

    casting = scenario.cast("Kappa Cannoneer")
    payment = casting.begin_paying()
    improvise(payment, casting.spell, junk[0])

    with pytest.raises(ValueError, match="already paying"):
        improvise(payment, casting.spell, junk[0])


def test_more_artifacts_than_the_cost_has_generic_mana_is_refused():
    """CR 702.126a bounds itself to "each generic mana **in this spell's total
    cost**". Whir of Invention is `{X}{U}{U}{U}` with X=0: three coloured
    symbols and nothing improvise may touch."""
    scenario = board(hand=["Whir of Invention"], islands=3).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    junk = artifacts_of(scenario)

    casting = scenario.cast("Whir of Invention")
    payment = casting.begin_paying()

    with pytest.raises(ValueError, match="has no"):
        improvise(payment, casting.spell, junk[0])

    assert not junk[0].tapped


def test_a_spell_without_improvise_refuses_the_offer():
    """CR 702.126a functions "while the spell **with improvise**" is on the
    stack, and Lightning Bolt has no such ability."""
    scenario = board(hand=["Lightning Bolt"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    junk = artifacts_of(scenario)

    casting = scenario.cast("Lightning Bolt", targets=["bob"])
    payment = casting.begin_paying()

    with pytest.raises(ValueError, match="does not have improvise"):
        improvise(payment, casting.spell, junk[0])


# -- when the tapping happens ---------------------------------------------


def test_nothing_is_tapped_until_the_cost_is_paid():
    """CR 601.2h pays the total cost; CR 702.126a's tapping is part of paying
    it, not part of announcing. A payment left open has tapped nothing."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    junk = artifacts_of(scenario)

    casting = scenario.cast("Kappa Cannoneer")
    payment = casting.begin_paying()
    improvise(payment, casting.spell, *junk)

    assert not any(artifact.tapped for artifact in junk)


def test_cancelling_the_cast_untaps_the_improvised_artifacts():
    """CR 733.1: "the entire action is reversed and any payments already made
    are canceled"."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    junk = artifacts_of(scenario)

    casting = scenario.cast("Kappa Cannoneer")
    payment = casting.begin_paying()
    improvise(payment, casting.spell, *junk)
    scenario.pay_with(payment, *scenario.untapped_sources("Island"))
    assert all(artifact.tapped for artifact in junk)

    casting.cancel()

    assert not any(artifact.tapped for artifact in junk)
    assert scenario.find("Kappa Cannoneer", Zone.HAND, "alice") is casting.spell


def test_a_summoning_sick_artifact_creature_still_improvises():
    """Improvise taps the artifact as a cost; it is not the `{T}` symbol, and
    CR 302.6 only stops a creature "activating an ability with the tap symbol
    in its cost". An artifact creature that entered this turn improvises."""
    scenario = board(artifacts=4, hand=["Kappa Cannoneer", "Ornithopter"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    fresh = scenario.put_onto_battlefield("Ornithopter", "alice")
    assert fresh.summoning_sick

    casting = scenario.cast("Kappa Cannoneer")
    payment = casting.begin_paying()
    improvise(payment, casting.spell, fresh, *artifacts_of(scenario, 4))

    assert str(payment.mana_owed) == "{U}"
    scenario.pay_with(payment, *scenario.untapped_sources("Island"))

    assert fresh.tapped


# -- driven through Game.cast, the seat-facing atomic entry point ---------
#
# Everything above drives `objects_as_costs.improvise` directly against a
# hand-opened `CostPayment`, the same low-level API `Casting`/`CostPayment`
# always exposed. A seat never calls that: it calls `Game.cast(...)`
# (`models/game.py`), the one atomic entry point `magic_cards_model_api`
# drives, and that method only ever knew about convoke and delve - it had no
# `improvise` parameter and `Game.object_cost_offers` never named improvise as
# a candidate offer either, so a seat with a settled affinity board (a land
# plus five untapped artifacts, exactly enough to improvise Kappa Cannoneer's
# `{5}{U}`) was refused with "no combination of the available mana sources can
# pay {5}{U}" - the improvise machinery below existed and was fully tested,
# but nothing on the seat-facing path ever reached it.


def test_game_cast_kappa_cannoneer_with_a_land_and_five_artifacts():
    """The reported repro: one Island for `{U}`, Mox Opal tapped for one
    generic mana ability, and four more artifacts improvised for the
    remaining four generic - `{5}{U}` exactly, from a land plus five untapped
    artifacts (Mox Opal among them) and nothing else."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Kappa Cannoneer"],
            battlefield=["Island", "Mox Opal", *ARTIFACTS[:4]],
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    cannoneer = scenario.find("Kappa Cannoneer", Zone.HAND, "alice")
    (island,) = scenario.untapped_sources("Island")
    (mox_opal,) = scenario.creatures("Mox Opal")
    junk = artifacts_of(scenario, 4)

    spell = scenario.game.cast(cannoneer, "alice", mana_sources=[island, mox_opal], improvise=junk)

    assert spell.zone is Zone.STACK
    assert island.tapped
    assert mox_opal.tapped
    assert all(artifact.tapped for artifact in junk)
    assert scenario.player("alice").mana_pool.total == 0
    scenario.game.assert_quiescent()


def test_game_cast_reports_improvise_could_have_paid_it():
    """The other half of the seat's report: with no `improvise=` named at all,
    the plain dry run - `legal_actions`' own affordability check - refused
    the same board outright instead of naming improvise as the honest
    `UNKNOWN` it names for convoke and delve (`test_legal_actions.py::
    test_improvise_widens_a_no_into_an_honest_unknown` covers this in full;
    this is the same fact from inside this file, on the exact reported
    board)."""
    from magic_cards_model.machines.legal_actions import legal_actions  # noqa: PLC0415
    from magic_cards_model.models.action import ActionKind, Affordability  # noqa: PLC0415

    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Kappa Cannoneer"],
            battlefield=["Island", "Mox Opal", *ARTIFACTS[:4]],
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    (cast,) = [
        action for action in legal_actions(scenario.game, "alice") if action.kind is ActionKind.CAST
    ]
    assert cast.affordable is Affordability.UNKNOWN
    assert "improvise" in (cast.unaffordable_reason or "")


def test_game_cast_refuses_with_too_few_artifacts_and_leaves_no_trace():
    """Two artifacts only reduce `{5}{U}` to `{3}{U}`; one Island cannot cover
    the rest, and `Game.cast` refuses in its own words (CR 733.1: nothing
    tapped, the card stays in hand)."""
    scenario = board(artifacts=2).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    cannoneer = scenario.find("Kappa Cannoneer", Zone.HAND, "alice")
    (island,) = scenario.untapped_sources("Island")
    junk = artifacts_of(scenario, 2)

    with pytest.raises(ValueError, match="no combination of the available mana sources can pay"):
        scenario.game.cast(cannoneer, "alice", mana_sources=[island], improvise=junk)

    assert cannoneer.zone is Zone.HAND
    assert island.untapped
    assert all(artifact.untapped for artifact in junk)
    scenario.game.assert_quiescent()


def test_game_cast_refuses_an_already_tapped_artifact():
    """One of the five is already tapped when the seat tries to improvise it -
    `Game.cast` surfaces `objects_as_costs.improvise`'s own refusal rather
    than silently skipping it, and leaves the game untouched."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    cannoneer = scenario.find("Kappa Cannoneer", Zone.HAND, "alice")
    (island,) = scenario.untapped_sources("Island")
    junk = artifacts_of(scenario)
    junk[0].tap()

    with pytest.raises(ValueError, match="already tapped"):
        scenario.game.cast(cannoneer, "alice", mana_sources=[island], improvise=junk)

    assert cannoneer.zone is Zone.HAND
    assert island.untapped
    scenario.game.assert_quiescent()
