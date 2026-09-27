"""A once-each-turn "one or more ... enter" trigger that copies one of the
creatures that entered - Twilight Diviner: "Whenever one or more other
creatures you control enter, if they entered or were cast from a graveyard,
create a token that's a copy of one of them. This ability triggers only once
each turn."

Every CR number here was read whole with `mise run rules:find` in the session
that wrote this file:

- **CR 603.6a** one event putting several permanents onto the battlefield
  is one event - so "one of them" is chosen among everything that entered
  with it.
- **CR 603.4** the intervening "if" is checked as the event happens and
  again as the ability resolves.
- **CR 603.2h** "only once each turn".
- **CR 707.2** a token copy takes the copiable values only; **CR 702.138b**
  a permanent "escaped" only if it was cast with escape - a token copy of an
  escaped Uro did not.
- **CR 111.2** the token's creator is its owner and controller.

Second printing (legal in Pioneer and Standard, in no deck list, Scryfall
printing read 2026-09-27): Kambal, Profiteering Mayor - "Whenever one or
more tokens your opponents control enter, for each of them, create a tapped
token that's a copy of it. This ability triggers only once each turn." - the
same "them" read off one entering event, every member copied rather than one
chosen, and tapped.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import PlayedScenario, Scenario

DIVINER = "Twilight Diviner"
KAMBAL = "Kambal, Profiteering Mayor"
URO = "Uro, Titan of Nature's Wrath"


def _chars(scenario: Scenario, permanent):
    return scenario.game.characteristics_of(permanent)


def _tokens(scenario: Scenario, username: str = "alice"):
    return [
        permanent
        for permanent in scenario.game.permanents_controlled_by(username)
        if getattr(permanent, "token", False)
    ]


def _resolve_all(scenario: PlayedScenario) -> None:
    scenario.game.put_triggers_on_stack()
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()


def _diviner(*, graveyard=("Grizzly Bears",), hand=("Unearth",), lands=("Swamp",) * 4, **bob):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=list(hand),
            graveyard=list(graveyard),
            battlefield=[DIVINER, *lands],
            library=["Swamp"] * 8,
        )
        .player("bob", library=["Island"] * 8, **bob)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _unearth(scenario: PlayedScenario, name: str = "Grizzly Bears") -> None:
    target = scenario.find(name, Zone.GRAVEYARD, "alice")
    scenario.cast_and_resolve("Unearth", *scenario.untapped_sources("Swamp"), targets=[target])
    _resolve_all(scenario)


def test_a_reanimated_creature_is_copied():
    scenario = _diviner()

    _unearth(scenario)

    tokens = _tokens(scenario)
    assert len(tokens) == 1
    assert _chars(scenario, tokens[0]).name == "Grizzly Bears"


def test_a_creature_cast_from_the_hand_is_not():
    """The intervening "if" (CR 603.4): it did not enter from a graveyard
    and was not cast from one."""
    scenario = _diviner(graveyard=(), hand=("Grizzly Bears",), lands=("Swamp", "Forest"))

    scenario.cast_and_resolve("Grizzly Bears", *scenario.untapped_sources("Swamp", "Forest"))
    _resolve_all(scenario)

    assert _tokens(scenario) == []


def test_only_once_each_turn():
    """CR 603.2h: the second reanimation this turn does not trigger it."""
    scenario = _diviner(graveyard=("Grizzly Bears", "Savannah Lions"), hand=("Unearth", "Unearth"))

    _unearth(scenario, "Grizzly Bears")
    _unearth(scenario, "Savannah Lions")

    assert [_chars(scenario, token).name for token in _tokens(scenario)] == ["Grizzly Bears"]


def test_one_of_them_is_chosen_among_creatures_that_entered_together():
    """CR 603.6a: Fix What's Broken returns both at once - one event, one
    trigger, and alice picks which to copy."""
    scenario = _diviner(
        graveyard=("Grizzly Bears", "Amoeboid Changeling"),
        hand=("Fix What's Broken",),
        lands=("Swamp", "Swamp", "Plains", "Plains"),
    )
    changeling = scenario.find("Amoeboid Changeling", Zone.GRAVEYARD, "alice")
    casting = scenario.cast("Fix What's Broken", username="alice")
    casting.game = scenario.game
    casting.determine_cost(x_value=2)
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Swamp", "Swamp", "Plains", "Plains"))
    scenario.put_on_stack(casting)
    scenario.resolve_top()
    scenario.will_choose_cards(changeling, username="alice", source=DIVINER)

    _resolve_all(scenario)

    assert [_chars(scenario, token).name for token in _tokens(scenario)] == ["Amoeboid Changeling"]


def test_the_diviner_itself_entering_from_a_graveyard_does_not_count():
    """ "Other creatures": the Diviner returning itself is not one of them."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Unearth"],
            graveyard=[DIVINER],
            battlefield=["Swamp"],
            library=["Swamp"] * 8,
        )
        .player("bob", library=["Island"] * 8)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    diviner = scenario.find(DIVINER, Zone.GRAVEYARD, "alice")
    scenario.will_choose_cards(username="alice")  # surveil 2: keep both on top
    scenario.cast_and_resolve("Unearth", *scenario.untapped_sources("Swamp"), targets=[diviner])
    _resolve_all(scenario)

    assert _tokens(scenario) == []


def test_an_opponents_reanimated_creature_does_not_count():
    """ "Creatures you control": bob reanimating his own creature on his turn
    does not trigger alice's Diviner."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=[DIVINER], library=["Swamp"] * 8)
        .player(
            "bob",
            hand=["Unearth"],
            graveyard=["Grizzly Bears"],
            battlefield=["Swamp"],
            library=["Island"] * 8,
        )
        .build()
    )
    turns = scenario.turn.turns_taken
    while scenario.turn.turns_taken == turns:
        scenario.advance()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "bob")

    scenario.cast_and_resolve(
        "Unearth",
        *scenario.untapped_sources("Swamp", username="bob"),
        targets=[bears],
        username="bob",
    )
    _resolve_all(scenario)

    assert scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "bob").zone is Zone.BATTLEFIELD
    assert _tokens(scenario, "alice") == []
    assert _tokens(scenario, "bob") == []


def test_a_creature_cast_from_the_graveyard_is_copied_and_the_copy_did_not_escape():
    """Uro cast with escape (CR 702.138b) was cast from a graveyard, so it is
    copied - and the token copy was never cast at all, so its own "sacrifice
    it unless it escaped" sacrifices it."""
    scenario = _diviner(
        graveyard=(URO, *["Mishra's Bauble"] * 5),
        hand=(),
        lands=("Forest", "Forest", "Island", "Island"),
    )
    life = scenario.player("alice").life
    fuel = [card for card in scenario.player("alice").graveyard if card.name != URO]
    casting = scenario.cast(URO, from_zone=Zone.GRAVEYARD)
    casting.use_keyword("Escape", choosing=fuel[:5])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Forest", "Forest", "Island", "Island"))
    scenario.put_on_stack(casting)

    _resolve_all(scenario)

    assert scenario.find(URO, Zone.BATTLEFIELD, "alice").zone is Zone.BATTLEFIELD
    assert _tokens(scenario) == []
    # Both Uros' enters triggers gained 3 life each (CR 113.7a).
    assert scenario.player("alice").life == life + 6


def test_the_copy_is_made_even_if_the_creature_is_gone():
    """CR 603.4's recheck reads the entering event's own facts, which have not
    changed, and CR 608.2h reads the creature that left by its last known
    information - so Lightning Bolt on the reanimated Bears in response does
    not stop the copy."""
    scenario = _diviner(hand=("Unearth", "Lightning Bolt"), lands=("Swamp", "Mountain"))
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")
    scenario.cast_and_resolve("Unearth", *scenario.untapped_sources("Swamp"), targets=[bears])
    scenario.game.put_triggers_on_stack()
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice")
    scenario.cast_and_resolve(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=[bears]
    )
    scenario.state_based_actions()
    assert scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice").zone is Zone.GRAVEYARD

    _resolve_all(scenario)

    assert [_chars(scenario, token).name for token in _tokens(scenario)] == ["Grizzly Bears"]


# --------------------------------------------------------------------------
# Kambal, Profiteering Mayor
# --------------------------------------------------------------------------


def test_kambal_copies_each_token_an_opponent_creates_tapped_once_a_turn():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=[KAMBAL], library=["Plains"] * 8)
        .player(
            "bob",
            hand=["Spectral Procession", "Spectral Procession"],
            battlefield=["Plains"] * 6,
            library=["Plains"] * 8,
        )
        .build()
    )
    turns = scenario.turn.turns_taken
    while scenario.turn.turns_taken == turns:
        scenario.advance()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.cast_and_resolve(
        "Spectral Procession",
        *scenario.untapped_sources("Plains", "Plains", "Plains", username="bob"),
        username="bob",
    )
    _resolve_all(scenario)

    mine = _tokens(scenario, "alice")
    assert len(mine) == 3
    assert all(token.tapped for token in mine)
    assert all("Spirit" in _chars(scenario, token).subtypes for token in mine)

    scenario.cast_and_resolve(
        "Spectral Procession",
        *scenario.untapped_sources("Plains", "Plains", "Plains", username="bob"),
        username="bob",
    )
    _resolve_all(scenario)

    assert len(_tokens(scenario, "alice")) == 3


@pytest.mark.parametrize("name", [DIVINER, KAMBAL])
def test_the_sweep_handles_every_clause(name):
    from magic_cards_model.support import HANDLED, card_support
    from tests.cards import card

    support = card_support(card(name))
    assert support.effect_outcome == HANDLED, support.effect_detail
