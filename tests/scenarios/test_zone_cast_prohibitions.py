"""Scenario: statics that forbid casting *from a zone* - Grafdigger's Cage and
Soulless Jailer.

- Grafdigger's Cage: "Players can't cast spells from graveyards or libraries."
- Soulless Jailer: "Players can't cast noncreature spells from graveyards or
  exile."

CR 601.3 is the prohibition and CR 101.2 is why it wins: the permission being
overruled is a real one - flashback (CR 702.34a) is what let the card be cast
from a graveyard at all - and "when a rule or effect allows or directs
something to happen, and another effect states that it can't happen, the
'can't' effect takes precedence."

Both are ordinary battlefield statics (CR 604.1: statics "do something all the
time rather than being activated or triggered"; CR 113.6: "abilities of all
other objects usually function only while that object is on the battlefield"),
whose continuous effect "affects players or the rules of the game" (CR 611.1)
and so writes no layer (CR 613.11).

**Not CR 113.6f.** That rule covers an ability restricting "what zones *that
particular object* can be played or cast from" - flashback's own zone clause,
on the card that has it. The Cage restricts every *other* object, which is why
`zone_cast_prohibition_source` scans the battlefield and takes the spell and
its origin zone as arguments rather than reading anything off the spell's own
text.

"Players" is every player, the Cage's own controller included, which is why
there is no player argument to get wrong.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.casting import PlayAction, PlayPermission, types_being_cast
from magic_cards_model.machines.casting_restrictions import zone_cast_prohibition_source
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import CardState
from tests.cards import card
from tests.scenarios.harness import Scenario


def _board(*, hate: list[str], graveyard: list[str] | None = None) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Bolt"],
            battlefield=["Mountain"] * 3,
            graveyard=graveyard or ["Faithless Looting"],
            library=["Mountain"] * 5,
        )
        .player("bob", battlefield=hate, library=["Mountain"] * 5)
        .build()
    )


# -- Grafdigger's Cage ------------------------------------------------------


def test_the_cage_forbids_a_cast_out_of_a_graveyard():
    scenario = _board(hate=["Grafdigger's Cage"])

    source = zone_cast_prohibition_source(scenario.game, card("Faithless Looting"), Zone.GRAVEYARD)

    assert source == "Grafdigger's Cage"


def test_the_cage_forbids_a_cast_out_of_a_library():
    """The second zone in the same sentence - a cascade or a Bolas's Citadel
    cast reaches the library, and the Cage names it too."""
    scenario = _board(hate=["Grafdigger's Cage"])

    source = zone_cast_prohibition_source(scenario.game, card("Lightning Bolt"), Zone.LIBRARY)

    assert source == "Grafdigger's Cage"


def test_the_cage_leaves_the_hand_alone():
    """The zone list is the whole restriction; an ordinary cast is untouched."""
    scenario = _board(hate=["Grafdigger's Cage"])

    assert zone_cast_prohibition_source(scenario.game, card("Lightning Bolt"), Zone.HAND) is None
    assert zone_cast_prohibition_source(scenario.game, card("Lightning Bolt"), Zone.EXILE) is None


def test_the_cage_catches_its_own_controller_too():
    """ "Players", not "your opponents" - so the same answer with the Cage on
    either side of the board."""
    scenario = _board(hate=["Grafdigger's Cage"])
    mine = (
        Scenario()
        .player("alice", battlefield=["Grafdigger's Cage"], graveyard=["Faithless Looting"])
        .player("bob")
        .build()
    )

    for game in (scenario.game, mine.game):
        assert (
            zone_cast_prohibition_source(game, card("Faithless Looting"), Zone.GRAVEYARD)
            == "Grafdigger's Cage"
        )


def test_an_empty_board_prohibits_nothing():
    scenario = _board(hate=["Mountain"])

    assert (
        zone_cast_prohibition_source(scenario.game, card("Faithless Looting"), Zone.GRAVEYARD)
        is None
    )


# -- Soulless Jailer: the same shape, narrowed twice ------------------------


def test_the_jailer_forbids_a_noncreature_cast_out_of_a_graveyard():
    scenario = _board(hate=["Soulless Jailer"])

    source = zone_cast_prohibition_source(scenario.game, card("Faithless Looting"), Zone.GRAVEYARD)

    assert source == "Soulless Jailer"


def test_the_jailer_forbids_a_noncreature_cast_out_of_exile():
    """Exile is the zone the Cage does not name and the Jailer does - the two
    sentences share a shape, not a zone list."""
    scenario = _board(hate=["Soulless Jailer"])

    source = zone_cast_prohibition_source(scenario.game, card("Lightning Bolt"), Zone.EXILE)

    assert source == "Soulless Jailer"


def test_the_jailer_lets_a_creature_spell_through():
    """ "Noncreature spells" - a reanimated-by-casting creature is the Jailer's
    deliberate blind spot, and the Cage's separate first sentence is what
    covers creatures for the Cage."""
    scenario = _board(hate=["Soulless Jailer"], graveyard=["Grizzly Bears"])

    assert (
        zone_cast_prohibition_source(scenario.game, card("Grizzly Bears"), Zone.GRAVEYARD) is None
    )
    assert zone_cast_prohibition_source(scenario.game, card("Grizzly Bears"), Zone.EXILE) is None


def test_the_jailer_leaves_the_library_alone():
    """The Cage's zone list and the Jailer's differ at both ends."""
    scenario = _board(hate=["Soulless Jailer"])

    assert (
        zone_cast_prohibition_source(scenario.game, card("Faithless Looting"), Zone.LIBRARY) is None
    )


# -- the enforcement, wired into the announcement ---------------------------


def test_flashback_out_of_a_graveyard_is_refused_under_the_cage():
    """CR 601.3's second half, now wired: `why_cannot_cast_restriction` asks
    `zone_cast_prohibition_source` about the zone the card is actually in, so
    the announcement itself is refused - CR 101.2 makes the Cage's "can't"
    beat flashback's "you may"."""
    scenario = _board(hate=["Grafdigger's Cage"])
    scenario.start_at(Step.PRECOMBAT_MAIN)

    with pytest.raises(ValueError, match="Grafdigger's Cage"):
        casting = scenario.cast("Faithless Looting", from_zone=Zone.GRAVEYARD)
        casting.use_keyword("Flashback")


# -- the type filter judged against the *chosen* face (CR 601.3e) -----------
#
# Soulless Jailer's filter is "noncreature", and `_matches_type_filter` read
# it off `Card.types` - which is `Card.front_type_line`, the front half's type
# line. An adventurer card's front half is the creature, so **Stomp, an
# `Instant - Adventure`, was castable out of a graveyard under "Players can't
# cast noncreature spells from graveyards or exile"**, inheriting "is a
# creature spell" from a face nobody was casting.
#
# CR 601.3e is the rule the substitution comes from - "Some rules and effects
# state that an alternative set of characteristics or a subset of
# characteristics are considered to determine if a card or copy of a card is
# legal to cast. These alternative characteristics replace the object's
# characteristics for this determination." - with CR 715.3a the instance for
# an Adventure and CR 709.3a the one for a split half. Read in full off
# `.rules/MagicCompRules.txt` (effective August 7, 2026) with `mise run
# rules:find` in the session that wrote this block, with CR 601.3, CR 101.2
# and CR 611.1.


def _adventurer_in_a_graveyard(name: str) -> tuple[Scenario, CardState]:
    """A real `PlayPermission` letting bob cast `name` out of his own
    graveyard - the same object cascade, suspend and Ugin's own grants build
    (`machines/casting.PlayPermission`), constructed directly here because no
    printing in the pool grants an adventurer card a graveyard cast.

    CR 715.3d's own exile pile cannot stage this: "It can't be cast as an
    Adventure this way", so the Adventure half is only ever reachable from a
    non-hand zone through some *other* effect's permission, which is exactly
    what this builds.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Soulless Jailer"], library=["Mountain"] * 5)
        .player(
            "bob",
            graveyard=[name],
            battlefield=["Mountain", "Mountain", "Island", "Island"],
            library=["Mountain"] * 5,
        )
        .build()
    )
    # Bob's own main phase, so CR 117.1a's timing - the *other* per-face
    # CR 601.3 question, unrelated to this one - leaves the creature half
    # legal. Otherwise every option is refused and the proposal dies on
    # timing, which proves nothing about the Jailer's type filter.
    while scenario.turn.active_player != "bob" or scenario.step is not Step.PRECOMBAT_MAIN:
        scenario.advance()
    buried = scenario.find(name, Zone.GRAVEYARD, "bob")
    scenario.game.play_permissions.append(
        PlayPermission(
            card_id=buried.id,
            player="bob",
            rule="CR 601.3",
            source_name="a graveyard cast grant",
            action=PlayAction.CAST,
            pays_mana_cost=True,
            zone=Zone.GRAVEYARD,
            zone_change_stamp=buried.zone_change_stamp,
        )
    )
    return scenario, buried


def test_the_jailer_forbids_an_adventure_half_out_of_a_graveyard():
    scenario, _buried = _adventurer_in_a_graveyard("Bonecrusher Giant")

    casting = scenario.cast("Bonecrusher Giant", username="bob", from_zone=Zone.GRAVEYARD)
    casting.use_permission()

    with pytest.raises(ValueError, match="Soulless Jailer"):
        casting.cast_as_adventure()


def test_the_jailer_lets_the_creature_half_of_the_same_card_through():
    """ "Noncreature" is the whole filter, and the creature half is a creature
    spell - so the same card, same zone, same Jailer, is allowed. This is
    what makes the chosen face load-bearing rather than the card: a fix that
    refused the whole printing would break this cast.
    """
    scenario, _buried = _adventurer_in_a_graveyard("Bonecrusher Giant")

    casting = scenario.cast("Bonecrusher Giant", username="bob", from_zone=Zone.GRAVEYARD)
    casting.use_permission()

    assert casting.face is None, "no face named is the creature half"
    assert str(casting.base_cost) == "{2}{R}", "the Giant's own cost, not Stomp's"


def test_the_jailer_forbids_another_adventurer_cards_half_too():
    """Generality: Brazen Borrower // Petty Theft, a printing this defect was
    not found on and no decklist here uses.
    """
    scenario, _buried = _adventurer_in_a_graveyard("Brazen Borrower")

    casting = scenario.cast("Brazen Borrower", username="bob", from_zone=Zone.GRAVEYARD)
    casting.use_permission()

    with pytest.raises(ValueError, match="Soulless Jailer"):
        casting.cast_as_adventure()


def test_the_prohibition_reads_the_types_it_is_handed():
    """`zone_cast_prohibition_source` takes the evaluated types rather than
    re-deriving them, because CR 601.3e's substitution belongs to the caller
    that knows which face is being cast - and `machines/casting_restrictions.
    py` must not import `machines/casting.py` (the dependency runs the other
    way). Asked directly here, both ways round, on one printing.
    """
    scenario, _buried = _adventurer_in_a_graveyard("Bonecrusher Giant")
    giant = card("Bonecrusher Giant")

    assert zone_cast_prohibition_source(scenario.game, giant, Zone.GRAVEYARD) is None, (
        "the printing's own front face is a creature (CR 715.4)"
    )
    assert (
        zone_cast_prohibition_source(
            scenario.game,
            giant,
            Zone.GRAVEYARD,
            types=types_being_cast(giant, "Stomp"),
        )
        == "Soulless Jailer"
    ), "CR 715.3a: the Adventure's own characteristics are the ones evaluated"
