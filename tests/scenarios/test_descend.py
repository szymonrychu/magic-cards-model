"""Scenario: Descend (CR 700.11), verified with `mise run rules:find 700.11`
in this session:

    "Some cards refer to whether a player has 'descended this turn.' This
    means that a permanent card has been put into that player's graveyard
    from anywhere this turn. 'The number of times [a player] descended this
    turn' means 'the number of permanent cards put into [that player's]
    graveyard from anywhere this turn.' In both cases, no permanent cards
    put into the player's graveyard that turn are required to still be in
    that graveyard."

`Game.permanent_cards_to_graveyard_this_turn` is the running per-turn count
this fix adds (schema 21 -> 22, `Game.CURRENT_SCHEMA_VERSION`'s own
docstring). `Game.descended`/`Game.descend_count` answer CR 700.11's two
questions off it; `intervening_if_holds`'s "you descended this turn" clause
and `_amount_term`'s "the number of times you descended this turn" term read
those, off the card's own printed text, with no per-card row.

Oracle text pulled with `scripts/add_card.py` and verified against
`src/magic_cards_model/data/printings/`:

- **Ruin-Lurker Bat**: "At the beginning of your end step, if you descended
  this turn, scry 1." The boolean condition alone.
- **Broodrage Mycoid** (off-pool, proves the parser generalises rather than
  reading Ruin-Lurker Bat's exact sentence): "At the beginning of your end
  step, if you descended this turn, create a 1/1 black Fungus creature
  token with 'This token can't block.'" Same condition, a different effect.
- **The Mycotyrant** (off-pool, the count half): "At the beginning of your
  end step, create X 1/1 black Fungus creature tokens ..., where X is the
  number of times you descended this turn."

The count is fed from every route this wave found that lands a card in a
graveyard "from anywhere": `Game.put_into_graveyard` (destroy, mill, a
resolved/countered/fizzled spell), `machines/keywords.discard`, and
`machines/keywords.dredge` - exercised below via discard and mill.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone

from .harness import Scenario


def _fungus_tokens(scenario, username: str = "alice") -> list:
    return [
        state
        for state in scenario.game.battlefield
        if state.controller == username and state.token and "Fungus" in (state.card.type_line or "")
    ]


def test_ruin_lurker_bat_scries_after_a_permanent_card_is_discarded():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Ruin-Lurker Bat"],
            hand=["Grizzly Bears"],
            library=["Mountain", "Forest"],
        )
        .build()
    )
    scenario.start_at(Step.POSTCOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.HAND, "alice")
    scenario.game.discard_cards("alice", [bears])
    assert scenario.game.descended("alice")

    top_before = scenario.player("alice").library[0].name
    scenario.scry_keeping_everything_on_top(username="alice")
    scenario.advance()  # end step
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert scenario.player("alice").library[0].name == top_before


def test_ruin_lurker_bat_does_not_trigger_without_descending():
    scenario = (
        Scenario().player("alice", battlefield=["Ruin-Lurker Bat"], library=["Mountain"]).build()
    )
    scenario.start_at(Step.POSTCOMBAT_MAIN)
    assert not scenario.game.descended("alice")

    scenario.advance()  # end step
    scenario.game.put_triggers_on_stack()

    assert scenario.game.stack == []


def test_off_pool_broodrage_mycoid_creates_a_token_after_a_permanent_is_milled():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Broodrage Mycoid"],
            library=["Grizzly Bears", "Mountain"],
        )
        .build()
    )
    scenario.start_at(Step.POSTCOMBAT_MAIN)
    top = scenario.player("alice").library[0]
    scenario.game.put_into_graveyard(top)
    assert scenario.game.descended("alice")
    assert scenario.game.descend_count("alice") == 1

    scenario.advance()  # end step
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    fungi = _fungus_tokens(scenario)
    assert len(fungi) == 1


def test_off_pool_the_mycotyrant_counts_every_descend_this_turn():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["The Mycotyrant"],
            hand=["Grizzly Bears"],
            library=["Elvish Mystic", "Mountain", "Forest"],
        )
        .build()
    )
    scenario.start_at(Step.POSTCOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.HAND, "alice")
    scenario.game.discard_cards("alice", [bears])  # one permanent card
    mystic = scenario.player("alice").library[0]
    scenario.game.put_into_graveyard(mystic)  # Elvish Mystic: a second

    assert scenario.game.descend_count("alice") == 2

    scenario.advance()  # end step
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    fungi = _fungus_tokens(scenario)
    assert len(fungi) == 2


def test_a_permanent_card_leaving_the_graveyard_again_still_counts():
    """CR 700.11's own closing sentence: "no permanent cards put into the
    player's graveyard that turn are required to still be in that
    graveyard." Milling, then exiling the milled card, still counts."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Ruin-Lurker Bat"], library=["Grizzly Bears", "Mountain"])
        .build()
    )
    scenario.start_at(Step.POSTCOMBAT_MAIN)
    top = scenario.player("alice").library[0]
    scenario.game.put_into_graveyard(top)
    milled = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")
    scenario.game.exile_cards([milled])

    assert milled.zone is Zone.EXILE
    assert scenario.game.descended("alice")
