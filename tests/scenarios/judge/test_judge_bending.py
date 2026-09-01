"""Judge scenarios: the Avatar bending keyword actions, at their edges.

Sourced from the DDR judge transcripts. Episodes covered:

- **How Does Airbend Work?** (2025-12-05) - airbending a spell exiles it and
  offers a *new* cast for {2}, carrying none of the original cast's choices
- **DDR#989** - Threaten + Earthbend (earthbend's return is a delayed triggered
  ability, so its controller is whoever earthbent, not whoever controlled the
  land when it left)

Earthbend (CR 701.66a) is the one of the four this engine implements - see
`tests/scenarios/test_earthbend.py` for the mechanic itself; this file only adds
the controller question DDR#989 is about. Airbend (CR 701.65a) is whole now:
`machines/effects._parse_airbend_clause` performs the exile and writes CR 406.4's
`ExileMarker.AIRBENT` note onto each exiled *card*, and
`machines/casting.marker_cast_options` reads the {2} back off that note.

Every CR number here was looked up with `knowledge_search(type="rules")`.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.casting import marker_cast_options
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import ExileAnnotation, ExileMarker
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


def test_an_airbent_card_in_exile_may_be_cast_by_its_owner_for_two():
    """CR 701.65a's *permission*, the half that is not the exile.

    "For each card exiled this way, for as long as it remains exiled, its owner
    may cast it for {2} rather than its mana cost." Airbend is a CR 701 keyword
    action, so nothing is printed on the exiled card to read that off - the pile
    it is in is the whole record, which is what `ExileMarker.AIRBENT` and
    `machines/casting.marker_cast_options` are.

    The board is staged at the state the exile leaves behind rather than played
    into it, so that this test is about `marker_cast_options` alone - the test
    above is the one that plays the exile out through Aang. Nothing is faked: a
    real Grizzly Bears printing, in the real exile zone, annotated the way
    CR 406.4 says the pile is tracked.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Island", "Island"])
        .player("bob", exile=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.EXILE, "bob")
    bears.exile_annotation = ExileAnnotation(marker=ExileMarker.AIRBENT, owner="bob")

    (option,) = marker_cast_options(bears)

    assert option.rule == "CR 701.65a"
    assert option.zone is Zone.EXILE
    assert option.pays_mana_cost is False
    assert str(option.cost.mana) == "{2}"
    # CR 701.65a gives the permission to the card's *owner*, and the player who
    # airbent it is somebody else - alice is refused, bob is not.
    assert option.why_not(bears, "alice") is not None
    assert option.why_not(bears, "bob") is None
    # No "on a later turn" clause anywhere in CR 701.65a, unlike plot
    # (CR 702.170d) and foretell (CR 702.143a).
    assert option.later_turn is False


def test_airbending_a_token_makes_it_cease_to_exist_before_anyone_can_recast_it():
    """The airbend episode's token corner: the {2} permission is worthless.

    CR 701.65a's permission is "for each *card* exiled this way", and a token
    is not a card; CR 111.7 finishes the job regardless - "A token that's in a
    zone other than the battlefield ceases to exist. This is a state-based
    action" (CR 704.5d). So the token is gone before any player would receive
    priority to cast it.

    Fire Navy Trebuchet (confirmed with `resolve_cards`): "Whenever you attack,
    create a 2/1 colorless Construct artifact creature token with flying named
    Ballistic Boulder that's tapped and attacking." So the token has to be made
    the way the card makes it - bob attacks - and Aang's own flash is what lets
    alice cast him in the middle of that combat to airbend it.
    """
    scenario = (
        Scenario()
        .player("bob", battlefield=["Fire Navy Trebuchet", "Grizzly Bears"])
        .player("alice", hand=["Aang, Swift Savior"], battlefield=["Plains", "Island", "Island"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(scenario.creature("Grizzly Bears", "bob"))
    scenario.pass_until_resolved()
    token = scenario.creature("Ballistic Boulder", "bob")

    # CR 117.1: bob is the active player and holds priority once his own
    # trigger has resolved; alice's flash cast needs her to have it.
    scenario.pass_priority("bob")
    scenario.choose_trigger_targets("Aang, Swift Savior", [token])
    scenario.cast_and_resolve(
        "Aang, Swift Savior",
        *scenario.untapped_sources("Plains", "Island", "Island", username="alice"),
        username="alice",
    )
    while scenario.game.stack or scenario.pending_triggers:
        scenario.pass_until_resolved()
    scenario.state_based_actions()

    # CR 111.7/CR 704.5d: it is in no zone at all, exile included.
    assert token.zone is not Zone.BATTLEFIELD
    assert scenario.zones_containing(token) == []
    # CR 701.65a's permission is "for each *card*", and a token is not one.
    assert marker_cast_options(token) == []


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
    reason="ONE gap now, and it is in models/card_state.py and models/game.py. Threaten is "
    "built: `machines/effects._parse_untap_and_gain_control_clause` reads its whole effect, "
    "untaps the target (CR 701.26b) and hands 'gain control of target creature until end of "
    "turn.' and 'target creature gains haste until end of turn.' to "
    "`machines/layers.parsed_layer_effects`, so `game.characteristics_of(forest).controller` "
    "really does answer 'bob' and the Forest really does gain haste. What is still missing is "
    "that `CardState.controller` is a plain stored field and `Game.controller_of` reads it "
    "directly, so that layer 2 effect (CR 613.1b) is invisible to `forest.controller`, to "
    "combat, to state-based actions and to the delayed trigger - both would have to consult "
    "the computed board (CR 613.5). The very next assertion in this test, "
    "`forest.controller == 'bob'`, is the one that fails.",
)
def test_an_earthbent_land_returns_to_the_earthbender_even_if_someone_else_killed_it():
    """DDR#989: bob steals and sacrifices the land, and alice gets it back.

    Threaten (confirmed with `resolve_cards`): "Untap target creature and gain
    control of it until end of turn. That creature gains haste until end of
    turn." The earthbent Forest is a land creature (CR 701.66a), so it is a
    legal target. Bob then sacrifices it (CR 701.21a: "its controller moves it
    from the battlefield directly to its owner's graveyard"), which is a death
    the delayed trigger is watching for.

    CR 603.7e already fixed that trigger's controller as alice when Badgermole
    Cub's ability resolved, so the land comes back tapped under *alice's*
    control - the "different from how a lot of similar effects in Magic's
    history have worked" the episode warns about.

    The turn is handed to bob before Threaten is cast, and that is not
    housekeeping: Threaten is a sorcery, and CR 307.1 lets a player cast one
    only "during a main phase of their turn when the stack is empty" (CR
    117.1a says the same about noninstants generally). An earlier version of
    this test cast it as bob during
    alice's turn and the engine correctly refused - the refusal, not the
    episode, was what it measured.
    """
    scenario, forest = _earthbend_a_forest()

    # Alice's turn ends and bob's begins (CR 500.1, CR 505.1) - the earthbend
    # animation has no duration in CR 701.66a, so the Forest is still a land
    # creature when bob's main phase arrives.
    scenario.turn.advance_to(Step.CLEANUP)
    scenario.advance()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    assert scenario.turn.active_player == "bob"

    bob_lands = scenario.untapped_sources("Mountain", "Mountain", "Mountain", username="bob")
    scenario.cast_and_resolve("Threaten", *bob_lands, username="bob", targets=[forest])
    assert forest.controller == "bob"

    scenario.game.sacrifice(forest)
    assert forest.zone is Zone.GRAVEYARD
    scenario.pass_until_resolved()

    assert forest.zone is Zone.BATTLEFIELD
    assert forest.tapped is True
    assert forest.controller == "alice"
