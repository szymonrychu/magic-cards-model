"""Judge scenario: Blood Moon against a creature that is not a land (DDR#966).

"Hydro-Man, Fluid Felon + Blood Moon and Eluge, the Shoreless Sea." The episode
starts from the point it calls uncontroversial and builds up:

- **Blood Moon does not touch Hydro-Man while Hydro-Man is a creature.** "Blood
  Moon literally says it applies to nonbasic lands. So if Hydro-Man is not a
  land, Blood Moon does not affect it, just like Blood Moon's effect doesn't
  apply to Grizzly Bears." That is layer 4 (CR 613.1d) with a selector that
  simply does not match.
- **A basic land is not a nonbasic land** either - the same selector, the other
  way round (CR 205.4b's basic supertype).
- **Setting a land's subtype to a basic land type takes its abilities away**,
  in layer 4 rather than layer 6, and replaces them with the mana ability of
  that type. That is why Blood Moon "is removal as much as it is a type
  change".
- **Hydro-Man's own end-step trigger makes it a land**, and *then* Blood Moon
  applies to it - not by timestamp but by dependency, CR 613.8a: "applying the
  other would change the text or the existence of this effect ... or what it
  applies to". Making Hydro-Man a land changes the set of objects Blood Moon
  applies to, so Blood Moon waits (CR 613.8b) even though it has the earlier
  timestamp.

The engine has a real `LAYER_EFFECTS` row for Blood Moon and a real dependency
system in `machines/layers.py`, so the first three are ordinary tests. The
fourth needs Hydro-Man's *triggered* ability to create a continuous type-changing
effect, which nothing in this engine builds - Hydro-Man has no `LAYER_EFFECTS`
row and `parsed_layer_effects` reads none of its text - so it is `xfail`.

Every CR number in this file was verified with `knowledge_search(q="...",
type="rules")` in the session that wrote it: CR 613.3, CR 613.8, CR 613.8a,
CR 613.8b, CR 613.8c.
"""

import pytest

from magic_cards_model.machines.layers import compute_board, static_effects
from magic_cards_model.models import Zone
from tests.cards import card_state


def permanent(name: str, controller: str = "alice"):
    return card_state(name, zone=Zone.BATTLEFIELD, controller=controller)


def moon_board():
    """Blood Moon, a Hydro-Man that is still a creature, a basic, and a nonbasic."""
    moon = permanent("Blood Moon")
    hydro = permanent("Hydro-Man, Fluid Felon")
    mountain = permanent("Mountain")
    bog = permanent("Bojuka Bog")
    cards = [moon, hydro, mountain, bog]
    return hydro, mountain, bog, compute_board(cards, static_effects(cards))


def test_blood_moon_leaves_a_creature_that_is_not_a_land_alone():
    """DDR#966's first point: "Blood Moon does not affect Hydro-Man at all
    unless Hydro-Man is a land."

    Hydro-Man keeps its card type, both its creature types, its legendary
    supertype, and both of its printed abilities. Nothing about Blood Moon
    reaches a permanent its selector does not pick up.
    """
    hydro, _, _, board = moon_board()
    characteristics = board.of(hydro)

    assert characteristics.is_creature
    assert not characteristics.is_land
    assert set(characteristics.subtypes) == {"Elemental", "Villain"}
    assert len(characteristics.abilities) == 2


def test_blood_moon_leaves_a_basic_mountain_alone_too():
    """ "Nonbasic lands are Mountains" excludes the basics by its own words.

    A basic Mountain keeps its basic supertype and its own reminder-text mana
    ability rather than being rewritten by an effect that was never about it.
    """
    _, mountain, _, board = moon_board()
    characteristics = board.of(mountain)

    assert characteristics.is_basic
    assert characteristics.subtypes == ("Mountain",)


def test_a_nonbasic_land_loses_its_abilities_along_with_its_subtypes():
    """The half of Blood Moon that is removal, not type-changing.

    Bojuka Bog's own "This land enters tapped" and graveyard-exiling trigger
    are gone, and the one ability left is the Mountain's. The episode makes the
    same observation about Hydro-Man once it *is* a land: "that would cause all
    the abilities from the text box to go away and get replaced by the ability
    to tap for the appropriate color of mana."
    """
    _, _, bog, board = moon_board()
    characteristics = board.of(bog)

    assert characteristics.is_land
    assert not characteristics.is_basic  # CR 205.4b: the supertype is not granted
    assert characteristics.subtypes == ("Mountain",)
    assert characteristics.abilities == ("{T}: Add {R}.",)


def test_blood_moon_reaches_a_nonbasic_land_whatever_else_is_on_the_board():
    """The control for the first test: same board, a land instead of a creature.

    Both permanents are under the same Blood Moon in the same computation. Only
    the one that is a nonbasic land is rewritten, which is what makes the
    creature's untouched characteristics a ruling rather than an accident of
    the effect not being registered at all.
    """
    hydro, _, bog, board = moon_board()

    assert board.of(bog).subtypes == ("Mountain",)
    assert board.of(hydro).subtypes == ("Elemental", "Villain")


@pytest.mark.xfail(
    reason=(
        "Hydro-Man's end-step trigger - 'Until your next turn, he becomes a land "
        'and gains "{T}: Add {U}"\' - creates a continuous effect on resolution, '
        "and nothing in this engine builds it: Hydro-Man has no `LAYER_EFFECTS` "
        "row and `parsed_layer_effects` reads none of its shapes. Without the "
        "layer-4 land-making effect there is no CR 613.8a dependency for Blood "
        "Moon to wait on, which is the whole of DDR#966."
    ),
    strict=True,
)
def test_hydro_man_becomes_a_land_and_blood_moon_then_applies_to_it():
    """CR 613.8a/613.8b: Blood Moon depends on Hydro-Man's own effect.

    Once Hydro-Man is a land it is a *nonbasic* land, so Blood Moon's set of
    affected objects changed - it waits and applies afterwards, however early
    its timestamp is. The end state the episode draws: a legendary land
    Mountain that also taps for blue, because Hydro-Man's layer 6 grant lands
    after Blood Moon's layer 4 ability removal.
    """
    hydro = permanent("Hydro-Man, Fluid Felon")
    moon = permanent("Blood Moon")
    cards = [moon, hydro]
    board = compute_board(cards, static_effects([moon, hydro]))
    characteristics = board.of(hydro)

    assert characteristics.is_land
    assert not characteristics.is_creature
    assert characteristics.subtypes == ("Mountain",)
