"""Judge scenarios: what "dies" means, and what stops a death from happening.

Sourced from the DDR judge transcripts. Episodes covered:

- **DDR#193** - Flinging Footlight Fiend vs. Rest in Peace
- **DDR#66** - Abrupt Decay vs. Rest in Peace
- **DDR#918** - The Sibsig Ceremony + Indestructible Creatures (Leyline of the Void)
- **DDR#932** - Traveling Chocobo + Teval (what still sees a death, and what does not)

The cornerstone the judges keep returning to: CR 700.4 defines *dies* as "is put
into a graveyard from the battlefield". A replacement effect that exiles the
permanent instead means the graveyard event never happens at all (CR 614.6),
so nothing watching for a death sees one - the trigger never triggers, because
CR 603.2 needs a game event that matches its trigger condition and there isn't
one.

Every CR number here was looked up with `knowledge_search(type="rules")`.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def bolt_board(*bob_battlefield: str) -> Scenario:
    """alice holds a Bolt over one Mountain; bob has whatever the case needs."""
    return (
        Scenario()
        .player("alice", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .player("bob", battlefield=list(bob_battlefield))
    )


def bolt(scenario, victim):
    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    return scenario.cast_and_resolve("Lightning Bolt", mountain, username="alice", targets=[victim])


def test_a_creature_with_no_replacement_effect_around_reaches_the_graveyard():
    """The baseline every other test in this file is measured against (CR 700.4).

    Footlight Fiend is a 1/1; three damage is lethal, the state-based action of
    CR 704.5g destroys it, and destroying is "move it from the battlefield to
    its owner's graveyard" (CR 701.8a). That is a death.
    """
    scenario = bolt_board("Footlight Fiend").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    fiend = scenario.creature("Footlight Fiend", "bob")

    bolt(scenario, fiend)

    assert fiend.zone is Zone.GRAVEYARD
    assert fiend in scenario.player("bob").graveyard


@pytest.mark.xfail(
    strict=True,
    reason="triggered abilities are not modelled (CR 603): nothing puts a dies trigger "
    "on the stack, so machines/triggers.py is never consulted by Game.resolve_top",
)
def test_a_dies_trigger_goes_on_the_stack_when_the_death_actually_happens():
    """DDR#193: the Fiend's own trigger, with nothing interfering.

    "When this creature dies, it deals 1 damage to any target." CR 603.2 says
    the ability triggers the moment the game event matches, and CR 603.3 puts it
    on the stack the next time a player would receive priority. Without this
    half working, the Rest in Peace case below cannot be told apart from the
    engine simply not having triggers.
    """
    scenario = bolt_board("Footlight Fiend").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    fiend = scenario.creature("Footlight Fiend", "bob")

    bolt(scenario, fiend)

    assert [state.name for state in scenario.game.stack] == ["Footlight Fiend"], (
        "the dies trigger should be waiting on the stack"
    )


def test_rest_in_peace_exiles_the_dying_creature_instead():
    """DDR#193, DDR#66: the zone change is replaced before it happens.

    Rest in Peace reads "If a card would be put into a graveyard from anywhere,
    exile it instead." CR 614.1a makes that a replacement effect, and CR 614.6
    says the replaced event never happens - a modified event occurs instead.
    """
    scenario = bolt_board("Footlight Fiend", "Rest in Peace").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    fiend = scenario.creature("Footlight Fiend", "bob")

    bolt(scenario, fiend)

    assert fiend.zone is Zone.EXILE
    assert fiend in scenario.game.exile


def test_the_fiend_never_dies_so_it_is_never_in_a_graveyard():
    """DDR#193, DDR#918: no graveyard, no death, no trigger.

    This is the assertion the judges actually make. It does not mention
    triggers, because the reason the trigger is absent is upstream of triggers:
    CR 700.4 defines *dies* as being put into a graveyard from the battlefield,
    and CR 614.6 means that never happened. Leyline of the Void (DDR#918) and
    Rest in Peace differ only in whose cards they catch.
    """
    scenario = bolt_board("Footlight Fiend", "Rest in Peace").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    fiend = scenario.creature("Footlight Fiend", "bob")

    bolt(scenario, fiend)

    assert scenario.player("bob").graveyard == [], "nothing ever reached a graveyard"


def test_leyline_of_the_void_only_catches_the_opponents_cards():
    """DDR#918: the same replacement, aimed by controller rather than at everything.

    "If a card would be put into an opponent's graveyard from anywhere, exile it
    instead." Same CR 614.1a replacement, but alice's Leyline replaces the event
    only for bob's cards, so alice's own Bolt still reaches alice's graveyard.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Bolt"],
            battlefield=["Mountain", "Leyline of the Void"],
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")

    spell = bolt(scenario, bears)

    assert bears.zone is Zone.EXILE, "bob is an opponent of the Leyline's controller"
    assert spell.zone is Zone.GRAVEYARD, "alice's own card is not an opponent's card"


def test_kalitas_exiles_an_opponents_creature_rather_than_letting_it_die():
    """DDR#932: another death-replacer, worded as a "would die" trigger-shaped clause.

    "If a nontoken creature an opponent controls would die, instead exile that
    card and create a 2/2 black Zombie creature token." The word *instead* is
    what makes it a replacement effect (CR 614.1a); *die* is CR 700.4, so the
    event being replaced is the move to the graveyard.

    Only the exile half runs. Tokens are not modelled, so the Zombie is not
    created - the modified event carries an instruction that cannot be carried
    out, which CR 614.6 covers explicitly: "the modified event may contain
    instructions that can't be carried out."
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Bolt"],
            battlefield=["Mountain", "Kalitas, Traitor of Ghet"],
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")

    bolt(scenario, bears)

    assert bears.zone is Zone.EXILE
    assert scenario.player("bob").graveyard == []


def test_rest_in_peace_exiles_itself_when_it_is_destroyed():
    """DDR#66: Abrupt Decay kills Rest in Peace, and Rest in Peace catches itself.

    A static ability's continuous effect is active for as long as its permanent
    is on the battlefield (CR 604.2, CR 611.3b). At the moment the destruction
    happens Rest in Peace is still there, so its own replacement effect applies
    to its own zone change and it goes to exile rather than the graveyard.

    The scenario destroys it directly rather than casting Abrupt Decay, because
    the effect registry in `machines/effects.py` has no entry for that card and
    the point under test is the replacement, not the removal spell.
    """
    scenario = Scenario().player("bob", battlefield=["Rest in Peace"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    rip = scenario.creature("Rest in Peace", "bob")

    scenario.game.destroy(rip)

    assert rip.zone is Zone.EXILE
