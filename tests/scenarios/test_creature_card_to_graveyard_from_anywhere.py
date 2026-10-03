"""Scenario: "a `<type>` card was put into your graveyard from anywhere this
turn" - CR 700.11's own "from anywhere" look-back, generalized from
`Game.descended`'s unqualified "permanent card" question to a *named* card
type, so any type word composes rather than only "creature".

Verified with `mise run rules:find` in this session:

- **CR 700.11**: "descended this turn" means "a permanent card has been put
  into that player's graveyard from anywhere this turn ... no permanent
  cards put into the player's graveyard that turn are required to still be
  in that graveyard." The identical look-back, narrowed here from "permanent
  card" to one named type.
- **CR 603.4**: the intervening "if" clause.
- **CR 601.2f**: a spell's total cost, and its cost reductions.

`GraveyardArrival.card_types` (schema 95 -> 96) keeps the arriving card's own
printed types (the same source `is_permanent_card` already reads off
`card_state.types`) alongside the existing `is_permanent_card` boolean, so a
"creature card" question is answered without touching `descended`'s own
"permanent card" one.

Oracle text pulled with `scripts/add_card.py`:

- **Raphael, Fiendish Savior** (the reported card, its static anthem line out
  of scope for this file): "At the beginning of each end step, if a creature
  card was put into your graveyard from anywhere this turn, create a 1/1 red
  Devil creature token with 'When this token dies, it deals 1 damage to any
  target.'"
- **Macabre Reconstruction** (Modern/Pioneer/Standard legal, the second
  printing of the template): "This spell costs {2} less to cast if a
  creature card was put into your graveyard from anywhere this turn." The
  identical condition read through `Game.cost_reduction_for`'s CR 601.2f
  self-discount - a different rules path from Raphael's own triggered-
  ability intervening if, both ending in the same `Game.condition_holds`/
  `machines/conditions.read_condition`. No Modern/Pioneer/Standard-legal
  printing carries a *different* quality word on this exact "from anywhere"
  template (a Scryfall search for "artifact card"/"land card"/"permanent
  card" variants of it turns up none at all besides the unqualified
  "permanent card" `descended` already owns), so the two real printings here
  are proven on two different rules paths instead of two different quality
  words.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone

from .harness import Scenario


def _devil_tokens(scenario, username: str = "alice") -> list:
    return [
        state
        for state in scenario.game.battlefield
        if state.controller == username and state.token and "Devil" in (state.card.type_line or "")
    ]


def test_raphael_creates_a_devil_after_a_creature_dies_this_turn():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Raphael, Fiendish Savior", "Grizzly Bears"],
        )
        .build()
    )
    scenario.start_at(Step.POSTCOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.game.destroy(bears)

    scenario.advance()  # end step
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    devils = _devil_tokens(scenario)
    assert len(devils) == 1
    assert not scenario.game.intervening_if_notices


def test_raphael_does_not_trigger_with_no_creature_card_to_the_graveyard():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Raphael, Fiendish Savior"], hand=["Mountain"])
        .build()
    )
    scenario.start_at(Step.POSTCOMBAT_MAIN)
    mountain = scenario.find("Mountain", Zone.HAND, "alice")
    scenario.game.discard_cards("alice", [mountain])  # a land card, not a creature card

    scenario.advance()  # end step
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == []
    assert not scenario.game.intervening_if_notices


def test_raphael_reads_a_discarded_creature_card_too():
    """ "From anywhere" (CR 700.11): a discard never touches the battlefield,
    the second of `descended`'s own two proof paths, exercised here for the
    typed question rather than the unqualified one."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Raphael, Fiendish Savior"], hand=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.POSTCOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.HAND, "alice")
    scenario.game.discard_cards("alice", [bears])

    scenario.advance()  # end step
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert len(_devil_tokens(scenario)) == 1


def test_macabre_reconstruction_costs_two_less_after_a_creature_card_arrives():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Macabre Reconstruction"],
            battlefield=["Swamp"] * 5 + ["Grizzly Bears"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.game.destroy(bears)

    casting = scenario.cast("Macabre Reconstruction")
    scenario.game.determine_total_cost(casting)

    assert str(casting.total_cost.mana) == "{1}{B}", "{3}{B} minus {2} generic (CR 118.7a)"


def test_macabre_reconstruction_costs_full_with_no_creature_card_arrival():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Macabre Reconstruction"], battlefield=["Swamp"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Macabre Reconstruction")
    scenario.game.determine_total_cost(casting)

    assert str(casting.total_cost.mana) == "{3}{B}", "the printed cost, undiscounted"
