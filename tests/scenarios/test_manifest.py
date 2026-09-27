"""Manifest and Manifest dread: CR 701.40a and CR 701.62a.

Both are bare CR 701 keyword actions, read generically off the printed
sentence in `machines/effects.py` - `manifest`/`_parse_manifest_top_card_
clause` and `manifest_dread`/`_parse_manifest_dread_clause` - rather than by
card name. Proved on two cards outside the deck pool and outside this wave's
brief: Mastery of the Unseen's plain "Manifest the top card of your
library." off an activated ability, and Bashful Beastie's "manifest dread"
off a dies trigger, alongside Abhorrent Oculus's own upkeep-triggered
"manifest dread".
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Type
from tests.scenarios.harness import Scenario


def test_mastery_of_the_unseen_manifests_the_top_card():
    """Mastery of the Unseen: "{3}{W}: Manifest the top card of your
    library." (Put it onto the battlefield face down as a 2/2 creature. Turn
    it face up any time for its mana cost if it's a creature card.)

    CR 701.40a, in full: a face-down permanent with no text, no name, no
    subtypes, and no mana cost - 2/2 regardless of what it hides.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Grizzly Bears", "Forest"],
            battlefield=["Mastery of the Unseen", "Plains", "Plains", "Plains", "Plains"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mastery = scenario.find("Mastery of the Unseen", Zone.BATTLEFIELD)
    library_before = len(scenario.player("alice").library)

    scenario.activate(mastery, index=0, username="alice", auto=True)
    scenario.pass_until_resolved()

    manifested = [
        state
        for state in scenario.game.battlefield
        if state.zone is Zone.BATTLEFIELD and state.face_down
    ]
    assert len(manifested) == 1
    (permanent,) = manifested
    assert permanent.name == "", "CR 701.40a: no name while face down"
    assert permanent.card.name == "Grizzly Bears", "the underlying card is still known by identity"
    assert scenario.game.power_of(permanent) == 2
    assert scenario.game.toughness_of(permanent) == 2
    assert list(scenario.game.characteristics_of(permanent).types) == [Type.CREATURE]
    assert len(scenario.player("alice").library) == library_before - 1


def test_abhorrent_oculus_manifest_dreads_on_each_opponents_upkeep():
    """Abhorrent Oculus: "At the beginning of each opponent's upkeep,
    manifest dread." (Look at the top two cards of your library. Put one
    onto the battlefield face down as a 2/2 creature and the other into your
    graveyard. Turn it face up any time for its mana cost if it's a creature
    card.)
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Grizzly Bears", "Forest"],
            battlefield=["Abhorrent Oculus"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    while not (scenario.turn.active_player == "bob" and scenario.step is Step.UPKEEP):
        scenario.advance()
        while not scenario.game.stack_is_empty:
            scenario.resolve_top()
    scenario.pass_until_resolved()

    manifested = [state for state in scenario.game.battlefield if state.face_down]
    graveyard = [state.name for state in scenario.player("alice").graveyard]
    assert len(manifested) == 1
    assert len(graveyard) == 1
    assert manifested[0].name == "", "CR 701.40a: no name while face down"
    assert {manifested[0].card.name, graveyard[0]} == {"Grizzly Bears", "Forest"}
    assert len(scenario.player("alice").library) == 0


def test_ethereal_ambush_manifests_the_top_two_cards():
    """Ethereal Ambush (off-pool, added with `scripts/add_card.py`, verified
    against its own printed text): "Manifest the top two cards of your
    library." Unlike Mastery of the Unseen's fixed "the top card" above, this
    is `_MANIFEST_TOP_CARD_RE`'s own counted shape - CR 701.40a run twice,
    top card first, each becoming its own separate 2/2 face-down permanent
    rather than one look-two-choose-one the way "manifest dread" works.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Ethereal Ambush"],
            library=["Grizzly Bears", "Forest"],
            battlefield=["Forest", "Forest", "Forest", "Island", "Island"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Forest", "Forest", "Forest", "Island", "Island")

    scenario.cast_and_resolve("Ethereal Ambush", *sources)

    manifested = [state for state in scenario.game.battlefield if state.face_down]
    assert len(manifested) == 2
    assert {state.card.name for state in manifested} == {"Grizzly Bears", "Forest"}
    for state in manifested:
        assert state.name == "", "CR 701.40a: no name while face down"
        assert scenario.game.power_of(state) == 2
        assert scenario.game.toughness_of(state) == 2
    assert len(scenario.player("alice").library) == 0


def test_bashful_beastie_manifest_dreads_when_it_dies():
    """Bashful Beastie: "When this creature dies, manifest dread." - a
    different trigger event from Abhorrent Oculus's own upkeep, and the same
    reader has to catch both. Not in the deck pool, not named in this wave's
    brief.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Grizzly Bears", "Forest"],
            battlefield=["Bashful Beastie"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    beastie = scenario.creature("Bashful Beastie", "alice")

    scenario.game.destroy(beastie)
    scenario.state_based_actions()
    scenario.pass_until_resolved()

    manifested = [state for state in scenario.game.battlefield if state.face_down]
    assert len(manifested) == 1
    assert len(scenario.player("alice").library) == 0


# -- Unidentified Hovership: the exiled card's owner manifests dread ------------------
#
# "When this Vehicle enters, exile up to one target creature with toughness 5
# or less. When this Vehicle leaves the battlefield, the exiled card's owner
# manifests dread." The two abilities are linked (CR 607.1): the leaves
# trigger (CR 603.6c) reads only what the enters trigger exiled, and it is the
# exiled card's *owner* - not the Vehicle's controller - who manifests dread
# (CR 701.62a). The exiled card itself stays in exile.

HOVERSHIP = "Unidentified Hovership"


def _hovership_board(bob_library=("Grizzly Bears", "Forest", "Island")):
    scenario = (
        Scenario()
        .player("alice", hand=[HOVERSHIP], library=["Plains"] * 5)
        .player("bob", battlefield=["Grizzly Bears"], library=list(bob_library))
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _enter_hovership(scenario, targets):
    scenario.choose_trigger_targets(HOVERSHIP, targets)
    return scenario.put_onto_battlefield(HOVERSHIP, "alice")


def _face_down(scenario, username):
    return [
        state
        for state in scenario.game.battlefield
        if state.face_down and scenario.game.controller_of(state).username == username
    ]


def test_hovership_leaving_makes_the_exiled_cards_owner_manifest_dread():
    scenario = _hovership_board()
    bears = scenario.creature("Grizzly Bears", "bob")
    hovership = _enter_hovership(scenario, [bears])
    scenario.pass_until_resolved()
    assert bears.zone is Zone.EXILE

    scenario.game.destroy(hovership)
    scenario.pass_until_resolved()

    assert len(_face_down(scenario, "bob")) == 1, "the owner manifests, under their control"
    assert _face_down(scenario, "alice") == []
    assert len(scenario.player("bob").library) == 1, "looked at two, one manifested"
    assert len(scenario.player("bob").graveyard) == 1, "the other into the graveyard"
    assert bears.zone is Zone.EXILE, "the exiled card stays exiled"


def test_hovership_with_no_exiled_card_manifests_nothing():
    """ "Up to one" chose none: there is no exiled card, so nobody manifests."""
    scenario = _hovership_board()
    hovership = _enter_hovership(scenario, [])
    scenario.pass_until_resolved()

    scenario.game.destroy(hovership)
    scenario.pass_until_resolved()

    assert _face_down(scenario, "bob") == []
    assert _face_down(scenario, "alice") == []
    assert len(scenario.player("bob").library) == 3


def test_hovership_leaving_before_its_enters_trigger_resolves_manifests_nothing():
    """The ruling: with the enters trigger still on the stack, the leaves
    trigger finds no exiled card and does nothing; the enters trigger then
    still exiles the target."""
    scenario = _hovership_board()
    bears = scenario.creature("Grizzly Bears", "bob")
    hovership = _enter_hovership(scenario, [bears])
    scenario.game.put_triggers_on_stack()

    scenario.game.return_to_hand(hovership)
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()  # the leaves trigger, above the enters trigger
    scenario.resolve_top()

    assert _face_down(scenario, "bob") == []
    assert len(scenario.player("bob").library) == 3
    assert bears.zone is Zone.EXILE


def test_unwanted_remake_makes_the_destroyed_creatures_controller_manifest_dread():
    """Unwanted Remake (the second manifest-dread printing here, not in the
    deck pool): "Destroy target creature. Its controller manifests dread." -
    the same CR 701.62a action performed by a player other than the one whose
    object caused it."""
    scenario = (
        Scenario()
        .player("alice", hand=["Unwanted Remake"], battlefield=["Plains"] * 2, library=["Plains"])
        .player("bob", battlefield=["Grizzly Bears"], library=["Forest", "Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")

    scenario.cast_and_resolve(
        "Unwanted Remake", *scenario.untapped_sources("Plains", "Plains"), targets=[bears]
    )

    assert bears.zone is Zone.GRAVEYARD
    assert len(_face_down(scenario, "bob")) == 1
    assert scenario.player("bob").library == []


def test_the_exiled_card_owner_dread_reader_reads_the_plural_too():
    """No second printing carries the leaves-trigger sentence, so the reader
    is proven on the template's own plural (CR 607.3)."""
    from magic_cards_model.machines.linked_exile import (
        parse_exiled_card_owner_manifests_dread_clause,
    )

    assert parse_exiled_card_owner_manifests_dread_clause(
        "the exiled cards' owners each manifest dread."
    )
    assert (
        parse_exiled_card_owner_manifests_dread_clause("the exiled card's owner draws a card.")
        is None
    )
