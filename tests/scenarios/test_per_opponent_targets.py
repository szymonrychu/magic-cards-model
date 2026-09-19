"""The per-opponent target family: "for each opponent, `<verb>` up to one
target `<X>` that player controls" - tap-then-stun, and counters equal to a
dynamic amount - plus landfall's own per-event damage/mana rider, and a
reflexive "you may pay `<cost>`. When you do, `<per-opponent consequence>`."

Verified this session with `knowledge_search(q="...", type="rules")` and
cross-checked with `mise run rules:find` (on-disk CR effective 2026-09-25):

- **CR 115.6** - "up to one target" legally chooses zero.
- **CR 122.1d** - a stun counter: if a permanent with one would become
  untapped, remove one instead and it stays tapped.
- **CR 122.5** - counters generally.
- **CR 508.4** is unrelated here; this file's own anchor is CR 603.12's
  reflexive trigger ("when you do") for Lich's Relic.
- **CR 118.12** - the optional-cost-then-consequence shape.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Color, Zone
from tests.scenarios.harness import Scenario


def test_hapatra_frost_taps_and_stuns_one_creature_per_opponent() -> None:
    """ "When Hapatra, the Desert Frost enters, for each opponent, tap up to
    one target creature that player controls. Put a stun counter on each of
    those creatures."
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Hapatra, the Desert Frost"], battlefield=["Island"] * 4)
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.choose_trigger_targets("Hapatra, the Desert Frost", [bears])

    scenario.cast_and_resolve(
        "Hapatra, the Desert Frost",
        *scenario.untapped_sources("Island", "Island", "Island", "Island"),
    )
    scenario.resolve_top()  # the enters trigger

    assert bears.tapped
    assert bears.counters["stun"] == 1


def test_hapatra_fang_puts_counters_equal_to_greatest_graveyard_mana_value() -> None:
    """ "When Hapatra, the Desert Fang enters, for each opponent, put X
    -1/-1 counters on up to one target creature that player controls, where
    X is the greatest mana value among cards in your graveyard."
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Hapatra, the Desert Fang"],
            battlefield=["Swamp", "Swamp", "Swamp", "Swamp", "Forest"],
            graveyard=["Grizzly Bears", "Serra Angel"],
        )
        .player("bob", battlefield=["Elder Gargaroth"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    gargaroth = scenario.creature("Elder Gargaroth", "bob")
    scenario.choose_trigger_targets("Hapatra, the Desert Fang", [gargaroth])

    scenario.cast_and_resolve(
        "Hapatra, the Desert Fang",
        *scenario.untapped_sources("Swamp", "Swamp", "Swamp", "Swamp", "Forest"),
    )
    scenario.resolve_top()  # the enters trigger

    assert gargaroth.counters["-1/-1"] == 5, (
        "Serra Angel's mana value 5 is the greatest in the yard"
    )


def test_koth_landfall_damages_each_opponent_and_adds_red_for_a_mountain() -> None:
    """ "Landfall - Whenever a land you control enters, Koth deals 1 damage
    to each opponent. If that land is a Mountain, add {R}."
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Mountain"], battlefield=["Koth, the Geomancer"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bob_life_before = scenario.game.player("bob").life

    scenario.play_land("Mountain", "alice")
    scenario.resolve_top()  # the landfall trigger

    assert scenario.game.player("bob").life == bob_life_before - 1
    assert scenario.game.player("alice").mana_pool.floating.get(Color.RED, 0) == 1


def test_lichs_relic_reflexively_destroys_one_permanent_per_opponent_when_paid() -> None:
    """ "When this Equipment enters, you may pay `{2}`. When you do, for each
    opponent, destroy up to one target creature or planeswalker that player
    controls."
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Lich's Relic"], battlefield=["Swamp", "Swamp", "Swamp"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.will_pay_the_mana_cost(True, source="Lich's Relic")
    scenario.will_choose_targets(bears, source="Lich's Relic")

    scenario.cast_and_resolve("Lich's Relic", *scenario.untapped_sources("Swamp"))
    scenario.resolve_top()  # the enters trigger, asking to pay {2} and
    # queuing the reflexive "when you do" trigger with its target chosen above
    scenario.resolve_top()  # the reflexive "when you do" trigger

    assert bears.zone is Zone.GRAVEYARD


def test_lichs_relic_does_nothing_when_the_payment_is_declined() -> None:
    scenario = (
        Scenario()
        .player("alice", hand=["Lich's Relic"], battlefield=["Swamp", "Swamp", "Swamp"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.will_pay_the_mana_cost(False, source="Lich's Relic")

    scenario.cast_and_resolve("Lich's Relic", *scenario.untapped_sources("Swamp"))
    scenario.resolve_top()  # the enters trigger, declining to pay {2}
    scenario.game._before_priority()

    assert bears.zone is Zone.BATTLEFIELD
    assert not scenario.game.stack
