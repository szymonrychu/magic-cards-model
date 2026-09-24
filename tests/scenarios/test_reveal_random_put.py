"""Getaway Barrel: "When this artifact is put into a graveyard from the
battlefield, reveal the top thirteen cards of your library. Put a random
creature card from among them onto the battlefield. Put the rest on the
bottom of your library in a random order."

CR 700.4's own "dies" wording, spelled out rather than the shorthand -
`machines/triggers.py` already reads it as the identical `TriggerEvent.DIES`
condition either way, so the only gap was the effect body itself:
`_parse_reveal_top_n_put_random_kind_clause` (`_REVEAL_TOP_N_PUT_RANDOM_
KIND_RE`), a new reader shaped like the existing `_parse_reveal_top_n_one_
per_card_type_clause` above it (reveal the top N, do something with them,
bottom the rest in a random order) with the middle step replaced: no
question is asked at all, because "a random" card is the engine's own
choice, not the controller's - the printed word itself, not a numbered
rule (the Comprehensive Rules never define "random" as a term; it is
plain English throughout, the same way "shuffle" is the only randomising
verb CR 701.24a gives a number to).

Every CR number below was looked up with `mise run rules:find` in the
session that wrote this file:

- **CR 700.4** - "dies" means "is put into a graveyard from the
  battlefield" - the same event this card spells out in full.
- **CR 701.20a** - revealing a card does not move it or change its zone.
- **CR 701.24a** - the remainder's random order is a real randomisation, not
  a shuffle of the whole library (nothing here is called "shuffle", so
  nothing watching for CR 701.24a's own verb fires).

No second printing on Scryfall pairs "reveal the top N cards" with "put a
random `<kind>` card from among them onto the battlefield. Put the rest on
the bottom ..." (checked in the session that wrote this file) - see the
dated `MEMORY.md` line.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _resolve_all(scenario: Scenario) -> None:
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()


def test_the_one_creature_among_the_revealed_cards_reaches_the_battlefield():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=["Getaway Barrel"],
            library=["Mountain", "Lightning Bolt", "Grizzly Bears", "Opt", "Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    barrel = scenario.find("Getaway Barrel", Zone.BATTLEFIELD, "alice")
    bears = next(state for state in alice.library if state.name == "Grizzly Bears")
    rest = [state for state in alice.library if state is not bears]

    scenario.game.sacrifice(barrel)
    _resolve_all(scenario)

    assert bears.zone is Zone.BATTLEFIELD, "the only creature among the revealed cards"
    assert bears.controller == "alice"
    for state in rest:
        assert state.zone is Zone.LIBRARY
    assert len(alice.library) == len(rest)


def test_no_creature_among_the_revealed_cards_puts_nothing_onto_the_battlefield():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=["Getaway Barrel"],
            library=["Mountain", "Lightning Bolt", "Opt", "Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    barrel = scenario.find("Getaway Barrel", Zone.BATTLEFIELD, "alice")
    original = list(alice.library)

    scenario.game.sacrifice(barrel)
    _resolve_all(scenario)

    on_battlefield = [
        state for state in scenario.game.battlefield if state.name != "Getaway Barrel"
    ]
    assert on_battlefield == [], "no creature was revealed, so nothing is put anywhere"
    for state in original:
        assert state.zone is Zone.LIBRARY
    assert len(alice.library) == len(original)


def test_multiple_creatures_put_exactly_one_of_them_onto_the_battlefield():
    """The engine's own random choice among every qualifying candidate -
    not the first, not the controller's pick."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=["Getaway Barrel"],
            library=["Grizzly Bears", "Elvish Mystic", "Mountain", "Opt"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    barrel = scenario.find("Getaway Barrel", Zone.BATTLEFIELD, "alice")
    bears = next(state for state in alice.library if state.name == "Grizzly Bears")
    mystic = next(state for state in alice.library if state.name == "Elvish Mystic")

    scenario.game.sacrifice(barrel)
    _resolve_all(scenario)

    on_battlefield = [state for state in (bears, mystic) if state.zone is Zone.BATTLEFIELD]
    assert len(on_battlefield) == 1, "exactly one of the two creatures, never both, never neither"
    other = mystic if on_battlefield[0] is bears else bears
    assert other.zone is Zone.LIBRARY
