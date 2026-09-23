"""Waterbend: tapping artifacts *or creatures* instead of spending mana.

CR 701.67a: "'Waterbend [cost]' means 'Pay [cost]. For each generic mana in
that cost, you may tap an untapped artifact or creature you control rather than
pay that mana.'"

It is improvise (CR 702.126a) one step wider - the same "for each generic mana
... you may tap an untapped X you control rather than pay that mana", with
creatures allowed alongside artifacts - and it is built out of the same
`ObjectOffer` in `machines/objects_as_costs.py`.

The one thing waterbend does *not* share with the rest of the family: it is an
action word introducing an **ability's** cost ("Waterbend {3}: ..."), not a
static ability of a spell on the stack. Most of the tests below open the
payment for that cost directly rather than through a `Casting`, the way every
other corner of this keyword's own arithmetic is checked; turning the printed
phrase "Waterbend {3}" into a cost is `total_cost_for_phrase` in
`machines/cost.py`, and `Game.activation_cost`'s own fold-in of it is what
`tests/scenarios/judge/test_judge_costs.py`'s DDR#991 case (no longer `xfail`)
covers - the end-to-end tests near the bottom of this file drive that same
branch through a real activation, on Geyser Leaper's own printed ability.

CR 701.67b: when a waterbend cost is only part of a larger total cost, the
tap method may cover only the waterbend's own generic, "even if the total
cost ... includes other generic mana components" - `CostPayment.
waterbend_generic` is that bound, and `test_the_taps_are_refused_for_generic_
mana_outside_the_waterbend_cost` below is the corner CR 701.67a's own bound
(tested above it) does not by itself catch.

CR 701.67c: "An ability that triggers whenever a player waterbends triggers
whenever that player pays a waterbend cost, regardless of how they paid that
cost." `ExtraTriggerEvent.WATERBENDS` (`machines/triggers.py`) is that event,
emitted once per waterbend cost actually paid by `Game.activate_ability`, and
proved here on Avatar Aang - a real printing whose own "Whenever you
waterbend, earthbend, firebend, or airbend, draw a card" is legal in every
supported format and carries no card in this pool's deck lists.

Every CR number here was looked up with `mise run rules:find` in the session
that wrote this file.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.cost import CostPayment, TotalCost
from magic_cards_model.machines.objects_as_costs import waterbend, waterbend_offer
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def board() -> Scenario:
    """Flexible Waterbender prints `Waterbend {3}` - three generic symbols, and
    a board with one creature, one artifact, one land to cover them."""
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=["Flexible Waterbender", "Grizzly Bears", "Welding Jar", "Island"],
        )
        .player("bob", battlefield=["Grizzly Bears"])
    )


def open_payment(
    scenario, cost: str = "{3}", *, waterbend_generic: int | None = None
) -> CostPayment:
    """The payment for a waterbend cost, opened on a real board state.

    `waterbend_generic` mirrors `TotalCost.waterbend_generic` (CR 701.67b) -
    left `None` for every ordinary case here, where the whole of `cost`'s
    generic *is* the waterbend's own, and set only by the one test that
    builds a total cost with other generic mana alongside it.
    """
    return CostPayment.for_total(
        TotalCost.of(cost, waterbend_generic=waterbend_generic), game=scenario.game, payer="alice"
    )


def test_the_offer_is_untapped_artifacts_or_creatures_you_control():
    """CR 701.67a's eligibility, read back off the offer."""
    offer = waterbend_offer()

    assert offer.rule == "CR 701.67a"
    assert offer.zone is Zone.BATTLEFIELD
    assert offer.untapped_only and offer.yours_only
    assert offer.pays_generic and not offer.pays_own_colors
    assert offer.noun == "an artifact or creature"


def test_a_creature_and_an_artifact_each_pay_one_generic():
    """The half that separates waterbend from improvise: a Grizzly Bears is not
    an artifact, and CR 701.67a takes it anyway."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bear = scenario.creature("Grizzly Bears", "alice")
    jar = scenario.creature("Welding Jar", "alice")

    payment = open_payment(scenario)
    waterbend(payment, bear, jar)

    assert str(payment.cost) == "{3}"
    assert str(payment.mana_owed) == "{1}"

    scenario.pay_with(payment, *scenario.untapped_sources("Island"))

    assert bear.tapped and jar.tapped


def test_nothing_is_tapped_until_the_cost_is_paid():
    """CR 601.2h again: the tapping is part of paying, not of announcing."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bear = scenario.creature("Grizzly Bears", "alice")

    payment = open_payment(scenario)
    waterbend(payment, bear)

    assert not bear.tapped
    payment.cancel()
    assert not bear.tapped


def test_a_land_cannot_be_waterbent():
    """CR 701.67a names artifacts and creatures, and an Island is neither."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    island = scenario.find("Island", Zone.BATTLEFIELD, "alice")

    payment = open_payment(scenario)

    with pytest.raises(ValueError, match="not an artifact or creature"):
        waterbend(payment, island)


def test_an_opponents_creature_cannot_be_waterbent():
    """CR 701.67a: "an untapped artifact or creature **you control**"."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    theirs = scenario.creature("Grizzly Bears", "bob")

    payment = open_payment(scenario)

    with pytest.raises(ValueError, match="does not control"):
        waterbend(payment, theirs)


def test_an_already_tapped_permanent_cannot_be_waterbent():
    """ "you may tap an **untapped** artifact or creature" (CR 701.67a)."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bear = scenario.creature("Grizzly Bears", "alice")
    bear.tap()

    payment = open_payment(scenario)

    with pytest.raises(ValueError, match="already tapped"):
        waterbend(payment, bear)


def test_more_permanents_than_the_cost_has_generic_mana_is_refused():
    """CR 701.67a bounds itself to "each generic mana **in that cost**"."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bender = scenario.creature("Flexible Waterbender", "alice")
    bear = scenario.creature("Grizzly Bears", "alice")
    jar = scenario.creature("Welding Jar", "alice")

    payment = open_payment(scenario, "{2}")
    waterbend(payment, bear, jar)

    with pytest.raises(ValueError, match="has no"):
        waterbend(payment, bender)

    assert not bender.tapped


def test_the_taps_are_refused_for_generic_mana_outside_the_waterbend_cost():
    """CR 701.67b: "If a waterbend cost is part of the total cost to cast a
    spell or activate an ability ..., the alternate method to pay for mana
    ... may be used only to pay for the amount of generic mana in the
    waterbend cost, even if the total cost ... includes other generic mana
    components." A total cost of {1}{3} where only the {3} is the
    waterbend's own (`waterbend_generic=3`, the way `Game.activation_cost`
    would set it for a cost like "Waterbend {3}, {1}" - not printed on any
    card yet, but CR 701.67b's own text anticipates the shape): tapping
    three permanents pays the waterbend's own share; a fourth tap, offered
    against the plain {1}, is refused even though `payment.mana_owed`
    (CR 701.67a's own bound, the one `test_more_permanents_than_the_cost_
    has_generic_mana_is_refused` above checks) still has a generic symbol
    open."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=[
                "Flexible Waterbender",
                "Grizzly Bears",
                "Welding Jar",
                "Llanowar Elves",
                "Island",
            ],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bender = scenario.creature("Flexible Waterbender", "alice")
    bear = scenario.creature("Grizzly Bears", "alice")
    jar = scenario.creature("Welding Jar", "alice")
    elves = scenario.creature("Llanowar Elves", "alice")

    payment = open_payment(scenario, "{1}{3}", waterbend_generic=3)
    waterbend(payment, bear, jar, bender)  # the waterbend's own {3}, in full

    with pytest.raises(ValueError, match="701.67b"):
        waterbend(payment, elves)

    assert not elves.tapped
    # The plain {1} still has to be paid with real mana - the waterbend
    # taps never reached it, and nothing about the refusal undid the three
    # taps that were legal.
    scenario.pay_with(payment, *scenario.untapped_sources("Island"))
    assert bear.tapped and jar.tapped and bender.tapped and payment.step.value == "paid"


# -- Geyser Leaper's own printed ability, end to end (CR 701.67a, 701.67c) --


def _geyser_leaper_board(*, aang: bool = False) -> Scenario:
    battlefield = ["Geyser Leaper", "Grizzly Bears", "Welding Jar", "Island", "Island"]
    if aang:
        battlefield = ["Avatar Aang", *battlefield]
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            library=["Forest", "Plains", "Swamp"],
            hand=["Llanowar Elves"],
            battlefield=battlefield,
        )
        .player("bob")
    )


def test_geyser_leaper_activated_end_to_end_tapping_its_own_source():
    """ "Waterbend {4}: Draw a card, then discard a card." - three of the
    four generic paid by tapping (a creature, an artifact, and the ability's
    own source - CR 701.67a says "an untapped artifact or creature you
    control" with no "other" the way crew's own "other untapped creatures"
    narrows itself, so Geyser Leaper may pay its own cost), the fourth with
    real mana from an Island."""
    scenario = _geyser_leaper_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    leaper = scenario.creature("Geyser Leaper", "alice")
    bear = scenario.creature("Grizzly Bears", "alice")
    jar = scenario.creature("Welding Jar", "alice")
    (elves,) = [
        state for state in scenario.player("alice").hand if state.card.name == "Llanowar Elves"
    ]
    scenario.will_discard(elves)
    assert not leaper.tapped

    (island,) = scenario.untapped_sources("Island", username="alice")
    scenario.activate(leaper, island, tapping=[leaper, bear, jar])
    scenario.resolve_top()

    assert leaper.tapped and bear.tapped and jar.tapped and island.tapped
    alice = scenario.player("alice")
    assert [c.name for c in alice.hand] == ["Forest"]
    assert any(c.name == "Llanowar Elves" for c in alice.graveyard)


def test_waterbend_fires_the_701_67c_trigger_on_avatar_aang():
    """CR 701.67c, proved on a real, off-pool, all-formats-legal printing:
    Avatar Aang's own "Whenever you waterbend, earthbend, firebend, or
    airbend, draw a card." Paying Geyser Leaper's Waterbend {4} - by a mix
    of taps and mana, "regardless of how they paid that cost" - draws a
    card off Aang's trigger, on top of Geyser Leaper's own draw."""
    scenario = _geyser_leaper_board(aang=True).build()
    leaper = scenario.creature("Geyser Leaper", "alice")
    bear = scenario.creature("Grizzly Bears", "alice")
    jar = scenario.creature("Welding Jar", "alice")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (elves,) = [
        state for state in scenario.player("alice").hand if state.card.name == "Llanowar Elves"
    ]
    scenario.will_discard(elves)

    assert scenario.game.turn_fact_holds("waterbent", "alice") is False

    islands = scenario.untapped_sources("Island", "Island", username="alice")
    scenario.activate(leaper, *islands, tapping=[bear, jar])
    while scenario.game.stack:
        scenario.pass_until_resolved()

    assert scenario.game.turn_fact_holds("waterbent", "alice") is True
    alice = scenario.player("alice")
    # Two draws happened - Aang's trigger and Geyser Leaper's own effect -
    # against one discard (Geyser Leaper's own second half); starting hand
    # was one card (Llanowar Elves, discarded).
    assert len(alice.hand) == 2
    assert not any(c.name == "Llanowar Elves" for c in alice.hand)


def test_avatar_aang_transforms_once_all_four_bends_happen_in_one_turn():
    """Avatar Aang's own second sentence: "Then if you've done all four this
    turn, transform Avatar Aang." Earthbend, firebend and airbend have no
    built mechanic in this engine yet (`docs/engine-coverage.md`) - their
    own per-turn facts are staged directly through the identical `Game.
    record_turn_fact` API any future mechanic for them would call, so what
    this proves is the transform *condition* reading `Game.turn_facts`
    correctly, not those three keywords."""
    scenario = _geyser_leaper_board(aang=True).build()
    aang = scenario.find("Avatar Aang", Zone.BATTLEFIELD, "alice")
    leaper = scenario.creature("Geyser Leaper", "alice")
    bear = scenario.creature("Grizzly Bears", "alice")
    jar = scenario.creature("Welding Jar", "alice")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (elves,) = [
        state for state in scenario.player("alice").hand if state.card.name == "Llanowar Elves"
    ]
    scenario.will_discard(elves)
    scenario.game.record_turn_fact("earthbent", "alice")
    scenario.game.record_turn_fact("firebent", "alice")
    scenario.game.record_turn_fact("airbent", "alice")

    islands = scenario.untapped_sources("Island", "Island", username="alice")
    scenario.activate(leaper, *islands, tapping=[bear, jar])
    while scenario.game.stack:
        scenario.pass_until_resolved()

    assert aang.up_face_name == "Aang, Master of Elements"


def test_avatar_aang_does_not_transform_with_only_three_of_four_bends():
    """The control: only two of the other three bending facts held before
    waterbend adds the third - "all four" never holds, and Aang stays put."""
    scenario = _geyser_leaper_board(aang=True).build()
    aang = scenario.find("Avatar Aang", Zone.BATTLEFIELD, "alice")
    leaper = scenario.creature("Geyser Leaper", "alice")
    bear = scenario.creature("Grizzly Bears", "alice")
    jar = scenario.creature("Welding Jar", "alice")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (elves,) = [
        state for state in scenario.player("alice").hand if state.card.name == "Llanowar Elves"
    ]
    scenario.will_discard(elves)
    scenario.game.record_turn_fact("earthbent", "alice")
    scenario.game.record_turn_fact("firebent", "alice")
    # airbend is never recorded this turn.

    islands = scenario.untapped_sources("Island", "Island", username="alice")
    scenario.activate(leaper, *islands, tapping=[bear, jar])
    while scenario.game.stack:
        scenario.pass_until_resolved()

    assert aang.up_face_name == "Avatar Aang"
