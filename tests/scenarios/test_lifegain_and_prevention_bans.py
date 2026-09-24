"""Scenario: "Players can't gain life this turn." / "Your opponents can't gain
life this turn." / "Damage can't be prevented [this turn]."

Rules-of-the-game effects (CR 611.1's third kind: they affect players or the
rules of the game, not any object's characteristics). A resolving spell's
version is recorded and lasts until the cleanup step (CR 611.2c, CR 514.2);
a permanent's static version lasts while the permanent is on the battlefield
(CR 604.2, CR 611.3a).

- CR 119.7: "If an effect says that a player can't gain life ..." - a life
  gain simply does not happen.
- CR 615.12: "If unpreventable damage would be dealt, any applicable
  prevention effects are still applied to it. Those effects won't prevent any
  damage, but any additional effects they have will take place. Existing
  damage prevention shields won't be reduced by damage that can't be
  prevented."

Cards: Skullcrack (both sentences), Roiling Vortex's "{R}: Your opponents
can't gain life this turn."; proof printings Atarka's Command's mode (the
opponents-only ban on a modal spell), Impractical Joke and Stomp (the
prevention ban alone), and Leyline of Punishment's static "Damage can't be
prevented." / "Players can't gain life.".

Every CR number here was looked up with `mise run rules:find` in the session
that wrote this file: 611.1, 611.2c, 514.2, 604.2, 611.3a, 119.7, 615.12,
702.16e.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _resolve_all(scenario) -> None:
    while scenario.stack_names() or scenario.pending_triggers:
        scenario.game.put_triggers_on_stack()
        scenario.pass_until_resolved()


def _skullcrack_board(**extra) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            library=["Forest", "Forest"],
            hand=["Skullcrack", *extra.get("alice_hand", [])],
            battlefield=["Mountain", "Mountain", *extra.get("alice_battlefield", [])],
        )
        .player(
            "bob",
            library=["Forest", "Forest"],
            hand=extra.get("bob_hand", []),
            battlefield=extra.get("bob_battlefield", []),
        )
    )


def _cast_skullcrack(scenario, target="bob") -> None:
    mountains = scenario.untapped_sources("Mountain", "Mountain", username="alice")
    scenario.cast_and_resolve("Skullcrack", *mountains, username="alice", targets=[target])


# -- Skullcrack: "Players can't gain life this turn." --------------------------


def test_skullcrack_deals_three_to_its_target():
    scenario = _skullcrack_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    _cast_skullcrack(scenario)

    assert scenario.player("bob").life == 17


def test_after_skullcrack_nobody_gains_life_this_turn():
    """ "Players" - its own caster included (CR 119.7)."""
    scenario = _skullcrack_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _cast_skullcrack(scenario)

    scenario.game.gain_life("bob", 4)
    scenario.game.gain_life("alice", 4)

    assert scenario.player("bob").life == 17
    assert scenario.player("alice").life == 20


def test_skullcrack_stops_a_lightning_helix_gain_after_it():
    scenario = _skullcrack_board(
        alice_hand=["Lightning Helix"], alice_battlefield=["Plains", "Mountain"]
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _cast_skullcrack(scenario)
    sources = scenario.untapped_sources("Mountain", "Plains", username="alice")

    scenario.cast_and_resolve("Lightning Helix", *sources, username="alice", targets=["bob"])

    assert scenario.player("bob").life == 14
    assert scenario.player("alice").life == 20


def test_the_life_gain_ban_ends_with_the_turn():
    """CR 514.2: "this turn" effects end in the cleanup step."""
    scenario = _skullcrack_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _cast_skullcrack(scenario)

    scenario.game.cleanup_step()
    scenario.game.gain_life("bob", 4)

    assert scenario.player("bob").life == 21


# -- Skullcrack: "Damage can't be prevented this turn." -----------------------


def test_skullcrack_makes_a_prevention_shield_prevent_nothing():
    """CR 615.12: the shield applies, prevents nothing, and is not reduced -
    so once the turn's ban is gone the shield would still be standing."""
    scenario = _skullcrack_board(
        bob_hand=["Bandage"], bob_battlefield=["Plains", "Grizzly Bears"]
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.pass_priority("alice")
    (plains,) = scenario.untapped_sources("Plains", username="bob")
    scenario.cast_and_resolve("Bandage", plains, username="bob", targets=[bears])
    (shield,) = scenario.game.active_prevention_shields()
    _cast_skullcrack(scenario, target="bob")

    assert scenario.game.deal_damage(bears, 1, source=bears) == 1
    assert shield.amount == 1
    assert shield.prevented == 0


def test_skullcrack_damage_itself_cannot_be_prevented():
    """The ban comes first in the text (CR 608.2c), so Skullcrack's own 3 is
    already unpreventable - a shield on Bob is not reduced by it."""
    scenario = _skullcrack_board(bob_hand=["Bandage"], bob_battlefield=["Plains"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.pass_priority("alice")
    (plains,) = scenario.untapped_sources("Plains", username="bob")
    scenario.cast_and_resolve("Bandage", plains, username="bob", targets=["bob"])

    _cast_skullcrack(scenario)

    assert scenario.player("bob").life == 17


def test_the_prevention_ban_ends_with_the_turn():
    scenario = _skullcrack_board(
        bob_hand=["Bandage"], bob_battlefield=["Plains", "Grizzly Bears"]
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    _cast_skullcrack(scenario)
    scenario.game.cleanup_step()
    scenario.pass_priority("alice")
    (plains,) = scenario.untapped_sources("Plains", username="bob")
    scenario.cast_and_resolve("Bandage", plains, username="bob", targets=[bears])

    assert scenario.game.deal_damage(bears, 2, source=bears) == 1


def test_damage_cant_be_prevented_beats_protection():
    """CR 702.16e's protection is a prevention effect like any other."""
    scenario = _skullcrack_board(
        alice_battlefield=["Sword of Fire and Ice", "Grizzly Bears"],
        bob_battlefield=["Goblin Guide"],
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sword = scenario.find("Sword of Fire and Ice", Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    guide = scenario.creature("Goblin Guide", "bob")
    sword.attach_to(bears)  # staging: protection from red
    assert scenario.game.deal_damage(bears, 1, source=guide) == 0

    _cast_skullcrack(scenario)

    assert scenario.game.deal_damage(bears, 1, source=guide) == 1


# -- Impractical Joke and Stomp (proof): the prevention ban alone -------------


def test_impractical_joke_bans_prevention_but_not_life_gain():
    scenario = (
        Scenario()
        .player("alice", library=["Forest"], hand=["Impractical Joke"], battlefield=["Mountain"])
        .player("bob", library=["Forest"], hand=["Bandage"], battlefield=["Plains", "Serra Angel"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.creature("Serra Angel", "bob")
    scenario.pass_priority("alice")
    (plains,) = scenario.untapped_sources("Plains", username="bob")
    scenario.cast_and_resolve("Bandage", plains, username="bob", targets=[angel])
    (mountain,) = scenario.untapped_sources("Mountain", username="alice")

    scenario.cast_and_resolve("Impractical Joke", mountain, username="alice", targets=[angel])

    assert angel.damage == 3
    scenario.game.gain_life("bob", 2)
    assert scenario.player("bob").life == 22


def test_impractical_joke_with_no_target_still_bans_prevention():
    """ "up to one target" - zero targets chosen, the ban still happens."""
    scenario = (
        Scenario()
        .player("alice", library=["Forest"], hand=["Impractical Joke"], battlefield=["Mountain"])
        .player("bob", library=["Forest"], hand=["Bandage"], battlefield=["Plains", "Serra Angel"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.creature("Serra Angel", "bob")
    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    scenario.cast_and_resolve("Impractical Joke", mountain, username="alice", targets=[])
    scenario.pass_priority("alice")
    (plains,) = scenario.untapped_sources("Plains", username="bob")
    scenario.cast_and_resolve("Bandage", plains, username="bob", targets=[angel])

    assert scenario.game.deal_damage(angel, 1, source=angel) == 1


def test_stomp_bans_prevention_for_the_turn():
    scenario = (
        Scenario()
        .player(
            "alice", library=["Forest"], hand=["Bonecrusher Giant"], battlefield=["Mountain"] * 2
        )
        .player("bob", library=["Forest"], hand=["Bandage"], battlefield=["Plains", "Serra Angel"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.creature("Serra Angel", "bob")
    scenario.pass_priority("alice")
    (plains,) = scenario.untapped_sources("Plains", username="bob")
    scenario.cast_and_resolve("Bandage", plains, username="bob", targets=[angel])
    casting = scenario.cast("Bonecrusher Giant", "alice")
    casting.cast_as_adventure()  # CR 715.3a
    casting.choose_targets(["bob"])
    scenario.pay_with(
        casting.begin_paying(), *scenario.untapped_sources("Mountain", "Mountain", username="alice")
    )
    scenario.put_on_stack(casting)
    _resolve_all(scenario)

    assert scenario.player("bob").life == 18
    assert scenario.game.deal_damage(angel, 1, source=angel) == 1


# -- Atarka's Command (proof): "Your opponents can't gain life this turn." ----


def _atarka(scenario, modes: list[int]) -> None:
    casting = scenario.cast("Atarka's Command", "alice")
    casting.choose_modes(modes)
    scenario.pay_with(
        casting.begin_paying(), *scenario.untapped_sources("Mountain", "Forest", username="alice")
    )
    scenario.put_on_stack(casting)
    _resolve_all(scenario)


def _atarka_board() -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            library=["Forest"],
            hand=["Atarka's Command"],
            battlefield=["Mountain", "Forest"],
        )
        .player("bob", library=["Forest"])
    )


def test_atarkas_command_stops_only_the_opponents_life_gain():
    scenario = _atarka_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    _atarka(scenario, [1, 2])

    assert scenario.player("bob").life == 17
    scenario.game.gain_life("bob", 5)
    scenario.game.gain_life("alice", 5)
    assert scenario.player("bob").life == 17
    assert scenario.player("alice").life == 25


# -- Roiling Vortex: "{R}: Your opponents can't gain life this turn." ----------


def test_roiling_vortex_activation_stops_opponents_gaining_life():
    scenario = (
        Scenario()
        .player("alice", library=["Forest"], battlefield=["Roiling Vortex", "Mountain"])
        .player("bob", library=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    vortex = scenario.find("Roiling Vortex", Zone.BATTLEFIELD, "alice")
    (mountain,) = scenario.untapped_sources("Mountain", username="alice")

    scenario.activate(vortex, mountain, username="alice")
    scenario.pass_until_resolved()

    scenario.game.gain_life("bob", 3)
    scenario.game.gain_life("alice", 3)
    assert scenario.player("bob").life == 20
    assert scenario.player("alice").life == 23


def test_roiling_vortex_ban_outlives_the_vortex():
    """CR 611.2c: the resolved ability's effect is recorded, not read off the
    permanent, so destroying the Vortex afterwards changes nothing."""
    scenario = (
        Scenario()
        .player("alice", library=["Forest"], battlefield=["Roiling Vortex", "Mountain"])
        .player("bob", library=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    vortex = scenario.find("Roiling Vortex", Zone.BATTLEFIELD, "alice")
    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    scenario.activate(vortex, mountain, username="alice")
    scenario.pass_until_resolved()
    scenario.game.destroy(vortex)

    scenario.game.gain_life("bob", 3)
    assert scenario.player("bob").life == 20


# -- Leyline of Punishment (proof): the static forms --------------------------


def test_leyline_makes_damage_unpreventable_while_it_is_on_the_battlefield():
    scenario = (
        Scenario()
        .player("alice", library=["Forest"], battlefield=["Leyline of Punishment"])
        .player("bob", library=["Forest"], hand=["Bandage"], battlefield=["Plains", "Serra Angel"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.creature("Serra Angel", "bob")
    leyline = scenario.find("Leyline of Punishment", Zone.BATTLEFIELD, "alice")
    scenario.pass_priority("alice")
    (plains,) = scenario.untapped_sources("Plains", username="bob")
    scenario.cast_and_resolve("Bandage", plains, username="bob", targets=[angel])

    assert scenario.game.deal_damage(angel, 1, source=angel) == 1
    scenario.game.destroy(leyline)
    assert scenario.game.deal_damage(angel, 1, source=angel) == 0  # the shield now works


def test_leyline_stops_life_gain():
    scenario = (
        Scenario()
        .player("alice", library=["Forest"], battlefield=["Leyline of Punishment"])
        .player("bob", library=["Forest"])
        .build()
    )

    scenario.game.gain_life("bob", 3)

    assert scenario.player("bob").life == 20
