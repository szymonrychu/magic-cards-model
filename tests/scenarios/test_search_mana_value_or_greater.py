"""A library search bounded by a mana-value *floor* - "with mana value N or
greater" - inside the "reveal it, [then shuffle and] put it into your
hand/on top" tutor family. `_SEARCH_AND_PUT_RE`/`_SEARCH_REVEAL_SHUFFLE_TOP_RE`
(`machines/effects.py`) already read "with mana value N or less" (Ranger-
Captain of Eos's own ceiling), but only that one direction - a card printing
the same clause with "or greater" (a floor, not a ceiling) failed to match at
all and fell through to a silent no-op, never even reaching `NOTICE`.

Conduit of Ruin is the reported card (R0a-T3's own scope-audit finding): its
cast trigger "you may search your library for a colorless creature card with
mana value 7 or greater, reveal it, then shuffle and put that card on top" is
`_SEARCH_REVEAL_SHUFFLE_TOP_RE`'s shape (the Loyal Tutor/Mystical Tutor
family, see `test_fra_s8_search_reveal_shuffle_top.py`) with a floor instead
of a ceiling. Fierce Empath is the off-pool, non-reported proof: a real,
Standard/Pioneer/Modern-legal printing of the *other* destination
(`_SEARCH_AND_PUT_RE`'s "into your hand" family) carrying the identical
floor - "you may search your library for a creature card with mana value 6
or greater, reveal it, put it into your hand, then shuffle" - so the fix
generalizes across both search-destination templates, not just the reported
card's own sentence.

Every CR number below was looked up with `mise run rules:find` in the
session that wrote this file.

- **CR 202.3** - mana value, the number `_bounded_quality_matcher` compares.
- **CR 701.23a** - "find a card that matches the given description" - a
  mana-value floor is part of the stated description, the same as a ceiling.
- **CR 701.23b** - a stated-quality search is declinable per find; nothing
  legal in the library means no card is taken.
- **CR 701.20a/701.20b** - a printed "reveal" shows the find to all players
  without moving it.
- **CR 701.24a** - the library is shuffled after the search removes the find.
- **CR 701.20d/CR 401.2** - "then shuffle and put that card on top" puts the
  find back above every card already there, in the shuffled library.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _resolve_everything(scenario: Scenario) -> None:
    game = scenario.game
    for _ in range(10):
        game.put_triggers_on_stack()
        if not game.stack:
            return
        scenario.pass_until_resolved()


# -- the reported card (R0a-T3) -----------------------------------------------


def test_conduit_of_ruin_finds_a_colorless_creature_at_or_above_the_floor():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Conduit of Ruin"],
            library=["World Breaker", "Grizzly Bears"],
            battlefield=["Wastes"] * 6,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    breaker = scenario.find("World Breaker", Zone.LIBRARY, "alice")
    scenario.will_take_the_may(True, username="alice", source="Conduit of Ruin")
    scenario.will_choose_cards(breaker, username="alice", source="Conduit of Ruin")

    scenario.cast_and_resolve("Conduit of Ruin", *scenario.untapped_sources(*["Wastes"] * 6))
    _resolve_everything(scenario)

    (reveal,) = [r for r in scenario.game.reveals if r.card_name == "World Breaker"]
    assert reveal.zone is Zone.LIBRARY
    assert breaker.zone is Zone.LIBRARY
    assert alice.library[0] is breaker, "CR 701.20d/401.2: the find sits on top"
    assert [state.name for state in alice.library] == ["World Breaker", "Grizzly Bears"]


def test_conduit_of_ruin_declines_when_nothing_clears_the_floor():
    """Grizzly Bears alone: mana value 2 and green, so no legal find exists -
    CR 701.23b lets the search come up empty rather than forcing a bad take,
    and `Game.may`'s own `affirmative_is_legal` (see `_search_and_place_for`'s
    docstring family) makes "no" the only legal answer in the first place."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Conduit of Ruin"],
            library=["Grizzly Bears"],
            battlefield=["Wastes"] * 6,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")

    scenario.cast_and_resolve("Conduit of Ruin", *scenario.untapped_sources(*["Wastes"] * 6))
    _resolve_everything(scenario)

    assert [state.name for state in alice.library] == ["Grizzly Bears"]
    assert scenario.game.reveals == []


# -- generality: the other search-destination template, an off-pool printing --


def test_fierce_empath_finds_a_creature_at_or_above_the_floor():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Fierce Empath"],
            library=["World Breaker", "Grizzly Bears"],
            battlefield=["Forest", "Forest", "Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    breaker = scenario.find("World Breaker", Zone.LIBRARY, "alice")
    scenario.will_take_the_may(True, username="alice", source="Fierce Empath")
    scenario.will_choose_cards(breaker, username="alice", source="Fierce Empath")

    scenario.cast_and_resolve("Fierce Empath", *scenario.untapped_sources(*["Forest"] * 3))
    _resolve_everything(scenario)

    assert breaker.zone is Zone.HAND
    assert [state.name for state in alice.library] == ["Grizzly Bears"]


def test_fierce_empath_leaves_a_creature_under_the_floor_behind():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Fierce Empath"],
            library=["Grizzly Bears"],
            battlefield=["Forest", "Forest", "Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")

    scenario.cast_and_resolve("Fierce Empath", *scenario.untapped_sources(*["Forest"] * 3))
    _resolve_everything(scenario)

    assert alice.hand == []
    assert [state.name for state in alice.library] == ["Grizzly Bears"]
