"""Judge scenario: what "transform all Humans" can and cannot turn over.

From DDR#31 (a re-shoot, numbered out of sequence) "Blackbloom Rogue +
Moonmist". The episode exists *because the rules changed*: modal double-faced
cards used not to be able to transform, and since the Spider-Man set they can.
Amy's Blackbloom Rogue - a Human on its front face, a land on its back - is
turned over by Moonmist like any other double-faced Human.

The rules the episode walks through:

- **CR 712.3** - "Modal double-faced cards have a Magic card face on each side.
  These faces are usually independent from one another, but they may have an
  ability that allows them to 'transform' or 'convert' on the battlefield." The
  restriction that used to distinguish them is gone; CR 712.2's nonmodal cards
  keep only the *casting* difference.
- **CR 701.27c** - "If a spell or ability instructs a player to transform a
  permanent that isn't represented by a double-faced token or a double-faced
  card, nothing happens." Elite Vanguard and a Clone copying a double-faced
  card both fall here.
- **CR 701.27d / CR 712.10** - "If a spell or ability instructs a player to
  transform a permanent, and the face that permanent would transform into is an
  instant or sorcery face nothing happens." Flamescroll Celebrant // Revel in
  Silence is the episode's example.

`CardState.transform` is the engine's primitive, and it now handles all three.
Moonmist's own "Transform all Humans." is read off its printed text now too;
what still fails closed is the card's *second* sentence - see the `xfail` at
the bottom for exactly which field `models/game.py` lacks.

Every CR number in this file was verified with `knowledge_search(q="...",
type="rules")` in the session that wrote it: CR 701.27c, CR 701.27d, CR 712.2,
CR 712.3, CR 712.10.
"""

import pytest

from magic_cards_model.machines.effects import _parse_mixed_clause, effect_for
from magic_cards_model.models import Zone
from tests.cards import card, card_state
from tests.scenarios.harness import Scenario


def permanent(name: str):
    return card_state(name, zone=Zone.BATTLEFIELD, controller="alice")


def test_a_modal_double_faced_card_really_has_two_faces():
    """The card data the ruling rests on, read off the real printing.

    Blackbloom Rogue is `modal_dfc`: a Human Rogue on the front, a land on the
    back. Both halves matter - Moonmist reaches it because the front face is a
    Human, and it has somewhere to go because the back face exists.
    """
    rogue = card("Blackbloom Rogue")

    assert rogue.layout.value == "modal_dfc"
    assert [face.name for face in rogue.card_faces] == [
        "Blackbloom Rogue",
        "Blackbloom Bog",
    ]
    assert "Human" in rogue.card_faces[0].type_line
    assert rogue.card_faces[1].type_line.startswith("Land")


def test_a_modal_double_faced_permanent_can_be_transformed():
    """DDR#31's ruling under the current rules (CR 712.3).

    This is the whole point of the re-shoot: the old answer was that a modal
    DFC could not transform at all. It can, and the permanent becomes its back
    face.
    """
    rogue = permanent("Blackbloom Rogue")
    assert rogue.name == "Blackbloom Rogue"

    rogue.transform()

    assert rogue.transformed
    assert rogue.name == "Blackbloom Bog"


def test_transforming_a_single_faced_creature_does_nothing():
    """CR 701.27c: "nothing happens".

    Not an error, not a refusal a caller has to catch - the instruction simply
    has no effect, which is what lets Moonmist say "transform all Humans" and
    sweep a board of mixed permanents without caring.
    """
    vanguard = permanent("Grizzly Bears")

    vanguard.transform()

    assert not vanguard.transformed
    assert vanguard.name == "Grizzly Bears"


def test_a_permanent_whose_back_face_is_an_instant_does_not_transform():
    """CR 701.27d, with the episode's own example printing.

    Flamescroll Celebrant // Revel in Silence is a modal DFC whose back face is
    an Instant, so the transform instruction finds nothing to do.
    """
    celebrant = permanent("Flamescroll Celebrant")
    assert card("Flamescroll Celebrant").card_faces[1].type_line == "Instant"

    celebrant.transform()

    assert not celebrant.transformed
    assert celebrant.name == "Flamescroll Celebrant"


def test_a_transformed_permanent_turns_back_over():
    """The refusal is about the face it would turn *into*, not about the card.

    CR 701.27a is "turn it over so that its other face is up", and while a
    Blackbloom Rogue is a Blackbloom Bog the other face is the Human Rogue it
    started as - a land face, not an instant one, so nothing stops it. The
    check has to read `face_it_would_transform_into` rather than the back face
    always, or a permanent could go over but never come back.
    """
    rogue = permanent("Blackbloom Rogue")
    rogue.transform()
    assert rogue.name == "Blackbloom Bog"

    rogue.transform()

    assert not rogue.transformed
    assert rogue.name == "Blackbloom Rogue"


def test_an_adventurer_card_is_not_a_double_faced_card_and_does_not_transform():
    """CR 712.9: "Only permanents represented by double-faced tokens and
    double-faced cards that are not meld cards can transform or convert."

    Bonecrusher Giant // Stomp has two `card_faces` in the Scryfall printing
    the way every multi-face layout does, so "does it have faces" is not the
    question that answers this one. CR 701.27d's own check is - Stomp is an
    Instant face - and it lands on the same "nothing happens".
    """
    giant = permanent("Bonecrusher Giant")
    assert card("Bonecrusher Giant").card_faces[1].type_line == "Instant — Adventure"

    giant.transform()

    assert not giant.transformed
    assert giant.name == "Bonecrusher Giant"


def test_the_transform_all_humans_clause_is_read_and_sweeps_the_battlefield():
    """Moonmist's first sentence, now readable off its own printed text.

    "Transform all Humans." is a board sweep, not a self-reference: every
    permanent whose *computed* subtypes (CR 205.3, read off the up face per CR
    712.8d) include Human is turned over, whoever controls it. CR 701.27a is
    the turning; CR 701.27c is why the sweep is safe to run over everything -
    "If a spell or ability instructs a player to transform a permanent that
    isn't represented by a double-faced token or a double-faced card, nothing
    happens", so the Youthful Knight beside the Rogue is a silent no-op rather
    than an error.
    """
    clause = _parse_mixed_clause("Transform all Humans", for_spell=True)
    assert clause is not None

    scenario = (
        Scenario()
        .player("alice", hand=["Moonmist"], battlefield=["Blackbloom Rogue", "Youthful Knight"])
        .player("bob", battlefield=["Blackbloom Rogue"])
        .build()
    )
    rogues = [
        scenario.creature("Blackbloom Rogue", "alice"),
        scenario.creature("Blackbloom Rogue", "bob"),
    ]
    knight = scenario.creature("Youthful Knight", "alice")

    clause(scenario.game, scenario.find("Moonmist", Zone.HAND, "alice"))

    assert [state.name for state in rogues] == ["Blackbloom Bog", "Blackbloom Bog"], (
        "both players' Humans turn over - 'all Humans' names no controller"
    )
    assert knight.name == "Youthful Knight", "CR 701.27c: a single-faced Human is a no-op"


@pytest.mark.xfail(
    reason=(
        "Moonmist's *second* sentence is what fails closed now, and it is a gap "
        "in `models/game.py`, not in the parser: 'Prevent all combat damage that "
        "would be dealt this turn by creatures other than Werewolves and Wolves' "
        "needs a prevention shield restricted by an *excluded* set of source "
        "subtypes, and `PreventionShield` carries only `source_quality`, a "
        "single quality the source must HAVE, matched by `Game.source_has_quality` "
        "against card types and colors only - never subtypes, and never negated. "
        "The first sentence parses (see the test above); CR 608.2c has no notion "
        "of running half an effect, so `effect_for` still refuses the whole card."
    ),
    strict=True,
)
def test_moonmist_transforms_the_humans_when_it_resolves():
    """The episode's actual play: Amy casts Moonmist, the Rogue turns over."""
    moonmist = card("Moonmist")

    assert effect_for(moonmist.name, moonmist.oracle_text) is not None
