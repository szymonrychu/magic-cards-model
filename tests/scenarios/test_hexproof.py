"""Hexproof: a permanent an opponent cannot target (CR 702.11).

CR 702.11a: "Hexproof is a static ability." CR 702.11b: "'Hexproof' on a
permanent means "This permanent can't be the target of spells or abilities your
opponents control.""

The word doing the work is *opponents*. Hexproof is not shroud (CR 702.18a,
"can't be the target of spells or abilities" full stop), so the controller's own
spells target it happily - which is the first corner case here.

The refusal belongs at CR 601.2c, as the targets are announced, so an illegal
target is never chosen and the caster keeps their card. CR 702.11c's hexproof on
a player is not modelled; see `docs/engine-coverage.md`.

CR 702.11d's "hexproof from [quality]" is the second half of this file:
"'Hexproof from [quality]' is a variant of the hexproof ability. 'Hexproof from
[quality]' on a permanent means 'This permanent can't be the target of [quality]
spells your opponents control...'" - so it refuses a spell *of that quality* and
nothing else. CR 702.11f: "'Hexproof from [quality A] and from [quality B]' is
shorthand for 'hexproof from [quality A]' and 'hexproof from [quality B]'; it
behaves as two separate hexproof abilities." Nevinyrral, Urborg Tyrant prints
the list form of that shorthand, "Hexproof from artifacts, creatures, and
enchantments".

Every CR number here was verified with `knowledge_search(type="rules")` in the
session that wrote it.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.cards import card
from tests.scenarios.harness import Scenario


def board(bolt_owner: str = "alice") -> Scenario:
    hands = {"alice": [], "bob": []}
    hands[bolt_owner] = ["Lightning Bolt"]
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=hands["alice"],
            battlefield=["Mountain", "Striped Riverwinder"],
        )
        .player("bob", hand=hands["bob"], battlefield=["Mountain"])
    )


def test_an_opponent_cannot_target_a_hexproof_creature():
    """CR 702.11b, the whole rule."""
    scenario = board(bolt_owner="bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    riverwinder = scenario.creature("Striped Riverwinder", "alice")

    casting = scenario.cast("Lightning Bolt", username="bob")
    with pytest.raises(ValueError, match="has hexproof"):
        casting.choose_targets([riverwinder])


def test_its_own_controller_can_target_it():
    """Hexproof is not shroud: CR 702.11b only names *your opponents*."""
    scenario = board(bolt_owner="alice").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    riverwinder = scenario.creature("Striped Riverwinder", "alice")

    scenario.cast_and_resolve(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=[riverwinder]
    )
    assert riverwinder.damage == 3


def test_a_refused_target_leaves_the_spell_in_hand():
    """CR 601.2c is an announcement step: a refusal is not a cast."""
    scenario = board(bolt_owner="bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    riverwinder = scenario.creature("Striped Riverwinder", "alice")

    casting = scenario.cast("Lightning Bolt", username="bob")
    with pytest.raises(ValueError):
        casting.choose_targets([riverwinder])

    bolt = scenario.find("Lightning Bolt", Zone.HAND, "bob")
    assert bolt.zone is Zone.HAND
    assert scenario.game.stack_is_empty


def test_the_opponents_face_is_still_a_legal_target():
    """A hexproof creature on the board changes nothing about other targets."""
    scenario = board(bolt_owner="bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.pass_priority("alice")

    scenario.cast_and_resolve(
        "Lightning Bolt",
        *scenario.untapped_sources("Mountain", username="bob"),
        username="bob",
        targets=["alice"],
    )
    assert scenario.player("alice").life == 17


def test_hexproof_in_the_graveyard_protects_nothing():
    """CR 702.11b speaks of a *permanent*, and a permanent is on the battlefield.

    The engine has no card in the pool that targets a graveyard, so this asserts
    the shape of the check rather than a whole spell: a hexproof card that is
    not on the battlefield is not refused.
    """
    scenario = board(bolt_owner="bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    riverwinder = scenario.creature("Striped Riverwinder", "alice")
    scenario.game.put_into_graveyard(riverwinder)

    casting = scenario.cast("Lightning Bolt", username="bob")
    assert casting._hexproof_refusal(riverwinder) is None


# -- CR 702.11d: hexproof from [quality] -----------------------------------


def quality_board() -> Scenario:
    """Nevinyrral, Urborg Tyrant under bob, with alice - the active player, so
    her Aura is castable (CR 117.1a) - holding one spell of a named quality
    (Hyena Umbra, an enchantment) and one of another (Lightning Bolt, an
    instant)."""
    return (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Hyena Umbra", "Lightning Bolt"], battlefield=["Plains", "Mountain"])
        .player("bob", battlefield=["Nevinyrral, Urborg Tyrant"])
    )


def test_scryfall_flattens_hexproof_from_into_a_bare_hexproof_keyword():
    """Why the refusal cannot be read off `keywords` (the defect this pins).

    Scryfall's `keywords` array on Nevinyrral lists both "Hexproof from" and a
    bare "Hexproof", though the printed ability is only CR 702.11d's variant.
    Trusting that list grants CR 702.11b's full hexproof to a permanent that
    never had it, so the check reads the printed ability text instead.
    """
    nevinyrral = card("Nevinyrral, Urborg Tyrant")
    assert "Hexproof" in nevinyrral.keywords
    assert nevinyrral.oracle_text.startswith("Hexproof from artifacts, creatures, and enchantments")


def test_an_opponents_spell_of_the_named_quality_is_refused():
    """CR 702.11d: an enchantment spell against "hexproof from ... enchantments".

    Hyena Umbra is an Aura, so the target is announced at CR 601.2c the same way
    Lightning Bolt's is, and Nevinyrral is a creature, so `Enchant creature`
    (CR 702.5a) has nothing to say about it - the refusal is hexproof's alone.
    """
    scenario = quality_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    nevinyrral = scenario.creature("Nevinyrral, Urborg Tyrant", "bob")

    casting = scenario.cast("Hyena Umbra", username="alice")
    with pytest.raises(ValueError, match="hexproof from enchantments"):
        casting.choose_targets([nevinyrral])


def test_an_opponents_spell_of_another_quality_is_allowed():
    """The defect: a Lightning Bolt the printed card plainly allows.

    An instant is none of artifacts, creatures, or enchantments, so CR 702.11d
    says nothing about it and the Bolt resolves.
    """
    scenario = quality_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    nevinyrral = scenario.creature("Nevinyrral, Urborg Tyrant", "bob")

    scenario.cast_and_resolve(
        "Lightning Bolt",
        *scenario.untapped_sources("Mountain", username="alice"),
        username="alice",
        targets=[nevinyrral],
    )
    assert nevinyrral.damage == 3


def test_its_own_controller_can_target_it_with_the_named_quality():
    """CR 702.11d names "your opponents control" the same way CR 702.11b does,
    so alice's own enchantment spell is free to target her Nevinyrral."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Hyena Umbra"], battlefield=["Nevinyrral, Urborg Tyrant", "Plains"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    nevinyrral = scenario.creature("Nevinyrral, Urborg Tyrant", "alice")

    casting = scenario.cast("Hyena Umbra", username="alice", targets=[nevinyrral])

    assert casting.targets[0].card_id == nevinyrral.id


def test_plain_hexproof_still_refuses_a_spell_of_any_quality():
    """The control: a card whose printed ability really is CR 702.11b's plain
    hexproof still stops an opponent's instant, which "hexproof from
    enchantments" does not."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Striped Riverwinder"])
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    riverwinder = scenario.creature("Striped Riverwinder", "alice")

    casting = scenario.cast("Lightning Bolt", username="bob")
    with pytest.raises(ValueError, match="has hexproof"):
        casting.choose_targets([riverwinder])
