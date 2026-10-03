"""Scenario: "you created a token this turn" - an intervening if (CR 603.4)
over CR 701.7's token creation, read generically for any card printing it
rather than for Bennie Bracks, Zoologist in particular.

Verified with `mise run rules:find` in this session:

- **CR 603.4**: the intervening "if" clause, checked as the trigger event
  occurs and again on resolution.
- **CR 111.2**: "The player who creates a token is its owner. The token
  enters the battlefield under that player's control."
- **CR 701.7a**: "To create one or more tokens with certain characteristics,
  put the specified number of tokens with the specified characteristics onto
  the battlefield." `models.token.create_tokens` calls
  `models.token._note_token_creation`, which already notes every creation
  event per player per turn (`Game.turn_counts`); this file's own job is
  wiring a *reader* for the printed condition onto that existing ledger.

Oracle text pulled with `scripts/add_card.py` and read off
`src/magic_cards_model/data/printings/`:

- **Bennie Bracks, Zoologist** (the reported card): "At the beginning of
  each end step, if you created a token this turn, draw a card."
- **Idol of Oblivion** (the second printing of the template, proving the
  reader is not keyed to Bennie Bracks's own sentence): "{T}: Draw a card.
  Activate only if you created a token this turn." The identical condition,
  read on a different CR 602.5b activation-restriction path rather than a
  triggered ability's own CR 603.4 intervening if - `Game.
  activation_instruction_refusal`'s "only if" branch and `intervening_if_
  answer` both end in the same `machines/conditions.read_condition`, so one
  reader serves both. Neither printing is Modern/Pioneer/Standard legal (a
  Scryfall `o:"you created a token this turn"` search turns up only these
  two, both Legacy/Vintage/Commander only); no third, format-legal printing
  of this template exists to substitute, which is the genuine reason a
  format-legal second card could not be found for this clause.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Color
from magic_cards_model.models.token import TokenDefinition, create_tokens

from .harness import Scenario

SOLDIER = TokenDefinition(subtypes=("Soldier",), colors=(Color.WHITE,), power=1, toughness=1)


def _resolve_all(scenario) -> None:
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()


def _to_end_step(scenario) -> None:
    while scenario.step is not Step.END_STEP:
        scenario.advance()


def test_bennie_bracks_draws_a_card_when_a_token_was_created_this_turn():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Bennie Bracks, Zoologist"], library=["Island"] * 5)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    create_tokens(scenario.game, SOLDIER, "alice")
    hand = len(scenario.player("alice").hand)

    _to_end_step(scenario)
    _resolve_all(scenario)

    assert len(scenario.player("alice").hand) == hand + 1
    assert not scenario.game.intervening_if_notices


def test_bennie_bracks_does_not_draw_with_no_token_created_this_turn():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Bennie Bracks, Zoologist", "Grizzly Bears"],
            library=["Island"] * 5,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    hand = len(scenario.player("alice").hand)

    _to_end_step(scenario)
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == []
    assert not scenario.game.intervening_if_notices
    assert len(scenario.player("alice").hand) == hand


def test_the_token_creation_is_this_turns_own():
    """A new turn starts from nothing (`Game.turn_counts` rolls at cleanup,
    the same per-turn ledger `Player.life_lost_this_turn` and every other
    "this turn" fact already resets on)."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Bennie Bracks, Zoologist"], library=["Island"] * 5)
        .player("bob", library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    create_tokens(scenario.game, SOLDIER, "alice")
    _to_end_step(scenario)
    _resolve_all(scenario)
    scenario.advance()  # cleanup
    scenario.advance()  # bob's untap
    scenario.advance()  # bob's upkeep
    scenario.advance()  # bob's draw
    hand = len(scenario.player("alice").hand)

    _to_end_step(scenario)
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == []
    assert len(scenario.player("alice").hand) == hand


def test_idol_of_oblivion_activation_restriction_reads_the_identical_condition():
    """Idol of Oblivion prints "you created a token this turn" as a CR
    602.5b activation restriction rather than a triggered ability's
    intervening if - the second rules path this package's readers are
    shared by, proven here since no third, format-legal printing of the
    template exists to add as a genuinely separate card."""
    scenario = Scenario().player("alice", battlefield=["Idol of Oblivion"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    idol = scenario.creature("Idol of Oblivion", "alice")

    assert scenario.why_cannot_activate(idol, index=0) is not None

    create_tokens(scenario.game, SOLDIER, "alice")

    assert scenario.why_cannot_activate(idol, index=0) is None
