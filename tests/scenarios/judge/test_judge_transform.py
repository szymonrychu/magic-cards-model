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

`CardState.transform` is the engine's primitive. It handles the first two and
gets the third wrong, which is the `xfail`. Moonmist's own instruction has no
entry in `machines/effects.py`, so driving the ruling through the card is a
second `xfail`.

Every CR number in this file was verified with `knowledge_search(q="...",
type="rules")` in the session that wrote it: CR 701.27c, CR 701.27d, CR 712.2,
CR 712.3, CR 712.10.
"""

import pytest

from magic_cards_model.machines.effects import effect_for
from magic_cards_model.models import Zone
from tests.cards import card, card_state


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


@pytest.mark.xfail(
    reason=(
        "CR 701.27d / CR 712.10: a permanent whose back face is an instant or "
        "sorcery face does not transform - 'nothing happens'. `CardState."
        "transform` checks only that the card has two faces, so Flamescroll "
        "Celebrant turns into Revel in Silence, an Instant sitting on the "
        "battlefield."
    ),
    strict=True,
)
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


@pytest.mark.xfail(
    reason=(
        "Moonmist's 'Transform all Humans.' has no entry in "
        "`machines/effects.py` and no generalised parse, so `effect_for` "
        "returns None and the spell resolves doing nothing - the ruling cannot "
        "be driven through the card that prompted it."
    ),
    strict=True,
)
def test_moonmist_transforms_the_humans_when_it_resolves():
    """The episode's actual play: Amy casts Moonmist, the Rogue turns over."""
    moonmist = card("Moonmist")

    assert effect_for(moonmist.name, moonmist.oracle_text) is not None
