"""Silvan Reveler: "When this creature enters, draw a card, then discard a
card. If you discard a land card this way, put it from your graveyard onto
the battlefield tapped."

CR 121.1's draw and CR 701.9a's discard were both already independently
readable clauses (`_DRAW_RE`, `_DISCARD_A_CARD_RE`) - the gap was the third
sentence, "If you discard a land card this way, put it from your graveyard
onto the battlefield tapped.", CR 400.7/CR 607.1 anaphora back to *the
specific card the discard just moved*, which a fresh graveyard scan cannot
tell apart from a land that was already there. `_merge_discard_then_land_
rebate_clauses`, a new two-clause merge, holds onto `_discard_cards`'s own
return value (the cards it actually moved - the same value Winternight
Stories' and CR 701.70a's "if you discarded a nonland card this way" family
already reads) and checks the rebate's own printed quality against exactly
those.

Every CR number below was looked up with `mise run rules:find` in the
session that wrote this file:

- **CR 121.1** - drawing a card, one at a time.
- **CR 701.9a/701.9b** - discarding moves a card from hand to graveyard; the
  discarding player chooses which, absent an override.
- **CR 400.7** - "this way" names the specific object the previous sentence
  moved, not the graveyard generally.
- **CR 110.2a** - a card returned to the battlefield "from your graveyard"
  is put there, never cast, so no cast trigger fires.

No second printing on Scryfall pairs "discard a card" with "If you discard a
land card this way, put it from your graveyard onto the battlefield tapped"
(checked in the session that wrote this file) - see the dated `MEMORY.md`
line.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _cast_silvan_reveler(scenario: Scenario) -> None:
    sources = scenario.untapped_sources("Forest", "Island", "Forest", "Island")
    scenario.cast_and_resolve("Silvan Reveler", *sources)
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()


def test_discarding_the_drawn_land_returns_it_tapped():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Silvan Reveler"],
            battlefield=["Forest", "Forest", "Island", "Island"],
            library=["Mountain"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    mountain = scenario.player("alice").library[0]
    scenario.will_discard(mountain, username="alice")
    _cast_silvan_reveler(scenario)

    assert mountain.zone is Zone.BATTLEFIELD
    assert mountain.tapped
    assert mountain.controller == "alice"


def test_discarding_a_nonland_card_stays_in_the_graveyard():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Silvan Reveler"],
            battlefield=["Forest", "Forest", "Island", "Island"],
            library=["Opt"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    opt = scenario.player("alice").library[0]
    scenario.will_discard(opt, username="alice")
    _cast_silvan_reveler(scenario)

    assert opt.zone is Zone.GRAVEYARD
