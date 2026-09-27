""" "Can't have counters put on it" (CR 101.2's "can't" precedence, CR 122.6),
two shapes:

- **Self, plain**: Melira's Keepers, Tatterkite - "This creature can't have
  counters put on it."
- **Attached, combined**: Blossombind's Aura - "Enchanted creature can't
  become untapped and can't have counters put on it." Both restrictions are
  granted together (`machines/layers._attached_cant_have_counters_builder`),
  reusing the pre-existing `CANT_BECOME_UNTAPPED_TEXT` marker
  `CardState.untap` already reads and adding its own new
  `CANT_HAVE_COUNTERS_TEXT`, read by the one place every counter placement
  passes through, `Game.add_counters` (CR 122.6: "on it while it's on the
  battlefield and also ... as it enters"). Both markers join `machines/
  layers.RULE_EFFECT_TEXTS`, the same way `CANT_BECOME_UNTAPPED_TEXT` already
  had to, so a later "loses all abilities" effect does not end either one
  (Humility over a Frozen in Ice already proves the pattern for the untap
  half).

CR 704.5q's own +1/+1-vs--1/-1 annihilation state-based action never has
anything to do on a permanent this restriction actually reaches, since
neither kind ever lands there in the first place - proven below by trying to
put *both* kinds on the same restricted creature and checking neither one
takes, rather than by asserting the SBA does not fire (nothing here can
observe the negative of "did not run" more directly than "there is nothing
for it to find").

Melira's Keepers and Tatterkite (both Modern-legal, off pool) prove the
plain self-shape is not fitted to Blossombind's own combined-with-untap one.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def test_blossombind_taps_the_enchanted_creature_on_etb():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Island", "Island", "Grizzly Bears"], hand=["Blossombind"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    assert not bears.tapped

    scenario.cast_and_resolve("Blossombind", auto=True, username="alice", targets=[bears])
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert bears.tapped


def test_blossombind_stops_the_enchanted_creature_from_becoming_untapped():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Island", "Island", "Grizzly Bears"], hand=["Blossombind"])
        .player("bob")
        .manual_turn_based_actions()
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.cast_and_resolve("Blossombind", auto=True, username="alice", targets=[bears])
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()
    assert bears.tapped

    bears.untap()  # CR 701.26b's ordinary route to untapping.

    assert bears.tapped, "CR 502.1/613.1f: an effect says it can't become untapped"


def test_blossombind_stops_counters_from_landing_on_the_enchanted_creature():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Island", "Island", "Grizzly Bears"], hand=["Blossombind"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.cast_and_resolve("Blossombind", auto=True, username="alice", targets=[bears])
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()
    assert bears.cant_have_counters_put_on_it

    scenario.game.add_counters(bears, Counter.PLUS_ONE, 3)
    scenario.game.add_counters(bears, Counter.MINUS_ONE, 3)
    scenario.state_based_actions()

    assert bears.counter_count(Counter.PLUS_ONE) == 0
    assert bears.counter_count(Counter.MINUS_ONE) == 0
    assert bears.zone is Zone.BATTLEFIELD, "CR 704.5q had nothing to annihilate"


def test_blossombind_falling_off_lets_counters_land_again():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Island", "Island", "Grizzly Bears"], hand=["Blossombind"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    blossombind = scenario.cast_and_resolve(
        "Blossombind", auto=True, username="alice", targets=[bears]
    )
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    scenario.game.destroy(blossombind)
    assert not bears.cant_have_counters_put_on_it

    scenario.game.add_counters(bears, Counter.PLUS_ONE, 2)
    assert bears.counter_count(Counter.PLUS_ONE) == 2


def test_meliras_keepers_off_pool_proves_the_plain_self_shape():
    scenario = Scenario().player("alice", battlefield=["Melira's Keepers"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    keepers = scenario.creature("Melira's Keepers")
    assert keepers.cant_have_counters_put_on_it

    scenario.game.add_counters(keepers, Counter.MINUS_ONE, 2)

    assert keepers.counter_count(Counter.MINUS_ONE) == 0


def test_tatterkite_off_pool_proves_the_plain_self_shape_a_second_time():
    scenario = Scenario().player("alice", battlefield=["Tatterkite"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    tatterkite = scenario.creature("Tatterkite")
    assert tatterkite.cant_have_counters_put_on_it

    scenario.game.add_counters(tatterkite, Counter.PLUS_ONE, 5)

    assert tatterkite.counter_count(Counter.PLUS_ONE) == 0
