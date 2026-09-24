"""Scenario: statics with two independent clauses over the graveyard and the
library - Grafdigger's Cage and Soulless Jailer.

- Grafdigger's Cage: "Creature cards in graveyards and libraries can't enter
  the battlefield. Players can't cast spells from graveyards or libraries."
- Soulless Jailer: "Permanent cards in graveyards can't enter the
  battlefield. Players can't cast noncreature spells from graveyards or
  exile."

The *cast* half of each is `machines.casting_restrictions.
zone_cast_prohibition_source`, already exhaustively covered by
`test_zone_cast_prohibitions.py`. This file is the *enter-the-battlefield*
half - CR 614.17d's family, `_cant_enter_replacements` in
`machines/replacement.py` - plus one light end-to-end check of the cast half
per card so this task's own file stands on its own.

CR 614.17: "Some effects state that something can't happen. These effects
aren't replacement effects, but follow similar rules." CR 614.17d names this
particular family: "Some 'can't' effects modify how a permanent enters the
battlefield or whether it can enter the battlefield." CR 400.4a's own "it
remains in its previous zone" is what happens when one applies: the object
never leaves the graveyard (or library) at all.

Soulless Jailer's "Permanent cards" clause was, until this task, silently
inert: `_CARD_TYPE_WORDS` had no entry for the word "permanent", so
`_cant_enter_replacements` read `wanted is None` and skipped building the
replacement entirely - a card put onto the battlefield out of a Soulless
Jailer controller's own graveyard sailed through uncontested. The tests below
prove the fix, not just the shape.
"""

from magic_cards_model.machines.casting_restrictions import zone_cast_prohibition_source
from magic_cards_model.models import Zone
from tests.cards import card
from tests.scenarios.harness import Scenario


def _board(*, hate: list[str], graveyard: list[str]) -> Scenario:
    return (
        Scenario()
        .player("alice", battlefield=["Mountain"] * 4, library=["Mountain"] * 5)
        .player("bob", battlefield=hate, graveyard=graveyard, library=["Mountain"] * 5)
        .build()
    )


# -- Grafdigger's Cage --------------------------------------------------


def test_the_cage_stops_a_creature_card_entering_from_a_graveyard():
    scenario = _board(hate=["Grafdigger's Cage"], graveyard=["Grizzly Bears"])
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "bob")

    result = scenario.game.put_onto_battlefield(bears, "bob")

    assert result.zone is Zone.GRAVEYARD, "CR 400.4a: it remains in its previous zone"
    assert scenario.find("Grizzly Bears", Zone.GRAVEYARD, "bob") is bears


def test_the_cage_stops_a_creature_card_entering_from_a_library():
    scenario = _board(hate=["Grafdigger's Cage"], graveyard=[])
    scenario = (
        Scenario()
        .player("alice", battlefield=["Mountain"] * 4, library=["Mountain"] * 5)
        .player(
            "bob",
            battlefield=["Grafdigger's Cage"],
            library=["Grizzly Bears"] + ["Mountain"] * 4,
        )
        .build()
    )
    bears = scenario.find("Grizzly Bears", Zone.LIBRARY, "bob")

    result = scenario.game.put_onto_battlefield(bears, "bob")

    assert result.zone is Zone.LIBRARY


def test_the_cage_leaves_a_noncreature_card_alone():
    """ "Creature cards" is the whole filter - an artifact reanimated some
    other way is untouched by this clause (the Cage's own second sentence
    covers casting, not this one)."""
    scenario = _board(hate=["Grafdigger's Cage"], graveyard=["Prophetic Prism"])
    prism = scenario.find("Prophetic Prism", Zone.GRAVEYARD, "bob")

    result = scenario.game.put_onto_battlefield(prism, "bob")

    assert result.zone is Zone.BATTLEFIELD


def test_the_cage_still_forbids_the_cast_half_too():
    scenario = _board(hate=["Grafdigger's Cage"], graveyard=["Faithless Looting"])

    source = zone_cast_prohibition_source(scenario.game, card("Faithless Looting"), Zone.GRAVEYARD)

    assert source == "Grafdigger's Cage"


# -- Soulless Jailer: the fix ---------------------------------------------


def test_the_jailer_stops_any_permanent_card_entering_from_a_graveyard():
    """This is the clause that was silently broken: "Permanent cards" with no
    entry in `_CARD_TYPE_WORDS` used to make `wanted` come back `None` and the
    whole replacement never got built at all."""
    scenario = _board(hate=["Soulless Jailer"], graveyard=["Prophetic Prism"])
    prism = scenario.find("Prophetic Prism", Zone.GRAVEYARD, "bob")

    result = scenario.game.put_onto_battlefield(prism, "bob")

    assert result.zone is Zone.GRAVEYARD, "the fix: this used to wrongly reach the battlefield"


def test_the_jailer_stops_a_creature_card_too():
    """ "Permanent cards" catches every permanent type, creatures included -
    unlike the Cage's own narrower "Creature cards"."""
    scenario = _board(hate=["Soulless Jailer"], graveyard=["Grizzly Bears"])
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "bob")

    result = scenario.game.put_onto_battlefield(bears, "bob")

    assert result.zone is Zone.GRAVEYARD


def test_the_jailer_leaves_the_library_alone():
    """Soulless Jailer's enter-the-battlefield clause names only "graveyards",
    unlike the Cage's "graveyards and libraries"."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Mountain"] * 4, library=["Mountain"] * 5)
        .player(
            "bob",
            battlefield=["Soulless Jailer"],
            library=["Prophetic Prism"] + ["Mountain"] * 4,
        )
        .build()
    )
    prism = scenario.find("Prophetic Prism", Zone.LIBRARY, "bob")

    result = scenario.game.put_onto_battlefield(prism, "bob")

    assert result.zone is Zone.BATTLEFIELD


def test_the_jailer_still_forbids_the_noncreature_cast_half_too():
    scenario = _board(hate=["Soulless Jailer"], graveyard=["Faithless Looting"])

    source = zone_cast_prohibition_source(scenario.game, card("Faithless Looting"), Zone.GRAVEYARD)

    assert source == "Soulless Jailer"


# -- widened-reader proof: a second and third printing --------------------


def test_kunoros_stops_a_creature_card_entering_from_its_one_named_zone():
    """Kunoros, Hound of Athreos: "Creature cards in graveyards can't enter
    the battlefield." - the Cage's exact shape narrowed to a single zone, on
    a real Modern- and Pioneer-legal printing this defect was never found on
    and that is not in any `magic-cards-model-api/decks/*.txt` list."""
    scenario = _board(hate=["Kunoros, Hound of Athreos"], graveyard=["Grizzly Bears"])
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "bob")

    result = scenario.game.put_onto_battlefield(bears, "bob")

    assert result.zone is Zone.GRAVEYARD


def test_weathered_runestone_reads_its_two_word_nonland_permanent_filter():
    """Weathered Runestone: "Nonland permanent cards in graveyards and
    libraries can't enter the battlefield." - the widened reader's real
    target: a two-word filter (`_CANT_ENTER_RE`'s new optional "non<type>"
    group) that stops an artifact or creature but lets a land through, on a
    printing legal in Modern and Pioneer, not in the decklist pool.
    """
    scenario = _board(hate=["Weathered Runestone"], graveyard=["Prophetic Prism", "Mountain"])
    prism = scenario.find("Prophetic Prism", Zone.GRAVEYARD, "bob")
    mountain = scenario.find("Mountain", Zone.GRAVEYARD, "bob")

    prism_result = scenario.game.put_onto_battlefield(prism, "bob")
    mountain_result = scenario.game.put_onto_battlefield(mountain, "bob")

    assert prism_result.zone is Zone.GRAVEYARD, "an artifact is a nonland permanent"
    assert mountain_result.zone is Zone.BATTLEFIELD, 'a land is excluded by "nonland"'


def test_weathered_runestone_also_reaches_the_library():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Mountain"] * 4, library=["Mountain"] * 5)
        .player(
            "bob",
            battlefield=["Weathered Runestone"],
            library=["Grizzly Bears"] + ["Mountain"] * 4,
        )
        .build()
    )
    bears = scenario.find("Grizzly Bears", Zone.LIBRARY, "bob")

    result = scenario.game.put_onto_battlefield(bears, "bob")

    assert result.zone is Zone.LIBRARY


def test_an_empty_board_forbids_nothing():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Mountain"] * 4, library=["Mountain"] * 5)
        .player(
            "bob",
            battlefield=["Mountain"] * 4,
            graveyard=["Grizzly Bears"],
            library=["Mountain"] * 5,
        )
        .build()
    )
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "bob")

    result = scenario.game.put_onto_battlefield(bears, "bob")

    assert result.zone is Zone.BATTLEFIELD


def test_the_ban_dies_with_the_permanent():
    """CR 604.2/611.3a: the restriction lasts only as long as its source is on
    the battlefield, and is re-read fresh every time - never locked in."""
    scenario = _board(hate=["Soulless Jailer"], graveyard=["Grizzly Bears"])
    (jailer,) = [c for c in scenario.game.battlefield if c.name == "Soulless Jailer"]
    scenario.game.destroy(jailer)
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "bob")

    result = scenario.game.put_onto_battlefield(bears, "bob")

    assert result.zone is Zone.BATTLEFIELD
