"""Roads Go Ever, Ever On, a Saga (CR 714) whose own chapter readers are new,
built on Saga chapter machinery this task does not own:

    I — Search your library for up to two basic Plains cards, exile them,
        then shuffle. You gain 2 life.
    II, III — Put a card exiled with this Saga into its owner's hand.
    IV — Whenever you attack this turn, target creature you control gets
        +1/+1 until end of turn for each Plains you control.

Chapter I is a fifth `_SEARCH_AND_PUT_RE` sibling: "exile" as the search's
own destination (`_parse_search_and_exile_then_shuffle_clause`,
`_SEARCH_AND_EXILE_THEN_SHUFFLE_RE`, built with the same quality/basic-
land-type/mana-value/mana-cost/having group names `_SEARCH_AND_PUT_RE`
already uses so `_search_descriptions` reads both identically). Nothing in
that reader tags the exiled cards as "belonging" to the Saga - CR 607.2a's
own link is already fully generic (`models/game.py`'s `link_cards_exiled_
during`, called after *every* ability resolves): whenever an object has one
printed ability that instructs exiling and another that reads "the exiled
cards" or "exiled with [this object]", whatever that first ability newly put
into exile and left untagged is linked back to the object automatically.
Roads Go Ever, Ever On already carries both halves of that pair (chapter I's
own "exile them"; chapters II/III's own "exiled with this Saga"), so the
link happens with no code in this reader at all.

Chapters II and III are a new `_parse_linked_exile_clause` branch,
`_put_card_exiled_with_it_into_owners_hand_effect`: CR 714.2c already turns
"II, III — [Effect]" into two separate `TriggeredAbility`s of the identical
text, so one reader closes both chapters without needing to know that -
this file drives it twice, at two lore counters and then at three, the same
way `test_grand_evolution_saga.py` already drives its own multi-chapter
Saga one `Game.saga_lore_step()` at a time.

Every CR number below was looked up with `mise run rules:find` in the
session that wrote this file:

- **CR 714.2b/714.2c** - a chapter ability's own lore-counter threshold; a
  shared chapter line is two abilities with the same text.
- **CR 714.3a** - a Saga without read ahead enters with a lore counter,
  firing chapter I immediately.
- **CR 607.2a** - the linked-pile rule: an object with an exile-instructing
  ability and an "exiled with [this object]"-reading ability links the two.
- **CR 400.7** - a card's owner, read off the exiled card itself, is who it
  returns to.
- **CR 701.23a/701.23b** - the search itself: a stated-quality find,
  declinable.
- **CR 119.3** - chapter I's own life gain.

Proof printing for chapter I's own reader: **Kaho, Minamo Historian** (real
Scryfall data, added with `scripts/add_card.py`, not a listed card, not in
any `magic-cards-model-api/decks/*.txt` list, Modern `legal`) - "search your
library for up to three instant cards, exile them, then shuffle", a
different quality and count, on a creature's own ETB rather than a Saga
chapter, with no trailing life gain at all. No second printing on Scryfall
pairs "Put a card exiled with this Saga into its owner's hand" with a Saga
subtype other than Roads Go Ever, Ever On's own (checked in the session that
wrote this file); see the dated `MEMORY.md` line for that one reader.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def _resolve_all(scenario: Scenario) -> None:
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()


def test_chapter_one_exiles_two_plains_and_gains_life():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Roads Go Ever, Ever On"],
            battlefield=["Plains", "Plains"],
            library=["Plains", "Plains", "Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    plains_in_library = [state for state in alice.library if state.name == "Plains"]
    life_before = alice.life
    sources = scenario.untapped_sources("Plains", "Plains")

    scenario.will_choose_cards(
        *plains_in_library, username="alice", source="Roads Go Ever, Ever On"
    )
    scenario.cast_and_resolve("Roads Go Ever, Ever On", *sources)
    _resolve_all(scenario)

    saga = scenario.find("Roads Go Ever, Ever On", Zone.BATTLEFIELD, "alice")
    assert saga.counters[Counter.LORE] == 1
    for state in plains_in_library:
        assert state.zone is Zone.EXILE
        assert state.exile_annotation is not None
    assert alice.life == life_before + 2


def test_chapters_two_and_three_each_return_one_exiled_plains_to_hand():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Roads Go Ever, Ever On"],
            battlefield=["Plains", "Plains"],
            library=["Plains", "Plains", "Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    plains_in_library = [state for state in alice.library if state.name == "Plains"]
    sources = scenario.untapped_sources("Plains", "Plains")

    scenario.will_choose_cards(
        *plains_in_library, username="alice", source="Roads Go Ever, Ever On"
    )
    scenario.cast_and_resolve("Roads Go Ever, Ever On", *sources)
    _resolve_all(scenario)
    saga = scenario.find("Roads Go Ever, Ever On", Zone.BATTLEFIELD, "alice")
    assert saga.counters[Counter.LORE] == 1
    exiled_a, exiled_b = plains_in_library
    assert exiled_a.zone is Zone.EXILE
    assert exiled_b.zone is Zone.EXILE

    # Chapter II (CR 714.2b: the second lore counter).
    scenario.will_choose_cards(exiled_a, username="alice", source="Roads Go Ever, Ever On")
    scenario.game.saga_lore_step()
    assert saga.counters[Counter.LORE] == 2
    _resolve_all(scenario)

    assert exiled_a.zone is Zone.HAND
    assert exiled_b.zone is Zone.EXILE, "chapter III has not fired yet"

    # Chapter III (CR 714.2b: the third lore counter) - the one card left in
    # the linked pile is taken without a question (`Game.ask`'s own "one
    # legal answer" rule).
    scenario.game.saga_lore_step()
    assert saga.counters[Counter.LORE] == 3
    _resolve_all(scenario)

    assert exiled_b.zone is Zone.HAND


def test_kaho_minamo_historian_reads_the_same_search_and_exile_template():
    """Proof card: "search your library for up to three instant cards,
    exile them, then shuffle." on a creature's ETB, no trailing life gain."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Kaho, Minamo Historian"],
            battlefield=["Island"] * 4,
            library=["Opt", "Lightning Bolt", "Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    opt = next(state for state in alice.library if state.name == "Opt")
    bolt = next(state for state in alice.library if state.name == "Lightning Bolt")
    bears = next(state for state in alice.library if state.name == "Grizzly Bears")
    sources = scenario.untapped_sources(*(["Island"] * 4))

    scenario.will_choose_cards(opt, bolt, username="alice", source="Kaho, Minamo Historian")
    scenario.cast_and_resolve("Kaho, Minamo Historian", *sources)
    _resolve_all(scenario)

    assert opt.zone is Zone.EXILE
    assert bolt.zone is Zone.EXILE
    assert bears.zone is Zone.LIBRARY, "not an instant, never a candidate"
