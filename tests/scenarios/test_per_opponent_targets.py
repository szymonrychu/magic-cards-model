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


def test_hapatra_frost_taps_one_creature_per_opponent_with_three_players() -> None:
    """The genuine CR 601.2c/603.3d reading, proven with **three** players,
    not the two the earlier single-opponent test cannot tell apart from a
    hardcoded single target: alice's own "for each opponent" trigger reaches
    both bob's and charlie's creature in the same resolution, each
    independently tapped and stunned, and nothing about the shared
    `TargetRequirement` lets either one be chosen twice for the other's own
    slot (`distinct_controllers`, CR 115.3's own "the same target can't be
    chosen multiple times").
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Hapatra, the Desert Frost"], battlefield=["Island"] * 4)
        .player("bob", battlefield=["Grizzly Bears"])
        .player("charlie", battlefield=["Serra Angel"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    angel = scenario.creature("Serra Angel", "charlie")
    scenario.choose_trigger_targets("Hapatra, the Desert Frost", [bears, angel])

    scenario.cast_and_resolve(
        "Hapatra, the Desert Frost",
        *scenario.untapped_sources("Island", "Island", "Island", "Island"),
    )
    scenario.resolve_top()  # the enters trigger

    assert bears.tapped
    assert bears.counters["stun"] == 1
    assert angel.tapped
    assert angel.counters["stun"] == 1


def test_hapatra_frost_may_tap_fewer_than_every_opponent() -> None:
    """ "Up to one" is independently optional per opponent (CR 115.6) - alice
    may choose only bob's creature and leave charlie's untouched.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Hapatra, the Desert Frost"], battlefield=["Island"] * 4)
        .player("bob", battlefield=["Grizzly Bears"])
        .player("charlie", battlefield=["Serra Angel"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    angel = scenario.creature("Serra Angel", "charlie")
    scenario.choose_trigger_targets("Hapatra, the Desert Frost", [bears])

    scenario.cast_and_resolve(
        "Hapatra, the Desert Frost",
        *scenario.untapped_sources("Island", "Island", "Island", "Island"),
    )
    scenario.resolve_top()  # the enters trigger

    assert bears.tapped
    assert not angel.tapped


# --------------------------------------------------------------------------
# "For each opponent, return up to one target `<X>` that player controls to
# its owner's hand." - `_FOR_EACH_OPPONENT_DESTROY_RE`'s own bounce twin
# (`_parse_for_each_opponent_return_to_hand_clause`). The Theorist, Jace
# Beleren's own `-2` targeting profile already read (an earlier wave); the
# resolved effect itself did not. Enigma Thief is the off-pool generality
# proof - an ETB trigger, not a loyalty ability, and "nonland permanent"
# rather than "artifact or creature".
# --------------------------------------------------------------------------


def test_the_theorist_returns_the_targeted_opponent_permanent_to_hand() -> None:
    scenario = (
        Scenario()
        .player("alice", battlefield=["The Theorist, Jace Beleren"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    theorist = scenario.creature("The Theorist, Jace Beleren", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")

    scenario.activate(theorist, index=1, targets=[bears])
    scenario.pass_until_resolved()

    assert bears.zone is Zone.HAND
    assert bears in scenario.player("bob").hand
    assert theorist.loyalty == 1


def test_enigma_thief_returns_a_nonland_permanent_per_opponent_off_pool() -> None:
    """Off-pool generality proof: Enigma Thief's own ETB trigger, "for each
    opponent, return up to one target nonland permanent that player controls
    to its owner's hand" - an artifact this time, not a creature, proving the
    parser's own `desc` is not fitted to "artifact or creature"."""
    islands = ["Island"] * 7
    scenario = (
        Scenario()
        .player("alice", hand=["Enigma Thief"], battlefield=islands)
        .player("bob", battlefield=["Mind Stone"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mind_stone = scenario.find("Mind Stone", Zone.BATTLEFIELD, "bob")
    scenario.choose_trigger_targets("Enigma Thief", [mind_stone])

    scenario.cast_and_resolve("Enigma Thief", *scenario.untapped_sources(*islands))
    scenario.resolve_top()  # the enters trigger

    assert mind_stone.zone is Zone.HAND
    assert mind_stone in scenario.player("bob").hand
