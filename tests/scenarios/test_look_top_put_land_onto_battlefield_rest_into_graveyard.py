"""Look at (or reveal) the top N cards, put a land card from among them onto
the battlefield tapped, and the rest into the graveyard.

One shape, two printings worded differently:

- Hit It! (trk), an enters trigger: "look at the top five cards of your
  library. Put a land card from among them onto the battlefield tapped and
  the rest into your graveyard." - a *mandatory* put, the rest joined to it
  by "and" in the same sentence.
- Shigeki, Jukai Visionary (tdc), an activated ability: "Reveal the top four
  cards of your library. You may put a land card from among them onto the
  battlefield tapped. Put the rest into your graveyard." - a reveal, an
  *optional* put, and the rest as its own sentence.

Before this file the look-top-put reader took only "put the rest on the
bottom of your library", so both cards did nothing at all.

CR rules looked up with `mise run rules:find` in the writing session:

- CR 701.20a: "To reveal a card, show that card to all players for a brief
  time." CR 701.20b: "Revealing a card doesn't cause it to leave the zone
  it's in."
- CR 608.2d: the player announces choices while applying the effect and
  "can't choose an option that's illegal or impossible".
- CR 609.3: "If an effect attempts to do something impossible, it does only
  as much as possible."
- CR 110.2a: an object put onto the battlefield enters under that player's
  control unless the effect states otherwise.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import DecisionKind
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _hit_it(library: list[str]) -> Scenario:
    return Scenario().player("alice", hand=["Hit It!"], library=library).player("bob")


def _enter_hit_it(scenario) -> None:
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.put_onto_battlefield("Hit It!", "alice")
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()


def _names(cards) -> list[str]:
    return [card.name for card in cards]


def test_hit_it_puts_the_chosen_land_onto_the_battlefield_tapped_and_bins_the_rest() -> None:
    """Two lands among the five: the controller chooses one (CR 608.2d), it
    enters tapped, and the other four looked-at cards go to the graveyard.
    The sixth card was never looked at and stays on top."""
    scenario = _hit_it(["Opt", "Forest", "Shock", "Island", "Grizzly Bears", "Mountain"]).build()
    island = scenario.player("alice").library[3]
    scenario.will_choose_cards(island, source="Hit It!")
    _enter_hit_it(scenario)

    alice = scenario.player("alice")
    assert island.zone is Zone.BATTLEFIELD
    assert island.tapped
    assert island.controller == "alice"
    assert sorted(_names(alice.graveyard)) == ["Forest", "Grizzly Bears", "Opt", "Shock"]
    assert _names(alice.library) == ["Mountain"]
    asked = [q for q in scenario.questions_asked() if q.kind is DecisionKind.CHOOSE_CARDS]
    assert len(asked) == 1
    names_by_id = {card.id: card.name for card in scenario.all_card_states()}
    assert sorted(names_by_id[card_id] for card_id in asked[0].cards) == [
        "Forest",
        "Island",
    ], "only the land cards are offered"


def test_hit_it_with_one_land_puts_it_without_asking() -> None:
    """A mandatory "put a land card" with exactly one land among them leaves
    no choice to make, so nothing is asked."""
    scenario = _hit_it(["Opt", "Shock", "Forest", "Opt", "Shock"]).build()
    _enter_hit_it(scenario)

    alice = scenario.player("alice")
    forest = scenario.find("Forest", Zone.BATTLEFIELD, "alice")
    assert forest.tapped
    assert sorted(_names(alice.graveyard)) == ["Opt", "Opt", "Shock", "Shock"]
    assert alice.library == []
    assert not [q for q in scenario.questions_asked() if q.kind is DecisionKind.CHOOSE_CARDS]


def test_hit_it_with_no_land_puts_every_looked_at_card_into_the_graveyard() -> None:
    """No land among the five: the put is impossible and does nothing
    (CR 609.3); "the rest" is all five."""
    scenario = _hit_it(["Opt", "Shock", "Grizzly Bears", "Opt", "Shock", "Forest"]).build()
    _enter_hit_it(scenario)

    alice = scenario.player("alice")
    assert scenario.battlefield_names() == ["Hit It!"]
    assert sorted(_names(alice.graveyard)) == ["Grizzly Bears", "Opt", "Opt", "Shock", "Shock"]
    assert _names(alice.library) == ["Forest"], "the sixth card is never looked at"


def test_hit_it_with_a_short_library_looks_at_what_is_there() -> None:
    """Two cards in the library: only those two are looked at (CR 609.3)."""
    scenario = _hit_it(["Shock", "Island"]).build()
    _enter_hit_it(scenario)

    alice = scenario.player("alice")
    assert scenario.find("Island", Zone.BATTLEFIELD, "alice").tapped
    assert _names(alice.graveyard) == ["Shock"]
    assert alice.library == []


def test_hit_it_with_an_empty_library_does_nothing() -> None:
    scenario = _hit_it([]).build()
    _enter_hit_it(scenario)

    alice = scenario.player("alice")
    assert scenario.battlefield_names() == ["Hit It!"]
    assert alice.graveyard == []


def _shigeki(library: list[str]) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            battlefield=["Shigeki, Jukai Visionary", "Forest", "Forest"],
            library=library,
        )
        .player("bob")
    )


def _activate_shigeki(scenario) -> None:
    scenario.start_at(Step.PRECOMBAT_MAIN)
    shigeki = scenario.find("Shigeki, Jukai Visionary", Zone.BATTLEFIELD, "alice")
    scenario.activate(shigeki, *scenario.untapped_sources("Forest", "Forest"))
    scenario.pass_until_resolved()


def test_shigeki_reveals_and_may_put_a_land_tapped_then_bins_the_rest() -> None:
    """The reveal shows all four cards (CR 701.20a), the optional put takes
    the chosen land onto the battlefield tapped, and the rest of the
    revealed cards go to the graveyard."""
    scenario = _shigeki(["Opt", "Island", "Shock", "Forest", "Mountain"]).build()
    island = scenario.player("alice").library[1]
    scenario.will_choose_cards(island, source="Shigeki, Jukai Visionary")
    _activate_shigeki(scenario)

    alice = scenario.player("alice")
    assert island.zone is Zone.BATTLEFIELD
    assert island.tapped
    assert sorted(_names(alice.graveyard)) == ["Forest", "Opt", "Shock"]
    assert _names(alice.library) == ["Mountain"]
    assert "Shigeki, Jukai Visionary" in _names(alice.hand), "returned as part of the cost"
    assert sorted(
        reveal.card_name
        for reveal in scenario.game.reveals
        if reveal.source == "Shigeki, Jukai Visionary" and reveal.viewers is None
    ) == ["Forest", "Island", "Opt", "Shock"], "shown to all players, once each"


def test_shigeki_declining_the_put_bins_all_four() -> None:
    """ "You may" (CR 608.2d): choosing no land puts nothing onto the
    battlefield, and all four revealed cards are the rest."""
    scenario = _shigeki(["Opt", "Island", "Shock", "Forest"]).build()
    scenario.will_choose_cards(source="Shigeki, Jukai Visionary")
    _activate_shigeki(scenario)

    alice = scenario.player("alice")
    assert sorted(_names(alice.graveyard)) == ["Forest", "Island", "Opt", "Shock"]
    assert sorted(scenario.battlefield_names()) == ["Forest", "Forest"]
