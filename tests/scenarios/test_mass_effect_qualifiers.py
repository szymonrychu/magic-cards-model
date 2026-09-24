"""Mass damage and mass destruction with a qualifier, read off the board as it
is when the effect is applied.

Flame Sweep: "Flame Sweep deals 2 damage to each creature except for
creatures you control with flying." Elspeth, Sun's Champion's -3: "Destroy all
creatures with power 4 or greater." Neither targets (CR 115.10a), so the set
of affected creatures is worked out once, as the effect is applied (CR
608.2h), and processed simultaneously (CR 608.2f). The qualifier - "you
control" (CR 109.5), flying (CR 702.9), power (CR 208.1) - is read off each
creature's characteristics after every continuous effect is applied (CR
613.1, CR 613.5), not off its printing.

Generality proofs on printings that are neither the listed cards nor in any
deck (legality and oracle text checked against Scryfall on 2026-09-23):

- Sagittars' Volley (Modern, Pioneer): "... deals 1 damage to each creature
  with flying your opponents control." - the same keyword-plus-controller
  qualifier Flame Sweep's exclusion prints, in the other word order.
- Fiery Cannonade (Modern, Pioneer): "... deals 2 damage to each non-Pirate
  creature." - a CR 205.3m creature-type negation as the qualifier.
- The Battle of Bywater (Modern): "Destroy all creatures with power 3 or
  greater. Then create a Food token for each creature you control." - the
  power comparison with a different threshold, followed by a count that has
  to see the board after the destruction.

Every CR number in this file was read in full with `mise run rules:find`:
CR 109.5, CR 115.10a, CR 205.3m, CR 208.1, CR 608.2f, CR 608.2h, CR 613.1,
CR 613.5, CR 702.9.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _names(cards) -> list[str]:
    return sorted(card.name for card in cards)


# -- Flame Sweep: "each creature except for creatures you control with flying"


def test_flame_sweep_spares_only_the_casters_own_fliers() -> None:
    """The exclusion is two qualifiers at once: controlled by the caster
    (CR 109.5) *and* flying (CR 702.9). An opponent's flier is hit, and so is
    the caster's own ground creature."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Flame Sweep"],
            battlefield=["Serra Angel", "Grizzly Bears", "Mountain", "Mountain", "Mountain"],
        )
        .player("bob", battlefield=["Birds of Paradise", "Grizzly Bears", "Serra Angel"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice_angel = scenario.creature("Serra Angel", "alice")
    bob_angel = scenario.creature("Serra Angel", "bob")

    scenario.cast_and_resolve(
        "Flame Sweep", *scenario.untapped_sources("Mountain", "Mountain", "Mountain")
    )
    scenario.state_based_actions()

    assert alice_angel.damage == 0, "alice's own flier is the one exclusion"
    assert bob_angel.damage == 2, "bob's flier is not alice's: it is hit"
    assert _names(scenario.game.permanents_controlled_by("alice")) == [
        "Mountain",
        "Mountain",
        "Mountain",
        "Serra Angel",
    ]
    assert (
        _names(p for p in scenario.game.permanents_controlled_by("bob") if p.name != "Serra Angel")
        == []
    ), "Birds of Paradise flies but is bob's; Grizzly Bears has no flying"


def test_flame_sweep_reads_flying_granted_by_a_static_ability() -> None:
    """CR 613.5: Abzan Falconer's "Each creature you control with a +1/+1
    counter on it has flying" is part of the board Flame Sweep reads. Grizzly
    Bears with a counter flies, so it is spared; the Falconer itself has no
    counter and no flying, so it takes the 2 (and survives at toughness 3)."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Flame Sweep"],
            battlefield=["Abzan Falconer", "Grizzly Bears", "Mountain", "Mountain", "Mountain"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    falconer = scenario.creature("Abzan Falconer", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.game.add_counters(bears, "+1/+1", 1)

    scenario.cast_and_resolve(
        "Flame Sweep", *scenario.untapped_sources("Mountain", "Mountain", "Mountain")
    )
    scenario.state_based_actions()

    assert bears.zone is Zone.BATTLEFIELD
    assert bears.damage == 0, "granted flying counts: the bears are spared"
    assert falconer.damage == 2, "no counter, so no flying: the Falconer is hit"
    assert falconer.zone is Zone.BATTLEFIELD


def test_flame_sweep_does_not_spare_an_opponents_creature_given_flying() -> None:
    """Flying on bob's creature (Angelic Blessing, cast by alice) does not
    make it "a creature you control" - both halves of the exclusion must hold."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Angelic Blessing", "Flame Sweep"],
            battlefield=["Plains"] * 3 + ["Mountain"] * 3,
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.cast_and_resolve(
        "Angelic Blessing",
        *scenario.untapped_sources("Plains", "Plains", "Plains"),
        targets=[bears],
    )

    scenario.cast_and_resolve(
        "Flame Sweep", *scenario.untapped_sources("Mountain", "Mountain", "Mountain")
    )

    assert bears.damage == 2


def test_flame_sweep_ignores_noncreature_permanents() -> None:
    """ "Each creature" (CR 115.10a, no target): a land is never touched, and
    a sweep with no creature to hit resolves without error."""
    scenario = (
        Scenario()
        .player("alice", hand=["Flame Sweep"], battlefield=["Mountain", "Mountain", "Mountain"])
        .player("bob", battlefield=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    forest = scenario.find("Forest", Zone.BATTLEFIELD, "bob")

    scenario.cast_and_resolve(
        "Flame Sweep", *scenario.untapped_sources("Mountain", "Mountain", "Mountain")
    )

    assert forest.zone is Zone.BATTLEFIELD
    assert forest.damage == 0


# -- proof: Sagittars' Volley, "each creature with flying your opponents control"


def test_sagittars_volley_hits_only_the_opponents_fliers() -> None:
    """The destroy half targets bob's Serra Angel; the damage half reads the
    keyword-plus-controller qualifier: bob's Birds of Paradise dies, alice's
    own Birds and bob's Grizzly Bears are untouched."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Sagittars' Volley"],
            battlefield=["Birds of Paradise", "Forest", "Forest", "Forest"],
        )
        .player("bob", battlefield=["Serra Angel", "Birds of Paradise", "Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.creature("Serra Angel", "bob")
    alice_birds = scenario.creature("Birds of Paradise", "alice")
    bob_birds = scenario.creature("Birds of Paradise", "bob")
    bears = scenario.creature("Grizzly Bears", "bob")

    scenario.cast_and_resolve(
        "Sagittars' Volley",
        *scenario.untapped_sources("Forest", "Forest", "Forest"),
        targets=[angel],
    )
    scenario.state_based_actions()

    assert angel.zone is Zone.GRAVEYARD
    assert bob_birds.zone is Zone.GRAVEYARD
    assert alice_birds.zone is Zone.BATTLEFIELD and alice_birds.damage == 0
    assert bears.damage == 0


# -- proof: Fiery Cannonade, "each non-Pirate creature"


def test_fiery_cannonade_spares_pirates_on_both_sides() -> None:
    """CR 205.3m: Pirate is a creature type. Every creature that is not a
    Pirate takes 2, whoever controls it; every Pirate is spared."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Fiery Cannonade"],
            battlefield=[
                "Ragavan, Nimble Pilferer",
                "Grizzly Bears",
                "Mountain",
                "Mountain",
                "Mountain",
            ],
        )
        .player("bob", battlefield=["Dire Fleet Daredevil", "Serra Angel"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ragavan = scenario.creature("Ragavan, Nimble Pilferer", "alice")
    daredevil = scenario.creature("Dire Fleet Daredevil", "bob")
    bears = scenario.creature("Grizzly Bears", "alice")
    angel = scenario.creature("Serra Angel", "bob")

    scenario.cast_and_resolve(
        "Fiery Cannonade", *scenario.untapped_sources("Mountain", "Mountain", "Mountain")
    )
    scenario.state_based_actions()

    assert ragavan.zone is Zone.BATTLEFIELD and ragavan.damage == 0
    assert daredevil.zone is Zone.BATTLEFIELD and daredevil.damage == 0
    assert bears.zone is Zone.GRAVEYARD
    assert angel.damage == 2


# -- Elspeth, Sun's Champion's -3: "Destroy all creatures with power 4 or greater."


def _elspeth_board(
    *alice_creatures: str, bob: tuple[str, ...] = (), bob_hand: tuple[str, ...] = ()
) -> Scenario:
    return (
        Scenario()
        .player("alice", battlefield=["Elspeth, Sun's Champion", *alice_creatures])
        .player("bob", battlefield=list(bob), hand=list(bob_hand))
    )


def test_elspeth_minus_three_destroys_power_four_or_greater_on_both_sides() -> None:
    """ "All creatures": the controller's own Serra Angel (power 4, exactly
    the threshold) goes too; power 2 and 1 stay."""
    scenario = _elspeth_board(
        "Serra Angel", "Grizzly Bears", bob=("Wurmcoil Engine", "Llanowar Elves")
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    elspeth = scenario.find("Elspeth, Sun's Champion", Zone.BATTLEFIELD, "alice")
    angel = scenario.creature("Serra Angel", "alice")
    wurmcoil = scenario.creature("Wurmcoil Engine", "bob")
    bears = scenario.creature("Grizzly Bears", "alice")
    elves = scenario.creature("Llanowar Elves", "bob")

    scenario.activate(elspeth, index=1)
    scenario.resolve_top()

    assert angel.zone is Zone.GRAVEYARD
    assert wurmcoil.zone is Zone.GRAVEYARD
    assert bears.zone is Zone.BATTLEFIELD
    assert elves.zone is Zone.BATTLEFIELD


def test_elspeth_reads_power_after_counters() -> None:
    """CR 613.1: two +1/+1 counters make Grizzly Bears a 4/4, so it goes; one
    counter makes a 3/3, one short of the threshold, so it stays."""
    scenario = _elspeth_board("Grizzly Bears", "Grizzly Bears").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    elspeth = scenario.find("Elspeth, Sun's Champion", Zone.BATTLEFIELD, "alice")
    big, small = scenario.creatures("Grizzly Bears", "Grizzly Bears", username="alice")
    scenario.game.add_counters(big, "+1/+1", 2)
    scenario.game.add_counters(small, "+1/+1", 1)

    scenario.activate(elspeth, index=1)
    scenario.resolve_top()

    assert big.zone is Zone.GRAVEYARD
    assert small.zone is Zone.BATTLEFIELD


def test_elspeth_reads_power_as_it_is_at_resolution() -> None:
    """CR 608.2h: the power is read when the ability resolves. Giant Growth
    cast in response makes bob's Grizzly Bears a 5/5, so it is destroyed even
    though it was a 2/2 when Elspeth's ability was activated."""
    scenario = _elspeth_board(bob=("Grizzly Bears", "Forest"), bob_hand=("Giant Growth",)).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    elspeth = scenario.find("Elspeth, Sun's Champion", Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "bob")

    scenario.activate(elspeth, index=1)
    scenario.pass_priority("alice")
    scenario.cast_and_resolve(
        "Giant Growth",
        *scenario.untapped_sources("Forest", username="bob"),
        username="bob",
        targets=[bears],
    )
    scenario.resolve_top()

    assert bears.zone is Zone.GRAVEYARD


def test_elspeth_leaves_a_board_of_small_creatures_alone() -> None:
    scenario = _elspeth_board("Llanowar Elves", bob=("Grizzly Bears",)).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    elspeth = scenario.find("Elspeth, Sun's Champion", Zone.BATTLEFIELD, "alice")

    scenario.activate(elspeth, index=1)
    scenario.resolve_top()

    assert scenario.creature("Llanowar Elves", "alice").zone is Zone.BATTLEFIELD
    assert scenario.creature("Grizzly Bears", "bob").zone is Zone.BATTLEFIELD
    assert elspeth.counters["loyalty"] == 1


# -- proof: The Battle of Bywater, "power 3 or greater", then a count


def test_the_battle_of_bywater_destroys_power_three_or_greater_then_counts_survivors() -> None:
    """A 3/3 (Grizzly Bears with a counter) is exactly the threshold and goes;
    the plain 2/2 stays. The Food count reads the board after the destruction
    (CR 608.2h): one creature left, one Food."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["The Battle of Bywater"],
            battlefield=["Grizzly Bears", "Grizzly Bears", "Plains", "Plains", "Plains"],
        )
        .player("bob", battlefield=["Serra Angel"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    big, small = scenario.creatures("Grizzly Bears", "Grizzly Bears", username="alice")
    scenario.game.add_counters(big, "+1/+1", 1)
    angel = scenario.creature("Serra Angel", "bob")

    scenario.cast_and_resolve(
        "The Battle of Bywater", *scenario.untapped_sources("Plains", "Plains", "Plains")
    )

    assert big.zone is Zone.GRAVEYARD
    assert angel.zone is Zone.GRAVEYARD
    assert small.zone is Zone.BATTLEFIELD
    foods = [p for p in scenario.game.permanents_controlled_by("alice") if "Food" in p.subtypes]
    assert len(foods) == 1
