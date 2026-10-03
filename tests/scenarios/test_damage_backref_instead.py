"""'`<base instruction>`. [If `<condition>`, ]`<alternative>` instead[ if
`<condition>`].' on an ability, where the alternative names its object by
back-reference to the base instead of announcing one of its own.

- Akoum Hellkite: "this creature deals 1 damage to any target. If that land
  is a Mountain, this creature deals 2 damage instead." - the condition's
  "that land" is the landfall trigger's own event object (CR 603.2), and the
  alternative elides the target the base already announced.
- Scepter of Empires: "This artifact deals 1 damage to target player or
  planeswalker. It deals 3 damage instead if you control artifacts named
  Crown of Empires and Throne of Empires." - "it" is the source, and the
  names are printed text (CR 201.2), read generally as "<type>s named <A>
  and <B>".
- Crown of Empires and Throne of Empires print the same condition over a
  control change ("that creature") and a token count ("those tokens"),
  which proves the condition reader is not Scepter's sentence.

CR 614.1a: "instead" replaces the base instruction whole; exactly one of the
two happens.

Rules looked up with `mise run rules:find` in the session that wrote this:

- CR 614.1a - effects that use "instead" are replacement effects.
- CR 603.2 / 603.10 - a triggered ability's event and the objects it names.
- CR 608.2b - all targets illegal: the ability doesn't resolve.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

HELLKITE = "Akoum Hellkite"
SCEPTER = "Scepter of Empires"
CROWN = "Crown of Empires"
THRONE = "Throne of Empires"


def _landfall(land: str) -> tuple[Scenario, object]:
    scenario = (
        Scenario()
        .player("alice", hand=[land], battlefield=[HELLKITE])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.choose_trigger_targets(HELLKITE, [bears])
    scenario.play_land(land)
    scenario.pass_until_resolved()
    return scenario, bears


def test_a_mountain_landfall_deals_two_instead():
    _scenario, bears = _landfall("Mountain")

    assert bears.zone is Zone.GRAVEYARD, "2 damage to the 2/2"


def test_a_swamp_landfall_deals_the_base_one():
    _scenario, bears = _landfall("Swamp")

    assert bears.zone is Zone.BATTLEFIELD
    assert bears.damage == 1


def test_the_landfall_damage_can_go_to_a_player():
    scenario = (
        Scenario().player("alice", hand=["Mountain"], battlefield=[HELLKITE]).player("bob").build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.choose_trigger_targets(HELLKITE, ["bob"])
    scenario.play_land("Mountain")
    scenario.pass_until_resolved()

    assert scenario.player("bob").life == 18


def _scepter_board(*artifacts: str) -> Scenario:
    scenario = Scenario().player("alice", battlefield=[SCEPTER, *artifacts]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_scepter_alone_deals_one():
    scenario = _scepter_board()
    scepter = scenario.find(SCEPTER, Zone.BATTLEFIELD)

    scenario.activate(scepter, targets=["bob"])
    scenario.pass_until_resolved()

    assert scenario.player("bob").life == 19


def test_scepter_with_crown_and_throne_deals_three():
    scenario = _scepter_board(CROWN, THRONE)
    scepter = scenario.find(SCEPTER, Zone.BATTLEFIELD)

    scenario.activate(scepter, targets=["bob"])
    scenario.pass_until_resolved()

    assert scenario.player("bob").life == 17


def test_scepter_needs_both_named_artifacts():
    scenario = _scepter_board(CROWN)
    scepter = scenario.find(SCEPTER, Zone.BATTLEFIELD)

    scenario.activate(scepter, targets=["bob"])
    scenario.pass_until_resolved()

    assert scenario.player("bob").life == 19


def test_crown_taps_or_with_the_set_steals():
    scenario = (
        Scenario()
        .player("alice", battlefield=[CROWN, SCEPTER, THRONE, "Plains", "Plains", "Plains"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    crown = scenario.find(CROWN, Zone.BATTLEFIELD)
    bears = scenario.creature("Grizzly Bears", "bob")

    scenario.activate(
        crown, *scenario.untapped_sources("Plains", "Plains", "Plains"), targets=[bears]
    )
    scenario.pass_until_resolved()

    assert scenario.game.controller_of(bears).username == "alice"
    assert not bears.tapped, "instead: the tap is replaced, not added to"


def test_crown_without_the_set_only_taps():
    scenario = (
        Scenario()
        .player("alice", battlefield=[CROWN, "Plains", "Plains", "Plains"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    crown = scenario.find(CROWN, Zone.BATTLEFIELD)
    bears = scenario.creature("Grizzly Bears", "bob")

    scenario.activate(
        crown, *scenario.untapped_sources("Plains", "Plains", "Plains"), targets=[bears]
    )
    scenario.pass_until_resolved()

    assert scenario.game.controller_of(bears).username == "bob"
    assert bears.tapped


def _soldiers(scenario: Scenario) -> int:
    return sum(
        1
        for state in scenario.game.permanents_controlled_by("alice")
        if state.name == "Soldier Token"
    )


def test_throne_makes_one_soldier_or_five_with_the_set():
    alone = Scenario().player("alice", battlefield=[THRONE, "Plains"]).player("bob").build()
    alone.start_at(Step.PRECOMBAT_MAIN)
    alone.activate(alone.find(THRONE, Zone.BATTLEFIELD), *alone.untapped_sources("Plains"))
    alone.pass_until_resolved()
    assert _soldiers(alone) == 1

    full = (
        Scenario()
        .player("alice", battlefield=[THRONE, CROWN, SCEPTER, "Plains"])
        .player("bob")
        .build()
    )
    full.start_at(Step.PRECOMBAT_MAIN)
    full.activate(full.find(THRONE, Zone.BATTLEFIELD), *full.untapped_sources("Plains"))
    full.pass_until_resolved()
    assert _soldiers(full) == 5
