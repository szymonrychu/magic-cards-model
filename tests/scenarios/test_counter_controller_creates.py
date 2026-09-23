"""Scenario: "Counter target `<types>` spell. Its controller creates `<token>`."

Strix Serenade, Swan Song and An Offer You Can't Refuse print the same
template: a counterspell whose second sentence hands a token to the
*countered spell's* controller - not to the counterspell's caster. The
second sentence is CR 400.7's anaphora back to the first sentence's own
target, read by `_parse_anaphoric_clause_pair` in `machines/effects.py`, the
same reader Crib Swap's "Exile target creature. Its controller creates ..."
already goes through on the permanent side.

Every CR number below was looked up with `mise run rules:find` in the session
that wrote this file.

- **CR 701.6a** - "To counter a spell or ability means to cancel it, removing
  it from the stack. ... A countered spell is put into its owner's
  graveyard."
- **CR 111.2** - "The player who creates a token is its owner. The token
  enters the battlefield under that player's control." - the Bird is the
  countered spell's controller's, not the caster's.
- **CR 113.6g** - "An object's ability that states it can't be countered ...
  functions on the stack." A spell that can't be countered stays put, but
  the printed rulings (Strix Serenade 2024-06-07, Swan Song 2013-09-15, An
  Offer You Can't Refuse 2022-04-29) say its controller still gets the token.
- **CR 608.2b** - a target that left the stack is illegal; with no legal
  target the counterspell does not resolve, so nobody gets a token.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Color
from tests.scenarios.harness import PlayedScenario, Scenario

ALICE_LANDS = [
    "Forest",
    "Forest",
    "Forest",
    "Forest",
    "Forest",
    "Island",
    "Island",
    "Swamp",
    "Mountain",
]


def board(alice_hand: list[str], bob_hand: list[str]) -> PlayedScenario:
    """Alice casts the spell; Bob holds the counterspell, four Islands and a Mind Stone."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=alice_hand, battlefield=ALICE_LANDS + ["Plains", "Plains"])
        .player(
            "bob", hand=bob_hand, battlefield=["Island", "Island", "Island", "Island", "Mind Stone"]
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def tokens_of(scenario: PlayedScenario, username: str) -> list:
    return [state for state in scenario.game.permanents_controlled_by(username) if state.token]


def cast_alices(scenario: PlayedScenario, name: str):
    spell = scenario.cast_onto_stack(name, username="alice", auto=True)
    scenario.pass_priority("alice")
    return spell


# -- Strix Serenade -----------------------------------------------------------


def test_strix_serenade_counters_a_creature_spell_and_its_controller_gets_the_bird():
    scenario = board(["Grizzly Bears"], ["Strix Serenade"])
    bears = cast_alices(scenario, "Grizzly Bears")

    scenario.cast_and_resolve("Strix Serenade", username="bob", auto=True, targets=[bears])

    assert bears.zone is Zone.GRAVEYARD
    (bird,) = tokens_of(scenario, "alice")
    assert bird.name == "Bird Token"
    assert (bird.card.power, bird.card.toughness) == ("2", "2")
    assert list(bird.colors) == [Color.BLUE]
    assert bird.card.keywords == ["Flying"]
    assert bird.owner == "alice"
    assert tokens_of(scenario, "bob") == [], "the caster of Strix Serenade gets nothing"


def test_strix_serenade_counters_an_artifact_spell():
    scenario = board(["Mind Stone"], ["Strix Serenade"])
    stone = cast_alices(scenario, "Mind Stone")

    scenario.cast_and_resolve("Strix Serenade", username="bob", auto=True, targets=[stone])

    assert stone.zone is Zone.GRAVEYARD
    assert [token.name for token in tokens_of(scenario, "alice")] == ["Bird Token"]


def test_strix_serenade_counters_a_planeswalker_spell():
    scenario = board(["Jace Beleren"], ["Strix Serenade"])
    jace = cast_alices(scenario, "Jace Beleren")

    scenario.cast_and_resolve("Strix Serenade", username="bob", auto=True, targets=[jace])

    assert jace.zone is Zone.GRAVEYARD
    assert [token.name for token in tokens_of(scenario, "alice")] == ["Bird Token"]


def test_strix_serenade_cannot_target_an_instant():
    """The comma list "artifact, creature, or planeswalker" is the whole
    restriction (CR 601.2c): an instant is not a legal target."""
    scenario = board(["Lightning Bolt"], ["Strix Serenade"])
    bolt = scenario.cast_onto_stack("Lightning Bolt", username="alice", auto=True, targets=["bob"])
    scenario.pass_priority("alice")

    with pytest.raises(ValueError):
        scenario.cast("Strix Serenade", username="bob").choose_targets([bolt])


def test_an_uncounterable_creature_spell_stays_but_its_controller_still_gets_the_bird():
    """Balustrade Wurm can't be countered (CR 113.6g). Strix Serenade
    2024-06-07: "That spell won't be countered ... but its controller will
    get a Bird token." """
    scenario = board(["Balustrade Wurm"], ["Strix Serenade"])
    wurm = cast_alices(scenario, "Balustrade Wurm")

    scenario.cast_and_resolve("Strix Serenade", username="bob", auto=True, targets=[wurm])

    assert wurm.zone is Zone.STACK
    assert [token.name for token in tokens_of(scenario, "alice")] == ["Bird Token"]
    permanent = scenario.resolve_top()
    assert permanent.zone is Zone.BATTLEFIELD


def test_a_counterspell_whose_target_is_gone_makes_no_bird():
    """CR 608.2b: the second Strix Serenade resolves first and counters the
    bears; the first one then has no legal target, does not resolve, and
    creates nothing - one Bird in total, not two."""
    scenario = board(["Grizzly Bears"], ["Strix Serenade", "Strix Serenade"])
    bears = cast_alices(scenario, "Grizzly Bears")

    first = scenario.cast_onto_stack("Strix Serenade", username="bob", auto=True, targets=[bears])
    scenario.cast_and_resolve("Strix Serenade", username="bob", auto=True, targets=[bears])
    assert bears.zone is Zone.GRAVEYARD
    scenario.resolve_top()

    assert first.zone is Zone.GRAVEYARD
    assert [token.name for token in tokens_of(scenario, "alice")] == ["Bird Token"]
    assert tokens_of(scenario, "bob") == []


def test_countering_your_own_spell_gives_you_the_bird():
    """ "Its controller" is whoever controls the countered spell - here Bob
    counters his own Opt with Swan Song, so the Bird is his."""
    scenario = board([], ["Opt", "Swan Song"])
    scenario.pass_priority("alice")
    (first_island,) = scenario.untapped_sources("Island", username="bob")
    opt = scenario.cast_onto_stack("Opt", first_island, username="bob")
    (second_island,) = scenario.untapped_sources("Island", username="bob")

    scenario.cast_and_resolve("Swan Song", second_island, username="bob", targets=[opt])

    assert opt.zone is Zone.GRAVEYARD
    assert [token.name for token in tokens_of(scenario, "bob")] == ["Bird Token"]
    assert tokens_of(scenario, "alice") == []


# -- Swan Song: a second printing, the other half of the type spectrum -----


def test_swan_song_counters_an_enchantment_and_gives_its_controller_a_bird():
    scenario = board(["Glorious Anthem"], ["Swan Song"])
    anthem = cast_alices(scenario, "Glorious Anthem")

    scenario.cast_and_resolve("Swan Song", username="bob", auto=True, targets=[anthem])

    assert anthem.zone is Zone.GRAVEYARD
    (bird,) = tokens_of(scenario, "alice")
    assert bird.name == "Bird Token"
    assert bird.card.keywords == ["Flying"]


def test_swan_song_cannot_target_a_creature_spell():
    scenario = board(["Grizzly Bears"], ["Swan Song"])
    bears = cast_alices(scenario, "Grizzly Bears")

    with pytest.raises(ValueError):
        scenario.cast("Swan Song", username="bob").choose_targets([bears])


# -- An Offer You Can't Refuse: a predefined token, a count, "non" qualifier -


def test_an_offer_you_cant_refuse_gives_the_spells_controller_two_treasures():
    scenario = board(["Opt"], ["An Offer You Can't Refuse"])
    opt = cast_alices(scenario, "Opt")

    scenario.cast_and_resolve("An Offer You Can't Refuse", username="bob", auto=True, targets=[opt])

    assert opt.zone is Zone.GRAVEYARD
    assert sorted(token.name for token in tokens_of(scenario, "alice")) == [
        "Treasure Token",
        "Treasure Token",
    ]
    assert tokens_of(scenario, "bob") == []


def test_an_offer_you_cant_refuse_on_an_uncounterable_spell_still_makes_treasures():
    """An Offer You Can't Refuse 2022-04-29: "If the target is still legal as
    it resolves but the spell can't be countered for some reason, its
    controller will still create two Treasure tokens." """
    scenario = board(["Abrupt Decay"], ["An Offer You Can't Refuse"])
    stone = scenario.find("Mind Stone", Zone.BATTLEFIELD, "bob")
    decay = scenario.cast_onto_stack("Abrupt Decay", username="alice", auto=True, targets=[stone])
    scenario.pass_priority("alice")

    scenario.cast_and_resolve(
        "An Offer You Can't Refuse", username="bob", auto=True, targets=[decay]
    )

    assert decay.zone is Zone.STACK
    assert sorted(token.name for token in tokens_of(scenario, "alice")) == [
        "Treasure Token",
        "Treasure Token",
    ]
