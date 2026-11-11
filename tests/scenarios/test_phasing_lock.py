"""Scenario: "All artifacts and creatures phase out." and a token with
"Permanents can't phase in." (The City on the Edge of Forever).

CR 702.26b: a phased-out permanent is treated as though it does not exist;
CR 702.26c / 502.1: at its controller's untap step it phases back in. CR 101.2:
a "can't" beats that "does" - while the Human token is on the battlefield,
nothing phases in, for either player. Chapter III sacrifices a creature token
(the Human, if nothing else), after which the next untap steps phase each
player's permanents back in.

No other legal printing phases out every artifact and creature, and the only
other "can't phase in" (Teferi, Timeless Voyager's -8) is a duration on named
permanents (Scryfall, in the writing session) - not this static.

CR rules cited here were looked up with `mise run rules:find` in the writing
session: 702.26b, 702.26c, 502.1, 101.2, 715.2b (a chapter ability triggers as
lore counters are added).
"""

from magic_cards_model.machines import Step
from magic_cards_model.models.zone import Zone
from tests.scenarios.harness import Scenario


def board() -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=["The City on the Edge of Forever"],
            battlefield=["Plains"] * 3 + ["Swamp"] * 2 + ["Grizzly Bears", "Ornithopter"],
            library=["Island"] * 10,
        )
        .player("bob", battlefield=["Grizzly Bears", "Memnite", "Forest"], library=["Island"] * 10)
    )


def cast_city(scenario):
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve(
        "The City on the Edge of Forever",
        *scenario.untapped_sources("Plains", "Plains", "Plains", "Swamp", "Swamp"),
    )
    scenario.pass_until_resolved()  # chapter I


def next_main_of(scenario, username):
    """Advance to `username`'s next precombat main phase, resolving anything
    that goes on the stack on the way (a Saga's chapter, CR 715.2b)."""
    scenario.advance()
    while not (scenario.turn.active_player == username and scenario.step is Step.PRECOMBAT_MAIN):
        if scenario.stack_names():
            scenario.pass_until_resolved()
            continue
        scenario.advance()
    while scenario.stack_names():
        scenario.pass_until_resolved()


def test_chapter_one_phases_out_every_artifact_and_creature():
    scenario = board().build()
    alice_bears = scenario.creature("Grizzly Bears", "alice")
    ornithopter = scenario.creature("Ornithopter", "alice")
    bob_bears = scenario.creature("Grizzly Bears", "bob")
    memnite = scenario.creature("Memnite", "bob")
    cast_city(scenario)
    assert all(p.phased_out for p in (alice_bears, ornithopter, bob_bears, memnite))
    names = scenario.battlefield_names()
    assert "Human" in names, "the token is created after the phasing, so it is here"
    assert "Forest" in names and "Plains" in names, "lands are neither artifacts nor creatures"


def test_nothing_phases_in_while_the_human_token_is_there():
    scenario = board().automatic_turn_based_actions().build()
    bob_bears = scenario.creature("Grizzly Bears", "bob")
    alice_bears = scenario.creature("Grizzly Bears", "alice")
    cast_city(scenario)
    next_main_of(scenario, "bob")
    assert bob_bears.phased_out, "bob's untap step: the token says permanents can't phase in"
    next_main_of(scenario, "alice")
    assert alice_bears.phased_out


def test_the_city_on_the_edge_of_forever_chapters_and_the_return():
    """II: alice draws two and each player loses 2. III: alice sacrifices a
    creature token (the Human) and gains 5; the Saga goes. The next untap steps
    phase each player's permanents back in."""
    scenario = board().automatic_turn_based_actions().build()
    bob_bears = scenario.creature("Grizzly Bears", "bob")
    alice_bears = scenario.creature("Grizzly Bears", "alice")
    cast_city(scenario)
    next_main_of(scenario, "alice")  # chapter II
    assert scenario.player("alice").life == 18
    assert scenario.player("bob").life == 18
    assert len(scenario.player("alice").hand) == 3, "her draw step plus two"
    next_main_of(scenario, "alice")  # chapter III
    assert "Human" not in scenario.battlefield_names()
    assert scenario.player("alice").life == 23
    assert "The City on the Edge of Forever" not in scenario.battlefield_names()
    assert alice_bears.phased_out, "alice's untap step came before chapter III"
    next_main_of(scenario, "bob")
    assert not bob_bears.phased_out
    assert bob_bears.zone is Zone.BATTLEFIELD
    next_main_of(scenario, "alice")
    assert not alice_bears.phased_out
