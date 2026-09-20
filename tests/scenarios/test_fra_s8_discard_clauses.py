"""FRA stream S8: discard templates - an ETB "each `<who>` discards a card"
(CR 701.9a), and a permanent watching any player's discard (CR 603.2,
`TriggerEvent.DISCARDS_A_CARD`).

Every CR number below was looked up with `mise run rules:find` in the
session that wrote this file.

- **CR 701.9a** - "To discard a card, move it from its owner's hand to that
  player's graveyard." **CR 701.9b** - by default the discarding player
  chooses which.
- **CR 603.2** - a triggered ability triggers when its event occurs; CR
  603.2c has it trigger once per occurrence, "even if it contains multiple
  discards."

Rank Rat ("When this creature enters, each opponent discards a card.") is
the reported card. Tinybones, Pocket Nuisance pairs an identical ETB with a
second, unrelated trigger - "Whenever a player discards one or more cards,
Tinybones deals 1 damage to each opponent" - watching *any* player's
discard, not only its own controller's, which is `TriggerEvent.
DISCARDS_A_CARD`'s existing subject-agnostic reading
(`machines.triggers.condition_matches`'s own `_controller_clause_holds`
default: a condition naming neither "you" nor "an opponent controls" is true
for anybody) plus the already-general "`<source>` deals N damage to each
opponent" clause (Guttersnipe's own shape).

Liliana of the Veil's `+1` ("Each player discards a card.") is the off-set
proof: a real, non-FRA, non-pool printing of the same ETB-discard shape
naming "each player" rather than "each opponent", and printed as a loyalty
ability's effect rather than an ETB trigger's - proving the clause reader
works from `parse_mixed_effect`'s shared dispatch regardless of which kind
of ability calls it in.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_rank_rat_makes_each_opponent_discard_on_entry():
    scenario = (
        Scenario()
        .player("alice", hand=["Rank Rat"], battlefield=["Swamp", "Swamp"])
        .player("bob", hand=["Grizzly Bears", "Lightning Bolt"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bob = scenario.player("bob")
    sources = scenario.untapped_sources("Swamp", "Swamp")
    bears = scenario.find("Grizzly Bears", Zone.HAND, "bob")

    scenario.will_choose_cards(bears, username="bob")
    scenario.cast_and_resolve("Rank Rat", *sources)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert bears.zone is Zone.GRAVEYARD
    assert len(bob.hand) == 1


def test_tinybones_etb_makes_each_opponent_discard():
    scenario = (
        Scenario()
        .player(
            "alice", hand=["Tinybones, Pocket Nuisance"], battlefield=["Swamp", "Swamp", "Swamp"]
        )
        .player("bob", hand=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bob = scenario.player("bob")
    sources = scenario.untapped_sources("Swamp", "Swamp", "Swamp")
    bears = scenario.find("Grizzly Bears", Zone.HAND, "bob")

    scenario.will_choose_cards(bears, username="bob")
    scenario.cast_and_resolve("Tinybones, Pocket Nuisance", *sources)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert bears.zone is Zone.GRAVEYARD
    assert bob.life == 19, "Tinybones' own second trigger: 1 damage for that same discard"


def test_tinybones_watches_any_players_discard_not_only_its_controllers():
    """The second trigger's own subject is "a player", not "you" - it fires
    off the *opponent's* discard too, dealing damage back to that same
    opponent (CR 119.3)."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Tinybones, Pocket Nuisance", "Swamp"])
        .player("bob", hand=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bob = scenario.player("bob")
    bears = scenario.find("Grizzly Bears", Zone.HAND, "bob")

    scenario.game.discard_cards("bob", [bears])
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert bears.zone is Zone.GRAVEYARD
    assert bob.life == 19


def test_liliana_of_the_veils_plus_one_makes_each_player_discard():
    """Off-set generality proof: the same ETB-discard clause shape, printed
    as a loyalty ability's own effect and naming "each player" rather than
    "each opponent"."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Grizzly Bears"],
            battlefield=["Liliana of the Veil"],
        )
        .player("bob", hand=["Lightning Bolt"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    liliana = scenario.creature("Liliana of the Veil", "alice")
    alice_bears = scenario.find("Grizzly Bears", Zone.HAND, "alice")
    bob_bolt = scenario.find("Lightning Bolt", Zone.HAND, "bob")

    scenario.will_choose_cards(alice_bears, username="alice")
    scenario.will_choose_cards(bob_bolt, username="bob")
    scenario.activate(liliana, index=0)
    scenario.pass_until_resolved()

    assert alice_bears.zone is Zone.GRAVEYARD
    assert bob_bolt.zone is Zone.GRAVEYARD
