"""Token-creation ETBs whose count is read off the board at resolution
(CR 608.2h), rather than a fixed number:

- "create X `<Descriptor>` tokens, where X is the number of nontoken
  creatures you control." - Sally Pride, Lioness Leader. `count_expression`'s
  shared "the number of `<qualifier>` you control" reader
  (`_COUNT_YOU_CONTROL_RE`) never read a leading "nontoken" qualifier before
  this file - Lena, Selfless Champion (a real, off-set, in-format printing,
  not this task's reported card and not in the deck pool) exercises the
  identical widened reader through the "for each `<qualifier>` you control"
  tail instead of "the number of ... where X is", proving the fix is in the
  shared reader both shapes call, not in a Sally-Pride-specific parser.

CR 111.1's own token/nontoken distinction is what "nontoken" excludes; CR
608.2h is what fixes the count once, at the moment the token-creating
instruction is applied - which is *after* the creature that triggered the
ETB has already entered the battlefield, so it counts itself among "the
number of nontoken creatures you control" the same way any other nontoken
creature there does.

CR numbers verified with `mise run rules:find` in the session that wrote this
file: **CR 111.1** (token), **CR 608.2h** (a variable's magnitude is
determined only once, as the effect is applied).
"""

from magic_cards_model.machines import Step
from magic_cards_model.models.token import PREDEFINED, create_tokens
from tests.scenarios.harness import Scenario


def _resolve_all(scenario: Scenario) -> None:
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()


def test_sally_pride_counts_herself_and_another_nontoken_creature() -> None:
    """Sally Pride enters with one other nontoken creature already on the
    board - she is counted too (CR 608.2h: the count is taken once, as the
    ability resolves, by which point she has already entered)."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Sally Pride, Lioness Leader"],
            battlefield=["Plains", "Plains", "Plains", "Plains", "Plains", "Grizzly Bears"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve("Sally Pride, Lioness Leader", auto=True)
    _resolve_all(scenario)

    mutants = [
        p for p in scenario.game.battlefield if p.name == "Mutant Token" and p.controller == "alice"
    ]
    assert len(mutants) == 2  # Grizzly Bears + Sally Pride herself
    assert all(p.card.power == "2" and p.card.toughness == "2" for p in mutants)


def test_sally_pride_does_not_count_a_token_creature() -> None:
    """A token creature already on the board does not add to the count -
    CR 111.1's own token/nontoken distinction."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Sally Pride, Lioness Leader"],
            battlefield=["Plains", "Plains", "Plains", "Plains", "Plains"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    create_tokens(scenario.game, PREDEFINED["Treasure"], "alice")

    scenario.cast_and_resolve("Sally Pride, Lioness Leader", auto=True)
    _resolve_all(scenario)

    mutants = [
        p for p in scenario.game.battlefield if p.name == "Mutant Token" and p.controller == "alice"
    ]
    assert len(mutants) == 1  # only Sally Pride herself; the Treasure token does not count


def test_lena_selfless_champion_creates_a_soldier_for_each_nontoken_creature() -> None:
    """Off the reported card, off the deck pool: Lena, Selfless Champion's
    own "create a 1/1 white Soldier creature token for each nontoken creature
    you control." - the identical widened `count_expression` reader, reached
    through the "for each" tail instead of "where X is the number of"."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Lena, Selfless Champion"],
            battlefield=[
                "Plains",
                "Plains",
                "Plains",
                "Plains",
                "Plains",
                "Plains",
                "Grizzly Bears",
            ],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve("Lena, Selfless Champion", auto=True)
    _resolve_all(scenario)

    soldiers = [
        p
        for p in scenario.game.battlefield
        if p.name == "Soldier Token" and p.controller == "alice"
    ]
    assert len(soldiers) == 2  # Grizzly Bears + Lena herself
