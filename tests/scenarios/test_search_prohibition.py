"""Scenario: Ashiok, Dream Render's "Spells and abilities your opponents
control can't cause their controller to search their library."

CR 701.23 is Search; no rule narrower than that names this specific
prohibition, so CR 101.2's ordinary "when a rule or effect allows or directs
something to happen, and another effect states that it can't happen, the
'can't' effect takes precedence" is what makes it bind, exactly the way every
other continuous "can't" in this pool already works.

The grammar is narrow on purpose: "their controller"/"their library" both
name the *same* person - the controller of the spell or ability doing the
causing. That is a *self*-search (a fetchland, a tutor: "search **your**
library"), and it is the only shape this static reaches. A Bribery-style
"search **target opponent's** library" names a different searcher than the
spell's own controller and is deliberately untouched - not tested here
because no such printing is in this pool, but the reader
(`machines.casting_restrictions.search_prohibition_source`) is asked only
when the searcher and the causer are the same player, which is what keeps
that door shut.

`Diabolic Tutor` is the generality proof: a plain, unrelated sorcery ("Search
your library for a card, put that card into your hand, then shuffle.") that
exercises the shared `Game.search_and_put`/`_search_and_place_for` funnel
every ordinary tutor and fetchland in this engine already goes through - the
mechanism is wired into that funnel once, not into Ashiok's own card.
"""

from magic_cards_model.machines import Step
from tests.scenarios.harness import Scenario


def _board(*, ashiok_for: str) -> Scenario:
    alice_battlefield = ["Swamp"] * 4
    bob_battlefield = ["Swamp"] * 4
    if ashiok_for == "alice":
        alice_battlefield.append("Ashiok, Dream Render")
    else:
        bob_battlefield.append("Ashiok, Dream Render")
    return (
        Scenario()
        .player(
            "alice",
            hand=["Diabolic Tutor"],
            battlefield=alice_battlefield,
            library=["Mountain"] * 6,
        )
        .player(
            "bob",
            hand=["Diabolic Tutor"],
            battlefield=bob_battlefield,
            library=["Mountain"] * 6,
        )
        .build()
    )


def test_an_opponents_tutor_is_refused_the_whole_search():
    """Ashiok is alice's; bob is her opponent, so his own Diabolic Tutor's
    self-search is stopped outright - nothing found, nothing shuffled."""
    scenario = _board(ashiok_for="alice")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    # A sorcery needs its own controller's main phase (CR 307.1) - advance to
    # bob's own precombat main before he tries to cast it.
    while scenario.turn.active_player != "bob" or scenario.step is not Step.PRECOMBAT_MAIN:
        scenario.advance()
    library_before = list(scenario.player("bob").library)
    hand_before = len(scenario.player("bob").hand)
    sources = scenario.untapped_sources("Swamp", "Swamp", "Swamp", "Swamp", username="bob")

    scenario.cast_and_resolve("Diabolic Tutor", *sources, username="bob")

    assert len(scenario.player("bob").hand) == hand_before - 1, (
        "Diabolic Tutor itself left the hand to be cast; nothing was found to replace it"
    )
    assert scenario.player("bob").library == library_before, (
        "the library is untouched - not even shuffled"
    )


def test_its_own_controllers_tutor_works_normally():
    """ "Your opponents" - alice, who controls Ashiok, tutors freely."""
    scenario = _board(ashiok_for="alice")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Swamp", "Swamp", "Swamp", "Swamp", username="alice")
    library_before = len(scenario.player("alice").library)

    scenario.cast_and_resolve("Diabolic Tutor", *sources, username="alice")

    assert len(scenario.player("alice").library) == library_before - 1, "one card left the library"


def test_with_no_ashiok_a_search_proceeds_normally():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Diabolic Tutor"],
            battlefield=["Swamp"] * 4,
            library=["Mountain"] * 6,
        )
        .player("bob", battlefield=["Swamp"] * 4, library=["Mountain"] * 6)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Swamp", "Swamp", "Swamp", "Swamp", username="alice")
    library_before = len(scenario.player("alice").library)

    scenario.cast_and_resolve("Diabolic Tutor", *sources, username="alice")

    assert len(scenario.player("alice").library) == library_before - 1


def test_the_reader_names_ashiok_as_the_restricting_source():
    from magic_cards_model.machines.casting_restrictions import search_prohibition_source

    scenario = _board(ashiok_for="alice")

    assert search_prohibition_source(scenario.game, "bob") == "Ashiok, Dream Render"
    assert search_prohibition_source(scenario.game, "alice") is None


def test_the_prohibition_dies_with_ashiok():
    scenario = _board(ashiok_for="alice")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    while scenario.turn.active_player != "bob" or scenario.step is not Step.PRECOMBAT_MAIN:
        scenario.advance()
    (ashiok,) = [c for c in scenario.game.battlefield if c.name == "Ashiok, Dream Render"]
    scenario.game.destroy(ashiok)
    sources = scenario.untapped_sources("Swamp", "Swamp", "Swamp", "Swamp", username="bob")
    library_before = len(scenario.player("bob").library)

    scenario.cast_and_resolve("Diabolic Tutor", *sources, username="bob")

    assert len(scenario.player("bob").library) == library_before - 1
