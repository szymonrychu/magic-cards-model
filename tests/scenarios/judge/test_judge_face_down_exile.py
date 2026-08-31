"""Judge scenarios: a card exiled face down has no characteristics.

Sourced from the DDR judge transcripts. Episode covered:

- **DDR#956** - Pyxis of Pandemonium + Ulamog, the Defiler. Lantern of Insight
  reveals Emrakul on top of Amy's library; Nick activates Pyxis and exiles it
  face down. Amy then casts Ulamog, the Defiler, which enters with counters
  equal to the greatest mana value among cards in exile. How many?

Zero from that card. CR 406.3a: "A card exiled face down has no
characteristics". Mana cost is a characteristic, so the face-down Emrakul has
none, and CR 202.3a then gives it a mana value of 0 - even though every player
at the table watched it go there and knows exactly what it is.

The engine models one half of CR 406.3 (a face-down exiled card is not a
face-up one, so an effect that reaches for face-up cards cannot see it) and
none of CR 406.3a (its characteristics are all still readable).

Card text verified with `resolve_cards`; every CR number here was looked up
with `knowledge_search(type="rules")` in this session.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_a_face_down_exiled_card_is_not_a_face_up_one():
    """DDR#956's modelled half: CR 406.3's choosability rule.

    CR 406.3: "Exiled cards are, by default, kept face up and may be examined
    by any player at any time. Cards 'exiled face down' can't be examined by
    any player except when instructions allow it."

    `Game.face_up_cards_in_exile` is the engine's expression of that, and it
    excludes the face-down card - so an effect that says "choose a face-up card
    in exile" cannot be pointed at it.
    """
    scenario = Scenario().player("alice", exile=["Emrakul, the Promised End"]).player("bob").build()
    emrakul = scenario.find("Emrakul, the Promised End", Zone.EXILE, "alice")

    assert [state.name for state in scenario.game.face_up_cards_in_exile()] == [
        "Emrakul, the Promised End"
    ]

    emrakul.face_up = False

    assert emrakul.face_down
    assert scenario.game.face_up_cards_in_exile() == []


@pytest.mark.xfail(
    reason="CR 406.3a is not modelled for exile: CardState only blanks its "
    "characteristics through face_down_characteristics, which is set by "
    "the morph/manifest path (CR 708.2). A card merely turned face down in "
    "exile keeps its printed name, types, and mana value",
    strict=True,
)
def test_a_face_down_exiled_card_has_a_mana_value_of_zero():
    """DDR#956's ruling: no characteristics means no mana cost means mana value
    0.

    CR 406.3a: "A card exiled face down has no characteristics, but the spell
    or ability that exiled it may allow it to be played from exile." CR 202.3a:
    "The mana value of an object with no mana cost is 0, unless that object is
    the back face of a nonmodal double-faced permanent or spell, or it is a
    melded permanent."

    Emrakul, the Promised End is {13} face up. Face down in exile it is 0, and
    Ulamog, the Defiler's "greatest mana value among cards in exile" gets
    nothing from it.

    Not modelled. `CardState.mana_value` returns 0 only when
    `face_down_characteristics` is set, which is CR 708.2's morph/manifest
    machinery for objects on the battlefield or the stack. A card sitting in
    exile with `face_up` cleared keeps everything: name, types, and a mana
    value of 13.
    """
    scenario = Scenario().player("alice", exile=["Emrakul, the Promised End"]).player("bob").build()
    emrakul = scenario.find("Emrakul, the Promised End", Zone.EXILE, "alice")
    emrakul.face_up = False

    assert emrakul.mana_value == 0
    assert emrakul.types == ()


@pytest.mark.xfail(
    reason="Pyxis of Pandemonium's '{T}: Each player exiles the top card of "
    "their library face down.' resolves and exiles nothing, and Ulamog, "
    "the Defiler's 'enters with counters equal to the greatest mana value "
    "among cards in exile' has no enters-replacement entry either",
    strict=True,
)
def test_pyxis_exiles_face_down_and_ulamog_counts_it_as_zero():
    """DDR#956's whole scenario, end to end.

    Pyxis of Pandemonium (verified with `resolve_cards`): "{T}: Each player
    exiles the top card of their library face down." Ulamog, the Defiler:
    "Ulamog enters with a number of +1/+1 counters on it equal to the greatest
    mana value among cards in exile."

    Nick taps Pyxis, exiling Amy's Emrakul face down. Amy casts Ulamog. Because
    of CR 406.3a and CR 202.3a the face-down Emrakul contributes 0, so Ulamog
    enters with no counters at all - and CR 122.1's counter-driven annihilator
    X is 0 with it.

    Two gaps stack up here. Pyxis' activated ability reaches the stack and
    resolves without moving a card, so exile stays empty; and Ulamog's
    enters-with-counters line is a CR 614.1c replacement with no row in
    `machines/replacement.py`'s registry, so the count is never asked for.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Emrakul, the Promised End", "Forest", "Forest"],
            hand=["Ulamog, the Defiler"],
            battlefield=["Forest"] * 10,
        )
        .player("bob", library=["Island"] * 3, battlefield=["Pyxis of Pandemonium"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    pyxis = scenario.find("Pyxis of Pandemonium", Zone.BATTLEFIELD, "bob")

    scenario.pass_priority("alice")
    scenario.activate(pyxis, username="bob")
    scenario.resolve_top()

    exiled = scenario.game.exile
    assert len(exiled) == 2, "each player exiled the top card of their library"
    assert all(state.face_down for state in exiled)

    scenario.pass_priority("bob")
    ulamog = scenario.cast_and_resolve("Ulamog, the Defiler", auto=True, username="alice")

    assert ulamog.counters["+1/+1"] == 0, "a face-down card's mana value is 0"
