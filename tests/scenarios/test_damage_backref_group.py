"""'`<Source>` deals N damage to target creature and each other creature
`<that shares a color with it|with the same name as that creature>`.'
(Wojek Embermage's Radiance ability, Izzet Staticaster).

One target; the rest of the group is a CR 400.7 back-reference to it, fixed
as the ability resolves from the target's characteristics then (the CR
example under Radiance, Wojek Apothecary, says the same of its own
shields: "each other creature on the battlefield that shares a color with
it at that time"). An illegal target means the ability does not resolve at
all (CR 608.2b), so nothing in the group is dealt damage either.

Rules looked up with `mise run rules:find` in the session that wrote this:

- CR 105.2c - "A colorless object has no color." So a colorless target
  shares a color with nothing, and only it is dealt damage.
- CR 608.2b - all targets illegal: the ability doesn't resolve.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

EMBERMAGE = "Wojek Embermage"
STATICASTER = "Izzet Staticaster"


def test_radiance_hits_the_target_and_each_other_creature_sharing_a_color():
    """Bloodbraid Elf is red and green: the green Bears and the red Goblin
    Guide both share a colour with it; the colourless Ornithopter does not.
    Embermage (red) shares one with it too, and is "each other creature"."""
    scenario = (
        Scenario()
        .player("alice", battlefield=[EMBERMAGE, "Ornithopter"])
        .player("bob", battlefield=["Bloodbraid Elf", "Grizzly Bears", "Goblin Guide", "Memnite"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    embermage = scenario.creature(EMBERMAGE, "alice")
    elf = scenario.creature("Bloodbraid Elf", "bob")

    scenario.activate(embermage, targets=[elf])
    scenario.pass_until_resolved()

    assert elf.damage == 1
    assert scenario.creature("Grizzly Bears", "bob").damage == 1
    assert scenario.creature("Goblin Guide", "bob").damage == 1
    assert embermage.damage == 1, "the source is red, so it shares a colour too"
    assert scenario.creature("Ornithopter", "alice").damage == 0
    assert scenario.creature("Memnite", "bob").damage == 0


def test_a_colorless_target_shares_a_color_with_nothing():
    scenario = (
        Scenario()
        .player("alice", battlefield=[EMBERMAGE, "Ornithopter"])
        .player("bob", battlefield=["Memnite", "Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    embermage = scenario.creature(EMBERMAGE, "alice")
    memnite = scenario.creature("Memnite", "bob")

    scenario.activate(embermage, targets=[memnite])
    scenario.pass_until_resolved()

    assert memnite.zone is Zone.GRAVEYARD, "1 damage to the 1/1 target"
    assert scenario.creature("Ornithopter", "alice").damage == 0, "CR 105.2c"
    assert scenario.creature("Grizzly Bears", "bob").damage == 0
    assert embermage.damage == 0


def test_staticaster_hits_every_creature_with_the_targets_name():
    scenario = (
        Scenario()
        .player("alice", battlefield=[STATICASTER, "Grizzly Bears"])
        .player("bob", battlefield=["Grizzly Bears", "Grizzly Bears", "Goblin Guide"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    staticaster = scenario.creature(STATICASTER, "alice")
    bob_bears = [
        state
        for state in scenario.game.permanents_controlled_by("bob")
        if state.name == "Grizzly Bears"
    ]

    scenario.activate(staticaster, targets=[bob_bears[0]])
    scenario.pass_until_resolved()

    bears = [state for state in scenario.game.battlefield if state.name == "Grizzly Bears"]
    assert len(bears) == 3
    assert all(state.damage == 1 for state in bears), "each creature with that name, both sides"
    assert scenario.creature("Goblin Guide", "bob").damage == 0
    assert staticaster.damage == 0


def test_an_illegal_target_spares_the_whole_group():
    scenario = (
        Scenario()
        .player("alice", hand=["Lightning Bolt"], battlefield=[STATICASTER, "Mountain"])
        .player("bob", battlefield=["Grizzly Bears", "Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    staticaster = scenario.creature(STATICASTER, "alice")
    first, second = [
        state for state in scenario.game.battlefield if state.name == "Grizzly Bears"
    ]
    (mountain,) = scenario.untapped_sources("Mountain")

    scenario.activate(staticaster, targets=[first])
    scenario.cast_and_resolve("Lightning Bolt", mountain, targets=[first])
    scenario.pass_until_resolved()

    assert first.zone is Zone.GRAVEYARD
    assert second.damage == 0, "CR 608.2b: the ability did not resolve"
