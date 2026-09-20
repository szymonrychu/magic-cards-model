"""FRA stream S8: "Exile the top card of your library. You may `<X>`. If
you don't, `<Y>`." where exactly one of `<X>`/`<Y>` grants CR 601.3
permission to cast/play the exiled card and the other is an ordinary
effect (CR 608.2d).

Every CR number below was looked up with `mise run rules:find` in the
session that wrote this file.

- **CR 701.13a** - exiling the top card.
- **CR 608.2d** - the "may" is a single choice; only one of the two branches
  ever runs.
- **CR 601.3** - the permission `Game.grant_play_permission` grants when the
  branch is taken.
- **CR 514.2** - "until end of turn" effects, `grant_play_permission`'s own
  default when no duration is printed at all.

Chandra, Torch of Defiance's own `+1` is the reported card: the permission
sits on the "you may" side (with no printed duration at all - this
engine's own `until_end_of_turn=True` default, not a claimed CR reading of
an implicit one), and a damage consequence sits on "if you don't". Synth
Eradicator (Marvel's Spider-Man, real, non-FRA, non-pool) is the off-set
proof: the identical shape *reversed* - an energy gain on the "you may"
side, the permission (this time with a printed "this turn") on "if you
don't" - proving the merge reads either ordering, not one hardcoded to
Chandra's own.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_chandra_casts_the_exiled_card_when_the_may_is_taken():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Chandra, Torch of Defiance"],
            library=["Grizzly Bears", "Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    chandra = scenario.creature("Chandra, Torch of Defiance", "alice")
    bob = scenario.player("bob")
    bob_life_before = bob.life

    scenario.will_take_the_may(True, source="Chandra, Torch of Defiance")
    scenario.activate(chandra, index=0)
    scenario.pass_until_resolved()

    bears = scenario.find("Grizzly Bears", Zone.EXILE, "alice")
    assert scenario.game.play_permission_for(bears, "alice") is not None
    assert bob.life == bob_life_before, "the may was taken, so no damage happened"


def test_chandra_deals_damage_when_the_may_is_declined():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Chandra, Torch of Defiance"],
            library=["Grizzly Bears", "Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    chandra = scenario.creature("Chandra, Torch of Defiance", "alice")
    bob = scenario.player("bob")
    bob_life_before = bob.life

    scenario.will_take_the_may(False, source="Chandra, Torch of Defiance")
    scenario.activate(chandra, index=0)
    scenario.pass_until_resolved()

    assert bob.life == bob_life_before - 2


def test_synth_eradicator_gets_energy_when_the_may_is_taken():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Synth Eradicator"],
            library=["Grizzly Bears", "Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    alice = scenario.player("alice")
    eradicator = scenario.creature("Synth Eradicator", "alice")

    scenario.will_take_the_may(True, source="Synth Eradicator")
    scenario.attack_with(eradicator)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert alice.counter_count("energy") == 2
    bears = scenario.find("Grizzly Bears", Zone.EXILE, "alice")
    assert scenario.game.play_permission_for(bears, "alice") is None, (
        "the may was taken (energy), so no permission was granted"
    )


def test_synth_eradicator_grants_the_permission_when_the_may_is_declined():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Synth Eradicator"],
            library=["Grizzly Bears", "Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    alice = scenario.player("alice")
    eradicator = scenario.creature("Synth Eradicator", "alice")

    scenario.will_take_the_may(False, source="Synth Eradicator")
    scenario.attack_with(eradicator)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert alice.counter_count("energy") == 0
    bears = scenario.find("Grizzly Bears", Zone.EXILE, "alice")
    assert scenario.game.play_permission_for(bears, "alice") is not None
