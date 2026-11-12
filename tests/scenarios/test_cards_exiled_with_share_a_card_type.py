"""Scenario: "If all cards exiled with this Saga share a card type, you gain 10
life." - a condition over the whole pile of cards exiled with an object
(CR 607.2a), asking whether one card type is common to all of them.

All Good Things... (trk): chapters I, II and III each "Draw two cards, then
exile a card from your hand", so by chapter IV the Saga has up to three cards
"exiled with" it. Chapter IV asks whether they all share a card type.

Card types are CR 205.2a's list; an object with more than one satisfies the
criteria of every one of them (CR 205.2b), so an artifact creature shares a
type with a plain creature and with a plain artifact. "Share a card type" is
read as a type common to every card in the pile, not a pair that happens to
overlap: three cards that overlap two at a time but have no one type in common
do not all share a type.

No ruling exists yet (the set releases 2026-11-13) and the CR does not define
"share a card type" for a pile of any size, so the empty and the one-card pile
follow the owner's decision recorded in `docs/automation/user-decisions.md`
(2026-11-12, T-136 decision 464): no cards means no life, one card is true,
two or more are true when their card-type sets intersect.

Cards, all from the real printings in `data/printings`: Memnite (artifact
creature), Grizzly Bears (creature), Sol Ring (artifact), Great Furnace
(artifact land), Dryad Arbor (land creature), Mountain (land), Island (land).

Rules, each read with `mise run rules:find` in the session that wrote this file:
CR 607.2a, CR 205.2a, CR 205.2b, CR 715.2b, CR 715.4, CR 119.1.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter

from .harness import Scenario


def _resolve_everything(scenario) -> None:
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.pass_until_resolved()
        scenario.game.put_triggers_on_stack()


def _next_chapter(scenario, saga) -> None:
    scenario.game.add_counters(saga, Counter.LORE, 1)
    _resolve_everything(scenario)


def _saga_with_pile(*exiled: str):
    """All Good Things... with chapters I to III behind it, each having exiled
    the named card from alice's hand (three names, in chapter order); chapter
    IV is next.

    Chapters run for real, so the cards really are "exiled with" the Saga
    through the chapter abilities' own exile, not planted in the exile zone.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=list(exiled),
            battlefield=["All Good Things..."],
            library=["Island"] * 12,
        )
        .player("bob", library=["Island"] * 4)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    saga = scenario.find("All Good Things...", Zone.BATTLEFIELD, "alice")
    scenario.game.pending_triggers.clear()
    saga.remove_counters(Counter.LORE, 1)
    assert len(exiled) == 3
    for name in exiled:
        scenario.will_choose_cards(scenario.find(name, Zone.HAND, "alice"), username="alice")
        _next_chapter(scenario, saga)
    return scenario, saga


def _pile_of(scenario, saga) -> list[str]:
    return sorted(c.name for c in scenario.game.cards_exiled_with(saga.id, saga.zone_change_stamp))


def _chapter_four(scenario, saga) -> int:
    alice = scenario.player("alice")
    before = alice.life
    _next_chapter(scenario, saga)
    return alice.life - before


def test_two_artifact_creatures_share_a_type_and_the_controller_gains_ten():
    scenario, saga = _saga_with_pile("Memnite", "Memnite", "Memnite")
    assert _pile_of(scenario, saga) == ["Memnite"] * 3

    assert _chapter_four(scenario, saga) == 10


def test_a_creature_and_an_artifact_creature_share_creature_and_gain_ten():
    """CR 205.2b: an artifact creature satisfies the criteria of "creature"."""
    scenario, saga = _saga_with_pile("Memnite", "Grizzly Bears", "Memnite")

    assert _chapter_four(scenario, saga) == 10


def test_a_land_and_a_creature_share_no_type_and_nothing_is_gained():
    scenario, saga = _saga_with_pile("Mountain", "Grizzly Bears", "Island")

    assert _chapter_four(scenario, saga) == 0


def test_cards_that_overlap_only_two_at_a_time_do_not_all_share_a_type():
    """Memnite {artifact, creature}, Great Furnace {artifact, land} and Dryad
    Arbor {land, creature}: each pair shares a type, no single type is common
    to all three."""
    scenario, saga = _saga_with_pile("Memnite", "Great Furnace", "Dryad Arbor")

    assert _chapter_four(scenario, saga) == 0


def test_three_lands_share_land_and_gain_ten():
    scenario, saga = _saga_with_pile("Mountain", "Island", "Great Furnace")

    assert _chapter_four(scenario, saga) == 10


def test_an_artifact_land_and_a_plain_artifact_share_artifact():
    scenario, saga = _saga_with_pile("Great Furnace", "Sol Ring", "Memnite")

    assert _chapter_four(scenario, saga) == 10


def test_a_single_exiled_card_trivially_shares_a_type_with_itself():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Mountain"],
            battlefield=["All Good Things..."],
            library=["Island"] * 12,
        )
        .player("bob", library=["Island"] * 4)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    saga = scenario.find("All Good Things...", Zone.BATTLEFIELD, "alice")
    scenario.game.pending_triggers.clear()
    saga.remove_counters(Counter.LORE, 1)
    scenario.will_choose_cards(scenario.find("Mountain", Zone.HAND, "alice"), username="alice")
    _next_chapter(scenario, saga)  # chapter I: one card in the pile
    assert _pile_of(scenario, saga) == ["Mountain"]
    saga.add_counters(Counter.LORE, 2)  # past II and III without running them

    assert _chapter_four(scenario, saga) == 10


def test_an_empty_pile_gains_nothing():
    """The owner's decision: zero cards exiled is not a vacuous truth."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["All Good Things..."], library=["Island"] * 4)
        .player("bob", library=["Island"] * 4)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    saga = scenario.find("All Good Things...", Zone.BATTLEFIELD, "alice")
    scenario.game.pending_triggers.clear()
    saga.add_counters(Counter.LORE, 2)  # lore 3: chapter IV is next
    assert _pile_of(scenario, saga) == []

    assert _chapter_four(scenario, saga) == 0


def test_a_card_exiled_by_something_else_is_not_in_the_pile():
    """CR 607.2a: only cards exiled by the linked chapter abilities count. A
    land exiled by an unrelated effect leaves the Saga's one creature pile of
    one, which trivially shares a type."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Grizzly Bears"],
            battlefield=["All Good Things..."],
            library=["Island"] * 6,
            exile=["Mountain"],
        )
        .player("bob", library=["Island"] * 4)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    saga = scenario.find("All Good Things...", Zone.BATTLEFIELD, "alice")
    scenario.game.pending_triggers.clear()
    saga.remove_counters(Counter.LORE, 1)
    scenario.will_choose_cards(scenario.find("Grizzly Bears", Zone.HAND, "alice"), username="alice")
    _next_chapter(scenario, saga)
    saga.add_counters(Counter.LORE, 2)
    assert _pile_of(scenario, saga) == ["Grizzly Bears"]

    assert _chapter_four(scenario, saga) == 10


def test_the_saga_is_sacrificed_after_chapter_four_whatever_it_gained():
    """CR 715.4: the final chapter ability resolved and left the stack."""
    scenario, saga = _saga_with_pile("Mountain", "Grizzly Bears", "Island")

    _chapter_four(scenario, saga)

    assert saga.zone is Zone.GRAVEYARD
