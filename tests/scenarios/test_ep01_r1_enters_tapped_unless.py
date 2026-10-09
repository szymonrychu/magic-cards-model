"""EP-01 round 1, task T2: "enters tapped" statics (CR 614.12, CR 614.1d).

Families proven here, each with real printings and a negative per condition:

- "This land enters tapped unless you control a <quality>" - a legendary
  creature, a legendary green creature, a Mount or Vehicle (the condition is
  read as the land enters, CR 614.12, and the sentence's polarity is "unless":
  condition true = untapped).
- "As this land enters, you may reveal a <type> card from your hand. This land
  enters tapped unless you revealed a <type> card this way or you control a
  <type>." (CR 614.12a - the choice is made before it enters).
- Group statics "<objects> enter tapped" (CR 614.1d - "[Objects] enter [the
  battlefield] ..." is a replacement effect), including comma lists and
  "non-<subtype>" qualifiers.
- "This creature enters tapped and doesn't untap during your untap step."
- "This artifact enters tapped and with three charge counters on it."

Every CR number was looked up with `mise run rules:find` for this task:
CR 614.12, CR 614.12a, CR 614.1d, CR 502.3.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _board(*, hand=(), battlefield=(), opp_battlefield=(), opp_hand=()):
    scenario = (
        Scenario()
        .player("alice", hand=list(hand), battlefield=list(battlefield))
        .player("bob", hand=list(opp_hand), battlefield=list(opp_battlefield))
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


# --------------------------------------------------------------------------
# "unless you control a legendary [green] creature"
# --------------------------------------------------------------------------


def test_minas_tirith_untapped_with_a_legendary_creature():
    scenario = _board(hand=["Minas Tirith"], battlefield=["Rick Jones, Destined Sidekick"])
    assert not scenario.play_land("Minas Tirith").tapped


def test_minas_tirith_tapped_with_only_a_nonlegendary_creature():
    scenario = _board(hand=["Minas Tirith"], battlefield=["Grizzly Bears"])
    assert scenario.play_land("Minas Tirith").tapped


def test_minas_tirith_tapped_with_a_legendary_noncreature():
    """The quality is "legendary creature", not "legendary permanent"."""
    scenario = _board(hand=["Minas Tirith"], battlefield=["Esika's Chariot"])
    assert scenario.play_land("Minas Tirith").tapped


def test_minas_tirith_ignores_an_opponents_legendary_creature():
    scenario = _board(hand=["Minas Tirith"], opp_battlefield=["Rick Jones, Destined Sidekick"])
    assert scenario.play_land("Minas Tirith").tapped


def test_argoth_untapped_with_a_legendary_green_creature():
    scenario = _board(
        hand=["Argoth, Sanctum of Nature"], battlefield=["Questing Beast"]
    )
    assert not scenario.play_land("Argoth, Sanctum of Nature").tapped


def test_argoth_tapped_with_a_legendary_creature_that_is_not_green():
    scenario = _board(
        hand=["Argoth, Sanctum of Nature"], battlefield=["Madame Masque"]
    )
    assert scenario.play_land("Argoth, Sanctum of Nature").tapped


def test_argoth_tapped_with_a_nonlegendary_green_creature():
    scenario = _board(hand=["Argoth, Sanctum of Nature"], battlefield=["Grizzly Bears"])
    assert scenario.play_land("Argoth, Sanctum of Nature").tapped


# --------------------------------------------------------------------------
# "unless you control a Mount or Vehicle"
# --------------------------------------------------------------------------


def test_country_roads_untapped_with_a_mount():
    scenario = _board(hand=["Country Roads"], battlefield=["Drover Grizzly"])
    assert not scenario.play_land("Country Roads").tapped


def test_country_roads_untapped_with_a_vehicle():
    scenario = _board(hand=["Country Roads"], battlefield=["Smuggler's Copter"])
    assert not scenario.play_land("Country Roads").tapped


def test_country_roads_tapped_with_neither():
    scenario = _board(hand=["Country Roads"], battlefield=["Grizzly Bears"])
    assert scenario.play_land("Country Roads").tapped


def test_country_roads_tapped_when_only_the_opponent_has_a_mount():
    scenario = _board(hand=["Country Roads"], opp_battlefield=["Drover Grizzly"])
    assert scenario.play_land("Country Roads").tapped


# --------------------------------------------------------------------------
# Reveal lands with an "or you control" rider (CR 614.12a)
# --------------------------------------------------------------------------


def test_temple_of_the_dragon_queen_revealing_a_dragon_enters_untapped():
    scenario = _board(hand=["Temple of the Dragon Queen", "Shivan Dragon"])
    scenario.will_choose("R", source="Temple of the Dragon Queen")
    temple = scenario.play_land("Temple of the Dragon Queen")
    assert not temple.tapped
    assert [(shown.card_name, shown.revealed_by) for shown in scenario.game.reveals] == [
        ("Shivan Dragon", "alice")
    ]


def test_temple_of_the_dragon_queen_declining_the_reveal_enters_tapped():
    scenario = _board(hand=["Temple of the Dragon Queen", "Shivan Dragon"])
    scenario.will_choose("R", source="Temple of the Dragon Queen")
    scenario.will_take_the_may(False)
    assert scenario.play_land("Temple of the Dragon Queen").tapped


def test_temple_of_the_dragon_queen_untapped_when_you_control_a_dragon():
    scenario = _board(hand=["Temple of the Dragon Queen"], battlefield=["Shivan Dragon"])
    scenario.will_choose("R", source="Temple of the Dragon Queen")
    assert not scenario.play_land("Temple of the Dragon Queen").tapped


def test_temple_of_the_dragon_queen_tapped_with_no_dragon_anywhere():
    scenario = _board(hand=["Temple of the Dragon Queen", "Island"], battlefield=["Grizzly Bears"])
    scenario.will_choose("R", source="Temple of the Dragon Queen")
    temple = scenario.play_land("Temple of the Dragon Queen")
    assert temple.tapped
    assert scenario.game.reveals == []


def test_temple_of_the_dragon_queen_ignores_an_opponents_dragon():
    scenario = _board(hand=["Temple of the Dragon Queen"], opp_battlefield=["Shivan Dragon"])
    scenario.will_choose("R", source="Temple of the Dragon Queen")
    assert scenario.play_land("Temple of the Dragon Queen").tapped


def test_fortified_beachhead_reveals_a_soldier_or_controls_one():
    revealed = _board(hand=["Fortified Beachhead", "Elite Vanguard"])
    assert not revealed.play_land("Fortified Beachhead").tapped
    controlled = _board(hand=["Fortified Beachhead"], battlefield=["Elite Vanguard"])
    assert not controlled.play_land("Fortified Beachhead").tapped
    neither = _board(hand=["Fortified Beachhead"], battlefield=["Grizzly Bears"])
    assert neither.play_land("Fortified Beachhead").tapped


# --------------------------------------------------------------------------
# Group "<objects> enter tapped" (CR 614.1d)
# --------------------------------------------------------------------------


def _enters(scenario, name, username="alice"):
    return scenario.put_onto_battlefield(name, username)


def test_orb_of_dreams_taps_every_permanent_entering_under_any_control():
    scenario = _board(
        battlefield=["Orb of Dreams"],
        hand=["Grizzly Bears", "Mountain"],
        opp_hand=["Smuggler's Copter"],
    )
    assert _enters(scenario, "Grizzly Bears").tapped
    assert _enters(scenario, "Mountain").tapped
    assert _enters(scenario, "Smuggler's Copter", "bob").tapped


def test_orb_of_dreams_does_not_tap_what_is_already_there():
    scenario = _board(battlefield=["Orb of Dreams", "Grizzly Bears"])
    assert not scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice").tapped


def test_root_maze_taps_artifacts_and_lands_but_not_creatures():
    scenario = _board(
        battlefield=["Root Maze"],
        hand=["Mountain", "Grizzly Bears", "Smuggler's Copter"],
        opp_hand=["Island"],
    )
    assert _enters(scenario, "Mountain").tapped
    assert _enters(scenario, "Smuggler's Copter").tapped
    assert _enters(scenario, "Island", "bob").tapped
    assert not _enters(scenario, "Grizzly Bears").tapped


def test_phyrexian_censor_taps_non_phyrexian_creatures_only():
    scenario = _board(
        battlefield=["Phyrexian Censor"],
        hand=["Grizzly Bears", "Vorinclex, Monstrous Raider", "Mountain"],
    )
    assert _enters(scenario, "Grizzly Bears").tapped
    assert not _enters(scenario, "Vorinclex, Monstrous Raider").tapped
    assert not _enters(scenario, "Mountain").tapped


def test_frozen_aether_taps_artifacts_creatures_and_lands_opponents_control():
    scenario = _board(
        battlefield=["Frozen Aether"],
        hand=["Smuggler's Copter", "Grizzly Bears", "Mountain", "Citadel Siege"],
        opp_hand=["Smuggler's Copter", "Grizzly Bears", "Mountain", "Citadel Siege"],
    )
    for name in ("Smuggler's Copter", "Grizzly Bears", "Mountain"):
        assert _enters(scenario, name, "bob").tapped, name
        assert not _enters(scenario, name, "alice").tapped, name
    assert not _enters(scenario, "Citadel Siege", "bob").tapped


def test_loxodon_gatekeeper_is_the_same_statement_on_a_creature():
    scenario = _board(
        battlefield=["Loxodon Gatekeeper"],
        opp_hand=["Smuggler's Copter", "Grizzly Bears", "Mountain", "Citadel Siege"],
        hand=["Grizzly Bears"],
    )
    for name in ("Smuggler's Copter", "Grizzly Bears", "Mountain"):
        assert _enters(scenario, name, "bob").tapped, name
    assert not _enters(scenario, "Citadel Siege", "bob").tapped
    assert not _enters(scenario, "Grizzly Bears", "alice").tapped


# --------------------------------------------------------------------------
# "enters tapped and doesn't untap during your untap step"; "... and with N counters"
# --------------------------------------------------------------------------


def test_grimgrin_enters_tapped_and_stays_tapped_through_the_untap_step():
    scenario = _board(hand=["Grimgrin, Corpse-Born", "Grizzly Bears"])
    grimgrin = _enters(scenario, "Grimgrin, Corpse-Born")
    bears = _enters(scenario, "Grizzly Bears")
    bears.tap()
    assert grimgrin.tapped
    scenario.game.untap_step()
    assert grimgrin.tapped
    assert not bears.tapped


def test_traxos_enters_tapped_and_does_not_untap():
    scenario = _board(hand=["Traxos, Scourge of Kroog"])
    traxos = _enters(scenario, "Traxos, Scourge of Kroog")
    assert traxos.tapped
    scenario.game.untap_step()
    assert traxos.tapped


def test_sphere_of_the_suns_enters_tapped_with_three_charge_counters():
    scenario = _board(hand=["Sphere of the Suns"])
    sphere = _enters(scenario, "Sphere of the Suns")
    assert sphere.tapped
    assert sphere.counters == {"charge": 3}
