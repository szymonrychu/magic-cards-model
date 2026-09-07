"""Scenario: a negated *supertype* in a target restriction (CR 205.4).

`_negated_type` (`machines/targeting.py`) only ever looked its stem up in
`_TYPE_NOUNS` - card types (CR 300.1). "basic" is not a card type, it is a
supertype (CR 205.4a: "the supertypes are basic, legendary, ongoing, snow, and
world" - verified this session, closed at five), so "nonbasic" resolved to
nothing and the whole "target ... nonbasic land ..." phrase failed to parse:
`TargetingProfile.understood` came back False. This is the defect behind the
reported bug - White Orchid Phantom's "destroy up to one target nonbasic
land" went on the stack through `Game._ask_trigger_targets`'s old silent
`return []` (see `test_unparsed_trigger_targets.py` for that half of the fix)
and did nothing, ever.

The fix adds `_SUPERTYPE_NOUNS` alongside `_TYPE_NOUNS` and
`TargetRequirement.required_supertypes`/`excluded_supertypes`, checked in
`_rejects_card` against `Card.supertypes` (CR 205.4c: "any land that doesn't
have this supertype is a nonbasic land, even if it has a basic land type" -
also verified this session).
"""

import pytest

from magic_cards_model.machines.targeting import profile_for_text
from magic_cards_model.models import Type
from magic_cards_model.models.card import Supertype
from magic_cards_model.models.card_state import TargetRef
from tests.cards import card
from tests.scenarios.harness import Scenario

# -- profile_for_text, directly ---------------------------------------------


def test_white_orchid_phantom_now_parses():
    profile = profile_for_text(
        "When this creature enters, destroy up to one target nonbasic land. Its "
        "controller may search their library for a basic land card, put it onto "
        "the battlefield tapped, then shuffle."
    )
    assert profile.understood, "'nonbasic' is a supertype, not an unknown word"
    (requirement,) = profile.requirements
    assert requirement.card_types == frozenset({Type.LAND})
    assert requirement.excluded_supertypes == frozenset({Supertype.BASIC})
    assert requirement.minimum == 0  # "up to one"


def test_boseiju_channels_nonbasic_land_item_also_parses():
    """The same "nonbasic" word, on a different card (Boseiju's Channel ability)."""
    profile = profile_for_text(
        "Destroy target artifact, enchantment, or nonbasic land an opponent "
        "controls. That player may search their library for a land card with a "
        "basic land type, put it onto the battlefield, then shuffle."
    )
    assert profile.understood
    (requirement,) = profile.requirements
    assert Type.LAND in requirement.card_types
    assert requirement.excluded_supertypes == frozenset({Supertype.BASIC})


# -- the reported case, played out in full -----------------------------------


def test_white_orchid_phantom_destroys_the_chosen_nonbasic_land():
    """A nonbasic land is offered, destroyed, and a basic land is fetched tapped."""
    scenario = (
        Scenario()
        .player("alice", hand=["White Orchid Phantom"])
        .player("bob", library=["Mountain"], battlefield=["Arid Mesa"])
        .build()
    )
    mesa = scenario.creature("Arid Mesa", "bob")
    scenario.choose_trigger_targets("White Orchid Phantom", [mesa])
    scenario.put_onto_battlefield("White Orchid Phantom")
    scenario.game.put_triggers_on_stack()
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()

    assert mesa.zone.value == "graveyard"
    (fetched,) = scenario.game.permanents_controlled_by("bob")
    assert fetched.name == "Mountain"
    assert fetched.tapped, "White Orchid Phantom's own addition to the template"


def test_a_basic_land_is_not_offered_as_a_candidate():
    """The candidate list for the decision never contains bob's Mountain."""
    scenario = (
        Scenario()
        .player("alice", hand=["White Orchid Phantom"])
        .player("bob", battlefield=["Mountain", "Arid Mesa"])
        .build()
    )
    mountain = scenario.creature("Mountain", "bob")
    mesa = scenario.creature("Arid Mesa", "bob")

    scenario.put_onto_battlefield("White Orchid Phantom")
    scenario.game.put_triggers_on_stack()

    offered = scenario.game.decisions.asked[-1].targets
    assert TargetRef.to_card(mesa) in offered
    assert TargetRef.to_card(mountain) not in offered, "a basic land is never legal here"


def test_a_basic_land_is_refused_if_named_directly():
    """`why_cannot_target_with_trigger` refuses a basic land by name, not just
    by omission from the candidate list."""
    scenario = (
        Scenario()
        .player("alice", hand=["White Orchid Phantom"])
        .player("bob", battlefield=["Mountain"])
        .build()
    )
    mountain = scenario.creature("Mountain", "bob")
    scenario.put_onto_battlefield("White Orchid Phantom")

    with pytest.raises(ValueError, match="nonbasic"):
        scenario.choose_trigger_targets("White Orchid Phantom", [mountain])


# -- the supertype list itself, closed at five -------------------------------


def test_the_supertype_enum_matches_cr_205_4a():
    """CR 205.4a: "The supertypes are basic, legendary, ongoing, snow, and
    world." Verified with `knowledge_search` this session - closed at five."""
    assert {s.value for s in Supertype} == {"basic", "legendary", "ongoing", "snow", "world"}


def test_arid_mesa_and_mountain_disagree_on_the_basic_supertype():
    """A sanity check straight off the real printings, not off an assumption."""
    assert Supertype.BASIC not in card("Arid Mesa").supertypes
    assert Supertype.BASIC in card("Mountain").supertypes
