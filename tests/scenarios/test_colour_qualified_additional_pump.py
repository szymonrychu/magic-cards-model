"""Scenario: a group pump followed by "<narrower group> get an additional
+N/+N [and gain <keyword>] until end of turn." - two instructions of one
resolving spell, the second over a subset of the first.

- **CR 608.2c** - the instructions are followed in the order written.
- **CR 613.4c** - sublayer 7c: effects that modify power and/or toughness
  add up, so "an additional -2/-2" stacks on the -1/-1 rather than replacing
  it; "additional" names no new rule, only that it is on top.
- **CR 613.1f** - layer 6 for a keyword riding on the second sentence.
- **CR 105.2** - an object can be one or more of the five colours; "green
  and/or white" is any creature that is green, white, or both, once.
- **CR 611.2c** - the set of objects each sentence affects is fixed when that
  effect begins; a creature that enters later is not in it.
- **CR 704.5f** - a creature with toughness 0 or less goes to its owner's
  graveyard.

Glistening Deluge is the reported card ("All creatures get -1/-1 until end of
turn. Creatures that are green and/or white get an additional -2/-2 until end
of turn."). Take to the Streets is the second printing: a controller-scoped
first sentence, a subtype (Citizen) rather than a colour filter, a positive
pump, and a keyword grant riding on the additional sentence.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import Keyword, has_keyword
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def computed(scenario: Scenario):
    return scenario.game.continuous_effects.board(scenario.game.battlefield)


def notices(scenario: Scenario) -> list[object]:
    game = scenario.game
    found: list[object] = list(game.continuous_effects.layer_notices)
    for name in type(game).model_fields:
        if name.endswith("_notices"):
            found.extend(getattr(game, name))
    return found


def _deluge(alice_battlefield: list[str], bob_battlefield: list[str]) -> Scenario:
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Glistening Deluge"],
            battlefield=["Swamp", "Swamp", "Swamp", *alice_battlefield],
        )
        .player("bob", battlefield=bob_battlefield)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _cast_deluge(scenario: Scenario) -> None:
    swamps = scenario.untapped_sources("Swamp", "Swamp", "Swamp", username="alice")
    scenario.cast_and_resolve("Glistening Deluge", *swamps)


def test_green_and_white_creatures_get_minus_three_everyone_else_minus_one():
    scenario = _deluge(["Craw Wurm", "Archive Dragon"], ["Blazing Archon", "Ornithopter"])
    wurm = scenario.creature("Craw Wurm", "alice")
    dragon = scenario.creature("Archive Dragon", "alice")
    archon = scenario.creature("Blazing Archon", "bob")
    thopter = scenario.creature("Ornithopter", "bob")

    _cast_deluge(scenario)

    board = computed(scenario)
    assert board.of(wurm).power_toughness == (3, 1), "green 6/4: -1/-1 and -2/-2"
    assert board.of(archon).power_toughness == (2, 3), "white 5/6: -1/-1 and -2/-2"
    assert board.of(dragon).power_toughness == (3, 5), "blue 4/6: only -1/-1"
    assert board.of(thopter).power_toughness == (-1, 1), "colourless 0/2: only -1/-1"
    assert notices(scenario) == []


def test_a_green_and_white_creature_gets_the_additional_minus_two_once():
    """CR 105.2: "green and/or white" is a set of colours to be in, not one
    -2/-2 per matching colour."""
    scenario = _deluge(["Blazing Archon"], [])
    archon = scenario.creature("Blazing Archon", "alice")
    _cast_deluge(scenario)

    effects_on_archon = [
        effect
        for effect in scenario.game.continuous_effects.effects
        if getattr(effect.selector, "card_id", None) == archon.id
    ]
    assert len(effects_on_archon) == 2, "one -1/-1 and one additional -2/-2"


def test_small_creatures_die_to_the_state_based_action():
    """CR 704.5f: a green 2/2 at -1/-1 then -2/-2 has toughness -1; a
    colourless 1/1 at -1/-1 has toughness 0. Both die; a bigger off-colour
    creature lives."""
    scenario = _deluge(["Grizzly Bears", "Memnite", "Archive Dragon"], ["Watchwolf"])
    bears = scenario.creature("Grizzly Bears", "alice")
    memnite = scenario.creature("Memnite", "alice")
    wolf = scenario.creature("Watchwolf", "bob")
    dragon = scenario.creature("Archive Dragon", "alice")

    _cast_deluge(scenario)
    scenario.state_based_actions()

    assert bears.zone is Zone.GRAVEYARD
    assert memnite.zone is Zone.GRAVEYARD
    assert wolf.zone is Zone.GRAVEYARD, "green-white 3/3 at -3/-3"
    assert dragon.zone is Zone.BATTLEFIELD


def test_a_creature_that_enters_afterwards_is_not_shrunk():
    """CR 611.2c: both sets are fixed as the spell resolves."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Glistening Deluge", "Craw Wurm"],
            battlefield=["Swamp", "Swamp", "Swamp"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _cast_deluge(scenario)
    wurm = scenario.put_onto_battlefield("Craw Wurm", "alice")

    assert computed(scenario).of(wurm).power_toughness == (6, 4)


def test_the_shrink_ends_in_the_cleanup_step():
    scenario = _deluge(["Craw Wurm"], [])
    wurm = scenario.creature("Craw Wurm", "alice")
    _cast_deluge(scenario)

    scenario.start_at(Step.END_STEP)
    assert computed(scenario).of(wurm).power_toughness == (3, 1)
    scenario.advance()  # cleanup
    assert computed(scenario).of(wurm).power_toughness == (6, 4)


# -- second printing: Take to the Streets ----------------------------------


def _streets() -> Scenario:
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Take to the Streets"],
            battlefield=[*["Forest"] * 5, "Delighted Halfling", "Grizzly Bears"],
        )
        .player("bob", battlefield=["Delighted Halfling"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources(*["Forest"] * 5, username="alice")
    scenario.cast_and_resolve("Take to the Streets", *sources)
    return scenario


def test_citizens_you_control_get_the_additional_pump_and_vigilance():
    scenario = _streets()
    halfling = scenario.creature("Delighted Halfling", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")

    board = computed(scenario)
    assert board.of(halfling).power_toughness == (4, 5), "1/2 +2/+2 +1/+1"
    assert has_keyword(halfling, Keyword.VIGILANCE, scenario.game)
    assert board.of(bears).power_toughness == (4, 4), "not a Citizen: only +2/+2"
    assert not has_keyword(bears, Keyword.VIGILANCE, scenario.game)
    assert notices(scenario) == []


def test_an_opponents_citizen_is_not_in_either_group():
    scenario = _streets()
    theirs = scenario.creature("Delighted Halfling", "bob")

    assert computed(scenario).of(theirs).power_toughness == (1, 2)
    assert not has_keyword(theirs, Keyword.VIGILANCE, scenario.game)
