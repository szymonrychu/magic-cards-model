"""Scenario: excess damage feeding an amass amount (CR 120.10, CR 701.47a).

Bolg of the North: "When Bolg enters, you may sacrifice another creature.
When you do, Bolg deals damage equal to that creature's power to another
target creature. If excess damage was dealt this way, amass Goblins X, where
X is that excess damage."

Verified this session with `mise run rules:find`:

- **CR 120.10** - "excess damage" for a creature is the amount dealt above
  its remaining toughness (damage already marked subtracted), read *before*
  the new damage is applied.
- **CR 607.1** - linked abilities: "When you do" refers only to the
  sacrifice this same paragraph's own first sentence offered.
- **CR 118.12** - the sacrifice is an optional cost, checked as a choice at
  resolution, not as a later board fact.

`Fall of Cair Andros` (off-pool, added with `scripts/add_card.py`, Modern-legal,
verified against its own printed text) proves the excess-damage-into-amass
composition is a real, non-HOB template rather than an invented one - its own
"amass Orcs X, where X is that excess damage" is `machines/effects.amass`'s
generic `subtype` reading unchanged from Bolg's own "Goblins"; only the
trigger condition watching the damage differs (a static "whenever a creature
is dealt excess damage", not this card's own sacrifice-then-damage
paragraph), and that difference is exactly why this file exercises Bolg's own
three-sentence shape directly rather than through that card.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter

from .harness import Scenario


def test_excess_damage_over_a_2_toughness_creature_amasses_the_difference():
    """Alice sacrifices a Grizzly Bears (power 2) to deal 2 damage to Bob's
    Runeclaw Bear (toughness 2, no damage marked): 0 excess, so nothing is
    amassed."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Bolg of the North"],
            battlefield=["Swamp"] * 4 + ["Mountain"] + ["Grizzly Bears"],
        )
        .player("bob", battlefield=["Runeclaw Bear"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears_to_sac = scenario.creature("Grizzly Bears", "alice")
    target = scenario.creature("Runeclaw Bear", "bob")

    scenario.will_take_the_may(True, source="Bolg of the North")
    scenario.choose_trigger_targets("Bolg of the North", [target])
    scenario.cast_and_resolve(
        "Bolg of the North",
        *scenario.untapped_sources(*(["Swamp"] * 4 + ["Mountain"])),
        sacrificing=[bears_to_sac],
    )
    scenario.pass_until_resolved()

    assert bears_to_sac.zone is Zone.GRAVEYARD
    assert target.zone is Zone.GRAVEYARD  # 2 damage killed the 2/2
    assert not any(state.name == "Goblin Army Token" for state in scenario.game.battlefield)


def test_excess_damage_over_a_1_toughness_creature_amasses_the_excess():
    """Sacrificing the same 2-power Grizzly Bears to deal damage to a 1/1
    Elvish Mystic: 1 lethal, 1 excess (CR 120.10), so Alice amasses Goblins
    1."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Bolg of the North"],
            battlefield=["Swamp"] * 4 + ["Mountain"] + ["Grizzly Bears"],
        )
        .player("bob", battlefield=["Elvish Mystic"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears_to_sac = scenario.creature("Grizzly Bears", "alice")
    target = scenario.creature("Elvish Mystic", "bob")

    scenario.will_take_the_may(True, source="Bolg of the North")
    scenario.choose_trigger_targets("Bolg of the North", [target])
    scenario.cast_and_resolve(
        "Bolg of the North",
        *scenario.untapped_sources(*(["Swamp"] * 4 + ["Mountain"])),
        sacrificing=[bears_to_sac],
    )
    scenario.pass_until_resolved()

    assert bears_to_sac.zone is Zone.GRAVEYARD
    assert target.zone is Zone.GRAVEYARD
    army = scenario.creature("Goblin Army Token", "alice")
    assert army.counters[Counter.PLUS_ONE] == 1
    assert "Goblin" in scenario.game.characteristics_of(army).subtypes


def test_declining_the_sacrifice_amasses_nothing():
    """CR 118.12/608.2d: declining the optional cost means "when you do"
    never fires at all, and the whole rest of the ability is skipped."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Bolg of the North"],
            battlefield=["Swamp"] * 4 + ["Mountain"] + ["Grizzly Bears"],
        )
        .player("bob", battlefield=["Elvish Mystic"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    target = scenario.creature("Elvish Mystic", "bob")

    scenario.will_take_the_may(False, source="Bolg of the North")
    scenario.cast_and_resolve(
        "Bolg of the North", *scenario.untapped_sources(*(["Swamp"] * 4 + ["Mountain"]))
    )
    scenario.pass_until_resolved()

    assert bears.zone is Zone.BATTLEFIELD
    assert target.zone is Zone.BATTLEFIELD
    assert target.damage == 0
    assert not any(state.name == "Goblin Army Token" for state in scenario.game.battlefield)
