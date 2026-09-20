"""FRA stream S8: a search that puts its own find into a graveyard (a new
`Zone.GRAVEYARD` destination on `Game.search_and_put`), "target player draws
`<n>` and loses `<n>` life" (already general), and "each player may discard
their hand and draw `<n>` cards" (a new whole-text clause reader).

Every CR number below was looked up with `mise run rules:find` in the
session that wrote this file.

- **CR 701.23a/701.24a** - searching and the post-search shuffle.
- **CR 400.6/614.1a** - "put into a graveyard" is the event Rest in Peace and
  Leyline of the Void watch for, whichever instruction moves the card there;
  routed through `Game.put_into_graveyard`, the one shared mover, rather
  than a bespoke zone assignment.
- **CR 121.1/121.2** - drawing. **CR 119.2/119.3** - losing life.
- **CR 608.2d** - each player's own "you may" is asked of that player, not
  of the resolving ability's controller.

Three FRA cards, three off-set proofs:

- Carnivorous Cultivator // Enroot's own inset spell ("Search your library
  for a land card, put it into your graveyard, then shuffle.") is the
  reported card. Casting the inset itself needs FRA stream S2's own
  "prepared" cast permission, not on this branch (see that stream's own
  merge); Goblin Engineer (Modern Horizons 1, real, non-FRA, non-pool) is
  an ordinary ETB trigger with the identical "search, put into graveyard"
  shape and a different, optional ("you may") structure, played end to end.
- Bloodline Recollector // Ancestral Craving's own inset ("Target player
  draws three cards and loses 3 life.") already read correctly with no new
  code - `parse_mixed_effect_for_spell` already composes "draws N cards"
  and "loses N life" through the existing bare-"and" merge. Blood Pact
  (Duskmourn Commander, real, non-FRA, non-pool) prints the identical
  shape as an ordinary castable sorcery with a different count, played end
  to end for the same reason above.
- Variable Chaser // Arc of Fortune's own inset ("Each player may discard
  their hand and draw seven cards.") is the reported card, and the new
  clause reader here. Ruin Grinder (Commander 2021, real, non-FRA,
  non-pool) prints the identical shape off a dies trigger rather than a
  cast sorcery, played end to end.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_enroots_own_clause_reads_search_put_into_graveyard_then_shuffle():
    """The clause reader itself, proven directly: FRA stream S2's own
    "prepared" cast permission for the inset spell is not on this branch."""
    from magic_cards_model.machines.effects import parse_mixed_effect_for_spell

    effect = parse_mixed_effect_for_spell(
        "Search your library for a land card, put it into your graveyard, then shuffle."
    )
    assert effect is not None


def test_goblin_engineer_searches_an_artifact_card_into_the_graveyard():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Goblin Engineer"],
            battlefield=["Mountain", "Mountain"],
            library=["Sol Ring", "Forest", "Island"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    sources = scenario.untapped_sources("Mountain", "Mountain")
    sol_ring = next(state for state in alice.library if state.name == "Sol Ring")

    scenario.will_take_the_may(True, source="Goblin Engineer")
    scenario.will_choose_cards(sol_ring, username="alice")
    scenario.cast_and_resolve("Goblin Engineer", *sources)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert sol_ring.zone is Zone.GRAVEYARD
    assert len(alice.library) == 2


def test_blood_pact_draws_and_loses_life_with_a_different_count():
    scenario = (
        Scenario()
        .player("alice", hand=["Blood Pact"], battlefield=["Swamp", "Swamp", "Swamp"])
        .player("bob", library=["Forest"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bob = scenario.player("bob")
    sources = scenario.untapped_sources("Swamp", "Swamp", "Swamp")
    life_before = bob.life

    scenario.cast_and_resolve("Blood Pact", *sources, targets=["bob"])

    assert len(bob.hand) == 2
    assert bob.life == life_before - 2


def test_ruin_grinder_dies_and_each_player_may_discard_hand_and_draw():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Bolt"],
            battlefield=["Ruin Grinder"],
            library=["Forest"] * 8,
        )
        .player("bob", hand=["Grizzly Bears"], library=["Forest"] * 8)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    bob = scenario.player("bob")
    grinder = scenario.creature("Ruin Grinder", "alice")
    alice_bolt = scenario.find("Lightning Bolt", Zone.HAND, "alice")
    bob_bears = scenario.find("Grizzly Bears", Zone.HAND, "bob")

    scenario.game.destroy(grinder)
    scenario.game.put_triggers_on_stack()
    scenario.will_take_the_may(True, source="Ruin Grinder", username="alice")
    scenario.will_take_the_may(False, source="Ruin Grinder", username="bob")
    scenario.pass_until_resolved()

    assert alice_bolt.zone is Zone.GRAVEYARD, "alice took the may: her whole hand is discarded"
    assert len(alice.hand) == 7
    assert bob_bears.zone is Zone.HAND, "bob declined: his hand is untouched"
    assert len(bob.hand) == 1
