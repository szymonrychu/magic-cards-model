"""Triggers on a permanent being returned to a hand from the battlefield.

Three printings, three wordings of one event:

- **Tameshi, Reality Architect** - "Whenever one or more noncreature
  permanents are returned to hand, draw a card. This ability triggers only
  once each turn." Any controller, any hand; the "one or more" plural is one
  trigger per event however many permanents it moved (CR 603.2c).
- **Azorius Aethermage** - "Whenever a permanent is returned to your hand,
  you may pay {1}. If you do, draw a card." Singular: one trigger per
  permanent, and "your hand" is the owner's hand, whoever controlled it. The
  printed ruling: it triggers for Aethermage itself too.
- **Justice, Vance Astrovik** (proof printing, not a listed card, not in any
  api deck) - "Whenever another nonland permanent you control is returned to
  its owner's hand, put a +1/+1 counter on Justice." A third wording: a
  controller clause, "another", and "its owner's hand".

CR numbers used, each read with `mise run rules:find` in this session:

- **CR 603.2c** - "An ability triggers only once each time its trigger event
  occurs. However, it can trigger repeatedly if one event contains multiple
  occurrences."
- **CR 603.6c** - leaves-the-battlefield abilities trigger when a permanent
  moves from the battlefield to another zone.
- **CR 603.10a** - leaves-the-battlefield abilities look back in time, so a
  permanent returned in the same event as the others still sees them, and
  its own departure (Aethermage's ruling).
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import DecisionKind
from magic_cards_model.models import Zone

from .harness import Scenario


def settle(scenario) -> None:
    """Put every waiting trigger on the stack and resolve everything."""
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()


def library_size(scenario, username: str = "alice") -> int:
    return len(scenario.player(username).library)


# -- Tameshi: "one or more noncreature permanents are returned to hand" ------


def tameshi_board(*, hand: list[str], extra: list[str] | None = None) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=hand,
            battlefield=["Tameshi, Reality Architect", *(extra or []), *["Island"] * 4],
            library=["Forest"] * 5,
        )
        .player("bob", battlefield=["Darksteel Relic", "Grizzly Bears"])
    )


def test_tameshi_draws_when_an_opponents_noncreature_permanent_is_bounced():
    scenario = tameshi_board(hand=["Boomerang Basics"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    relic = scenario.find("Darksteel Relic", Zone.BATTLEFIELD, "bob")
    before = library_size(scenario)

    (island,) = scenario.untapped_sources("Island")
    scenario.cast_and_resolve("Boomerang Basics", island, targets=[relic])
    settle(scenario)

    assert relic.zone is Zone.HAND
    # Boomerang Basics' own draw needs alice to have controlled it; she did
    # not, so the one card drawn is Tameshi's.
    assert library_size(scenario) == before - 1


def test_tameshi_draws_for_its_own_controllers_noncreature_permanent_too():
    scenario = tameshi_board(hand=["Boomerang Basics"], extra=["Darksteel Relic"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    relic = scenario.find("Darksteel Relic", Zone.BATTLEFIELD, "alice")
    before = library_size(scenario)

    (island,) = scenario.untapped_sources("Island")
    scenario.cast_and_resolve("Boomerang Basics", island, targets=[relic])
    settle(scenario)

    assert relic.zone is Zone.HAND
    # One from Boomerang Basics (alice controlled it), one from Tameshi.
    assert library_size(scenario) == before - 2


def test_tameshi_ignores_a_creature_returned_to_hand():
    scenario = tameshi_board(hand=["Unsummon"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "bob")
    before = library_size(scenario)

    (island,) = scenario.untapped_sources("Island")
    scenario.cast_and_resolve("Unsummon", island, targets=[bears])
    settle(scenario)

    assert bears.zone is Zone.HAND
    assert library_size(scenario) == before


def test_an_artifact_creature_is_still_a_creature_to_tameshi():
    """ "noncreature" forbids the creature type whatever else the permanent
    is - Memnite is an artifact, and a creature, so it does not count."""
    scenario = tameshi_board(hand=["Unsummon"], extra=["Memnite"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    memnite = scenario.find("Memnite", Zone.BATTLEFIELD, "alice")
    before = library_size(scenario)

    (island,) = scenario.untapped_sources("Island")
    scenario.cast_and_resolve("Unsummon", island, targets=[memnite])
    settle(scenario)

    assert memnite.zone is Zone.HAND
    assert library_size(scenario) == before


def test_tameshi_draws_only_once_for_two_bounces_in_one_turn():
    scenario = tameshi_board(
        hand=["Boomerang Basics", "Boomerang Basics"], extra=["Darksteel Relic"]
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    theirs = scenario.find("Darksteel Relic", Zone.BATTLEFIELD, "bob")
    mine = scenario.find("Darksteel Relic", Zone.BATTLEFIELD, "alice")
    before = library_size(scenario)

    first, second = scenario.untapped_sources("Island", "Island")
    scenario.cast_and_resolve("Boomerang Basics", first, targets=[theirs])
    settle(scenario)
    assert library_size(scenario) == before - 1  # Tameshi

    scenario.cast_and_resolve("Boomerang Basics", second, targets=[mine])
    settle(scenario)

    assert mine.zone is Zone.HAND
    # Only Boomerang Basics' own draw this time: Tameshi already triggered.
    assert library_size(scenario) == before - 2


def test_two_noncreature_permanents_returned_together_draw_one_card():
    """CR 603.2c: Marang River Regent returns both in one event, and "one or
    more" triggers once for it."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Marang River Regent"],
            battlefield=["Tameshi, Reality Architect"],
            library=["Forest"] * 5,
        )
        .player("bob", battlefield=["Darksteel Relic", "Darksteel Relic"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    relics = [state for state in scenario.game.battlefield if state.name == "Darksteel Relic"]
    before = library_size(scenario)

    scenario.put_onto_battlefield("Marang River Regent", "alice")
    scenario.choose_trigger_targets("Marang River Regent", relics)
    settle(scenario)

    assert all(relic.zone is Zone.HAND for relic in relics)
    assert library_size(scenario) == before - 1


def test_a_creature_and_a_noncreature_returned_together_still_draw_once():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Marang River Regent"],
            battlefield=["Tameshi, Reality Architect"],
            library=["Forest"] * 5,
        )
        .player("bob", battlefield=["Grizzly Bears", "Darksteel Relic"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "bob")
    relic = scenario.find("Darksteel Relic", Zone.BATTLEFIELD, "bob")
    before = library_size(scenario)

    scenario.put_onto_battlefield("Marang River Regent", "alice")
    scenario.choose_trigger_targets("Marang River Regent", [bears, relic])
    settle(scenario)

    assert bears.zone is Zone.HAND and relic.zone is Zone.HAND
    assert library_size(scenario) == before - 1


def test_a_noncreature_card_returned_from_a_graveyard_does_not_trigger_tameshi():
    """The printed ruling: only permanents returned from the battlefield
    count - Eternal Witness returning Darksteel Relic from the graveyard is a
    card, not a permanent, going to hand."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Eternal Witness"],
            battlefield=["Tameshi, Reality Architect"],
            graveyard=["Darksteel Relic"],
            library=["Forest"] * 5,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    relic = scenario.find("Darksteel Relic", Zone.GRAVEYARD, "alice")
    before = library_size(scenario)

    scenario.will_take_the_may(True)
    scenario.put_onto_battlefield("Eternal Witness", "alice")
    scenario.choose_trigger_targets("Eternal Witness", [relic])
    settle(scenario)

    assert relic.zone is Zone.HAND
    assert library_size(scenario) == before


def test_tameshis_own_land_return_cost_triggers_it():
    """The cost returns a land - a noncreature permanent - to its owner's
    hand, which is exactly Tameshi's own trigger event. X=0 brings back a
    mana value 0 artifact (Darksteel Relic) from the graveyard."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Tameshi, Reality Architect", "Plains", "Island"],
            graveyard=["Darksteel Relic"],
            library=["Forest"] * 5,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    tameshi = scenario.find("Tameshi, Reality Architect", Zone.BATTLEFIELD, "alice")
    relic = scenario.find("Darksteel Relic", Zone.GRAVEYARD, "alice")
    island = scenario.find("Island", Zone.BATTLEFIELD, "alice")
    (plains,) = scenario.untapped_sources("Plains")
    before = library_size(scenario)

    scenario.will_choose_cards(island)
    scenario.activate(tameshi, plains, targets=[relic], x_value=0)
    assert island.zone is Zone.HAND  # paid as the cost (CR 601.2h via 602.2b)
    settle(scenario)

    assert relic.zone is Zone.BATTLEFIELD
    assert library_size(scenario) == before - 1


def test_tameshis_land_return_cost_offers_only_lands_you_control():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Tameshi, Reality Architect", "Plains", "Island", "Darksteel Relic"],
            graveyard=["Darksteel Relic"],
            library=["Forest"] * 5,
        )
        .player("bob", battlefield=["Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    tameshi = scenario.find("Tameshi, Reality Architect", Zone.BATTLEFIELD, "alice")
    target = scenario.find("Darksteel Relic", Zone.GRAVEYARD, "alice")
    island = scenario.find("Island", Zone.BATTLEFIELD, "alice")
    (plains,) = scenario.untapped_sources("Plains")

    scenario.will_choose_cards(island)
    scenario.activate(tameshi, plains, targets=[target], x_value=0)

    (asked,) = [q for q in scenario.questions_asked() if q.kind is DecisionKind.CHOOSE_CARDS]
    assert set(asked.cards) == {plains.id, island.id}


def test_tameshis_cost_cannot_be_paid_without_a_land_to_return():
    """CR 118.3: with no land to return the cost cannot be paid, so the
    ability cannot be activated - the Relic on the battlefield is not a land,
    and Chromatic Lantern pays the {W} without being one."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Tameshi, Reality Architect", "Chromatic Lantern", "Darksteel Relic"],
            graveyard=["Darksteel Relic"],
            library=["Forest"] * 5,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    tameshi = scenario.find("Tameshi, Reality Architect", Zone.BATTLEFIELD, "alice")
    relic_on_board = scenario.find("Darksteel Relic", Zone.BATTLEFIELD, "alice")
    target = scenario.find("Darksteel Relic", Zone.GRAVEYARD, "alice")
    before = library_size(scenario)

    with pytest.raises(ValueError, match="return_to_hand needs 1 card"):
        scenario.activate(tameshi, targets=[target], x_value=0, auto=True)

    assert relic_on_board.zone is Zone.BATTLEFIELD
    assert target.zone is Zone.GRAVEYARD
    assert library_size(scenario) == before


# -- Azorius Aethermage: "a permanent is returned to your hand" -------------


def aethermage_board(*, hand: list[str], extra: list[str] | None = None) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=hand,
            battlefield=["Azorius Aethermage", *(extra or []), *["Island"] * 4],
            library=["Forest"] * 5,
        )
        .player("bob", battlefield=["Grizzly Bears"], library=["Forest"] * 5)
    )


def test_aethermage_pays_one_and_draws_for_your_own_permanent():
    scenario = aethermage_board(hand=["Unsummon"], extra=["Memnite"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    memnite = scenario.find("Memnite", Zone.BATTLEFIELD, "alice")
    before = library_size(scenario)

    scenario.will_pay_the_mana_cost(True, times=None)
    (island,) = scenario.untapped_sources("Island")
    scenario.cast_and_resolve("Unsummon", island, targets=[memnite])
    settle(scenario)

    assert memnite.zone is Zone.HAND
    assert library_size(scenario) == before - 1


def test_declining_to_pay_draws_nothing():
    scenario = aethermage_board(hand=["Unsummon"], extra=["Memnite"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    memnite = scenario.find("Memnite", Zone.BATTLEFIELD, "alice")
    before = library_size(scenario)

    scenario.will_pay_the_mana_cost(False, times=None)
    (island,) = scenario.untapped_sources("Island")
    scenario.cast_and_resolve("Unsummon", island, targets=[memnite])
    settle(scenario)

    assert library_size(scenario) == before


def test_an_opponents_permanent_returned_to_their_hand_is_not_your_hand():
    scenario = aethermage_board(hand=["Unsummon"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "bob")
    before = library_size(scenario)

    scenario.will_pay_the_mana_cost(True, times=None)
    (island,) = scenario.untapped_sources("Island")
    scenario.cast_and_resolve("Unsummon", island, targets=[bears])
    settle(scenario)

    assert bears.zone is Zone.HAND
    assert not scenario.game.stack
    assert library_size(scenario) == before


def test_aethermage_triggers_on_its_own_return():
    """The printed ruling, and CR 603.10a's look-back: Aethermage is in the
    hand by the time the event is checked, and triggers all the same."""
    scenario = aethermage_board(hand=["Unsummon"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    aethermage = scenario.find("Azorius Aethermage", Zone.BATTLEFIELD, "alice")
    before = library_size(scenario)

    scenario.will_pay_the_mana_cost(True, times=None)
    (island,) = scenario.untapped_sources("Island")
    scenario.cast_and_resolve("Unsummon", island, targets=[aethermage])
    settle(scenario)

    assert aethermage.zone is Zone.HAND
    assert library_size(scenario) == before - 1


def test_two_permanents_returned_together_trigger_it_twice():
    """Singular "a permanent": CR 603.2c's multiple occurrences, one trigger
    for each - and Aethermage returned alongside the other one still sees
    both (CR 603.10a)."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Marang River Regent"],
            battlefield=["Azorius Aethermage", "Memnite", *["Island"] * 4],
            library=["Forest"] * 5,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    aethermage = scenario.find("Azorius Aethermage", Zone.BATTLEFIELD, "alice")
    memnite = scenario.find("Memnite", Zone.BATTLEFIELD, "alice")
    before = library_size(scenario)

    scenario.will_pay_the_mana_cost(True, times=None)
    scenario.put_onto_battlefield("Marang River Regent", "alice")
    scenario.choose_trigger_targets("Marang River Regent", [aethermage, memnite])
    settle(scenario)

    assert aethermage.zone is Zone.HAND and memnite.zone is Zone.HAND
    assert library_size(scenario) == before - 2


def test_a_card_returned_from_the_graveyard_is_not_a_permanent():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Eternal Witness"],
            battlefield=["Azorius Aethermage", *["Island"] * 4],
            graveyard=["Darksteel Relic"],
            library=["Forest"] * 5,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    relic = scenario.find("Darksteel Relic", Zone.GRAVEYARD, "alice")
    before = library_size(scenario)

    scenario.will_pay_the_mana_cost(True, times=None)
    scenario.will_take_the_may(True)
    scenario.put_onto_battlefield("Eternal Witness", "alice")
    scenario.choose_trigger_targets("Eternal Witness", [relic])
    settle(scenario)

    assert relic.zone is Zone.HAND
    assert library_size(scenario) == before


def test_a_returned_token_is_a_permanent_returned_to_your_hand():
    """The printed ruling names a token creature: Stormchaser's Talent's
    Otter, bounced, triggers Aethermage before it ceases to exist."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Stormchaser's Talent", "Unsummon"],
            battlefield=["Azorius Aethermage", *["Island"] * 4],
            library=["Forest"] * 5,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.put_onto_battlefield("Stormchaser's Talent", "alice")
    settle(scenario)
    (otter,) = [state for state in scenario.game.battlefield if state.token]
    before = library_size(scenario)

    scenario.will_pay_the_mana_cost(True, times=None)
    (island,) = scenario.untapped_sources("Island")
    scenario.cast_and_resolve("Unsummon", island, targets=[otter])
    settle(scenario)

    assert otter not in scenario.game.battlefield
    assert library_size(scenario) == before - 1


# -- Justice, Vance Astrovik: "another nonland permanent you control is
# returned to its owner's hand" (proof printing) ---------------------------


def justice_board(*, battlefield: list[str], bob: list[str] | None = None) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=["Justice, Vance Astrovik"],
            battlefield=battlefield,
            library=["Forest"] * 5,
        )
        .player("bob", battlefield=bob or [])
    )


def test_justice_grows_when_it_returns_your_own_nonland_permanent():
    scenario = justice_board(battlefield=["Memnite"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    memnite = scenario.find("Memnite", Zone.BATTLEFIELD, "alice")

    justice = scenario.put_onto_battlefield("Justice, Vance Astrovik", "alice")
    scenario.choose_trigger_targets("Justice, Vance Astrovik", [memnite])
    settle(scenario)

    assert memnite.zone is Zone.HAND
    assert justice.counter_count("+1/+1") == 1


def test_justice_ignores_an_opponents_permanent():
    scenario = justice_board(battlefield=[], bob=["Grizzly Bears"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "bob")

    justice = scenario.put_onto_battlefield("Justice, Vance Astrovik", "alice")
    scenario.choose_trigger_targets("Justice, Vance Astrovik", [bears])
    settle(scenario)

    assert bears.zone is Zone.HAND
    assert justice.counter_count("+1/+1") == 0


def test_justice_ignores_a_land_you_control():
    """Tameshi's cost returns a land alice controls - not a nonland
    permanent, so Justice does not grow."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[
                "Justice, Vance Astrovik",
                "Tameshi, Reality Architect",
                "Plains",
                "Island",
            ],
            graveyard=["Darksteel Relic"],
            library=["Forest"] * 5,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    justice = scenario.find("Justice, Vance Astrovik", Zone.BATTLEFIELD, "alice")
    tameshi = scenario.find("Tameshi, Reality Architect", Zone.BATTLEFIELD, "alice")
    relic = scenario.find("Darksteel Relic", Zone.GRAVEYARD, "alice")
    island = scenario.find("Island", Zone.BATTLEFIELD, "alice")
    (plains,) = scenario.untapped_sources("Plains")

    scenario.will_choose_cards(island)
    scenario.activate(tameshi, plains, targets=[relic], x_value=0)
    settle(scenario)

    assert island.zone is Zone.HAND
    assert justice.counter_count("+1/+1") == 0


def test_justice_returned_itself_is_not_another_permanent():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Unsummon"],
            battlefield=["Justice, Vance Astrovik", "Island"],
            library=["Forest"] * 5,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    justice = scenario.find("Justice, Vance Astrovik", Zone.BATTLEFIELD, "alice")

    (island,) = scenario.untapped_sources("Island")
    scenario.cast_and_resolve("Unsummon", island, targets=[justice])
    scenario.game.put_triggers_on_stack()

    assert justice.zone is Zone.HAND
    assert not scenario.game.stack
