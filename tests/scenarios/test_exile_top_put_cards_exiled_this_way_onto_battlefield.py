"""Exile the top N cards of your library, then put the qualifying ones
"exiled this way" onto the battlefield.

Deep Space 9 (trk): "When Deep Space 9 enters and at the beginning of your
upkeep, exile the top four cards of your library. Put all permanent cards
exiled this way onto the battlefield." The reader already took Tezzeret,
Master of the Bridge's "Put all artifact cards from among them onto the
battlefield." and Xenagos, the Reveler's "You may put any number of creature
and/or land cards from among them"; "exiled this way" is the same anaphor
spelled another way. No non-trk printing says "put all ... cards exiled this
way onto the battlefield" (Scryfall checked in the writing session), so the
board varies inside the one card: both of its trigger events, every kind of
permanent card, a short and an empty library.

CR rules looked up with `mise run rules:find` in the writing session:

- CR 110.4a: "permanent card" means "an artifact, battle, creature,
  enchantment, land, or planeswalker card".
- CR 406.1: the exile zone is a holding area; what is not put onto the
  battlefield stays exiled.
- CR 609.3: an effect that attempts something impossible does only as much
  as possible (a short library).
- CR 503.1a: abilities that trigger at the beginning of the upkeep go on the
  stack before the active player gets priority.
- CR 110.2a: an object put onto the battlefield enters under the control of
  the player the effect instructs.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _names(cards) -> list[str]:
    return [card.name for card in cards]


def _deep_space_9(library: list[str]) -> Scenario:
    return Scenario().player("alice", hand=["Deep Space 9"], library=library).player("bob")


def _enter(scenario) -> None:
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.put_onto_battlefield("Deep Space 9", "alice")
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()


def test_deep_space_9_puts_every_permanent_card_exiled_this_way_onto_the_battlefield() -> None:
    """A creature, an artifact and a land among the four all enter, untapped,
    under the controller's control; the instant stays in exile and the fifth
    card is never exiled."""
    scenario = _deep_space_9(["Grizzly Bears", "Opt", "Sol Ring", "Forest", "Island"]).build()
    _enter(scenario)

    alice = scenario.player("alice")
    for name in ("Grizzly Bears", "Sol Ring", "Forest"):
        permanent = scenario.find(name, Zone.BATTLEFIELD, "alice")
        assert permanent.controller == "alice"
        assert not permanent.tapped
    assert _names(scenario.game.exile) == ["Opt"]
    assert _names(alice.library) == ["Island"]
    assert not [q for q in scenario.questions_asked() if q.source == "Deep Space 9"], (
        '"all" asks nothing'
    )


def test_deep_space_9_with_no_permanent_card_leaves_all_four_in_exile() -> None:
    scenario = _deep_space_9(["Opt", "Shock", "Lightning Bolt", "Opt"]).build()
    _enter(scenario)

    assert scenario.battlefield_names() == ["Deep Space 9"]
    assert sorted(_names(scenario.game.exile)) == ["Lightning Bolt", "Opt", "Opt", "Shock"]


def test_deep_space_9_with_a_short_library_exiles_what_is_there() -> None:
    """Two cards left: both are exiled and the land among them enters
    (CR 609.3)."""
    scenario = _deep_space_9(["Mountain", "Shock"]).build()
    _enter(scenario)

    assert "Mountain" in scenario.battlefield_names()
    assert _names(scenario.game.exile) == ["Shock"]
    assert scenario.player("alice").library == []


def test_deep_space_9_with_an_empty_library_does_nothing() -> None:
    scenario = _deep_space_9([]).build()
    _enter(scenario)

    assert scenario.battlefield_names() == ["Deep Space 9"]
    assert scenario.game.exile == []


def test_deep_space_9_triggers_again_at_the_beginning_of_your_upkeep() -> None:
    """The second trigger event: at the beginning of its controller's upkeep
    it exiles the top four again and puts the permanent cards onto the
    battlefield (CR 503.1a)."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Deep Space 9"],
            library=["Opt", "Grizzly Bears", "Shock", "Plains", "Island"],
        )
        .player("bob")
        .build()
    )
    assert scenario.step is Step.UNTAP
    scenario.advance()  # the upkeep begins: the trigger goes on the stack
    assert scenario.step is Step.UPKEEP
    assert len(scenario.game.stack) == 1
    scenario.pass_until_resolved()

    assert sorted(scenario.battlefield_names()) == ["Deep Space 9", "Grizzly Bears", "Plains"]
    assert sorted(_names(scenario.game.exile)) == ["Opt", "Shock"]
    assert _names(scenario.player("alice").library) == ["Island"]
