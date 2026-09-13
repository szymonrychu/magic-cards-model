"""A mode that says "<this card's name> deals N damage to any target" (CR 700.2a).

A mode stands on its own once chosen, and it names its source by its printed
name - which for Kolaghan's Command and Darigaaz's Charm contains an
apostrophe. The damage reader must not treat that apostrophe as the quote mark
that opens a granted ability's quoted text (CR 113.3), or the whole mode reads
as nothing and resolves as a `ModeNotice`: Kolaghan's Command dealt no damage
in battle 8's review.

CR 120.3 is what damage to a player does; CR 115.4 is "any target". Every pair
of Kolaghan's Command's four modes is played (it says "Choose two"), and
Darigaaz's Charm (off the deck pool, "Choose one", 3 damage) and Prismari
Command (off the pool, no apostrophe) show the reader is the template's.
"""

import itertools

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

MODES = (1, 2, 3, 4)


def command_board() -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Kolaghan's Command"],
            graveyard=["Grizzly Bears"],
            battlefield=["Swamp", "Mountain", "Mountain"],
        )
        .player("bob", hand=["Island"], battlefield=["Aether Spellbomb"])
    )


@pytest.mark.parametrize("pair", list(itertools.combinations(MODES, 2)))
def test_every_pair_of_kolaghans_command_modes_does_both_things(pair):
    scenario = command_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")
    spellbomb = scenario.find("Aether Spellbomb", Zone.BATTLEFIELD, "bob")
    target_for = {1: bears, 2: "bob", 3: spellbomb, 4: "bob"}

    casting = scenario.cast("Kolaghan's Command")
    casting.choose_modes(list(pair))
    casting.choose_targets([target_for[mode] for mode in pair])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Swamp", "Mountain", "Mountain"))
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert (bears.zone is Zone.HAND) is (1 in pair)
    assert (scenario.player("bob").hand == []) is (2 in pair)
    assert (spellbomb.zone is Zone.GRAVEYARD) is (3 in pair)
    assert scenario.player("bob").life == (18 if 4 in pair else 20)
    assert scenario.game.mode_notices == []


def test_the_damage_mode_can_target_a_creature():
    """ "Any target" is a creature, player, planeswalker or battle (CR 115.4)."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Kolaghan's Command"],
            battlefield=["Swamp", "Mountain", "Mountain"],
        )
        .player("bob", hand=["Island"], battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "bob")
    casting = scenario.cast("Kolaghan's Command")
    casting.choose_modes([2, 4])
    casting.choose_targets(["bob", bears])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Swamp", "Mountain", "Mountain"))
    scenario.put_on_stack(casting)
    scenario.resolve_top()
    scenario.state_based_actions()

    assert bears.zone is Zone.GRAVEYARD
    assert scenario.game.mode_notices == []


def test_darigaazs_charm_damage_mode_off_the_pool():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Darigaaz's Charm"], battlefield=["Swamp", "Mountain", "Forest"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    casting = scenario.cast("Darigaaz's Charm")
    casting.choose_modes([2])
    casting.choose_targets(["bob"])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Swamp", "Mountain", "Forest"))
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert scenario.player("bob").life == 17
    assert scenario.game.mode_notices == []


def test_prismari_commands_damage_mode_off_the_pool():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Prismari Command"], battlefield=["Island", "Mountain", "Mountain"])
        .player("bob", battlefield=["Aether Spellbomb"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    spellbomb = scenario.find("Aether Spellbomb", Zone.BATTLEFIELD, "bob")
    casting = scenario.cast("Prismari Command")
    casting.choose_modes([1, 4])
    casting.choose_targets(["bob", spellbomb])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Island", "Mountain", "Mountain"))
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert scenario.player("bob").life == 18
    assert spellbomb.zone is Zone.GRAVEYARD
    assert scenario.game.mode_notices == []


def test_a_quoted_granted_ability_is_still_not_read_as_the_damage():
    """The apostrophe allowance is for a word's own possessive, not a quote:
    Weapons Manufacturing's token grant keeps failing this reader."""
    from magic_cards_model.machines.effects import _DAMAGE_TARGET_RE

    granted = (
        'create a colorless artifact token named Munitions with "When this token '
        'leaves the battlefield, it deals 2 damage to any target."'
    )
    assert _DAMAGE_TARGET_RE.fullmatch(granted) is None
    assert _DAMAGE_TARGET_RE.fullmatch("Kolaghan's Command deals 2 damage to any target.")
