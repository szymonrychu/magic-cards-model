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
