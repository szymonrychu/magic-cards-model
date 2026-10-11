"""EP-01 round 2, task T7: a static ability granting a castability keyword to
the cards in a zone or to the spells its controller casts (CR 611.3d, CR 610.5,
CR 400.7g), the cost computed from each card's own mana cost.

    Underworld Breach - each nonland card in your graveyard has escape (CR 702.138a)
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import ExileMarker
from magic_cards_model.support import HANDLED, classify_clauses
from tests.cards import card
from tests.scenarios.harness import Scenario


def _handled(name: str) -> None:
    outcomes = classify_clauses(card(name))
    assert {o.category for o in outcomes} == {HANDLED}, outcomes


def _board(**kwargs) -> Scenario:
    return Scenario().manual_turn_based_actions().player("alice", **kwargs).player("bob")


# -- Underworld Breach: escape for every nonland card in the graveyard -------


def test_underworld_breach_clauses_are_handled():
    _handled("Underworld Breach")


def test_breach_gives_a_graveyard_card_escape_at_its_own_mana_cost_plus_three_exiled():
    scenario = _board(
        battlefield=["Underworld Breach", "Mountain"],
        graveyard=["Lightning Bolt", "Mountain", "Mountain", "Mountain"],
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    fuel = [c for c in scenario.player("alice").graveyard if c.name == "Mountain"]
    assert len(fuel) == 3

    casting = scenario.cast("Lightning Bolt", from_zone=Zone.GRAVEYARD)
    casting.use_keyword("Escape", choosing=fuel)
    casting.choose_targets(["bob"])
    payment = casting.begin_paying()
    assert str(payment.cost).startswith("{R}")
    (mountain,) = scenario.untapped_sources("Mountain")
    scenario.pay_with(payment, mountain)
    bolt = scenario.put_on_stack(casting)

    assert bolt.zone is Zone.STACK
    for exiled in fuel:
        assert exiled.zone is Zone.EXILE


def test_breach_reads_each_cards_own_mana_cost():
    scenario = _board(
        battlefield=["Underworld Breach", "Mountain", "Mountain"],
        graveyard=["Fireblast", "Mountain", "Mountain", "Mountain"],
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    fuel = [c for c in scenario.player("alice").graveyard if c.name == "Mountain"]

    casting = scenario.cast("Fireblast", from_zone=Zone.GRAVEYARD)
    casting.use_keyword("Escape", choosing=fuel)
    casting.choose_targets(["bob"])

    assert str(casting.begin_paying().cost).startswith("{4}{R}{R}")


def test_breach_needs_three_other_graveyard_cards():
    scenario = _board(
        battlefield=["Underworld Breach", "Mountain"],
        graveyard=["Lightning Bolt", "Mountain", "Mountain"],
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    fuel = [c for c in scenario.player("alice").graveyard if c.name == "Mountain"]

    casting = scenario.cast("Lightning Bolt", from_zone=Zone.GRAVEYARD)
    casting.use_keyword("Escape", choosing=fuel)
    casting.choose_targets(["bob"])
    payment = casting.begin_paying()
    with pytest.raises(ValueError):
        payment.pay()


def test_breach_does_not_cover_a_land_card():
    scenario = _board(
        battlefield=["Underworld Breach"],
        graveyard=["Mountain", "Mountain", "Mountain", "Mountain"],
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    with pytest.raises(ValueError):
        casting = scenario.cast("Mountain", from_zone=Zone.GRAVEYARD)
        casting.use_keyword("Escape")


def test_without_breach_the_graveyard_card_has_no_escape():
    scenario = _board(
        battlefield=["Mountain"],
        graveyard=["Lightning Bolt", "Mountain", "Mountain", "Mountain"],
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    with pytest.raises(ValueError):
        casting = scenario.cast("Lightning Bolt", from_zone=Zone.GRAVEYARD)
        casting.use_keyword("Escape")


# -- Djinn Illuminatus: replicate for every instant and sorcery spell --------


def _djinn(hand: list[str], lands: list[str]) -> Scenario:
    return _board(hand=hand, battlefield=["Djinn Illuminatus", *lands])


def test_djinn_illuminatus_clauses_are_handled():
    _handled("Djinn Illuminatus")


def test_djinn_gives_an_instant_replicate_at_its_own_mana_cost():
    scenario = _djinn(["Lightning Bolt"], ["Mountain", "Mountain"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Mountain", "Mountain")

    casting = scenario.cast("Lightning Bolt")
    casting.pay_replicate(1)
    casting.choose_targets(["bob"])
    payment = casting.begin_paying()
    assert str(payment.cost) == "{R}{R}", "the mana cost plus the replicate cost equal to it"
    scenario.pay_with(payment, *sources)
    scenario.put_on_stack(casting)

    assert len(scenario.game.stack) == 2, "the replicate trigger above the spell"
    scenario.resolve_top()
    assert len(scenario.game.stack) == 2, "the original and one copy"
    scenario.resolve_top()
    scenario.resolve_top()
    assert scenario.player("bob").life == 14


def test_djinn_replicate_can_be_paid_twice():
    scenario = _djinn(["Lightning Bolt"], ["Mountain"] * 3).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Mountain", "Mountain", "Mountain")

    casting = scenario.cast("Lightning Bolt")
    casting.pay_replicate(2)
    casting.choose_targets(["bob"])
    payment = casting.begin_paying()
    assert str(payment.cost) == "{R}{R}{R}"
    scenario.pay_with(payment, *sources)
    scenario.put_on_stack(casting)
    scenario.resolve_top()
    assert len(scenario.game.stack) == 3


def test_djinn_reads_each_spells_own_mana_cost():
    scenario = _djinn(["Counterspell"], ["Island", "Island", "Island", "Island"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    casting = scenario.cast("Counterspell")
    casting.pay_replicate(1)
    assert str(casting.begin_paying().cost) == "{U}{U}{U}{U}"


def test_djinn_does_not_cover_a_creature_spell():
    scenario = _djinn(["Grizzly Bears"], ["Forest"] * 4).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    casting = scenario.cast("Grizzly Bears")
    with pytest.raises(ValueError, match="replicate"):
        casting.pay_replicate(1)


def test_without_djinn_an_instant_has_no_replicate():
    scenario = _board(hand=["Lightning Bolt"], battlefield=["Mountain", "Mountain"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    casting = scenario.cast("Lightning Bolt")
    with pytest.raises(ValueError, match="replicate"):
        casting.pay_replicate(1)


# -- Falkenrath Gorger: madness for the Vampire cards you own off the battlefield


def _gorger(hand: list[str], bob_hand: list[str] | None = None, gorger: bool = True) -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=hand,
            battlefield=[*(["Falkenrath Gorger"] if gorger else []), "Wild Mongrel", "Swamp"]
            + ["Swamp", "Swamp", "Swamp"],
        )
        .player("bob", hand=bob_hand or [])
    )


def _discard_to_mongrel(scenario, name: str, owner: str = "alice"):
    target = scenario.find(name, Zone.HAND, owner)
    scenario.activate(scenario.creature("Wild Mongrel"), discarding=[target])
    return target


def test_falkenrath_gorger_clauses_are_handled():
    _handled("Falkenrath Gorger")


def test_gorger_makes_a_discarded_vampire_card_go_to_exile():
    scenario = _gorger(["Nighthawk Scavenger"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    vampire = _discard_to_mongrel(scenario, "Nighthawk Scavenger")

    assert vampire.zone is Zone.EXILE
    assert vampire.exile_annotation is not None
    assert vampire.exile_annotation.marker is ExileMarker.MADNESS
    assert "Nighthawk Scavenger's triggered ability" in scenario.stack_names()


def test_the_granted_madness_casts_the_card_for_its_own_mana_cost():
    scenario = _gorger(["Nighthawk Scavenger"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    vampire = _discard_to_mongrel(scenario, "Nighthawk Scavenger")

    casting = scenario.cast("Nighthawk Scavenger", from_zone=Zone.EXILE)
    casting.use_keyword("Madness")
    assert str(casting.total_cost.mana) == "{1}{B}{B}"
    scenario.pay_with(casting.begin_paying(), *scenario.untapped_sources("Swamp", "Swamp", "Swamp"))
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert vampire.zone is Zone.BATTLEFIELD


def test_declining_the_granted_madness_puts_the_card_into_the_graveyard():
    scenario = _gorger(["Nighthawk Scavenger"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    vampire = _discard_to_mongrel(scenario, "Nighthawk Scavenger")

    scenario.resolve_top()  # the madness trigger: the owner does not cast it

    assert vampire.zone is Zone.GRAVEYARD


def test_gorger_does_not_cover_a_non_vampire_card():
    scenario = _gorger(["Grizzly Bears"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    assert _discard_to_mongrel(scenario, "Grizzly Bears").zone is Zone.GRAVEYARD


def test_without_gorger_a_vampire_card_is_discarded_to_the_graveyard():
    scenario = _gorger(["Nighthawk Scavenger"], gorger=False).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    assert _discard_to_mongrel(scenario, "Nighthawk Scavenger").zone is Zone.GRAVEYARD


def test_gorger_only_covers_cards_its_controller_owns():
    scenario = (
        _gorger([], bob_hand=["Nighthawk Scavenger"])
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bobs = scenario.find("Nighthawk Scavenger", Zone.HAND, "bob")
    from magic_cards_model.machines.keywords import discard

    discard(scenario.game, bobs, "bob")

    assert bobs.zone is Zone.GRAVEYARD
