"""Scenario: "Return the exiled card to the battlefield under its owner's
control." followed by another sentence in the same chapter.

A Saga's chapter I exiles a card, and its last chapter returns "the exiled
card" - the two abilities are linked (CR 607.2a): the second refers only to
cards put into exile by the first. Alone the sentence was always readable; once
a further instruction follows in the same ability ("You gain 2 life.") the
lone-sentence reader no longer saw it and the chapter did nothing.

Cards, all from the real printings in `data/printings`:

- **The Measure of a Man** (trk): "III - Return the exiled card to the
  battlefield under its owner's control. You gain 2 life."
- **The Princess Takes Flight** (woe), differently worded: the same return as
  the chapter's only sentence (regression proof; chapter I exiles a creature).

Rules, each read with `mise run rules:find` in the session that wrote this
file: CR 607.2a, CR 400.7, CR 111.7, CR 715.2b.
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


def _saga(name: str, *, bob_board: list[str], alice_board: list[str] | None = None):
    """The Saga is on the battlefield already holding its first lore counter, so
    the next `_next_chapter` runs chapter II ... and the chapters run for
    real: chapter I's exile is what chapter III returns."""
    scenario = (
        Scenario()
        .player("alice", battlefield=[name, *(alice_board or [])], library=["Island"] * 6)
        .player("bob", battlefield=bob_board, library=["Island"] * 6)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    saga = scenario.find(name, Zone.BATTLEFIELD, "alice")
    scenario.game.pending_triggers.clear()
    saga.remove_counters(Counter.LORE, 1)
    return scenario, saga


def _chapter_one(scenario, saga, target) -> None:
    scenario.choose_trigger_targets(saga.name, [target])
    _next_chapter(scenario, saga)


def test_chapter_three_returns_the_exiled_card_and_gains_life():
    scenario, saga = _saga("The Measure of a Man", bob_board=["Grizzly Bears"])
    alice = scenario.player("alice")
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "bob")
    _chapter_one(scenario, saga, bears)
    assert bears.zone is Zone.EXILE
    life = alice.life

    _next_chapter(scenario, saga)  # II: investigate
    _next_chapter(scenario, saga)  # III: return, then gain 2 life

    assert bears.zone is Zone.BATTLEFIELD
    assert bears.controller == "bob"
    assert alice.life == life + 2


def test_with_nothing_exiled_chapter_three_still_gains_life():
    """ "Up to one" target: chapter I may exile nothing, and then there is no
    exiled card to return (CR 607.2a), but the next instruction still happens."""
    scenario, saga = _saga("The Measure of a Man", bob_board=["Grizzly Bears"])
    alice = scenario.player("alice")
    life = alice.life

    _next_chapter(scenario, saga)
    _next_chapter(scenario, saga)
    _next_chapter(scenario, saga)

    assert alice.life == life + 2
    assert scenario.game.exile == []


def test_an_exiled_artifact_returns_too():
    scenario, saga = _saga("The Measure of a Man", bob_board=["Sol Ring"])
    sol_ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "bob")
    _chapter_one(scenario, saga, sol_ring)
    assert sol_ring.zone is Zone.EXILE

    _next_chapter(scenario, saga)
    _next_chapter(scenario, saga)

    assert sol_ring.zone is Zone.BATTLEFIELD


def test_a_card_exiled_by_another_effect_is_not_returned():
    """CR 607.2a: only cards exiled by the linked chapter I come back."""
    scenario, saga = _saga("The Measure of a Man", bob_board=["Grizzly Bears", "Sol Ring"])
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "bob")
    sol_ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "bob")
    _chapter_one(scenario, saga, bears)
    scenario.game.exile_permanent(sol_ring)

    _next_chapter(scenario, saga)
    _next_chapter(scenario, saga)

    assert bears.zone is Zone.BATTLEFIELD
    assert sol_ring.zone is Zone.EXILE


def test_the_single_sentence_chapter_still_returns_its_card():
    scenario, saga = _saga(
        "The Princess Takes Flight", bob_board=["Grizzly Bears"], alice_board=["Memnite"]
    )
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "bob")
    _chapter_one(scenario, saga, bears)
    assert bears.zone is Zone.EXILE
    scenario.choose_trigger_targets(
        saga.name, [scenario.find("Memnite", Zone.BATTLEFIELD, "alice")]
    )

    _next_chapter(scenario, saga)
    _next_chapter(scenario, saga)

    assert bears.zone is Zone.BATTLEFIELD
