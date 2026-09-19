"""Eye of Jace's own upkeep trigger: a surveil, then a graveyard-count-
gated three-instruction Oxford-comma list ("sacrifice this artifact, it
deals 2 damage to each opponent, and you gain 2 life") - the comma-list
fallback split `_parse_if_graveyard_count_clause` needed this session,
plus a "tried whole" pre-check ahead of the ordinary sentence-count branch
in `_parse_mixed_clauses`.

Verified this session with `knowledge_search(q="...", type="rules")` and
cross-checked with `mise run rules:find` (on-disk CR effective 2026-09-25):

- **CR 701.25a** - to surveil N: look at the top N cards, then put any
  number of them into the graveyard and the rest back on top in any order.
- **CR 603.4** - the "if there are seven or more cards" gate is checked as
  the ability resolves (CR 608.2a's recheck), after the surveil that just
  ran has already changed the graveyard's own count.
- **CR 608.2c** - the three post-gate instructions run in printed order.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_eye_of_jace_surveils_then_sacrifices_and_burns_at_seven_cards() -> None:
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Eye of Jace"],
            library=["Opt"],
            graveyard=["Grizzly Bears"] * 6,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.UNTAP)
    eye = scenario.find("Eye of Jace", Zone.BATTLEFIELD, "alice")
    bob_life_before = scenario.game.player("bob").life
    alice_life_before = scenario.game.player("alice").life
    scenario.surveil_to_graveyard(scenario.find("Opt", Zone.LIBRARY, "alice"))
    while scenario.step is not Step.UPKEEP:
        scenario.advance()

    scenario.resolve_top()  # the upkeep trigger

    assert eye.zone is Zone.GRAVEYARD
    assert scenario.game.player("bob").life == bob_life_before - 2
    assert scenario.game.player("alice").life == alice_life_before + 2


def test_eye_of_jace_only_surveils_below_seven_cards() -> None:
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Eye of Jace"],
            library=["Opt"],
            graveyard=["Grizzly Bears"] * 3,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.UNTAP)
    eye = scenario.find("Eye of Jace", Zone.BATTLEFIELD, "alice")
    bob_life_before = scenario.game.player("bob").life
    scenario.surveil_keeping_everything_on_top()
    while scenario.step is not Step.UPKEEP:
        scenario.advance()

    scenario.resolve_top()  # the upkeep trigger

    assert eye.zone is Zone.BATTLEFIELD
    assert scenario.game.player("bob").life == bob_life_before
