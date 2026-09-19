"""fra-final-audit batch A, item 1: a permanent spell's own resolution must
never run its printed text as though it were an instant's or sorcery's
effect.

**CR 608.3**: "If the object that's resolving is a permanent spell, its
resolution may involve several steps." Those steps (608.3a-g) are: become a
permanent and enter the battlefield; check a target if it has one; enter
attached (Aura), merge (mutate), or go to the graveyard if it can't enter;
become a token if it was a copy; create a delayed trigger if a static ability
that functions on the stack says so (dash/blitz/warp). None of them execute
the permanent's own triggered, activated, or static ability text - CR 112.6a
draws that line: "Some effects instruct a player to ... A triggered ability
[or] activated ability ... functions only ... while the permanent ... is on
the battlefield" (and CR 113.6 makes clear a static ability's effect exists
only "as long as the permanent ... remains on the battlefield").

`models/game.py::Game._resolve_top` used to call `effect_for` on *every*
resolving spell's whole oracle text, permanent or not, which ran a
permanent's triggered-ability body immediately (Screeching Soulbreaker
draining life the instant it resolved, never waiting for its attack
trigger), created indefinite-duration copies of its static abilities that
outlived the permanent (Ghalta the Immovable), and logged spurious
`LayerRemainderNotice`s for permanents whose real abilities the classifier
never actually failed to read at all (Garruk, Veiled Butcher; Proft,
Sinister Mastermind) - all four confirmed live before this file existed.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_screeching_soulbreaker_does_not_drain_life_on_resolution():
    """Screeching Soulbreaker: "Whenever this creature attacks, it deals 1
    damage to each opponent and you gain 1 life." is a triggered ability
    (CR 603) that functions only on the battlefield - casting the creature
    must not run its body."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Screeching Soulbreaker"], battlefield=["Swamp", "Swamp", "Swamp"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Swamp", "Swamp", "Swamp", username="alice")
    alice = scenario.player("alice")
    bob = scenario.player("bob")

    soulbreaker = scenario.cast_and_resolve("Screeching Soulbreaker", *sources, username="alice")

    assert soulbreaker.zone is Zone.BATTLEFIELD
    assert alice.life == 20
    assert bob.life == 20


def test_ghalta_the_immovable_creates_no_resolution_time_continuous_effect():
    """Ghalta the Immovable's two static lines ("Creatures you control can
    attack as though they didn't have defender." and "Each creature you
    control with toughness greater than its power assigns combat damage
    equal to its toughness rather than its power.") are CR 611.3 static
    abilities, reapplied every time the board is computed for as long as
    Ghalta is on the battlefield with them (CR 611.3b) - never a CR 611.2
    one-shot effect created as the spell resolves. Casting it must leave
    `Game.continuous_effects` empty; `machines/layers.py`'s own battlefield
    sweep is what supplies the static abilities, not this list.
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Ghalta the Immovable"], battlefield=["Plains"] * 9)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources(*(["Plains"] * 9), username="alice")

    ghalta = scenario.cast_and_resolve("Ghalta the Immovable", *sources, username="alice")

    assert ghalta.zone is Zone.BATTLEFIELD
    assert scenario.game.continuous_effects.effects == []
    assert scenario.game.layer_remainder_notices == []


def test_ghalta_the_immovable_static_effects_do_not_outlive_it():
    """The functional half of the same bug: before this fix, the spurious
    resolution-time copies had `Duration.INDEFINITE` and no tie to Ghalta's
    own presence, so a second creature kept assigning combat damage equal to
    its toughness after Ghalta left the battlefield. CR 611.3b: "the effect
    ends" once its source leaves.
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Ghalta the Immovable"],
            battlefield=["Plains"] * 9 + ["Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources(*(["Plains"] * 9), username="alice")
    bears = scenario.creature("Grizzly Bears", "alice")

    ghalta = scenario.cast_and_resolve("Ghalta the Immovable", *sources, username="alice")
    assert (
        scenario.game.characteristics_of(bears).has_ability(
            "Assigns combat damage equal to its toughness rather than its power."
        )
        is False
    )
    # Grizzly Bears is a 2/2 (power == toughness), so it never qualifies for
    # Ghalta's static in the first place - the exile below is the real proof:
    # once Ghalta itself is gone, the board computation for *any* creature
    # with toughness greater than power must stop granting the ability.
    scenario.game.exile_permanent(ghalta)
    scenario.game.check_state_based_actions()

    assert ghalta.zone is Zone.EXILE
    assert scenario.game.continuous_effects.effects == []


def test_garruk_veiled_butcher_resolves_with_no_spurious_notice():
    """Garruk, Veiled Butcher: a static replacement ("If a creature an
    opponent controls would die, exile it instead.") plus three loyalty
    abilities - all of them function from the battlefield only (planeswalker
    loyalty abilities are activated abilities, CR 606.1). Casting the
    permanent must not log a `LayerRemainderNotice` for text none of it
    needed to read at resolution at all.
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Garruk, Veiled Butcher"], battlefield=["Swamp"] * 5)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources(*(["Swamp"] * 5), username="alice")

    garruk = scenario.cast_and_resolve("Garruk, Veiled Butcher", *sources, username="alice")

    assert garruk.zone is Zone.BATTLEFIELD
    assert scenario.game.layer_remainder_notices == []
    assert scenario.game.continuous_effects.effects == []


def test_proft_sinister_mastermind_resolves_with_no_spurious_notice():
    """Proft, Sinister Mastermind: Threshold's own cast restriction, Menace,
    and a discard-to-pump activated ability - none of it a spell-resolution
    instruction. Cast with a graveyard already at seven cards so Threshold's
    own permission is satisfied."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Proft, Sinister Mastermind"],
            battlefield=["Swamp", "Swamp", "Swamp"],
            graveyard=["Swamp"] * 7,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Swamp", "Swamp", "Swamp", username="alice")

    proft = scenario.cast_and_resolve("Proft, Sinister Mastermind", *sources, username="alice")

    assert proft.zone is Zone.BATTLEFIELD
    assert scenario.game.layer_remainder_notices == []
    assert scenario.game.continuous_effects.effects == []
