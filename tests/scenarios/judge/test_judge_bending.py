"""Judge scenarios: the Avatar bending keyword actions, at their edges.

Sourced from the DDR judge transcripts. Episodes covered:

- **How Does Airbend Work?** (2025-12-05) - airbending a spell exiles it and
  offers a *new* cast for {2}, carrying none of the original cast's choices
- **DDR#989** - Threaten + Earthbend (earthbend's return is a delayed triggered
  ability, so its controller is whoever earthbent, not whoever controlled the
  land when it left)

Earthbend (CR 701.66a) is the one of the four this engine implements - see
`tests/scenarios/test_earthbend.py` for the mechanic itself; this file only adds
the controller question DDR#989 is about. Airbend (CR 701.65a) has no
implementation at all: `Aang, Swift Savior`'s enters trigger parses ("airbend up
to one other target creature or spell") but resolves to nothing.

Every CR number here was looked up with `knowledge_search(type="rules")`.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

# --------------------------------------------------------------------------
# Airbend - CR 701.65a
# --------------------------------------------------------------------------


def _aang_airbending(target_name: str, target_owner: str):
    """Alice casts Aang, Swift Savior and airbends one of bob's permanents."""
    scenario = (
        Scenario()
        .player("alice", hand=["Aang, Swift Savior"], battlefield=["Plains", "Island", "Island"])
        .player("bob", battlefield=[target_name])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    target = scenario.creature(target_name, target_owner)
    scenario.choose_trigger_targets("Aang, Swift Savior", [target])
    scenario.cast_and_resolve(
        "Aang, Swift Savior", *scenario.untapped_sources("Plains", "Island", "Island")
    )
    while scenario.game.stack or scenario.pending_triggers:
        scenario.pass_until_resolved()
    return scenario, target


@pytest.mark.xfail(
    strict=True,
    reason="airbend has no implementation: `effect_for('Aang, Swift Savior', "
    "...)` is None and nothing in `machines/keywords.py` or "
    "`machines/effects.py` handles the word, so the enters trigger goes on the "
    "stack, resolves, and leaves the targeted permanent exactly where it was.",
)
def test_airbending_a_permanent_exiles_it_and_leaves_a_two_mana_permission():
    """The airbend episode's first half: it is an exile plus a permission.

    CR 701.65a: "Certain spells and abilities instruct a player to airbend one
    or more permanents and/or spells. To do so, that player exiles those
    objects. For each card exiled this way, for as long as it remains exiled,
    its owner may cast it for {2} rather than its mana cost."

    Aang, Swift Savior (confirmed with `resolve_cards`): "When Aang enters,
    airbend up to one other target creature or spell." The Bears leave the
    battlefield for exile, and it is *bob* - the owner - who gets the
    permission, not alice, which is why the episode keeps stressing that the
    recast is a brand new spell rather than a continuation of the old one.
    """
    _, bears = _aang_airbending("Grizzly Bears", "bob")

    assert bears.zone is Zone.EXILE


@pytest.mark.xfail(
    strict=True,
    reason="same gap - nothing is exiled, so nothing ceases to exist either. "
    "The token half of the episode cannot be reached until airbend is "
    "implemented at all.",
)
def test_airbending_a_token_makes_it_cease_to_exist_before_anyone_can_recast_it():
    """The airbend episode's token corner: the {2} permission is worthless.

    CR 701.65a's permission is "for each *card* exiled this way", and a token
    is not a card; CR 111.7 finishes the job regardless - "A token that's in a
    zone other than the battlefield ceases to exist. This is a state-based
    action" (CR 704.5d). So the token is gone before any player would receive
    priority to cast it.

    Fire Navy Trebuchet's Ballistic Boulder is the pool's nearest token to the
    episode's example; the assertion is only that the token is not on the
    battlefield and not castable from exile.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Aang, Swift Savior"], battlefield=["Plains", "Island", "Island"])
        .player("bob", battlefield=["Fire Navy Trebuchet", "Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.choose_trigger_targets("Aang, Swift Savior", [bears])
    scenario.cast_and_resolve(
        "Aang, Swift Savior", *scenario.untapped_sources("Plains", "Island", "Island")
    )
    while scenario.game.stack or scenario.pending_triggers:
        scenario.pass_until_resolved()

    assert bears.zone is Zone.EXILE
    assert "Grizzly Bears" not in scenario.battlefield_names()


# --------------------------------------------------------------------------
# DDR#989 - who controls earthbend's return
# --------------------------------------------------------------------------


def _earthbend_a_forest():
    """Alice casts Badgermole Cub and earthbends a Forest she already had."""
    scenario = (
        Scenario()
        .player("alice", hand=["Badgermole Cub"], battlefield=["Forest", "Forest", "Forest"])
        .player("bob", hand=["Threaten"], battlefield=["Mountain", "Mountain", "Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    first, second, target = scenario.untapped_sources("Forest", "Forest", "Forest")
    scenario.choose_trigger_targets("Badgermole Cub", [target])
    scenario.cast_and_resolve("Badgermole Cub", first, second)
    scenario.pass_until_resolved()
    return scenario, target


def test_the_earthbend_return_is_a_delayed_trigger_controlled_by_the_earthbender():
    """DDR#989's rules half: the return ability belongs to nobody's card.

    CR 701.66a: "'Earthbend N' means 'Target land you control becomes a 0/0
    land creature with haste in addition to its other types. Put N +1/+1
    counters on it. When that land dies or is put into exile, return it to the
    battlefield tapped under your control.'" That last sentence is a delayed
    triggered ability created on resolution (CR 603.7a), and CR 603.7e settles
    whose it is: "If an activated or triggered ability creates a delayed
    triggered ability, the source of that delayed triggered ability is the same
    as the source of that other ability. The controller of that delayed
    triggered ability is the player who controlled that other ability as it
    resolved."

    So "your control" in the return means alice, fixed at the moment Badgermole
    Cub's trigger resolved - not read again later off whoever happens to
    control the land. That is what the engine records, on both the dies and the
    exile halves of "dies or is put into exile".
    """
    scenario, forest = _earthbend_a_forest()

    delayed = scenario.game.delayed_triggers.triggers
    assert [trigger.controller for trigger in delayed] == ["alice", "alice"]
    assert all(trigger.subject_id == forest.id for trigger in delayed)


@pytest.mark.xfail(
    strict=True,
    reason="Threaten has no scripted effect - `effect_for('Threaten', ...)` is "
    "None - so it resolves, goes to the graveyard, and the Forest is still "
    "controlled by alice. There is no control-changing effect anywhere in "
    "`machines/layers.LAYER_EFFECTS` (CR 613.1b's layer 2 is unpopulated), so "
    "the board state this episode asks about cannot be built.",
)
def test_an_earthbent_land_returns_to_the_earthbender_even_if_someone_else_killed_it():
    """DDR#989: bob steals and sacrifices the land, and alice gets it back.

    Threaten (confirmed with `resolve_cards`): "Untap target creature and gain
    control of it until end of turn." The earthbent Forest is a land creature
    (CR 701.66a), so it is a legal target. Bob then sacrifices it (CR 701.21a:
    "its controller moves it from the battlefield directly to its owner's
    graveyard"), which is a death the delayed trigger is watching for.

    CR 603.7e already fixed that trigger's controller as alice when Badgermole
    Cub's ability resolved, so the land comes back tapped under *alice's*
    control - the "different from how a lot of similar effects in Magic's
    history have worked" the episode warns about.
    """
    scenario, forest = _earthbend_a_forest()

    scenario.pass_priority("alice")
    bob_lands = scenario.untapped_sources("Mountain", "Mountain", "Mountain", username="bob")
    scenario.cast_and_resolve("Threaten", *bob_lands, username="bob", targets=[forest])
    assert forest.controller == "bob"

    scenario.game.sacrifice(forest)
    assert forest.zone is Zone.GRAVEYARD
    scenario.pass_until_resolved()

    assert forest.zone is Zone.BATTLEFIELD
    assert forest.tapped is True
    assert forest.controller == "alice"
