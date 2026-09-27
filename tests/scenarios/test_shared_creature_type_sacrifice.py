"""Winnowing: "For each player, you choose a creature that player controls.
Then each player sacrifices all other creatures they control that don't
share a creature type with the chosen creature they control." CR 702.73a's
changeling ("This object is every creature type") is what makes two
creatures with no printed subtype in common still share one whenever either
side is a changeling - `machines/chosen_type.shares_creature_type` is the
new comparator this task adds for it, reused nowhere else yet (Winnowing is
the only pool card that compares creature types across a board this way).
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_winnowing_keeps_only_creatures_sharing_a_type_with_each_chosen_creature():
    """Alice keeps her chosen Bear and her other Bear (shares "Bear"), loses
    her Elf. Bob keeps his chosen Elf and his other Elf, loses his Bear."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Winnowing"],
            battlefield=(
                ["Plains"] * 6 + ["Grizzly Bears", "Grizzly Bears", "Lys Alana Dignitary"]
            ),
        )
        .player(
            "bob",
            battlefield=["Lys Alana Dignitary", "Lys Alana Dignitary", "Grizzly Bears"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice_bears = [
        state
        for state in scenario.game.permanents_controlled_by("alice")
        if state.name == "Grizzly Bears"
    ]
    alice_elf = scenario.creature("Lys Alana Dignitary", "alice")
    bob_elves = [
        state
        for state in scenario.game.permanents_controlled_by("bob")
        if state.name == "Lys Alana Dignitary"
    ]
    bob_bear = scenario.creature("Grizzly Bears", "bob")
    sources = scenario.untapped_sources(*["Plains"] * 6)

    casting = scenario.cast("Winnowing", "alice")
    payment = casting.begin_paying()
    scenario.pay_with(payment, *sources)
    scenario.put_on_stack(casting)
    # APNAP order: alice (active) chooses first, then bob.
    scenario.will_choose_cards(alice_bears[0])
    scenario.will_choose_cards(bob_elves[0])
    scenario.pass_until_resolved()

    assert alice_bears[0].zone is Zone.BATTLEFIELD
    assert alice_bears[1].zone is Zone.BATTLEFIELD
    assert alice_elf.zone is Zone.GRAVEYARD
    assert bob_elves[0].zone is Zone.BATTLEFIELD
    assert bob_elves[1].zone is Zone.BATTLEFIELD
    assert bob_bear.zone is Zone.GRAVEYARD


def test_winnowing_changeling_shares_every_creature_type():
    """CR 702.73a: a changeling shares a creature type with anything, so a
    chosen changeling keeps every other creature its controller has."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Winnowing"],
            battlefield=(
                ["Plains"] * 6 + ["Changeling Wayfinder", "Grizzly Bears", "Lys Alana Dignitary"]
            ),
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    changeling = scenario.creature("Changeling Wayfinder", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    elf = scenario.creature("Lys Alana Dignitary", "alice")
    sources = scenario.untapped_sources(*["Plains"] * 6)

    casting = scenario.cast("Winnowing", "alice")
    payment = casting.begin_paying()
    scenario.pay_with(payment, *sources)
    scenario.put_on_stack(casting)
    scenario.will_choose_cards(changeling)
    scenario.pass_until_resolved()

    assert changeling.zone is Zone.BATTLEFIELD
    assert bears.zone is Zone.BATTLEFIELD
    assert elf.zone is Zone.BATTLEFIELD
