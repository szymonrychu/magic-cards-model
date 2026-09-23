"""Scenario: recruit, the keyword action, and what its "if" actually reads.

Recruit is three instructions in one word, and the third depends on the outcome
of the second. That is the whole reason it needs a file: an engine that assumed
the discard rather than reading it back would create a token off a discarded
land, and an engine that discarded before drawing would refuse a recruit from an
empty hand that the draw was about to fill.

Every CR number below was looked up with `knowledge_search(q="...",
type="rules")` in the session that wrote this file.

- **CR 701.70a** - ""Recruit" means "Draw a card, then discard a card. If you
  discarded a nonland card this way, create a 1/1 white Human Soldier creature
  token.""
- **CR 701.9a** - "To discard a card, move it from its owner's hand to that
  player's graveyard."
- **CR 701.9b** - the discarding player chooses which card, unless the effect
  says otherwise. Recruit does not, so the choice is answered by the harness.
- **CR 121.4** - "A player who attempts to draw a card from a library with no
  cards in it loses the game the next time a player would receive priority."
- **CR 704.5b** - the state-based action that carries that out: "If a player
  attempted to draw a card from a library with no cards in it since the last
  time state-based actions were checked, that player loses the game."
- **CR 700.4** - "dies" means "is put into a graveyard from the battlefield".
- **CR 603.10a** - a dies-trigger looks back in time, so the ability triggers
  even though its source is already in the graveyard when it does.
- **CR 111.2** - the player who creates a token is its owner and controller.

The card is Lake-town Lookout, a 1/1 white Human Scout: "When this creature
dies, recruit." It is killed with Lightning Bolt, which is the whole of the
setup in every test here.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Color, Type
from magic_cards_model.models.token import is_token
from tests.scenarios.harness import Scenario

TOKEN = "Human Soldier Token"


def _board(*library: str, hand: list[str] | None = None) -> Scenario:
    """Alice holding the Lookout's executioner, with a library to draw from."""
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            library=list(library),
            hand=["Lightning Bolt", *(hand or [])],
            battlefield=["Lake-town Lookout", "Mountain"],
        )
        .player("bob", life=20)
    )


def _kill_the_lookout(scenario):
    """Bolt the Lookout, then resolve the dies-trigger it leaves behind."""
    scenario.start_at(Step.PRECOMBAT_MAIN)
    lookout = scenario.creature("Lake-town Lookout", "alice")
    (mountain,) = scenario.untapped_sources("Mountain")
    scenario.cast_and_resolve("Lightning Bolt", mountain, targets=[lookout])
    assert lookout.zone is Zone.GRAVEYARD
    assert scenario.stack_names() == ["Lake-town Lookout's triggered ability"]
    scenario.resolve_top()
    return lookout


def _hand_names(scenario) -> list[str]:
    return [state.card.name for state in scenario.player("alice").hand]


def _graveyard_names(scenario) -> list[str]:
    return [state.card.name for state in scenario.player("alice").graveyard]


def test_discarding_a_nonland_creates_the_soldier():
    """The happy path (CR 701.70a), and the token's own characteristics.

    A 1/1 white Human Soldier creature token - every one of those words is a
    separate thing the engine has to get right, and none of them is printed on
    Lake-town Lookout, so they come from the keyword's own definition.
    """
    scenario = _board("Forest", hand=["Llanowar Elves"]).build()
    (elves,) = [
        state for state in scenario.player("alice").hand if state.card.name == "Llanowar Elves"
    ]
    scenario.will_discard(elves)

    _kill_the_lookout(scenario)

    token = scenario.find(TOKEN, Zone.BATTLEFIELD, "alice")
    assert is_token(token)
    assert token.card.colors == [Color.WHITE]
    assert Type.CREATURE in token.card.types
    assert token.card.subtypes == ["Human", "Soldier"]
    assert scenario.game.power_of(token) == 1
    assert scenario.game.toughness_of(token) == 1
    assert token.controller == "alice"  # CR 111.2
    assert _hand_names(scenario) == ["Forest"]  # the drawn card stayed


def test_discarding_a_land_creates_nothing():
    """The "if" in CR 701.70a is read off what was actually discarded.

    Same recruit, same draw, one different card chosen - and no token. This is
    the case an engine that assumed the discard would get wrong.
    """
    scenario = _board("Llanowar Elves", hand=["Forest"]).build()
    (forest,) = [state for state in scenario.player("alice").hand if state.card.name == "Forest"]
    scenario.will_discard(forest)

    _kill_the_lookout(scenario)

    assert TOKEN not in scenario.battlefield_names()
    assert _graveyard_names(scenario).count("Forest") == 1


def test_the_card_just_drawn_is_available_to_discard():
    """ "Draw a card, then discard a card" is ordered, and the order matters.

    Alice's hand is empty of anything but the Bolt she is about to spend, so
    the only card she can discard is the one the recruit's own draw put there.
    An engine that discarded first would find nothing to discard and create no
    token.
    """
    scenario = _board("Llanowar Elves").build()

    _kill_the_lookout(scenario)

    assert _hand_names(scenario) == []
    assert _graveyard_names(scenario).count("Llanowar Elves") == 1
    assert TOKEN in scenario.battlefield_names()


def test_the_trigger_fires_from_the_graveyard_not_the_battlefield():
    """CR 700.4 and CR 603.10a: it triggers on the way out, not while it is in.

    The source is already in the graveyard by the time the ability is put on
    the stack - CR 603.10a is what lets it trigger anyway - so the recruit
    happens with nothing named Lake-town Lookout on the battlefield.
    """
    scenario = _board("Llanowar Elves").build()

    lookout = _kill_the_lookout(scenario)

    assert lookout.zone is Zone.GRAVEYARD
    assert "Lake-town Lookout" not in scenario.battlefield_names()
    assert TOKEN in scenario.battlefield_names()


def test_a_lookout_that_never_dies_never_recruits():
    """The control for the test above: being on the battlefield is not the
    trigger condition.

    Nothing about a Lookout sitting there draws, discards or makes a Soldier.
    """
    scenario = _board("Llanowar Elves").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.advance()

    assert scenario.pending_triggers == []
    assert TOKEN not in scenario.battlefield_names()
    assert _hand_names(scenario) == ["Lightning Bolt"]


def test_an_empty_library_costs_the_recruiting_player_the_game():
    """CR 121.4 and CR 704.5b: the draw that finds nothing is still attempted.

    Recruit's draw is an ordinary draw, so an empty library is not a shrug -
    it is a loss the next time state-based actions are checked. Nothing is
    discarded and no token is created either, because the "if" never holds.
    """
    scenario = _board().build()

    _kill_the_lookout(scenario)

    alice = scenario.player("alice")
    assert alice.tried_to_draw_from_empty_library is True
    assert TOKEN not in scenario.battlefield_names()
    assert _hand_names(scenario) == []

    scenario.state_based_actions()
    assert "alice" in scenario.game.losers


# -- Esgaroth Garrison (off-set): an ETB recruit, not a dies trigger --------


def test_esgaroth_garrison_enters_and_recruits_off_a_discarded_nonland():
    """ "When this creature enters, recruit." - a second real printing on a
    different trigger event than Lake-town Lookout's (CR 603.6a's "enters"
    rather than CR 700.4's "dies"), proving the recruit clause itself is not
    fitted to being a dies-trigger's payload."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            library=["Forest"],
            hand=["Esgaroth Garrison", "Llanowar Elves"],
            battlefield=["Plains"] * 5,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (elves,) = [
        state for state in scenario.player("alice").hand if state.card.name == "Llanowar Elves"
    ]
    scenario.will_discard(elves)

    sources = scenario.untapped_sources(*(["Plains"] * 5))
    scenario.cast_and_resolve("Esgaroth Garrison", *sources)
    scenario.pass_until_resolved()

    token = scenario.find(TOKEN, Zone.BATTLEFIELD, "alice")
    assert is_token(token)
    assert token.controller == "alice"
    assert _hand_names(scenario) == ["Forest"]


def test_esgaroth_garrison_recruits_nothing_off_a_discarded_land():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            library=["Llanowar Elves"],
            hand=["Esgaroth Garrison", "Forest"],
            battlefield=["Plains"] * 5,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (forest,) = [state for state in scenario.player("alice").hand if state.card.name == "Forest"]
    scenario.will_discard(forest)

    sources = scenario.untapped_sources(*(["Plains"] * 5))
    scenario.cast_and_resolve("Esgaroth Garrison", *sources)
    scenario.pass_until_resolved()

    assert TOKEN not in scenario.battlefield_names()
    assert _graveyard_names(scenario).count("Forest") == 1


# -- Sound the Trumpets: recruit gated on the countered spell's mana value --


def test_sound_the_trumpets_recruits_when_the_countered_spells_mana_value_is_two_or_less():
    """CR 701.70a's recruit, this time gated by CR 400.7's "that spell" -
    Lightning Bolt is mana value 1, at or under the printed "2 or less"."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            library=["Forest"],
            hand=["Sound the Trumpets", "Llanowar Elves"],
            battlefield=["Island"] * 3,
        )
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (elves,) = [
        state for state in scenario.player("alice").hand if state.card.name == "Llanowar Elves"
    ]
    scenario.will_discard(elves)
    scenario.pass_priority("alice")

    (mountain,) = scenario.untapped_sources("Mountain", username="bob")
    bolt = scenario.cast_onto_stack("Lightning Bolt", mountain, username="bob", targets=["alice"])
    scenario.pass_priority("bob")

    islands = scenario.untapped_sources("Island", "Island", "Island", username="alice")
    scenario.cast_onto_stack("Sound the Trumpets", *islands, username="alice", targets=[bolt])
    scenario.pass_until_resolved()

    assert bolt.zone is Zone.GRAVEYARD, "CR 701.6a: countered"
    assert scenario.player("alice").life == 20, "Lightning Bolt never resolved"
    token = scenario.find(TOKEN, Zone.BATTLEFIELD, "alice")
    assert is_token(token)
    assert _hand_names(scenario) == ["Forest"]


def test_sound_the_trumpets_recruits_nothing_when_the_countered_spells_mana_value_is_higher():
    """Watchwolf, mana value 3, crosses the printed "2 or less" and recruits
    nothing - the control this file's other cards already give the "if" (a
    discarded land, an empty draw): the counter still happens, only the
    recruit does not. Watchwolf has no flash, so it is bob's own board and
    his own main phase that casts it - alice, not the active player, is the
    one responding with Sound the Trumpets."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("bob", hand=["Watchwolf"], battlefield=["Forest", "Plains"])
        .player(
            "alice",
            library=["Forest"],
            hand=["Sound the Trumpets", "Llanowar Elves"],
            battlefield=["Island"] * 3,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    sources = scenario.untapped_sources("Forest", "Plains", username="bob")
    wolf = scenario.cast_onto_stack("Watchwolf", *sources, username="bob")
    scenario.pass_priority("bob")

    islands = scenario.untapped_sources("Island", "Island", "Island", username="alice")
    scenario.cast_onto_stack("Sound the Trumpets", *islands, username="alice", targets=[wolf])
    scenario.pass_until_resolved()

    assert wolf.zone is Zone.GRAVEYARD, "still countered - CR 701.6a"
    assert TOKEN not in scenario.battlefield_names()
    # No draw or discard happened at all: recruit's own "if" never ran.
    assert _hand_names(scenario) == ["Llanowar Elves"]
