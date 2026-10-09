"""EP-01 R1 T4: soulbond pairing (CR 702.95) and Flowering Lumberknot's "can't
attack or block unless it's paired with a creature with soulbond" (CR 508.1c,
509.1b).

A pair is two creatures one player controls (CR 702.95a); it breaks as soon as
either leaves the battlefield, stops being a creature, or changes controller
(CR 702.95c-e), checked lazily whenever the pairing is read.
"""

import pytest

from magic_cards_model.machines import Step, soulbond
from magic_cards_model.models import Zone

from .harness import Scenario

KNOT = "Flowering Lumberknot"
PALADIN = "Silverblade Paladin"


def _board(*, alice=(KNOT, PALADIN), hand=()):
    scenario = (
        Scenario()
        .player("alice", battlefield=list(alice), hand=list(hand))
        .player("bob", battlefield=["Hill Giant"])
        .build()
    )
    return scenario


def _pair(scenario, a=KNOT, b=PALADIN):
    soulbond.pair(scenario.game, scenario.creature(a, "alice"), scenario.creature(b, "alice"))


def _attack(scenario):
    scenario.start_at(Step.DECLARE_ATTACKERS)
    try:
        scenario.attack_with(scenario.creature(KNOT, "alice"), defending="bob")
    except ValueError as error:
        return str(error)
    return None


def test_unpaired_lumberknot_cannot_attack():
    refusal = _attack(_board())
    assert refusal is not None and "paired" in refusal


def test_paired_with_a_soulbond_creature_attacks():
    scenario = _board()
    _pair(scenario)
    assert _attack(scenario) is None


def test_paired_with_a_creature_without_soulbond_still_cannot_attack():
    scenario = _board(alice=(KNOT, "Grizzly Bears"))
    _pair(scenario, b="Grizzly Bears")
    refusal = _attack(scenario)
    assert refusal is not None and "paired" in refusal


def test_paired_lumberknot_blocks_and_unpaired_does_not():
    for paired in (True, False):
        scenario = (
            Scenario()
            .player("alice", battlefield=["Hill Giant"])
            .player("bob", battlefield=[KNOT, PALADIN])
            .build()
        )
        if paired:
            soulbond.pair(
                scenario.game, scenario.creature(KNOT, "bob"), scenario.creature(PALADIN, "bob")
            )
        scenario.start_at(Step.DECLARE_ATTACKERS)
        giant = scenario.creature("Hill Giant", "alice")
        scenario.attack_with(giant, defending="bob")
        if paired:
            scenario.block(giant, scenario.creature(KNOT, "bob"))
        else:
            with pytest.raises(ValueError, match="paired"):
                scenario.block(giant, scenario.creature(KNOT, "bob"))


def test_pair_breaks_when_the_partner_leaves_the_battlefield():
    scenario = _board()
    _pair(scenario)
    paladin = scenario.creature(PALADIN, "alice")
    scenario.game.destroy(paladin)
    knot = scenario.creature(KNOT, "alice")
    assert soulbond.partner_of(scenario.game, knot) is None
    refusal = _attack(scenario)
    assert refusal is not None and "paired" in refusal


def test_pair_breaks_when_the_partner_changes_controller():
    scenario = _board()
    _pair(scenario)
    scenario.creature(PALADIN, "alice").controller = "bob"
    assert soulbond.partner_of(scenario.game, scenario.creature(KNOT, "alice")) is None
    refusal = _attack(scenario)
    assert refusal is not None and "paired" in refusal


def test_pair_breaks_when_the_partner_stops_being_a_creature():
    """CR 702.95e: Mutavault's animation ends at cleanup (CR 514.2), and with
    it the creature the pair was made of."""
    scenario = _board(alice=(KNOT, "Mutavault", "Mountain"))
    scenario.start_at(Step.PRECOMBAT_MAIN)
    vault = scenario.find("Mutavault", Zone.BATTLEFIELD, "alice")
    scenario.activate(vault, *scenario.untapped_sources("Mountain", username="alice"), index=1)
    scenario.pass_until_resolved()
    knot = scenario.creature(KNOT, "alice")
    soulbond.pair(scenario.game, knot, vault)
    assert soulbond.partner_of(scenario.game, knot) is vault
    while scenario.step is not Step.CLEANUP:
        scenario.advance()
    assert soulbond.partner_of(scenario.game, knot) is None


def test_soulbond_creature_entering_pairs_with_an_unpaired_creature():
    scenario = _board(alice=(KNOT,), hand=(PALADIN,))
    scenario.will_take_the_may(True)
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.put_onto_battlefield(PALADIN, "alice")
    scenario.pass_until_resolved()
    knot = scenario.creature(KNOT, "alice")
    assert soulbond.partner_of(scenario.game, knot).name == PALADIN


def test_another_creature_entering_pairs_with_an_unpaired_soulbond_creature():
    scenario = _board(alice=(PALADIN,), hand=(KNOT,))
    scenario.will_take_the_may(True)
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.put_onto_battlefield(KNOT, "alice")
    scenario.pass_until_resolved()
    paladin = scenario.creature(PALADIN, "alice")
    assert soulbond.partner_of(scenario.game, paladin).name == KNOT


def test_declining_the_may_leaves_both_unpaired():
    scenario = _board(alice=(KNOT,), hand=(PALADIN,))
    scenario.will_take_the_may(False)
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.put_onto_battlefield(PALADIN, "alice")
    scenario.pass_until_resolved()
    assert soulbond.is_unpaired(scenario.game, scenario.creature(KNOT, "alice"))


def test_paired_creatures_both_have_double_strike_and_a_broken_pair_loses_it():
    """Silverblade Paladin: "As long as this creature is paired with another
    creature, both creatures have double strike." (CR 702.95a, CR 613.1f)."""
    from magic_cards_model.machines.combat import has_keyword

    scenario = _board(alice=(PALADIN, "Grizzly Bears"))
    paladin = scenario.creature(PALADIN, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    assert not has_keyword(paladin, "double strike", scenario.game)
    assert not has_keyword(bears, "double strike", scenario.game)
    soulbond.pair(scenario.game, paladin, bears)
    assert has_keyword(paladin, "double strike", scenario.game)
    assert has_keyword(bears, "double strike", scenario.game)
    scenario.game.destroy(bears)
    assert not has_keyword(paladin, "double strike", scenario.game)


def test_a_broken_pair_stays_broken_when_control_comes_back():
    """CR 702.95e: losing the partner to another player's control makes both
    unpaired for good - getting it back does not restore the pair."""
    scenario = _board()
    _pair(scenario)
    paladin = scenario.creature(PALADIN, "alice")
    paladin.controller = "bob"
    scenario.game.check_state_based_actions()
    paladin.controller = "alice"
    knot = scenario.creature(KNOT, "alice")
    assert soulbond.partner_of(scenario.game, knot) is None
    assert knot.paired_with is None
