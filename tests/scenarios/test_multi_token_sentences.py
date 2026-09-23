"""One "create" instruction naming a comma-separated list of different tokens:
"Create a <A> token, a <B> token, and a <C> token."

- **CR 701.7a** - "To create one or more tokens with certain characteristics,
  put the specified number of tokens with the specified characteristics onto
  the battlefield." A list names three sets of characteristics, one token each.
- **CR 111.3** - each item's own descriptor (and only it) defines that token's
  characteristics, so a "with flying" printed on the first item belongs to the
  first token and to no other.
- **CR 111.2** - the player who creates a token is its owner and controller.

Mascot Exhibition is the listed card; Bestial Menace (a spell with no keyword
tails at all) and Trostani's Summoner (the same list inside an enters trigger,
keyword tails on the first *and* last items) prove the reader is the list
template, not one printed sentence.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import has_keyword
from magic_cards_model.models import Color, Zone
from tests.scenarios.harness import Scenario


def _tokens(scenario, username: str) -> dict[str, object]:
    return {
        state.name: state
        for state in scenario.game.battlefield
        if state.controller == username and state.name.endswith(" Token")
    }


def test_mascot_exhibition_creates_all_three_distinct_tokens():
    scenario = (
        Scenario()
        .player("alice", hand=["Mascot Exhibition"], battlefield=["Island"] * 7)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.cast_and_resolve("Mascot Exhibition", auto=True, username="alice")

    tokens = _tokens(scenario, "alice")
    assert sorted(tokens) == ["Elemental Token", "Inkling Token", "Spirit Token"]
    inkling, spirit, elemental = (
        tokens["Inkling Token"],
        tokens["Spirit Token"],
        tokens["Elemental Token"],
    )
    assert (inkling.power, inkling.toughness) == (2, 1)
    assert set(inkling.card.colors) == {Color.WHITE, Color.BLACK}
    assert inkling.card.keywords == ["Flying"]
    assert (spirit.power, spirit.toughness) == (3, 2)
    assert set(spirit.card.colors) == {Color.RED, Color.WHITE}
    assert (elemental.power, elemental.toughness) == (4, 4)
    assert set(elemental.card.colors) == {Color.BLUE, Color.RED}


def test_mascot_exhibition_first_items_flying_does_not_leak_to_the_others():
    """CR 111.3: "with flying" is part of the Inkling's descriptor only."""
    scenario = (
        Scenario()
        .player("alice", hand=["Mascot Exhibition"], battlefield=["Island"] * 7)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.cast_and_resolve("Mascot Exhibition", auto=True, username="alice")

    tokens = _tokens(scenario, "alice")
    assert tokens["Spirit Token"].card.keywords == []
    assert tokens["Elemental Token"].card.keywords == []
    assert tokens["Spirit Token"].card.subtypes == ["Spirit"]
    assert tokens["Elemental Token"].card.subtypes == ["Elemental"]


def test_mascot_exhibition_makes_exactly_one_of_each():
    scenario = (
        Scenario()
        .player("alice", hand=["Mascot Exhibition"], battlefield=["Island"] * 7)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.cast_and_resolve("Mascot Exhibition", auto=True, username="alice")

    created = [state for state in scenario.game.battlefield if state.name.endswith(" Token")]
    assert len(created) == 3
    assert all(state.controller == "alice" and state.owner == "alice" for state in created)
    assert scenario.find("Mascot Exhibition", Zone.GRAVEYARD, "alice") is not None


def test_bestial_menace_creates_its_three_green_tokens():
    """A second printing of the same list, with no keyword tail on any item."""
    scenario = (
        Scenario()
        .player("alice", hand=["Bestial Menace"], battlefield=["Forest"] * 5)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.cast_and_resolve("Bestial Menace", auto=True, username="alice")

    tokens = _tokens(scenario, "alice")
    assert sorted(tokens) == ["Elephant Token", "Snake Token", "Wolf Token"]
    sizes = {name: (state.power, state.toughness) for name, state in tokens.items()}
    assert sizes == {"Snake Token": (1, 1), "Wolf Token": (2, 2), "Elephant Token": (3, 3)}
    assert all(state.card.colors == [Color.GREEN] for state in tokens.values())
    assert all(state.card.keywords == [] for state in tokens.values())


def test_trostanis_summoner_trigger_creates_the_list_with_each_items_own_keyword():
    """The list inside an enters trigger, keyword tails on the first and last
    items: vigilance is the Knight's alone, trample the Rhino's alone."""
    scenario = (
        Scenario()
        .player("alice", hand=["Trostani's Summoner"], battlefield=["Forest"] * 6 + ["Plains"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.cast_and_resolve("Trostani's Summoner", auto=True, username="alice")
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    tokens = _tokens(scenario, "alice")
    assert sorted(tokens) == ["Centaur Token", "Knight Token", "Rhino Token"]
    knight, centaur, rhino = tokens["Knight Token"], tokens["Centaur Token"], tokens["Rhino Token"]
    assert (knight.power, knight.toughness, knight.card.colors) == (2, 2, [Color.WHITE])
    assert knight.card.keywords == ["Vigilance"]
    assert (centaur.power, centaur.toughness, centaur.card.colors) == (3, 3, [Color.GREEN])
    assert centaur.card.keywords == []
    assert (rhino.power, rhino.toughness, rhino.card.colors) == (4, 4, [Color.GREEN])
    assert rhino.card.keywords == ["Trample"]


def test_only_the_inkling_has_flying_on_the_computed_board():
    """The keyword reaches the computed board (CR 613.5) on the Inkling alone -
    what combat's CR 702.9b evasion check reads."""
    scenario = (
        Scenario()
        .player("alice", hand=["Mascot Exhibition"], battlefield=["Island"] * 7)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.cast_and_resolve("Mascot Exhibition", auto=True, username="alice")

    tokens = _tokens(scenario, "alice")
    assert has_keyword(tokens["Inkling Token"], "Flying", scenario.game)
    assert not has_keyword(tokens["Spirit Token"], "Flying", scenario.game)
    assert not has_keyword(tokens["Elemental Token"], "Flying", scenario.game)
