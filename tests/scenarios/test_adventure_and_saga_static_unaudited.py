"""Scenario: proof for the `static_unaudited` clauses `scripts/sweep_pool.py`
found on two adventure faces and one Saga chapter - CR 715's Adventure
already reaches the underlying readers, only the readers themselves lacked a
scenario.

- Gollum, Silent Slinker // Meager Meal: "Put a +1/+1 counter on up to one
  target creature. Target player gains 2 life." (the adventure sorcery
  half).
- Great Ugly-Looking Goblin // Clap! Snap!: "Amass Goblins 2." (the adventure
  sorcery half).
- The Misty Mountains Cold's own chapter effect (see
  test_count_based_tokens.py's docstring for the mechanic table row; this
  file is the chapter's own scenario proof).

Verified this session with `mise run rules:find`: CR 715.3 (an Adventure
sorcery is cast from hand like any other, CR 601), CR 122.1 (a +1/+1
counter), CR 701.47a (amass), CR 119.3 (life gain), CR 714.4 (a Saga chapter
ability).
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.effects import PREDEFINED, create_tokens
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter

from .harness import Scenario


def test_meager_meal_counters_a_creature_and_gains_its_targets_life():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Gollum, Silent Slinker // Meager Meal"],
            battlefield=["Elvish Mystic"] + ["Swamp"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mystic = scenario.creature("Elvish Mystic", "alice")
    life_before = scenario.player("alice").life

    casting = scenario.cast("Gollum, Silent Slinker")
    casting.cast_as_adventure()
    casting.choose_targets([mystic, "alice"])
    scenario.pay_with(casting.begin_paying(), *scenario.untapped_sources("Swamp"))
    scenario.put_on_stack(casting)
    scenario.pass_until_resolved()

    assert mystic.counters[Counter.PLUS_ONE] == 1
    assert scenario.player("alice").life == life_before + 2
    exiled = scenario.find("Gollum, Silent Slinker", Zone.EXILE, "alice")
    assert exiled.zone is Zone.EXILE  # CR 715.3d: waits to be cast as the creature


def test_clap_snap_amasses_goblins_two():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Great Ugly-Looking Goblin // Clap! Snap!"],
            battlefield=["Swamp", "Swamp"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Great Ugly-Looking Goblin")
    casting.cast_as_adventure()
    scenario.pay_with(casting.begin_paying(), *scenario.untapped_sources("Swamp", "Swamp"))
    scenario.put_on_stack(casting)
    scenario.pass_until_resolved()

    army = scenario.creature("Goblin Army Token", "alice")
    assert army.counters[Counter.PLUS_ONE] == 2
    assert "Goblin" in scenario.game.characteristics_of(army).subtypes


def test_misty_mountains_cold_makes_treasures_then_a_dragon():
    """Each chapter's own effect ("create a Treasure. Then if you control
    four or more Treasures, sacrifice this Saga. If you do, create a 6/6 red
    Dragon creature token with flying.") is proven with two Treasures already
    on the battlefield, so this card's own "four or more Treasures" threshold
    is crossed by an *earlier* chapter than CR 714.4's own unconditional
    "sacrifice once lore counters reach the final chapter" state-based
    action would apply on its own (that generic Saga rule - S26's, not this
    task's - would otherwise sacrifice the Saga at the same lore count
    regardless of what its own printed chapter text says, making the two
    indistinguishable at the last chapter)."""
    scenario = (
        Scenario().player("alice", battlefield=["The Misty Mountains Cold"]).player("bob").build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    saga = scenario.creature("The Misty Mountains Cold", "alice")
    create_tokens(scenario.game, PREDEFINED["Treasure"], "alice", 2)

    for _ in range(3):
        if saga.zone is not Zone.BATTLEFIELD:
            break
        scenario.game.add_counters(saga, Counter.LORE, 1)
        scenario.pass_until_resolved()
        scenario.pass_until_resolved()

    assert saga.zone is Zone.GRAVEYARD
    treasures = [
        state
        for state in scenario.game.permanents_controlled_by("alice")
        if state.name == "Treasure Token"
    ]
    assert len(treasures) == 4
    dragon = scenario.creature("Dragon Token", "alice")
    assert dragon.zone is Zone.BATTLEFIELD
    characteristics = scenario.game.characteristics_of(dragon)
    assert characteristics.power == 6
    assert characteristics.toughness == 6
