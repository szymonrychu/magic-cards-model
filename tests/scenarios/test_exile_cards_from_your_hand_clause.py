"""Scenario: "exile a card from your hand" as an instruction of a resolving
spell or ability, not a cost - the player clause behind a "then" and behind a
"may ... If you do".

The instruction is the controller's own choice from their own hand (CR 608.2d)
and moves the card to the exile zone (CR 701.13a); a hand holding fewer cards
than asked exiles what is there (CR 609.3). In "You may exile a card from your
hand. If you do, draw a card." the exile is a cost paid as the ability resolves
(CR 118.12), so a hand with nothing to exile cannot pay it and the consequence
does not happen.

Cards, all from the real printings in `data/printings`:

- **All Good Things...** (trk) I, II, III: "Draw two cards, then exile a card
  from your hand." - the "then" clause. What it exiles is "exiled with" the Saga
  (CR 607.2a), which chapter IV reads (see `test_cards_exiled_with_share_a_card_type.py`).
- **The Wrath of Khan** (trk) II: "You may exile a card from your hand. If you
  do, draw a card." - the may / if-you-do pair.
- **Ego Drain** (woe), differently worded: the clause stands alone behind a
  condition, "If you don't control a Faerie, exile a card from your hand."
- **Gemstone Caverns** and **Azor's Gateway** keep their own readers and are
  regression proofs that the new clause reader did not take their text.

Rules, each read with `mise run rules:find` in the session that wrote this file:
CR 701.13a, CR 608.2d, CR 609.3, CR 118.12, CR 607.2a, CR 715.2b, CR 715.3a,
CR 121.2.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import DecisionKind
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter

from .harness import Scenario


def _resolve_everything(scenario) -> None:
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.pass_until_resolved()
        scenario.game.put_triggers_on_stack()


def _enter(scenario, name: str, username: str = "alice"):
    saga = scenario.put_onto_battlefield(name, username)
    _resolve_everything(scenario)
    return saga


def _next_chapter(scenario, saga) -> None:
    scenario.game.add_counters(saga, Counter.LORE, 1)
    _resolve_everything(scenario)


def _exiled_names(scenario, username: str = "alice") -> list[str]:
    return [state.name for state in scenario.game.exile if state.owner == username]


# -- The Wrath of Khan II: "You may exile a card from your hand. If you do, draw a card." --


def _khan_at_chapter_two(*, hand: list[str], bob_hand: list[str] | None = None):
    """A Saga set up on the battlefield already holds its first lore counter
    (chapter I is behind it, nothing triggered), so only chapter II is under
    test once the next counter goes on."""
    scenario = (
        Scenario()
        .player("alice", hand=hand, battlefield=["The Wrath of Khan"], library=["Island"] * 6)
        .player("bob", hand=bob_hand or [], library=["Island"] * 6)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    saga = scenario.find("The Wrath of Khan", Zone.BATTLEFIELD, "alice")
    assert saga.counters[Counter.LORE] == 1
    scenario.game.pending_triggers.clear()
    return scenario, saga


def test_may_exile_a_card_from_hand_then_draws_a_card():
    scenario, saga = _khan_at_chapter_two(hand=["Mountain", "Forest", "Swamp"])
    alice = scenario.player("alice")
    forest = scenario.find("Forest", Zone.HAND, "alice")
    scenario.will_take_the_may(True, username="alice")
    scenario.will_choose_cards(forest, username="alice")

    _next_chapter(scenario, saga)

    assert forest.zone is Zone.EXILE
    assert len(alice.hand) == 3  # three, minus the exiled card, plus the drawn one
    assert "Forest" not in [state.name for state in alice.hand]
    assert len(alice.library) == 5


def test_declining_the_may_exiles_nothing_and_draws_nothing():
    scenario, saga = _khan_at_chapter_two(hand=["Mountain", "Forest"])
    alice = scenario.player("alice")
    scenario.will_take_the_may(False, username="alice")

    _next_chapter(scenario, saga)

    assert _exiled_names(scenario) == []
    assert len(alice.hand) == 2
    assert len(alice.library) == 6


def test_an_empty_hand_cannot_pay_the_exile_so_no_question_and_no_draw():
    """CR 118.12 / CR 608.2d: there is no card to exile, so the optional action
    is impossible - nothing is asked, and "if you do" is not met."""
    scenario, saga = _khan_at_chapter_two(hand=[])
    alice = scenario.player("alice")

    _next_chapter(scenario, saga)

    assert not any(d.kind is DecisionKind.CHOOSE_CARDS for d in scenario.questions_asked())
    assert alice.hand == []
    assert len(alice.library) == 6


def test_a_one_card_hand_exiles_it_and_the_draw_refills_the_hand():
    scenario, saga = _khan_at_chapter_two(hand=["Mountain"])
    alice = scenario.player("alice")
    mountain = scenario.find("Mountain", Zone.HAND, "alice")
    scenario.will_take_the_may(True, username="alice")

    _next_chapter(scenario, saga)

    assert mountain.zone is Zone.EXILE
    assert [state.name for state in alice.hand] == ["Island"]


def test_only_the_controllers_hand_is_touched():
    scenario, saga = _khan_at_chapter_two(hand=["Mountain"], bob_hand=["Forest", "Swamp"])
    bob = scenario.player("bob")
    scenario.will_take_the_may(True, username="alice")

    _next_chapter(scenario, saga)

    assert [state.name for state in bob.hand] == ["Forest", "Swamp"]
    assert _exiled_names(scenario, "bob") == []
    assert len(bob.library) == 6


def test_the_exiled_card_stays_its_owners_in_the_shared_exile_zone():
    scenario, saga = _khan_at_chapter_two(hand=["Mountain", "Forest"])
    forest = scenario.find("Forest", Zone.HAND, "alice")
    scenario.will_take_the_may(True, username="alice")
    scenario.will_choose_cards(forest, username="alice")

    _next_chapter(scenario, saga)

    assert forest in scenario.game.exile
    assert forest.owner == "alice"


# -- All Good Things... I, II, III: "Draw two cards, then exile a card from your hand." --


def _all_good_things(*, hand: list[str], library: list[str] | None = None):
    """The Saga is on the battlefield with its first lore counter, chapter I
    not yet run: each `_next_chapter` puts the next lore counter on."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=hand,
            battlefield=["All Good Things..."],
            library=library or ["Island", "Plains", "Mountain", "Forest", "Swamp"],
        )
        .player("bob", library=["Island"] * 4)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    saga = scenario.find("All Good Things...", Zone.BATTLEFIELD, "alice")
    scenario.game.pending_triggers.clear()
    saga.remove_counters(Counter.LORE, 1)
    return scenario, saga


def test_chapter_one_draws_two_then_exiles_a_card_from_the_new_hand():
    scenario, saga = _all_good_things(hand=["Mountain"])
    alice = scenario.player("alice")
    drawn = [state for state in alice.library[:2]]

    # The player may exile either a card already in hand or one just drawn:
    # the draw is performed first (CR 608.2c's printed order).
    scenario.will_choose_cards(drawn[0], username="alice")
    _next_chapter(scenario, saga)

    assert drawn[0].zone is Zone.EXILE
    assert len(alice.hand) == 2  # one in hand, plus two drawn, minus one exiled
    assert drawn[1] in alice.hand


def test_the_exile_is_mandatory_even_when_the_only_card_is_one_just_drawn():
    scenario, saga = _all_good_things(hand=[])
    alice = scenario.player("alice")

    _next_chapter(scenario, saga)

    assert len(alice.hand) == 1
    assert len(_exiled_names(scenario)) == 1


def test_the_exile_asks_for_exactly_one_card():
    scenario, saga = _all_good_things(hand=["Mountain", "Forest"])

    _next_chapter(scenario, saga)

    asked = [d for d in scenario.questions_asked() if d.kind is DecisionKind.CHOOSE_CARDS]
    assert len(asked) == 1
    assert asked[0].amount == 1
    assert asked[0].player == "alice"


def test_every_chapter_that_says_it_exiles_one_more_card():
    scenario, saga = _all_good_things(
        hand=["Mountain"], library=["Island"] * 9
    )  # chapter I, II and III each draw two
    alice = scenario.player("alice")

    for _ in range(3):
        _next_chapter(scenario, saga)

    assert len(_exiled_names(scenario)) == 3
    assert len(alice.hand) == 1 + 3 * 2 - 3
    assert len(alice.library) == 9 - 3 * 2


# -- Ego Drain: the same clause behind a condition, in a spell --


def _ego_drain(*, alice_battlefield: list[str], alice_hand: list[str]):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Ego Drain", *alice_hand],
            battlefield=["Swamp", "Swamp", "Swamp", *alice_battlefield],
            library=["Island"] * 4,
        )
        .player("bob", hand=["Lightning Bolt", "Forest"], library=["Island"] * 4)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_ego_drain_without_a_faerie_exiles_a_card_from_your_hand():
    scenario = _ego_drain(alice_battlefield=[], alice_hand=["Mountain", "Plains"])
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "bob")
    plains = scenario.find("Plains", Zone.HAND, "alice")
    scenario.will_discard(bolt, username="alice")
    scenario.will_choose_cards(plains, username="alice")
    sources = scenario.untapped_sources("Swamp", "Swamp", "Swamp")

    scenario.cast_and_resolve("Ego Drain", *sources, targets=["bob"])

    assert bolt.zone is Zone.GRAVEYARD
    assert plains.zone is Zone.EXILE


def test_ego_drain_with_a_faerie_keeps_your_hand():
    scenario = _ego_drain(alice_battlefield=["Vendilion Clique"], alice_hand=["Mountain", "Plains"])
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "bob")
    scenario.will_discard(bolt, username="alice")
    sources = scenario.untapped_sources("Swamp", "Swamp", "Swamp")

    scenario.cast_and_resolve("Ego Drain", *sources, targets=["bob"])

    assert bolt.zone is Zone.GRAVEYARD
    assert [state.name for state in scenario.player("alice").hand] == ["Mountain", "Plains"]
    assert _exiled_names(scenario) == []


def test_ego_drain_with_an_empty_hand_exiles_nothing():
    scenario = _ego_drain(alice_battlefield=[], alice_hand=[])
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "bob")
    scenario.will_discard(bolt, username="alice")
    sources = scenario.untapped_sources("Swamp", "Swamp", "Swamp")

    scenario.cast_and_resolve("Ego Drain", *sources, targets=["bob"])

    assert bolt.zone is Zone.GRAVEYARD
    assert _exiled_names(scenario) == []
