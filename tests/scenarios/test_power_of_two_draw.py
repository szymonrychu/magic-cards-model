"""Scenario: Mathemagics - "Target player draws 2ˣ cards. (2⁰ = 1, 2¹ = 2,
2² = 4, 2³ = 8, 2⁴ = 16, 2⁵ = 32, and so on.)"

The one power-of-two amount in the pool: X is CR 107.3a's ordinary announced
X (`{X}{X}{U}{U}` prints two `{X}` symbols in its own mana cost, so the total
paid for both is `CastRecord.x_value`'s own single announced value, CR
107.3b - "if a spell or ability has multiple X's in its mana cost, all of
them have the same value"), and the amount drawn is 2 raised to that value,
not X itself.

Every CR number here was looked up with `mise run rules:find` in the session
that wrote this file:

- **CR 107.3a** - a spell's controller announces X's value as they cast it.
- **CR 107.3b** - multiple `{X}` symbols in one cost all take the same
  value.
- **CR 121.4** - drawing more cards than are left in the library draws the
  rest and no more.
- **CR 207.2** - reminder text (the parenthetical spelling out `2⁰ = 1`, ...)
  carries no rules meaning of its own.
"""

from magic_cards_model.machines import Step

from .harness import Scenario


def _to_main(scenario: Scenario) -> None:
    scenario.start_at(Step.PRECOMBAT_MAIN)


def _cast_with_x(scenario: Scenario, x_value: int, *sources, targets, username: str = "alice"):
    casting = scenario.cast("Mathemagics", username=username)
    casting.choose_targets(targets)
    casting.determine_cost(x_value=x_value)
    payment = casting.begin_paying()
    scenario.pay_with(payment, *sources)
    scenario.put_on_stack(casting)
    return casting


def test_mathemagics_draws_two_to_the_x_cards():
    """X=3 -> 2**3 = 8 cards, not 3."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Mathemagics"],
            battlefield=["Island"] * 8,
            library=["Mountain"] * 20,
        )
        .build()
    )
    _to_main(scenario)
    sources = scenario.untapped_sources(*(["Island"] * 8))
    _cast_with_x(scenario, 3, *sources, targets=["alice"])
    scenario.resolve_top()

    assert len(scenario.player("alice").hand) == 8


def test_mathemagics_at_x_zero_draws_exactly_one_card():
    """2**0 = 1, the reminder text's own first worked example - never zero,
    the way a literal, un-exponentiated X would read."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Mathemagics"],
            battlefield=["Island", "Island"],
            library=["Mountain"] * 5,
        )
        .build()
    )
    _to_main(scenario)
    sources = scenario.untapped_sources("Island", "Island")
    _cast_with_x(scenario, 0, *sources, targets=["alice"])
    scenario.resolve_top()

    assert len(scenario.player("alice").hand) == 1


def test_mathemagics_can_target_a_different_player():
    scenario = (
        Scenario()
        .player("alice", hand=["Mathemagics"], battlefield=["Island"] * 6)
        .player("bob", library=["Mountain"] * 10)
        .build()
    )
    _to_main(scenario)
    sources = scenario.untapped_sources(*(["Island"] * 6))
    _cast_with_x(scenario, 2, *sources, targets=["bob"])
    scenario.resolve_top()

    assert len(scenario.player("bob").hand) == 4
    assert len(scenario.player("alice").hand) == 0


def test_mathemagics_draws_no_more_than_the_library_holds():
    """CR 121.4: a request for more cards than remain draws only what is
    left."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Mathemagics"],
            battlefield=["Island"] * 10,
            library=["Mountain", "Forest"],
        )
        .build()
    )
    _to_main(scenario)
    sources = scenario.untapped_sources(*(["Island"] * 10))
    _cast_with_x(scenario, 4, *sources, targets=["alice"])  # 2**4 = 16, only 2 left
    scenario.resolve_top()

    assert len(scenario.player("alice").hand) == 2
    assert scenario.player("alice").library == []
