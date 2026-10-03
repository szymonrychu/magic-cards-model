"""Life gained or lost equal to "the sacrificed creature's power/toughness",
when the sacrifice paid an activated ability's own cost.

Rules verified with `mise run rules:find` in the session that wrote this file:

- **CR 602.2b** - activating an ability follows the casting process, so the
  sacrifice cost is paid before the ability is on the stack.
- **CR 608.2h** - an effect that needs information from a specific object no
  longer in the zone it was expected in uses that object's last known
  information: a pumped creature's toughness is the pumped one, and a token
  that has since ceased to exist (**CR 704.5d**) still had one.
- **CR 119.3** - the life total is adjusted by the gain or loss.
- **CR 701.27a** - the back faces are reached by transforming the front.
- **CR 603.4** - the front faces' transform triggers are intervening-if.

Arguel's Blood Fast // Temple of Aclazotz ("You gain life equal to the
sacrificed creature's toughness") and Catapult Fodder // Catapult Captain
("Target opponent loses life equal to the sacrificed creature's toughness")
are the two printings; Ayli, Eternal Pilgrim is the off-face proof of the
gain shape and Tom, Bert, and William of the power reader.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Color, Zone
from magic_cards_model.models.card_state import Counter
from magic_cards_model.models.token import TokenDefinition, create_tokens
from magic_cards_model.support import HANDLED, classify_clauses
from tests.cards import card
from tests.scenarios.harness import PlayedScenario, Scenario

WALL = TokenDefinition(subtypes=("Wall",), colors=(Color.WHITE,), power=0, toughness=3)


def _transformed(scenario: PlayedScenario, name: str):
    front = scenario.creature(name, "alice")
    return scenario.game.put_onto_battlefield(
        scenario.game.exile_permanent(front), "alice", transformed=True
    )


@pytest.mark.parametrize(
    "name", ["Arguel's Blood Fast", "Arguel's Blood Fast // Temple of Aclazotz"]
)
def test_temple_clauses_are_handled(name) -> None:
    assert all(c.category == HANDLED for c in classify_clauses(card(name)))


@pytest.mark.parametrize("name", ["Catapult Fodder", "Catapult Fodder // Catapult Captain"])
def test_captain_clauses_are_handled(name) -> None:
    assert all(c.category == HANDLED for c in classify_clauses(card(name)))


def _temple(*extra: str, life: int = 10):
    scenario = (
        Scenario()
        .player("alice", life=life, battlefield=["Arguel's Blood Fast", *extra])
        .player("bob", life=20)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario, _transformed(scenario, "Arguel's Blood Fast")


def test_temple_gains_the_sacrificed_creatures_toughness() -> None:
    scenario, temple = _temple("Wall of Omens")
    assert temple.name == "Temple of Aclazotz"
    wall = scenario.creature("Wall of Omens", "alice")
    scenario.activate(temple, index=1, sacrificing=[wall])
    scenario.resolve_top()
    assert scenario.player("alice").life == 14, "Wall of Omens is a 0/4"
    assert wall.zone is Zone.GRAVEYARD


def test_temple_uses_last_known_toughness_with_counters_and_anthem() -> None:
    scenario, temple = _temple("Grizzly Bears", "Glorious Anthem")
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.game.add_counters(bears, Counter.PLUS_ONE, 2)
    scenario.activate(temple, index=1, sacrificing=[bears])
    scenario.resolve_top()
    assert scenario.player("alice").life == 10 + 2 + 2 + 1, "2 + two counters + anthem"


def test_temple_reads_a_token_that_has_ceased_to_exist() -> None:
    scenario, temple = _temple()
    (token,) = create_tokens(scenario.game, WALL, "alice", 1)
    scenario.activate(temple, index=1, sacrificing=[token])
    scenario.resolve_top()
    assert scenario.player("alice").life == 13


def test_temple_cannot_sacrifice_a_noncreature() -> None:
    scenario, temple = _temple("Island")
    island = scenario.find("Island", Zone.BATTLEFIELD, "alice")
    with pytest.raises(ValueError):
        scenario.activate(temple, index=1, sacrificing=[island])


def _captain(*extra: str, bob_life: int = 20):
    scenario = (
        Scenario()
        .player(
            "alice",
            life=20,
            battlefield=["Catapult Fodder", "Swamp", "Swamp", "Swamp", *extra],
        )
        .player("bob", life=bob_life)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    captain = _transformed(scenario, "Catapult Fodder")
    captain.summoning_sick = False
    return scenario, captain


def test_captain_makes_the_target_opponent_lose_the_sacrificed_toughness() -> None:
    scenario, captain = _captain("Wall of Omens")
    assert captain.name == "Catapult Captain"
    wall = scenario.creature("Wall of Omens", "alice")
    scenario.activate(captain, index=0, sacrificing=[wall], targets=["bob"], auto=True)
    scenario.resolve_top()
    assert scenario.player("bob").life == 16
    assert scenario.player("alice").life == 20


def test_captain_uses_last_known_toughness_including_pumps() -> None:
    scenario, captain = _captain("Grizzly Bears", "Glorious Anthem")
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.game.add_counters(bears, Counter.PLUS_ONE, 1)
    scenario.activate(captain, index=0, sacrificing=[bears], targets=["bob"], auto=True)
    scenario.resolve_top()
    assert scenario.player("bob").life == 20 - 4


def test_captain_cannot_sacrifice_itself_or_target_its_controller() -> None:
    scenario, captain = _captain("Grizzly Bears")
    bears = scenario.creature("Grizzly Bears", "alice")
    with pytest.raises(ValueError):
        scenario.activate(captain, index=0, sacrificing=[captain], targets=["bob"], auto=True)
    with pytest.raises(ValueError):
        scenario.activate(captain, index=0, sacrificing=[bears], targets=["alice"], auto=True)


def test_captain_token_sacrifice_still_counts() -> None:
    scenario, captain = _captain()
    (token,) = create_tokens(scenario.game, WALL, "alice", 1)
    scenario.activate(captain, index=0, sacrificing=[token], targets=["bob"], auto=True)
    scenario.resolve_top()
    assert scenario.player("bob").life == 17


def test_captain_is_reached_through_the_real_transform_trigger() -> None:
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            library=["Island"] * 5,
            battlefield=["Catapult Fodder", "Wall of Omens", "Celestial Enforcer"],
        )
        .player("bob", library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    while scenario.step is not Step.BEGINNING_OF_COMBAT:
        scenario.advance()
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()
    fodder = scenario.find("Catapult Captain", Zone.BATTLEFIELD, "alice")
    assert fodder.name == "Catapult Captain"


@pytest.mark.parametrize(
    "name",
    [
        "Ayli, Eternal Pilgrim",
        "Kheru Dreadmaw",
        "Disciple of Griselbrand",
        "Miren, the Moaning Well",
    ],
)
def test_other_printings_of_the_gain_shape_have_the_gain_clause_handled(name) -> None:
    gain = [c for c in classify_clauses(card(name)) if "sacrificed creature" in c.text]
    assert gain and all(c.category == HANDLED for c in gain)


@pytest.mark.parametrize(
    ("name", "lands", "index"),
    [
        ("Ayli, Eternal Pilgrim", ["Plains"], 0),
        ("Kheru Dreadmaw", ["Forest", "Forest"], 0),
        ("Disciple of Griselbrand", ["Swamp"], 0),
    ],
)
def test_other_printings_gain_the_sacrificed_toughness(name, lands, index) -> None:
    scenario = (
        Scenario()
        .player("alice", life=10, battlefield=[name, "Wall of Omens", *lands])
        .player("bob", life=20)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    source = scenario.creature(name, "alice")
    wall = scenario.creature("Wall of Omens", "alice")
    scenario.activate(source, index=index, sacrificing=[wall], auto=True)
    scenario.resolve_top()
    assert scenario.player("alice").life == 14
    assert wall.zone is Zone.GRAVEYARD


def test_jarad_each_opponent_loses_the_sacrificed_creatures_power() -> None:
    """Jarad, Golgari Lich Lord is the second printing of the loss shape
    ("Each opponent loses life equal to the sacrificed creature's power")."""
    assert all(c.category == HANDLED for c in classify_clauses(card("Jarad, Golgari Lich Lord")))
    scenario = (
        Scenario()
        .player(
            "alice",
            life=20,
            battlefield=["Jarad, Golgari Lich Lord", "Grizzly Bears", "Swamp", "Forest", "Forest"],
        )
        .player("bob", life=20)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    jarad = scenario.creature("Jarad, Golgari Lich Lord", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.game.add_counters(bears, Counter.PLUS_ONE, 1)
    scenario.activate(jarad, index=0, sacrificing=[bears], auto=True)
    scenario.resolve_top()
    assert scenario.player("bob").life == 20 - 3
    assert scenario.player("alice").life == 20
