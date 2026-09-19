"""Sheoldred, Whispering One and Sheoldred, the Apocalypse's own "an
opponent" triggers - both used to fire for *every* player, not only an
opponent, because two different condition matchers read "opponent" only for
a narrower verb than the one actually printed:

- **CR 500.6 / CR 603.1**: "At the beginning of each opponent's upkeep, ..."
  (Sheoldred, Whispering One) - `machines/triggers._step_matches` only ever
  special-cased "your" against `event.player`; anything else, including
  "each opponent's", fell to the "whoever's step it is" default and matched
  the ability's own controller's upkeep too.
- **CR 121.2**: "Whenever an opponent draws a card, ..." (used generally,
  Sheoldred, the Apocalypse's own trigger) - `machines/triggers.
  intervening_if_holds`'s CAST_SPELL branch had the identical bug for "an
  opponent casts" (see `test_jin_gitaxias.py`); DRAWS_A_CARD's own branch was
  already correct, so this file is proof the fix generalises rather than a
  second bug to fix.

Two effect-side gaps closed alongside them:

- **"That player sacrifices `<n>` `<description>` of their choice."** - CR
  607.1's anaphora to whichever specific opponent's upkeep just triggered
  the ability (`GameEvent.player`), not "each opponent" all at once
  (`_parse_that_player_sacrifices_of_their_choice_clause`, a sibling of the
  existing `_parse_each_sacrifices_of_their_choice_clause`).
- **"They gain/lose N life."** - the same CR 607.1 anaphora for a life total
  (`_parse_they_gain_or_lose_life_clause`).
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone

from .harness import Scenario


def test_sheoldred_whispering_one_makes_only_the_opponent_sacrifice_on_their_own_upkeep():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Sheoldred, Whispering One"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.UPKEEP)
    # Alice's own upkeep: no trigger for her, since she is not her own opponent.
    scenario.game.put_triggers_on_stack()
    assert scenario.game.stack == []

    while not (scenario.step is Step.UPKEEP and scenario.turn.active_player == "bob"):
        scenario.advance()
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == ["Sheoldred, Whispering One's triggered ability"]
    scenario.pass_until_resolved()

    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "bob")
    assert bears.zone is Zone.GRAVEYARD


def test_sheoldred_whispering_one_does_not_ask_alice_to_sacrifice_on_her_own_upkeep():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Sheoldred, Whispering One", "Elvish Mystic"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.UPKEEP)
    scenario.game.put_triggers_on_stack()

    assert scenario.game.stack == []
    mystic = scenario.creature("Elvish Mystic", "alice")
    assert mystic.zone is Zone.BATTLEFIELD


def test_sheoldred_the_apocalypse_only_opponents_lose_life_when_they_draw():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Sheoldred, the Apocalypse"], library=["Mountain"] * 3)
        .player("bob", library=["Forest"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.draw(1, "alice")
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()
    assert scenario.player("alice").life == 22  # her own draw: she gains
    assert scenario.player("bob").life == 20

    scenario.draw(1, "bob")
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()
    assert scenario.player("bob").life == 18  # an opponent's draw: bob loses
    assert scenario.player("alice").life == 22  # unaffected by bob's draw
