"""Mana-spent gates on a spell's own instructions (CR 601.2h): what was spent
paying the total cost is recorded on the cast, and "`<instruction>` if {R}
was spent to cast this spell" is checked as each instruction is followed
(CR 608.2c), never at cast time.

Firespout ({2}{R/G}): "Firespout deals 3 damage to each creature without
flying if {R} was spent to cast this spell and 3 damage to each creature with
flying if {G} was spent to cast this spell. (Do both if {R}{G} was spent.)"
- one sentence, two independently gated instructions. The hybrid symbol lets
the caster spend red, green or both, which is what separates the branches.

Batwing Brume ({1}{W/B}): "Prevent all combat damage that would be dealt this
turn if {W} was spent to cast this spell. Each player loses 1 life for each
attacking creature they control if {B} was spent to cast this spell." - the
trailing gate composes with a prevention instruction and with a per-player
count.

Proof printings on the same readers: Rolling Spoil and Dryad's Caress (a
trailing/leading gate after an unconditional instruction), Rally for the
Throne (Adamant, "at least three white mana"), Slaying Fire (Adamant with
"instead"), and Torrent of Souls (two gated sentences, hybrid cost).
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _firespout_board() -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Firespout"],
            battlefield=["Mountain", "Mountain", "Forest", "Forest", "Plains"],
        )
        .player("bob", battlefield=["Grizzly Bears", "Wind Drake"])
    )


def _cast_firespout(*lands: str):
    scenario = _firespout_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve("Firespout", *scenario.untapped_sources(*lands))
    return scenario


def _on(scenario, name: str) -> bool:
    return name in scenario.battlefield_names()


def test_firespout_red_spent_hits_only_the_creatures_without_flying():
    scenario = _cast_firespout("Mountain", "Mountain", "Plains")
    assert not _on(scenario, "Grizzly Bears")
    assert _on(scenario, "Wind Drake")


def test_firespout_green_spent_hits_only_the_creatures_with_flying():
    scenario = _cast_firespout("Forest", "Forest", "Plains")
    assert _on(scenario, "Grizzly Bears")
    assert not _on(scenario, "Wind Drake")


def test_firespout_both_colours_spent_do_both():
    scenario = _cast_firespout("Mountain", "Forest", "Plains")
    assert not _on(scenario, "Grizzly Bears")
    assert not _on(scenario, "Wind Drake")


# -- Batwing Brume --------------------------------------------------------


def _brume_board() -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Batwing Brume"],
            battlefield=["Plains", "Plains", "Swamp", "Swamp", "Grizzly Bears", "Hill Giant"],
        )
        .player("bob", life=20)
    )


def _attack_then_brume(*lands: str):
    scenario = _brume_board().build()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(
        scenario.creature("Grizzly Bears", "alice"), scenario.creature("Hill Giant", "alice")
    )
    scenario.cast_and_resolve("Batwing Brume", *scenario.untapped_sources(*lands))
    scenario.no_blocks()
    scenario.combat_damage()
    return scenario


def test_brume_white_spent_prevents_all_combat_damage():
    scenario = _attack_then_brume("Plains", "Plains")
    assert scenario.player("bob").life == 20
    assert scenario.player("alice").life == 20


def test_brume_black_spent_alone_makes_each_player_lose_life_per_their_attackers():
    """Two attackers are alice's, so alice loses 2; bob attacks with nothing
    and loses 0 - and with no white spent, the combat damage is not
    prevented (3 + 2 from the two attackers)."""
    scenario = _attack_then_brume("Swamp", "Swamp")
    assert scenario.player("alice").life == 18
    assert scenario.player("bob").life == 20 - 5


def test_brume_both_colours_spent_do_both():
    scenario = _attack_then_brume("Plains", "Swamp")
    assert scenario.player("alice").life == 18
    assert scenario.player("bob").life == 20


# -- the same readers on other printings -------------------------------------


def test_rolling_spoil_shrinks_every_creature_only_if_black_was_spent():
    """Trailing "If {B} was spent to cast this spell, all creatures get
    -1/-1 until end of turn": a Forest-only cast leaves the 1/1 alone."""

    def run(*lands: str):
        scenario = (
            Scenario()
            .manual_turn_based_actions()
            .player(
                "alice",
                hand=["Rolling Spoil"],
                battlefield=["Forest", "Forest", "Forest", "Swamp", "Forest"],
            )
            .player("bob", battlefield=["Forest", "Elite Vanguard"])
            .build()
        )
        scenario.start_at(Step.PRECOMBAT_MAIN)
        land = scenario.find("Forest", Zone.BATTLEFIELD, "bob")
        scenario.cast_and_resolve(
            "Rolling Spoil", *scenario.untapped_sources(*lands), targets=[land]
        )
        return scenario

    green_only = run("Forest", "Forest", "Forest", "Forest")
    assert "Elite Vanguard" in green_only.battlefield_names()
    black_too = run("Forest", "Forest", "Forest", "Swamp")
    assert "Elite Vanguard" not in black_too.battlefield_names()


def test_dryad_s_caress_untaps_your_creatures_only_if_white_was_spent():
    def run(*lands: str):
        scenario = (
            Scenario()
            .manual_turn_based_actions()
            .player(
                "alice",
                hand=["Dryad's Caress"],
                battlefield=[*["Forest"] * 6, "Plains", "Elite Vanguard"],
            )
            .player("bob")
            .build()
        )
        scenario.start_at(Step.PRECOMBAT_MAIN)
        vanguard = scenario.creature("Elite Vanguard", "alice")
        vanguard.tapped = True
        scenario.cast_and_resolve("Dryad's Caress", *scenario.untapped_sources(*lands))
        return vanguard

    assert run("Forest", "Forest", "Forest", "Forest", "Forest", "Forest").tapped
    assert not run("Forest", "Forest", "Forest", "Forest", "Forest", "Plains").tapped


def test_adamant_gates_on_three_mana_of_one_colour():
    """Rally for the Throne: "Adamant - If at least three white mana was
    spent to cast this spell, you gain 1 life for each creature you control."
    {2}{W}: three Plains is adamant, two Plains and a Forest is not."""

    def life_after(*lands: str) -> int:
        scenario = (
            Scenario()
            .manual_turn_based_actions()
            .player(
                "alice",
                hand=["Rally for the Throne"],
                battlefield=["Plains", "Plains", "Plains", "Forest"],
            )
            .player("bob")
            .build()
        )
        scenario.start_at(Step.PRECOMBAT_MAIN)
        scenario.cast_and_resolve("Rally for the Throne", *scenario.untapped_sources(*lands))
        return scenario.player("alice").life

    assert life_after("Plains", "Plains", "Plains") == 22
    assert life_after("Plains", "Plains", "Forest") == 20


def test_adamant_instead_branch_replaces_the_base_damage():
    """Slaying Fire: "deals 3 damage to any target. Adamant - If at least
    three red mana was spent to cast this spell, it deals 4 damage instead."
    """

    def bob_life_after(*lands: str) -> int:
        scenario = (
            Scenario()
            .manual_turn_based_actions()
            .player(
                "alice",
                hand=["Slaying Fire"],
                battlefield=["Mountain", "Mountain", "Mountain", "Forest"],
            )
            .player("bob", life=20)
            .build()
        )
        scenario.start_at(Step.PRECOMBAT_MAIN)
        scenario.cast_and_resolve(
            "Slaying Fire", *scenario.untapped_sources(*lands), targets=["bob"]
        )
        return scenario.player("bob").life

    assert bob_life_after("Mountain", "Mountain", "Mountain") == 16
    assert bob_life_after("Mountain", "Mountain", "Forest") == 17


def test_each_player_loses_life_per_group_they_control_spell_and_trigger():
    """The life.py reader on its other printings: Stronghold Discipline (a
    spell, each player) and Netherborn Phalanx's ETB (each opponent only)."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Stronghold Discipline"],
            battlefield=["Swamp"] * 4 + ["Elite Vanguard", "Hill Giant"],
        )
        .player("bob", life=20, battlefield=["Elite Vanguard"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve("Stronghold Discipline", *scenario.untapped_sources(*["Swamp"] * 4))
    assert scenario.player("alice").life == 18
    assert scenario.player("bob").life == 19


def test_netherborn_phalanx_drains_each_opponent_per_creature_they_control():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Netherborn Phalanx"], battlefield=["Swamp"] * 6)
        .player("bob", life=20, battlefield=["Elite Vanguard", "Hill Giant"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve("Netherborn Phalanx", *scenario.untapped_sources(*["Swamp"] * 6))
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()
    assert scenario.player("bob").life == 18
    assert scenario.player("alice").life == 20
