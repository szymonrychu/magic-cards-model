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
from magic_cards_model.machines.casting_restrictions import zone_cast_prohibition_source
from magic_cards_model.models import Zone
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


# -- the enforcement that is not this task's file ---------------------------


@pytest.mark.xfail(
    strict=True,
    reason=(
        "the prohibition is read here but has no call site: "
        "`machines/casting.py::why_cannot_cast_restriction` is what refuses a "
        "cast at CR 601.3, and it takes no origin zone, so wiring "
        "`zone_cast_prohibition_source` into it belongs to the task that owns "
        "machines/casting.py"
    ),
)
def test_flashback_out_of_a_graveyard_is_refused_under_the_cage():
    scenario = _board(hate=["Grafdigger's Cage"])
    scenario.start_at(Step.PRECOMBAT_MAIN)

    with pytest.raises(ValueError, match="Grafdigger's Cage"):
        casting = scenario.cast("Faithless Looting", from_zone=Zone.GRAVEYARD)
        casting.use_keyword("Flashback")
