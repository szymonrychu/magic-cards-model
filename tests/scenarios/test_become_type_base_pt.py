"""Scenario: "Until end of turn, target creature becomes a `<color>`[ and
`<color>`] `<creature type>` with base power and toughness `<n>`/`<m>` | each
equal to `<n>`[ plus `<m>`]." - one resolving effect applied in four layers
(`machines/layers._BECOMES_CREATURE_TYPE_WITH_BASE_PT_RE`).

Fractalize is the reported card: "Until end of turn, target creature becomes
a green and blue Fractal with base power and toughness each equal to X plus
1. (It loses all other colors and creature types.)" - two colours, and a base
power/toughness read from CR 107.3a's announced X rather than printed as a
number, which reaches the layer reader because the resolving spell's own text
has X substituted in (`machines/effects.create_continuous_effect`).

Turn to Frog is the second printing the same reader reads: one colour, a
printed 1/1, and "loses all abilities" - legal in Modern and Pioneer
(Scryfall legalities, 2026-09-26) and in no deck under
`magic-cards-model-api/decks/`. Dragonshift is the only other printing with
two colours in this template and carries overload, which this engine does not
implement (see MEMORY.md).

Every CR number below was looked up with `mise run rules:find` in the session
that wrote this file:

- **CR 613.1d** - layer 4: type-changing effects.
- **CR 205.1a** - an effect that sets a subtype replaces the old subtypes of
  that kind: the creature stops being every other creature type.
- **CR 613.1e** - layer 5: colour-changing effects - the new colours replace
  the old ones.
- **CR 613.4b** - layer 7b: effects that set power and/or toughness, and ones
  that refer to base power and toughness.
- **CR 613.4c** - layer 7c: modifications (+1/+1 counters, pumps) apply on top
  of the base set in 7b.
- **CR 107.3a** - X is announced as the spell is cast.
- **CR 611.2a** - "until end of turn" lasts as stated.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import Keyword, has_keyword
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Color, Type
from magic_cards_model.support import HANDLED, classify_clauses
from tests.cards import card
from tests.scenarios.harness import Scenario


def computed(scenario):
    return scenario.game.continuous_effects.board(scenario.game.battlefield)


def notices(scenario) -> list[object]:
    game = scenario.game
    found: list[object] = list(game.continuous_effects.layer_notices)
    for name in type(game).model_fields:
        if name.endswith("_notices"):
            found.extend(getattr(game, name))
    return found


def _board(*, hand=("Fractalize",), islands: int = 4):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=list(hand),
            battlefield=["Grizzly Bears", *["Island"] * islands, "Forest"],
            library=["Island"] * 5,
        )
        .player("bob", battlefield=["Serra Angel"], library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _fractalize(scenario, target, x: int) -> None:
    casting = scenario.cast("Fractalize", targets=[target])
    casting.determine_cost(x_value=x)
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources(*["Island"] * (x + 1)))
    scenario.put_on_stack(casting)
    scenario.resolve_top()


def test_both_cards_are_handled() -> None:
    for name in ("Fractalize", "Turn to Frog"):
        clauses = [c for c in classify_clauses(card(name)) if c.text]
        assert {c.category for c in clauses} == {HANDLED}, name


def test_fractalize_sets_base_pt_to_x_plus_one() -> None:
    scenario = _board()
    angel = scenario.creature("Serra Angel", "bob")

    _fractalize(scenario, angel, 3)

    board = computed(scenario).of(angel)
    assert (board.power, board.toughness) == (4, 4)
    assert notices(scenario) == []


def test_x_of_zero_makes_it_a_1_1() -> None:
    scenario = _board()
    angel = scenario.creature("Serra Angel", "bob")

    _fractalize(scenario, angel, 0)

    board = computed(scenario).of(angel)
    assert (board.power, board.toughness) == (1, 1)


def test_it_becomes_a_green_and_blue_fractal_and_loses_other_colors_and_types() -> None:
    """CR 205.1a / CR 613.1e: the Angel is no longer white or an Angel."""
    scenario = _board()
    angel = scenario.creature("Serra Angel", "bob")

    _fractalize(scenario, angel, 1)

    board = computed(scenario).of(angel)
    assert set(board.colors) == {Color.GREEN, Color.BLUE}
    assert tuple(board.subtypes) == ("Fractal",)
    assert Type.CREATURE in board.types


def test_it_keeps_its_abilities() -> None:
    """Unlike Turn to Frog, Fractalize removes no ability: flying stays."""
    scenario = _board()
    angel = scenario.creature("Serra Angel", "bob")

    _fractalize(scenario, angel, 1)

    assert has_keyword(angel, Keyword.FLYING, scenario.game)


def test_a_pump_applies_on_top_of_the_set_base() -> None:
    """CR 613.4b then CR 613.4c: Giant Growth's +3/+3 after the 3/3 base."""
    scenario = _board(hand=("Fractalize", "Giant Growth"))
    bears = scenario.creature("Grizzly Bears")

    _fractalize(scenario, bears, 2)
    (forest,) = scenario.untapped_sources("Forest")
    scenario.cast_and_resolve("Giant Growth", forest, targets=[bears])

    board = computed(scenario).of(bears)
    assert (board.power, board.toughness) == (6, 6)


def test_a_pump_from_before_still_applies() -> None:
    """Timestamp order does not matter across sublayers: a 7c pump cast
    before Fractalize still applies after Fractalize's 7b set."""
    scenario = _board(hand=("Fractalize", "Giant Growth"))
    bears = scenario.creature("Grizzly Bears")
    (forest,) = scenario.untapped_sources("Forest")
    scenario.cast_and_resolve("Giant Growth", forest, targets=[bears])

    _fractalize(scenario, bears, 0)

    board = computed(scenario).of(bears)
    assert (board.power, board.toughness) == (4, 4)


def test_it_ends_in_the_cleanup_step() -> None:
    scenario = _board()
    angel = scenario.creature("Serra Angel", "bob")
    _fractalize(scenario, angel, 3)

    scenario.start_at(Step.END_STEP)
    scenario.advance()  # cleanup

    board = computed(scenario).of(angel)
    assert (board.power, board.toughness) == (4, 4)
    assert set(board.colors) == {Color.WHITE}
    assert "Angel" in board.subtypes


def test_a_lethal_shrink_kills_it() -> None:
    """X = 0 on the Angel after it took 2 damage: a 1/1 with 2 damage dies to
    state-based actions."""
    scenario = _board()
    angel = scenario.creature("Serra Angel", "bob")
    angel.damage = 2

    _fractalize(scenario, angel, 0)
    scenario.state_based_actions()

    assert angel.zone is Zone.GRAVEYARD


def test_turn_to_frog_is_read_by_the_same_reader() -> None:
    """The second printing: one colour, a printed 1/1, and "loses all
    abilities"."""
    scenario = _board(hand=("Turn to Frog",))
    angel = scenario.creature("Serra Angel", "bob")
    sources = scenario.untapped_sources("Island", "Island")

    scenario.cast_and_resolve("Turn to Frog", *sources, targets=[angel])

    board = computed(scenario).of(angel)
    assert (board.power, board.toughness) == (1, 1)
    assert set(board.colors) == {Color.BLUE}
    assert tuple(board.subtypes) == ("Frog",)
    assert not has_keyword(angel, Keyword.FLYING, scenario.game)
