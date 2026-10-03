"""'`<Source>` deals damage equal to its power to target creature. That
creature deals damage equal to its power to this creature.' (Karplusan
Yeti, Vein Drinker).

Not fight. CR 701.14a's fight has each creature deal damage equal to its
power to the other, and CR 701.14b stops *both* when either is no longer on
the battlefield. This is two instructions in order: the source deals its
damage (its last known power if it has left, CR 608.2h), then the target
deals its own power back to "this creature" - which, once the source has
left, is nothing to damage. The target is the only target, so if it is
illegal the ability doesn't resolve at all (CR 608.2b).

Rules looked up with `mise run rules:find` in the session that wrote this:

- CR 701.14a / 701.14b - fight, for the contrast above.
- CR 120.8 - "If a source would deal 0 damage, it does not deal damage at
  all."
- CR 608.2b - all targets illegal: the ability doesn't resolve.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

YETI = "Karplusan Yeti"
DRINKER = "Vein Drinker"


def test_each_deals_its_power_to_the_other():
    """3 to the 3/2 Bloodbraid Elf, then the Elf's 3 back to the 3/3 Yeti."""
    scenario = (
        Scenario()
        .player("alice", battlefield=[YETI])
        .player("bob", battlefield=["Bloodbraid Elf"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    yeti = scenario.creature(YETI, "alice")
    elf = scenario.creature("Bloodbraid Elf", "bob")

    scenario.activate(yeti, targets=[elf])
    scenario.pass_until_resolved()

    assert elf.zone is Zone.GRAVEYARD
    assert yeti.zone is Zone.GRAVEYARD


def test_a_zero_power_target_deals_no_damage_back():
    scenario = (
        Scenario()
        .player("alice", battlefield=[YETI])
        .player("bob", battlefield=["Ornithopter"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    yeti = scenario.creature(YETI, "alice")
    thopter = scenario.creature("Ornithopter", "bob")

    scenario.activate(yeti, targets=[thopter])
    scenario.pass_until_resolved()

    assert thopter.zone is Zone.GRAVEYARD
    assert yeti.damage == 0, "CR 120.8: 0 damage is not dealt"


def test_the_target_damages_the_source_back():
    scenario = (
        Scenario()
        .player("alice", battlefield=[YETI])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    yeti = scenario.creature(YETI, "alice")
    bears = scenario.creature("Grizzly Bears", "bob")

    scenario.activate(yeti, targets=[bears])
    scenario.pass_until_resolved()

    assert bears.zone is Zone.GRAVEYARD
    assert yeti.damage == 2


def test_a_source_gone_before_resolution_still_deals_its_last_known_power():
    """Unlike fight (CR 701.14b), the first instruction still happens with
    the source's last known power, and the second has no "this creature" to
    damage."""
    scenario = (
        Scenario()
        .player("alice", hand=["Lightning Bolt"], battlefield=[YETI, "Mountain"])
        .player("bob", battlefield=["Bloodbraid Elf"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    yeti = scenario.creature(YETI, "alice")
    elf = scenario.creature("Bloodbraid Elf", "bob")
    (mountain,) = scenario.untapped_sources("Mountain")

    scenario.activate(yeti, targets=[elf])
    scenario.cast_and_resolve("Lightning Bolt", mountain, targets=[yeti])
    assert yeti.zone is Zone.GRAVEYARD
    scenario.pass_until_resolved()

    assert elf.zone is Zone.GRAVEYARD, "3 damage: the Yeti's last known power"


def test_an_illegal_target_means_neither_deals_damage():
    scenario = (
        Scenario()
        .player("alice", hand=["Lightning Bolt"], battlefield=[YETI, "Mountain"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    yeti = scenario.creature(YETI, "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    (mountain,) = scenario.untapped_sources("Mountain")

    scenario.activate(yeti, targets=[bears])
    scenario.cast_and_resolve("Lightning Bolt", mountain, targets=[bears])
    scenario.pass_until_resolved()

    assert yeti.damage == 0


def test_vein_drinker_bites_and_grows_when_its_victim_dies():
    """The same shape behind a different cost ({R}, {T}), and the damage is
    dealt by Vein Drinker itself, so its own "a creature dealt damage by this
    creature this turn dies" trigger sees the kill."""
    scenario = (
        Scenario()
        .player("alice", battlefield=[DRINKER, "Mountain"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    drinker = scenario.creature(DRINKER, "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    (mountain,) = scenario.untapped_sources("Mountain")

    scenario.activate(drinker, mountain, targets=[bears])
    scenario.pass_until_resolved()
    scenario.pass_until_resolved()  # the death trigger

    assert bears.zone is Zone.GRAVEYARD
    assert drinker.damage == 2
    assert scenario.game.power_of(drinker) == 5, "one +1/+1 counter"
