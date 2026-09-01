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

The engine models both halves of CR 406.3 now: a face-down exiled card is not a
face-up one, so an effect that reaches for face-up cards cannot see it
(`Game.face_up_cards_in_exile`), and it has no characteristics either
(`CardState.has_no_characteristics`). The one departure is a card in a pile
that grants permission to play it - a foretold or plotted card - which stays
readable, because this engine does not yet turn such a card face up at
announcement the way CR 406.3a's second sentence and CR 601.3f do. Driving the
whole DDR#956 scenario through Pyxis and Ulamog is a separate `xfail`.

Card text verified with `resolve_cards`; every CR number here was looked up
with `knowledge_search(type="rules")` in this session.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.casting import MarkedExile
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

    Modelled by `CardState.has_no_characteristics`, which every characteristic
    property on `CardState` consults: a card in exile with `face_up` cleared
    has no name, no types, no colors, no text and no mana cost, so CR 202.3a
    reads its mana value as 0 rather than the printed 13. Distinct from
    CR 708.2's morph/manifest set (`face_down_characteristics`), which
    *replaces* the printing with a listed 2/2 for a face-down spell or
    permanent; a card in exile is neither, so nothing is listed for it.
    """
    scenario = Scenario().player("alice", exile=["Emrakul, the Promised End"]).player("bob").build()
    emrakul = scenario.find("Emrakul, the Promised End", Zone.EXILE, "alice")
    emrakul.face_up = False

    assert emrakul.mana_value == 0
    assert emrakul.types == ()


def _ulamog_board(exiled_face_down: bool):
    """Amy's side of DDR#956, with the exile staged by hand.

    Ulamog, the Defiler is {10}, so ten lands; bob's library is basics, whose
    mana value is 0 (CR 202.3a - no mana cost), so whatever the cast trigger
    reaches for cannot raise the greatest mana value in exile above Emrakul's.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            exile=["Emrakul, the Promised End"],
            hand=["Ulamog, the Defiler"],
            battlefield=["Forest"] * 10,
        )
        .player("bob", library=["Forest"] * 6)
        .build()
    )
    if exiled_face_down:
        scenario.find("Emrakul, the Promised End", Zone.EXILE, "alice").face_up = False
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_ulamog_counts_a_face_up_exiled_card_at_its_printed_mana_value():
    """The control for the ruling below: face **up**, Emrakul is {13}.

    CR 614.1c: "[This permanent] enters with . . ." is a replacement effect,
    and CR 614.12 lets it come from the permanent itself. The count is an
    expression rather than a number, so it is worked out against the game as
    Ulamog enters. Asserted against Emrakul's printed cost, not against a
    value read back off the same code path.
    """
    scenario = _ulamog_board(exiled_face_down=False)
    emrakul = scenario.find("Emrakul, the Promised End", Zone.EXILE, "alice")
    assert emrakul.card.mana_cost == "{13}"

    scenario.cast_and_resolve("Ulamog, the Defiler", auto=True, username="alice")
    # Ulamog's own "when you cast this spell" trigger (CR 603.2) went on the
    # stack above the spell and resolved first; the spell itself is still
    # waiting under it.
    while scenario.game.stack:
        scenario.resolve_top()
    ulamog = scenario.creature("Ulamog, the Defiler", "alice")

    assert ulamog.counters["+1/+1"] == 13


def test_ulamog_counts_a_face_down_exiled_card_as_zero():
    """DDR#956's ruling itself, with the exile staged rather than made by Pyxis.

    CR 406.3a: "A card exiled face down has no characteristics"; CR 202.3a:
    "The mana value of an object with no mana cost is 0". So the greatest mana
    value among cards in exile is 0, Ulamog enters with no counters, and
    CR 122.1's counter-driven annihilator X is 0 with it.
    """
    scenario = _ulamog_board(exiled_face_down=True)

    scenario.cast_and_resolve("Ulamog, the Defiler", auto=True, username="alice")
    # Ulamog's own "when you cast this spell" trigger (CR 603.2) went on the
    # stack above the spell and resolved first; the spell itself is still
    # waiting under it.
    while scenario.game.stack:
        scenario.resolve_top()
    ulamog = scenario.creature("Ulamog, the Defiler", "alice")

    assert ulamog.counters["+1/+1"] == 0


@pytest.mark.xfail(
    reason="Pyxis of Pandemonium's '{T}: Each player exiles the top card of "
    "their library face down.' resolves and exiles nothing: ACTIVATED_EFFECTS "
    "in machines/effects.py has no entry for the card and effect_for returns "
    "None, so exile stays empty. Ulamog's own half now works - see the two "
    "tests above, which stage the same exile by hand and get 13 and 0.",
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


def test_the_whole_characteristic_set_goes_not_just_the_mana_value():
    """CR 406.3a says "no characteristics", and means all of them.

    Name, types, subtypes, supertypes, colors, text, mana cost, power and
    toughness are all characteristics (CR 109.3), so a face-down Emrakul in
    exile answers with nothing for every one of them - which is what stops an
    effect that reaches for "each legendary card in exile", "each colorless
    card in exile" or "the greatest power among cards in exile" finding it
    either.
    """
    scenario = Scenario().player("alice", exile=["Emrakul, the Promised End"]).player("bob").build()
    emrakul = scenario.find("Emrakul, the Promised End", Zone.EXILE, "alice")
    emrakul.face_up = False

    assert emrakul.name == ""
    assert emrakul.types == ()
    assert emrakul.subtypes == ()
    assert emrakul.supertypes == ()
    assert emrakul.colors == ()
    assert emrakul.keywords == ()
    assert emrakul.oracle_text == ""
    assert emrakul.mana_cost is None
    assert (emrakul.power, emrakul.toughness) == (None, None)
    assert not emrakul.is_creature


def test_turning_it_back_face_up_gives_everything_back():
    """CR 406.3a's own second sentence, and CR 400.6: the blanking is a fact
    about the card being face down, not a change written into it. Nothing is
    lost - `CardState.card` is still the printing throughout."""
    scenario = Scenario().player("alice", exile=["Emrakul, the Promised End"]).player("bob").build()
    emrakul = scenario.find("Emrakul, the Promised End", Zone.EXILE, "alice")

    emrakul.face_up = False
    assert emrakul.mana_value == 0

    emrakul.face_up = True

    assert emrakul.name == "Emrakul, the Promised End"
    assert emrakul.mana_value == 13


def test_a_card_in_a_pile_that_may_be_played_is_still_readable():
    """The engine's documented departure from CR 406.3a, stated as a test.

    CR 601.3f: "Some effects allow a player to cast a spell with certain
    qualities from among face-down cards in exile. A player may begin to cast
    such a spell only if they can look at the face-down card in exile", and
    CR 406.3a then turns that card face up before its controller announces
    they are playing it. This engine does not turn it face up at announcement
    (that is a `machines/casting.py` change), so a card in a pile that grants
    permission to play it - foretell's, CR 702.143c - keeps its characteristics
    readable the whole time it sits there. `CardState.has_no_characteristics`
    is scoped to a card with no `exile_annotation` for exactly that reason.
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Lupine Harbingers"], battlefield=["Forest"] * 3)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    harbingers = scenario.find("Lupine Harbingers", Zone.HAND, "alice")
    action = MarkedExile.foretell(scenario.game, harbingers, "alice")
    forests = scenario.untapped_sources("Forest", "Forest", username="alice")
    scenario.pay_with(action.begin_paying(), *forests)
    action.take()

    foretold = scenario.find("Lupine Harbingers", Zone.EXILE, "alice")

    assert foretold.face_down, "CR 702.143a exiles it face down"
    assert foretold.exile_annotation is not None
    assert not foretold.has_no_characteristics
    assert foretold.name == "Lupine Harbingers"
