"""Part in Friendship: "Whenever a nontoken creature you control dies,
reveal cards from the top of your library until you reveal a creature card.
If its mana value is less than or equal to the number of lands you control,
put it onto the battlefield. Otherwise, put it into your hand. Put the rest
on the bottom of your library in a random order."

`_REVEAL_UNTIL_KIND_RE` (the reveal-until-a-creature half) and
`count_expression` ("the number of lands you control", `_SEARCH_MV_LTE_
COUNT_RE`'s own board-count reader) both already existed. The gap was the
four-clause shape itself: `_merge_reveal_until_kind_then_put_clauses`
already merges the reveal with a *fixed* destination three clauses at a
time, but this card's own destination branches on a live board comparison -
a new merge, `_merge_reveal_until_kind_conditional_mv_clauses`, spans all
four of `_CLAUSE_SEPARATOR`'s own splits ("reveal cards from the top ...",
"If its mana value is less than or equal to ..., put it onto the
battlefield", "Otherwise, put it into your hand", "Put the rest on the
bottom ...") because "its"/"it" (CR 400.7/CR 607.1) is the one specific card
that stopped the reveal, which only a caller holding that live object can
answer either branch of "if" against.

Every CR number below was looked up with `mise run rules:find` in the
session that wrote this file:

- **CR 700.4** - dies: put into a graveyard from the battlefield.
- **CR 701.20a** - revealing a card does not move it.
- **CR 107.1a** - "less than or equal to" is a plain numeric comparison.
- **CR 202.3** - mana value.
- **CR 701.24a** vs **plain randomisation** - "the rest ... in a random
  order" is not CR 701.24a's shuffle (that verb is never printed), so
  nothing watching for a shuffle fires; it is the identical randomisation
  `_merge_reveal_until_kind_then_put_clauses` and `_select_from_top_runner`
  already use.

No second printing on Scryfall pairs "reveal cards from the top of your
library until you reveal a creature card" with this card's own conditional
mana-value destination (every other printing of the reveal-until-creature
family sends the found card to one fixed place - checked in the session
that wrote this file); see the dated `MEMORY.md` line. The two branches of
the "if" are both exercised here instead, on the one card that prints them.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _board(*, lands: int, library: list[str]) -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Part in Friendship"],
            battlefield=["Forest"] * lands + ["Grizzly Bears"],
            library=library,
        )
        .player("bob")
    )


def _resolve_all(scenario: Scenario) -> None:
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()


def test_mana_value_at_most_lands_controlled_puts_the_creature_onto_the_battlefield():
    scenario = _board(
        lands=6, library=["Opt", "Elvish Mystic", "Mountain", "Lightning Bolt"]
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    mystic = next(state for state in alice.library if state.name == "Elvish Mystic")
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.put_onto_battlefield("Part in Friendship", "alice")

    scenario.game.destroy(bears)
    _resolve_all(scenario)

    assert mystic.zone is Zone.BATTLEFIELD, "mana value 1 <= 6 lands controlled"
    assert mystic.controller == "alice"


def test_mana_value_above_lands_controlled_puts_the_creature_into_hand():
    scenario = _board(lands=1, library=["Opt", "Craterhoof Behemoth", "Mountain"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    hoof = next(state for state in alice.library if state.name == "Craterhoof Behemoth")
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.put_onto_battlefield("Part in Friendship", "alice")
    scenario.game.destroy(bears)
    _resolve_all(scenario)

    assert hoof not in scenario.game.battlefield, "mana value 8 > 1 land controlled"
    assert hoof in alice.hand


def test_no_creature_anywhere_bottoms_the_whole_library_and_puts_nothing():
    scenario = _board(lands=6, library=["Opt", "Lightning Bolt", "Mountain"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    original = list(alice.library)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.put_onto_battlefield("Part in Friendship", "alice")

    scenario.game.destroy(bears)
    _resolve_all(scenario)

    for state in original:
        assert state.zone is Zone.LIBRARY
    assert len(alice.library) == len(original)
