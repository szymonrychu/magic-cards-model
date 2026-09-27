"""Invasion of Amonkhet // Lazotep Convert: "You may have this creature enter
as a copy of any creature card in a graveyard, except it's a 4/4 black Zombie
in addition to its other colors and types."

This is the identical "enter as a copy ... except ..." shape
`test_echoing_deeps_copy_exception.py` already documents (CR 614.1c,
CR 707.9b) - the same `machines/replacement._parse_copy_exception` and
`machines/layers._become_a_copy_builder` - with one addition that shape had
no reader for: the exception tail says "its other **colors** and types",
never printed on Echoing Deeps (a Cave, no colour) or Superior Spider-Man (a
Spider Human Hero, no colour). Before this session, `_COPY_EXCEPT_PT_AND_
TYPES` only matched a tail ending "in addition to its other **types**" -
Lazotep Convert's own "colors and types" fell through the whole regex,
`_parse_copy_exception` returned `None` for a tail that was genuinely there,
and `copy_exception_unparsed` recorded it as unreadable (a `notice`), the
same "fail closed, loudly" distinction that file's own docstring explains.

`CopyException` gained an `added_colors` field and `_become_a_copy_builder`
now adds them on top of the copied object's own colours (CR 105.3: "in
addition" is an explicit retaining form for colour, the identical shape CR
205.1b already gives types/subtypes/supertypes) - Lazotep Convert copying a
green Grizzly Bears keeps green and gains black, exactly the way it keeps
"Bear" and gains "Zombie".

No other current Modern/Pioneer/Standard-legal printing combines "enter as a
copy of any creature card in a graveyard" with a "colors and types" tail (a
Scryfall search this session found only Lazotep Convert), so this file also
checks the underlying `_COPY_EXCEPT_PT_AND_TYPES`/`added_colors` machinery
directly against the real "colors and types" retaining-value sentence at
the unit level - the identical grammar 20 other real printings share
(Liliana, Death's Majesty; Grave Betrayal; Ratadrabik of Urborg's own token
copy among them), proving the fix reads the *template*, not a Lazotep-only
regex.

CR numbers verified this session with `mise run rules:find`:

- **CR 707.9b** - "Some copy effects modify a characteristic as part of the
  copying process. The final set of values for that characteristic becomes
  part of the copiable values of the copy."
- **CR 105.3** - "If an effect gives an object a new color, the new color
  replaces all previous colors the object had (unless the effect said the
  object became that color 'in addition' to its other colors)."
- **CR 310.12b** / **CR 115.4** / **CR 310.6** - a Siege's own defeat
  trigger; damage to a battle removes defense counters.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.replacement import _parse_copy_exception
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Color, Type
from tests.scenarios.harness import Scenario


def test_the_colors_and_types_tail_is_read_as_a_template():
    """The exact real sentence, off the card's own printing: read as a
    colour, a power/toughness, and a subtype, not name-matched to Lazotep
    Convert in any way - `_parse_copy_exception` never sees a card name."""
    exception = _parse_copy_exception(
        "it's a 4/4 black Zombie in addition to its other colors and types"
    )
    assert exception is not None
    assert exception.power == 4
    assert exception.toughness == 4
    assert exception.added_colors == (Color.BLACK,)
    assert exception.added_subtypes == ("Zombie",)
    assert exception.added_types == ()


def test_lazotep_convert_copies_a_graveyard_creature_and_gains_black_and_zombie():
    """The reported card, played for real: defeats Invasion of Amonkhet,
    casts it transformed, and lets Lazotep Convert enter as a copy of a
    green Grizzly Bears in alice's graveyard - CR 707.2's copy keeps green
    and "Bear"; CR 707.9b's exception adds black (CR 105.3's "in addition")
    and Zombie (CR 205.1b) and sets the printed 4/4."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Invasion of Amonkhet", "Lightning Bolt", "Lightning Bolt"],
            battlefield=["Mountain", "Mountain"],
            library=["Mountain", "Mountain", "Mountain", "Mountain"],
            graveyard=["Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    siege = scenario.put_onto_battlefield("Invasion of Amonkhet", "alice")
    # "each player mills three cards, then each opponent discards a card and
    # you draw a card" - bob's hand is empty, so there is nothing for him to
    # discard and no decision to answer.
    scenario.pass_until_resolved()  # the Siege's own enters trigger

    mountains = scenario.untapped_sources("Mountain", "Mountain", username="alice")
    scenario.cast_and_resolve("Lightning Bolt", mountains[0], username="alice", targets=[siege])
    scenario.cast_and_resolve("Lightning Bolt", mountains[1], username="alice", targets=[siege])
    scenario.game.check_state_based_actions()
    assert siege.counter_count("defense") == 0
    scenario.will_take_the_may(True, username="alice")
    scenario.pass_until_resolved()  # CR 310.12b's defeat trigger: exile, then cast
    scenario.pass_until_resolved()  # the transformed spell resolves and enters,
    # accepting the "you may have this creature enter as a copy" offer against
    # the only candidate in any graveyard.

    assert siege.zone is Zone.BATTLEFIELD
    assert siege.transformed
    characteristics = scenario.game.characteristics_of(siege)
    assert characteristics.name == "Grizzly Bears"
    assert characteristics.power == 4
    assert characteristics.toughness == 4
    assert Color.GREEN in characteristics.colors  # CR 707.2's own copied colour
    assert Color.BLACK in characteristics.colors  # CR 105.3's "in addition"
    assert "Bear" in characteristics.subtypes  # CR 205.1b's retaining form
    assert "Zombie" in characteristics.subtypes
    assert Type.CREATURE in characteristics.types
