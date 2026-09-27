""" "You may have this creature assign its combat damage as though it
weren't blocked." - printed directly (Rhox), and granted distributively by
Zilortha, Apex of Ikoria's own back-face static: "For each non-Human
creature you control, you may have that creature assign its combat damage
as though it weren't blocked."

Verified this session with `mise run rules:find` against the current CR:

- **CR 510.1b** - "An unblocked creature assigns its combat damage to the
  player, planeswalker, or battle it's attacking."
- **CR 510.1c** - "A blocked creature assigns its combat damage to the
  creatures blocking it. ... If exactly one creature is blocking it, it
  assigns all its combat damage to that creature."
- **CR 510.1d** - "A blocking creature assigns combat damage to the
  creatures it's blocking" - unaffected by the attacker's own choice below,
  which is why the blocker still deals its own damage to the attacker.
- **CR 608.2d** - a resolving/active "you may" is a choice its controller
  makes, never forced.
- **CR 310.12b** / **CR 712.11a** - a Siege's own intrinsic defeat trigger
  exiles it, then its controller may cast it transformed.

Nothing in the Comprehensive Rules names this permission a keyword; it is
plain English overriding CR 510.1c with CR 510.1b for one creature the game
otherwise considers blocked. Rhox's own printed ruling: "You can't split the
damage assignment between them" - all-or-nothing, never divided the ordinary
CR 510.1c way.

Rhox (a bare, printed "You may have this creature assign its combat damage
as though it weren't blocked.", Modern-legal) is the generality proof: the
detector in `machines/combat.may_assign_as_though_unblocked` reads a
creature's own computed ability lines the same way whether the sentence was
printed directly or granted by a wholly different card's static ability, and
this wave's own author had not looked at Rhox while building the grant for
Zilortha.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import PlayedScenario, Scenario

IKORIA = "Invasion of Ikoria"
ZILORTHA = "Zilortha, Apex of Ikoria"


def _transform_ikoria_with_bolts(scenario: PlayedScenario, siege, mountains: list) -> None:
    """Defeats a staged Invasion of Ikoria (defense 6) with two Lightning
    Bolts (CR 115.4/310.6) and casts it transformed (CR 310.12b)."""
    scenario.cast_and_resolve("Lightning Bolt", mountains[0], username="alice", targets=[siege])
    scenario.cast_and_resolve("Lightning Bolt", mountains[1], username="alice", targets=[siege])
    scenario.game.check_state_based_actions()
    assert siege.counter_count("defense") == 0
    scenario.will_take_the_may(True, username="alice")
    scenario.pass_until_resolved()  # CR 310.12b's defeat trigger: exile, then cast
    scenario.pass_until_resolved()  # the transformed spell resolves and enters


def test_zilortha_may_assign_as_though_unblocked_and_send_damage_to_the_player():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[IKORIA, "Lightning Bolt", "Lightning Bolt"],
            battlefield=["Mountain", "Mountain"],
        )
        .player("bob", battlefield=["Grizzly Bears"], life=20)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    siege = scenario.put_onto_battlefield(IKORIA, "alice")
    scenario.pass_until_resolved()  # the Siege's own enters trigger (no legal candidate)
    mountains = scenario.untapped_sources("Mountain", "Mountain", username="alice")
    _transform_ikoria_with_bolts(scenario, siege, mountains)
    assert siege.transformed and siege.name == ZILORTHA
    siege.summoning_sick = False  # cast this same turn; not the reported clause

    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(siege)
    scenario.start_at(Step.DECLARE_BLOCKERS)
    scenario.block(siege, bears)

    scenario.will_take_the_may(True, username="alice", source=ZILORTHA)
    scenario.combat_damage()

    assert scenario.player("bob").life == 12, "all 8 power went to the defending player"
    assert bears.zone is Zone.BATTLEFIELD, "the blocker took none of the attacker's damage"
    assert siege.damage == 2, "CR 510.1d: the blocker still deals its own damage to the attacker"


def test_zilortha_declining_the_permission_assigns_to_the_blocker_as_usual():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[IKORIA, "Lightning Bolt", "Lightning Bolt"],
            battlefield=["Mountain", "Mountain"],
        )
        .player("bob", battlefield=["Grizzly Bears"], life=20)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    siege = scenario.put_onto_battlefield(IKORIA, "alice")
    scenario.pass_until_resolved()
    mountains = scenario.untapped_sources("Mountain", "Mountain", username="alice")
    _transform_ikoria_with_bolts(scenario, siege, mountains)
    siege.summoning_sick = False  # cast this same turn; not the reported clause

    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(siege)
    scenario.start_at(Step.DECLARE_BLOCKERS)
    scenario.block(siege, bears)

    scenario.will_take_the_may(False, username="alice", source=ZILORTHA)
    scenario.combat_damage()

    assert scenario.player("bob").life == 20, "declined - CR 510.1c governs instead"
    assert bears.zone is Zone.GRAVEYARD, "all 8 power went to the sole blocker"


def test_rhox_may_also_assign_as_though_unblocked():
    """Rhox's own bare printed ability - a different card the grant above was
    never written against, proving the detector reads a printed line exactly
    as it reads a granted one."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Rhox", "Forest", "Forest", "Forest", "Forest", "Forest"])
        .player("bob", battlefield=["Grizzly Bears"], life=20)
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    rhox = scenario.creature("Rhox", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.attack_with(rhox)
    scenario.start_at(Step.DECLARE_BLOCKERS)
    scenario.block(rhox, bears)

    scenario.will_take_the_may(True, username="alice", source="Rhox")
    scenario.combat_damage()

    assert scenario.player("bob").life == 15, "all 5 power went to the defending player"
    assert bears.zone is Zone.BATTLEFIELD
