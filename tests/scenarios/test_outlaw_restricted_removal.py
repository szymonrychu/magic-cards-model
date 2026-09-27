"""Shoot the Sheriff: "Destroy target non-outlaw creature." - CR 700.12a's
outlaw quality, negated, read by `machines/targeting.py`'s `_Adjectives`/
`TargetRequirement` (`requires_outlaw`/`excludes_outlaw`) rather than by any
reader of this task's own: the generic "destroy target `<phrase>`." dispatch
(`machines/effects.py`'s `destroy_ability_targets`) already handles the verb
once the target phrase itself is understood.

Every CR number below was looked up with `mise run rules:find` in the
session that wrote this file:

- **CR 700.12a** - "Some cards refer to outlaws that a player controls. Only
  outlaw permanents are considered for these effects unless otherwise
  specified" - and CR 700.12 itself: "The term outlaw refers to an object
  that has the Assassin, Mercenary, Pirate, Rogue, and/or Warlock creature
  types."
- **CR 601.2c** - a spell's targets must be "an appropriate object ... for
  each target the spell requires", checked again at CR 608.2b.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_shoot_the_sheriff_destroys_a_non_outlaw_creature():
    """Grizzly Bears carries none of CR 700.12's five outlaw creature types,
    so it is a legal target."""
    scenario = (
        Scenario()
        .player("alice", hand=["Shoot the Sheriff"], battlefield=["Swamp", "Swamp"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")

    scenario.cast_and_resolve(
        "Shoot the Sheriff", *scenario.untapped_sources("Swamp", "Swamp"), targets=[bears]
    )

    assert bears.zone is Zone.GRAVEYARD


def test_shoot_the_sheriff_refuses_a_rogue():
    """Agent of Kotis (a Human Rogue - CR 700.12's own named type) is an
    outlaw and so an illegal target for "target non-outlaw creature"."""
    scenario = (
        Scenario()
        .player("alice", hand=["Shoot the Sheriff"], battlefield=["Swamp", "Swamp"])
        .player("bob", battlefield=["Agent of Kotis"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    rogue = scenario.creature("Agent of Kotis", "bob")

    casting = scenario.cast("Shoot the Sheriff")
    try:
        casting.choose_targets([rogue])
    except ValueError as error:
        assert "outlaw" in str(error).lower()
    else:
        raise AssertionError("a Rogue should not be a legal target")


def test_maelstrom_pulse_destroys_target_and_every_same_name_permanent():
    """Maelstrom Pulse's own "and all other permanents with the same name as
    that permanent" - CR 201.2a's grouping, proved separately in
    `test_same_name_destroy.py`; this file only owns the outlaw mechanic, so
    this test just confirms Shoot the Sheriff's own sibling spell still
    destroys a bare non-outlaw creature the ordinary way."""
    scenario = (
        Scenario()
        .player("alice", hand=["Maelstrom Pulse"], battlefield=["Swamp", "Forest", "Forest"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")

    scenario.cast_and_resolve(
        "Maelstrom Pulse",
        *scenario.untapped_sources("Swamp", "Forest", "Forest"),
        targets=[bears],
    )

    assert bears.zone is Zone.GRAVEYARD
