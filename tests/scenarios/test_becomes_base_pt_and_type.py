"""Scenario: resolution effects that set a creature's base power and toughness
together with its creature type (and colour) - one instruction, several
layers.

Every CR number here was read in full with `mise run rules:find` in the
session that wrote this file:

- **CR 613.1d** - layer 4: type-changing effects.
- **CR 613.1e** - layer 5: colour-changing effects.
- **CR 613.4b** - layer 7b: effects that set power and/or toughness, and
  effects that refer to the *base* power and/or toughness.
- **CR 613.4c** - layer 7c: effects that modify power and/or toughness apply
  after 7b, whatever their timestamps.
- **CR 613.6** - one effect applies in each layer it names.
- **CR 613.7** / **CR 613.7b** - within one layer, timestamp order; a
  resolving spell's or ability's effect is timestamped when it is created.
- **CR 205.1a** - "becomes a blue Serpent" *sets* the creature types: the new
  one replaces the old ones, card types untouched.
- **CR 205.1b** - "in addition to its other types" keeps every prior type.
- **CR 611.2a** - "until end of turn" ends in the cleanup step.
- **CR 611.2c** - the set of objects affected is fixed when the effect
  begins: a creature that arrives afterward is not in it.
- **CR 107.3a** - an activated ability's X is announced as it is activated.
- **CR 602.5d** - "Activate only as a sorcery".
- **CR 702.29a** - cycling works from the hand; the keyword line is not part
  of the spell's resolution.
- **CR 608.2b** - a spell whose only target is gone does nothing; **CR
  400.7** - the object that comes back is a new one.
- **CR 704.5f** - a creature with toughness 0 is put into its graveyard.

Startling Development (colour + type + base P/T, and a Cycling line beside
it) and Minsc, Beloved Ranger ({X}: base P/T X/X plus a Giant in addition)
are the reported cards. Serpentine Ambush is the second printing of the
colour/type/base-P/T template (no keyword line, different numbers); Mirror
Entity is the second printing of the {X} base-P/T activation (a group of
creatures rather than one target, and "gain all creature types" rather than
one named type). Both are legal in Modern (Scryfall legalities, 2026-09-23)
and in no deck under `magic-cards-model-api/decks/`.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import Keyword, has_keyword
from magic_cards_model.machines.layers import Layer, Sublayer
from magic_cards_model.models import Color, Type, Zone
from tests.scenarios.harness import Scenario


def computed(scenario: Scenario):
    return scenario.game.continuous_effects.board(scenario.game.battlefield)


def notices(scenario: Scenario) -> list[object]:
    """Every fail-closed notice the game recorded."""
    game = scenario.game
    found: list[object] = list(game.continuous_effects.layer_notices)
    for name in type(game).model_fields:
        if name.endswith("_notices"):
            found.extend(getattr(game, name))
    return found


def _end_the_turn(scenario: Scenario) -> None:
    scenario.start_at(Step.END_STEP)
    scenario.advance()  # cleanup


# --------------------------------------------------------------------------
# Startling Development
# --------------------------------------------------------------------------


def _startling(*, alice_battlefield=("Grizzly Bears",), bob_battlefield=(), extra_hand=()):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Startling Development", *extra_hand],
            battlefield=["Island", "Island", "Forest", *alice_battlefield],
            library=["Island"] * 5,
        )
        .player("bob", battlefield=list(bob_battlefield), library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _cast_startling(scenario: Scenario, target):
    islands = scenario.untapped_sources("Island", "Island", username="alice")
    scenario.cast_and_resolve("Startling Development", *islands, targets=[target])


def test_startling_development_makes_a_blue_serpent_4_4():
    scenario = _startling()
    bears = scenario.creature("Grizzly Bears")
    _cast_startling(scenario, bears)

    board = computed(scenario).of(bears)
    assert board.subtypes == ("Serpent",), "CR 205.1a: Bear is replaced, not kept"
    assert board.colors == (Color.BLUE,), "CR 613.1e: green is replaced"
    assert Type.CREATURE in board.types, "card types are untouched"
    assert (board.power, board.toughness) == (4, 4)
    assert notices(scenario) == [], "the Cycling line is not an unread remainder"


def test_startling_development_keeps_the_creatures_abilities():
    """Nothing in the sentence removes an ability (contrast Turn to Frog's
    "loses all abilities") - Serra Angel is still a flyer with vigilance."""
    scenario = _startling(alice_battlefield=("Serra Angel",))
    angel = scenario.creature("Serra Angel")
    _cast_startling(scenario, angel)

    board = computed(scenario).of(angel)
    assert (board.power, board.toughness) == (4, 4)
    assert board.subtypes == ("Serpent",)
    assert has_keyword(angel, Keyword.FLYING, scenario.game)
    assert has_keyword(angel, Keyword.VIGILANCE, scenario.game)


def test_startling_development_lands_in_layers_4_5_and_7b_with_one_timestamp():
    scenario = _startling()
    bears = scenario.creature("Grizzly Bears")
    _cast_startling(scenario, bears)

    effects = scenario.game.continuous_effects.effects
    assert sorted((e.layer.value, e.sublayer) for e in effects) == sorted(
        [
            (Layer.TYPE.value, None),
            (Layer.COLOR.value, None),
            (Layer.POWER_TOUGHNESS.value, Sublayer.SET),
        ]
    )
    assert len({e.timestamp for e in effects}) == 1


def test_an_earlier_pump_still_applies_on_top_of_the_new_base():
    """CR 613.4c after CR 613.4b: Giant Growth resolved first (earlier
    timestamp) and still adds +3/+3 to the 4/4 base - 7/7, not 4/4."""
    scenario = _startling(extra_hand=("Giant Growth",))
    bears = scenario.creature("Grizzly Bears")
    (forest,) = scenario.untapped_sources("Forest", username="alice")
    scenario.cast_and_resolve("Giant Growth", forest, targets=[bears])
    _cast_startling(scenario, bears)

    board = computed(scenario).of(bears)
    assert (board.power, board.toughness) == (7, 7)


def test_every_creature_type_of_a_changeling_is_replaced_too():
    """Changeling's "every creature type" (a characteristic-defining ability)
    applies first; "becomes a blue Serpent" then sets the creature types to
    exactly Serpent (CR 205.1a)."""
    scenario = _startling(alice_battlefield=("Mirror Entity",))
    entity = scenario.creature("Mirror Entity")
    _cast_startling(scenario, entity)

    board = computed(scenario).of(entity)
    assert board.subtypes == ("Serpent",)
    assert board.colors == (Color.BLUE,), "white is replaced"


def test_it_can_target_an_opponents_creature():
    scenario = _startling(alice_battlefield=(), bob_battlefield=("Hill Giant",))
    giant = scenario.creature("Hill Giant", "bob")
    _cast_startling(scenario, giant)

    board = computed(scenario).of(giant)
    assert (board.power, board.toughness) == (4, 4)
    assert board.subtypes == ("Serpent",)


def test_everything_ends_together_in_the_cleanup_step():
    scenario = _startling()
    bears = scenario.creature("Grizzly Bears")
    _cast_startling(scenario, bears)
    _end_the_turn(scenario)

    board = computed(scenario).of(bears)
    assert board.subtypes == ("Bear",)
    assert board.colors == (Color.GREEN,)
    assert (board.power, board.toughness) == (2, 2)


def test_a_target_gone_before_resolution_gets_nothing():
    """CR 608.2b: the only target is illegal; the returned Bears is a new
    object (CR 400.7) the effect never names."""
    scenario = _startling()
    bears = scenario.creature("Grizzly Bears")
    islands = scenario.untapped_sources("Island", "Island", username="alice")
    scenario.cast_onto_stack("Startling Development", *islands, targets=[bears])
    scenario.game.return_to_hand(bears)
    scenario.pass_until_resolved()

    assert scenario.game.continuous_effects.effects == []
    assert notices(scenario) == []


def test_cycling_still_draws_from_the_hand():
    """CR 702.29a: the Cycling line is the card's own hand ability, untouched
    by reading the spell's resolution without it."""
    scenario = _startling()
    card = scenario.find("Startling Development", Zone.HAND, "alice")
    hand_before = len(scenario.player("alice").hand)
    (island, *_) = scenario.untapped_sources("Island", username="alice")
    scenario.cycle(card, island)
    scenario.pass_until_resolved()

    assert card.zone is Zone.GRAVEYARD
    assert len(scenario.player("alice").hand) == hand_before  # discarded one, drew one


def test_serpentine_ambush_is_the_same_template_with_other_numbers():
    """Second printing: no keyword line, a 5/5 rather than a 4/4."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Serpentine Ambush"],
            battlefield=["Island"] * 5 + ["Llanowar Elves"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    elves = scenario.creature("Llanowar Elves")
    islands = scenario.untapped_sources(*["Island"] * 5, username="alice")
    scenario.cast_and_resolve("Serpentine Ambush", *islands, targets=[elves])

    board = computed(scenario).of(elves)
    assert (board.power, board.toughness) == (5, 5)
    assert board.subtypes == ("Serpent",)
    assert board.colors == (Color.BLUE,)
    assert board.has_ability("{T}: Add {G}."), "its mana ability is kept"
    assert notices(scenario) == []


# --------------------------------------------------------------------------
# Minsc, Beloved Ranger
# --------------------------------------------------------------------------


def _minsc(*, lands: int = 6, others=("Grizzly Bears",), bob=()):
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Minsc, Beloved Ranger", *others, *(["Wastes"] * lands)],
            library=["Wastes"] * 5,
        )
        .player("bob", battlefield=list(bob), library=["Wastes"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _activate_minsc(scenario: Scenario, target, x: int) -> None:
    minsc = scenario.creature("Minsc, Beloved Ranger")
    wastes = scenario.untapped_sources(*["Wastes"] * x, username="alice") if x else []
    scenario.activate(minsc, *wastes, index=0, targets=[target], x_value=x)
    scenario.pass_until_resolved()


def test_minsc_sets_base_power_and_toughness_to_x_and_adds_giant():
    scenario = _minsc()
    bears = scenario.creature("Grizzly Bears")
    _activate_minsc(scenario, bears, 5)

    board = computed(scenario).of(bears)
    assert (board.power, board.toughness) == (5, 5), "CR 107.3a: X was 5"
    assert "Giant" in board.subtypes
    assert "Bear" in board.subtypes, "CR 205.1b: in addition to its other types"
    assert board.colors == (Color.GREEN,), "no colour change in this instruction"
    assert notices(scenario) == []


def test_minsc_lands_in_layer_4_and_7b_with_one_timestamp():
    scenario = _minsc()
    bears = scenario.creature("Grizzly Bears")
    _activate_minsc(scenario, bears, 3)

    effects = [e for e in scenario.game.continuous_effects.effects]
    assert sorted((e.layer.value, e.sublayer) for e in effects) == sorted(
        [(Layer.TYPE.value, None), (Layer.POWER_TOUGHNESS.value, Sublayer.SET)]
    )
    assert len({e.timestamp for e in effects}) == 1


def test_the_later_activation_wins_in_layer_7b():
    """CR 613.7: two base-P/T sets in the same sublayer apply in timestamp
    order - the second activation (X=2) overrides the first (X=4)."""
    scenario = _minsc(lands=6)
    bears = scenario.creature("Grizzly Bears")
    _activate_minsc(scenario, bears, 4)
    _activate_minsc(scenario, bears, 2)

    board = computed(scenario).of(bears)
    assert (board.power, board.toughness) == (2, 2)
    assert board.subtypes.count("Giant") == 1


def test_counters_still_modify_the_new_base():
    """CR 613.4c: a +1/+1 counter applies after the 7b set."""
    scenario = _minsc()
    bears = scenario.creature("Grizzly Bears")
    bears.add_counters("+1/+1", 1)
    _activate_minsc(scenario, bears, 3)

    board = computed(scenario).of(bears)
    assert (board.power, board.toughness) == (4, 4)


def test_x_zero_makes_a_0_0_that_dies():
    """X=0 is legal (CR 107.3a); a 0/0 creature is put into its owner's
    graveyard as a state-based action (CR 704.5f)."""
    scenario = _minsc()
    bears = scenario.creature("Grizzly Bears")
    _activate_minsc(scenario, bears, 0)
    scenario.state_based_actions()

    assert bears.zone is Zone.GRAVEYARD


def test_minsc_can_target_himself():
    scenario = _minsc(others=())
    minsc = scenario.creature("Minsc, Beloved Ranger")
    _activate_minsc(scenario, minsc, 6)

    board = computed(scenario).of(minsc)
    assert (board.power, board.toughness) == (6, 6)
    assert {"Human", "Ranger", "Giant"} <= set(board.subtypes)


def test_minsc_cannot_target_an_opponents_creature():
    scenario = _minsc(bob=("Grizzly Bears",))
    theirs = scenario.creature("Grizzly Bears", "bob")
    minsc = scenario.creature("Minsc, Beloved Ranger")

    with pytest.raises(ValueError):
        scenario.activate(minsc, index=0, targets=[theirs], x_value=0)


def test_minsc_activates_only_as_a_sorcery():
    """CR 602.5d: not during combat, even on his controller's own turn."""
    scenario = _minsc()
    minsc = scenario.creature("Minsc, Beloved Ranger")
    scenario.start_at(Step.BEGINNING_OF_COMBAT)

    assert scenario.why_cannot_activate(minsc, 0, "alice") is not None


def test_minsc_effect_ends_in_the_cleanup_step():
    scenario = _minsc()
    bears = scenario.creature("Grizzly Bears")
    _activate_minsc(scenario, bears, 5)
    _end_the_turn(scenario)

    board = computed(scenario).of(bears)
    assert (board.power, board.toughness) == (2, 2)
    assert "Giant" not in board.subtypes


# --------------------------------------------------------------------------
# Mirror Entity - the second printing of the {X} activation
# --------------------------------------------------------------------------


def _entity(*, lands: int = 4, bob=("Hill Giant",)):
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Mirror Entity", "Grizzly Bears", *(["Plains"] * lands)],
            hand=["Llanowar Elves", "Forest"],
            library=["Plains"] * 5,
        )
        .player("bob", battlefield=list(bob), library=["Plains"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _activate_entity(scenario: Scenario, x: int) -> None:
    entity = scenario.creature("Mirror Entity")
    plains = scenario.untapped_sources(*["Plains"] * x, username="alice")
    scenario.activate(entity, *plains, index=0, x_value=x)
    scenario.pass_until_resolved()


def test_mirror_entity_sets_each_of_your_creatures_to_x_and_every_type():
    scenario = _entity()
    entity = scenario.creature("Mirror Entity")
    bears = scenario.creature("Grizzly Bears")
    _activate_entity(scenario, 4)

    for creature in (entity, bears):
        board = computed(scenario).of(creature)
        assert (board.power, board.toughness) == (4, 4)
        assert {"Bear", "Giant", "Serpent", "Elf"} <= set(board.subtypes)
    assert notices(scenario) == []


def test_mirror_entity_leaves_the_opponents_creatures_alone():
    scenario = _entity()
    giant = scenario.creature("Hill Giant", "bob")
    _activate_entity(scenario, 4)

    board = computed(scenario).of(giant)
    assert (board.power, board.toughness) == (3, 3)
    assert board.subtypes == ("Giant",)


def test_a_creature_arriving_afterward_is_not_affected():
    """CR 611.2c: the group is fixed as the ability resolves."""
    scenario = _entity(lands=3)
    _activate_entity(scenario, 3)
    scenario.play_land("Forest")
    (forest,) = scenario.untapped_sources("Forest", username="alice")
    elves = scenario.cast_and_resolve("Llanowar Elves", forest)

    board = computed(scenario).of(elves)
    assert (board.power, board.toughness) == (1, 1)
    assert board.subtypes == ("Elf", "Druid")
