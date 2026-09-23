"""A library search for "an artifact card with a mana ability".

"{1}, {T}, Sacrifice this artifact: Search your library for an artifact card
with a mana ability or a basic land card, reveal it, put it into your hand,
then shuffle." (Moonsilver Key) names two whole card descriptions joined by
"or a", and the first one is a card type qualified by *having a mana ability*.

- **CR 701.23a** - "find a card that matches the given description."
- **CR 605.1a** - "An activated ability is a mana ability if it meets all of
  the following criteria: it doesn't require a target (see rule 115.6), it
  could add mana to a player's mana pool when it resolves, it's not a loyalty
  ability (see rule 606, "Loyalty Abilities"), and its cost and effect don't
  move any card to or from a library." Whatever else the cost asks for - a
  sacrifice (Lotus Petal), tapping another creature (Springleaf Drum) - does
  not matter; drawing a card as part of the effect (Chromatic Sphere) does.
- **CR 605.1b** - a triggered ability can be a mana ability too.
- **CR 305.6** - a land with a basic land type has the intrinsic "{T}: Add"
  ability even when its text box does not print it.
- **Quoted text** - an ability an artifact *grants* to something
  else ("Equipped creature has "{T}: Add one mana of any color."", Paradise
  Mantle) is not an ability of the artifact itself.
- **CR 205.4c** - "a basic land card" is the basic supertype, so a nonbasic
  land (Hallowed Fountain) is not one even though it has basic land types.
- **CR 701.23e** - "reveal it" is a real reveal.

No other printing legal in Modern, Pioneer or Standard carries "with a mana
ability" (Scryfall `o:"with a mana ability"` returns Moonsilver Key alone,
2026-09-23), so the reader is proven by the breadth of artifacts below rather
than by a second search card. Every CR number above was read in full from
`mise run rules:find` in the session that wrote this file.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.abilities import TriggerEvent
from magic_cards_model.machines.decisions import DecisionKind
from magic_cards_model.machines.effects import trigger_effect_for
from magic_cards_model.models import Game, Zone

from .harness import Scenario

LIBRARY = [
    "Mind Stone",
    "Lotus Petal",
    "Springleaf Drum",
    "Mox Amber",
    "Seat of the Synod",
    "Chromatic Sphere",
    "Paradise Mantle",
    "Ornithopter",
    "Expedition Map",
    "Moonsilver Key",
    "Hallowed Fountain",
    "Island",
    "Grizzly Bears",
]

#: Every card in `LIBRARY` that is an artifact with a mana ability or a basic
#: land.
QUALIFYING = {
    "Mind Stone",
    "Lotus Petal",
    "Springleaf Drum",
    "Mox Amber",
    "Seat of the Synod",
    "Island",
}


def _scenario(library: list[str]) -> Scenario:
    scenario = (
        Scenario()
        .player("alice", battlefield=["Moonsilver Key", "Plains"], library=library)
        .player("bob", library=["Plains"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _activate_key(scenario: Scenario) -> None:
    key = scenario.find("Moonsilver Key", Zone.BATTLEFIELD, "alice")
    (plains,) = scenario.untapped_sources("Plains")
    scenario.activate(key, plains)
    scenario.resolve_top()


def _search_questions(scenario: Scenario):
    return [q for q in scenario.questions_asked() if q.kind is DecisionKind.CHOOSE_CARDS]


def _offered(scenario: Scenario) -> set[str]:
    (asked,) = _search_questions(scenario)
    return {scenario.game.find_by_id(card_id).name for card_id in asked.cards}


def _known(game: Game, viewer: str) -> list[tuple[str, Zone]]:
    return sorted((entry.card_name, entry.zone) for entry in game.known_to(viewer))


# -- what qualifies -------------------------------------------------------------


def test_artifacts_with_a_mana_ability_and_basic_lands_qualify_and_nothing_else():
    scenario = _scenario(LIBRARY)
    stone = scenario.find("Mind Stone", Zone.LIBRARY, "alice")
    scenario.will_choose_cards(stone, username="alice", source="Moonsilver Key")

    _activate_key(scenario)

    assert _offered(scenario) == QUALIFYING
    assert stone.zone is Zone.HAND


def test_a_mana_ability_with_a_sacrifice_cost_is_still_a_mana_ability():
    scenario = _scenario(["Lotus Petal", "Ornithopter"])
    petal = scenario.find("Lotus Petal", Zone.LIBRARY, "alice")
    scenario.will_choose_cards(petal, username="alice", source="Moonsilver Key")

    _activate_key(scenario)

    assert _offered(scenario) == {"Lotus Petal"}
    assert petal.zone is Zone.HAND


def test_an_ability_that_adds_mana_and_draws_a_card_is_not_a_mana_ability():
    """CR 605.1a's fourth criterion: Chromatic Sphere's "Add one mana of any
    color. Draw a card." moves a card from a library, so it is not a mana
    ability and Chromatic Sphere is not an artifact card with one."""
    scenario = _scenario(["Chromatic Sphere", "Lotus Petal"])
    scenario.will_choose_cards(username="alice", source="Moonsilver Key")

    _activate_key(scenario)

    assert _offered(scenario) == {"Lotus Petal"}


def test_a_triggered_mana_ability_counts():
    """CR 605.1b: Caged Sun's "Whenever a land's ability causes you to add one
    or more mana of the chosen color, add an additional one mana of that
    color." triggers on mana being added and adds mana, so it is a mana
    ability and Caged Sun is an artifact card with one."""
    scenario = _scenario(["Caged Sun", "Ornithopter"])
    sun = scenario.find("Caged Sun", Zone.LIBRARY, "alice")
    scenario.will_choose_cards(sun, username="alice", source="Moonsilver Key")

    _activate_key(scenario)

    assert _offered(scenario) == {"Caged Sun"}
    assert sun.zone is Zone.HAND


def test_a_mana_ability_granted_to_another_object_is_not_the_artifacts_own():
    scenario = _scenario(["Paradise Mantle", "Lotus Petal"])
    scenario.will_choose_cards(username="alice", source="Moonsilver Key")

    _activate_key(scenario)

    assert _offered(scenario) == {"Lotus Petal"}


def test_a_nonbasic_land_and_an_artifact_without_one_are_never_offered():
    scenario = _scenario(["Hallowed Fountain", "Ornithopter", "Expedition Map"])

    _activate_key(scenario)

    assert _search_questions(scenario) == [] or _offered(scenario) == set()
    assert scenario.player("alice").hand == []
    assert scenario.game.search_description_notices == []


def test_the_basic_land_half_can_be_taken():
    scenario = _scenario(LIBRARY)
    island = scenario.find("Island", Zone.LIBRARY, "alice")
    scenario.will_choose_cards(island, username="alice", source="Moonsilver Key")

    _activate_key(scenario)

    assert island.zone is Zone.HAND


def test_the_find_is_revealed_and_the_key_is_sacrificed():
    scenario = _scenario(LIBRARY)
    seat = scenario.find("Seat of the Synod", Zone.LIBRARY, "alice")
    scenario.will_choose_cards(seat, username="alice", source="Moonsilver Key")

    _activate_key(scenario)

    assert ("Seat of the Synod", Zone.HAND) in _known(scenario.game, "bob")
    assert [state.name for state in scenario.player("alice").graveyard] == ["Moonsilver Key"]
    assert len(scenario.player("alice").library) == len(LIBRARY) - 1


def test_the_searcher_may_find_nothing():
    scenario = _scenario(LIBRARY)
    scenario.will_choose_cards(username="alice", source="Moonsilver Key")

    _activate_key(scenario)

    (asked,) = _search_questions(scenario)
    assert asked.exact is False
    assert scenario.player("alice").hand == []


def test_the_search_is_read_not_a_notice():
    effect = trigger_effect_for(
        "Moonsilver Key",
        TriggerEvent.ENTERS_THE_BATTLEFIELD,
        "search your library for an artifact card with a mana ability or a basic land card, "
        "reveal it, put it into your hand, then shuffle.",
    )
    assert effect is not None
    assert effect.__name__ != "search_description_notice_only"
