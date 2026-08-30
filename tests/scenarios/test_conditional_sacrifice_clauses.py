""" "You may sacrifice `<restriction>`. If you do, `<consequence>`." (CR
118.12), read off a card's own printed text with no per-card table row -
`_parse_conditional_sacrifice_clause` in `machines/effects.py`.

Two real cards carry this shape in the fixture pool, each covering a
different half of it:

- **Disciple of Freyalise**: "When this creature enters, you may sacrifice
  another creature. If you do, you gain X life and draw X cards, where X is
  that creature's power." - a real choice of *which* permanent to sacrifice,
  and a magnitude ("X") threaded from the sacrificed creature's power into
  the consequence.
- **Sanctum of Ugin**: "Whenever you cast a colorless spell with mana value 7
  or greater, you may sacrifice this land. If you do, search your library for
  a colorless creature card, reveal it, put it into your hand, then shuffle."
  - no choice of *which* permanent (there is only ever one - itself), and a
  plain mandatory search as the consequence, mandatory because CR 118.12's
  own "you may" has already gated it once.

Before this file, both cards resolved doing nothing at all, with nothing
anywhere recording that a choice had gone unoffered - the same silent gap
`test_imprint.py` documents for Ugin's Labyrinth.

Every CR number below was looked up with `knowledge_search(q="...",
type="rules")` in the session that wrote this file, and CR 118.12's own text
(the search excerpt truncates around 180 characters) was then read in full
from the local Comprehensive Rules mirror, one revision behind live but with
this number already confirmed live:

- **CR 118.12** - "Some spells, activated abilities, and triggered abilities
  read ... '[A player] may [do something]. If [that player] [does, doesn't,
  or can't], [effect].' The action [do something] is a cost, paid when the
  spell or ability resolves. The 'If [a player] [does, doesn't, or can't]'
  clause checks whether the player chose to pay an optional cost or started
  to pay a mandatory cost, **regardless of what events actually occurred**."
  This is why the consequence runs whenever the player says yes, with no
  second check on the board afterward - CR 701.21a's sacrifice has no
  failure mode for a permanent the player controls, so there is nothing for
  a second check to ever catch anyway, but the rule itself does not ask one.
- **CR 608.2d** - "If an effect ... offers any choices ... the player
  announces these while applying the effect. The player can't choose an
  option that's illegal or impossible" - the reason a "you may sacrifice
  another creature" with no other creature on the battlefield is never even
  offered, the same shape `may_pay_life` (CR 119.4) and `_parse_imprint_
  clause` already use for their own impossible options.
- **CR 608.2i** - a look-back effect uses information as it existed
  immediately before the event that changed it - the sacrificed creature's
  power is read before `Game.sacrifice` moves it to the graveyard, the same
  snapshot `_parse_anaphoric_clause_pair` already takes for Solitude's "its
  power".
- **CR 701.21a** - "To sacrifice a permanent, its controller moves it from
  the battlefield directly to its owner's graveyard" - `Game.sacrifice`.
- **CR 107.1b** - "You can't ... gain negative life" - a value expression
  reading a negative last-known power floors at zero.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import DecisionKind
from magic_cards_model.models import Zone

from .harness import Scenario

#: `AbilityOnStack.source_name` for the ETB trigger is `CardState.name`
#: (`machines/triggers.py`'s `triggers_for`), which since the CR 201.1 name
#: fix is the up face's own name alone - "Disciple of Freyalise", not
#: Scryfall's combined "Front // Back" string - because CR 712.8a/712.8d
#: give a double-faced object only the characteristics of whichever face is
#: up. Every `Decision.source` this creature's ETB trigger asks carries this
#: face name, so every scripted answer about *that* trigger must match it.
DISCIPLE = "Disciple of Freyalise"

#: Discovered while writing the CR 118.12 wave, and out of scope for it:
#: `machines/replacement.py`'s generic "As this land enters, you may pay N
#: life. If you don't, it enters tapped" compiler still labels its `Decision`
#: with `card_state.card.name` - Scryfall's raw, un-fixed combined name -
#: rather than `CardState.name`, so it reads *both* faces of a modal
#: double-faced card's printed text and offers Garden of Freyalise's "pay 3
#: life" replacement even off Disciple of Freyalise's own creature-face ETB.
#: That mismatch is also why this decision has to be scripted under the
#: combined name, not `DISCIPLE` above, even though both questions come off
#: the same physical card: one caller was fixed to the face-aware name, the
#: other was not. Scripted closed (declining it, so nothing about it touches
#: life or tapped-state) rather than asserted on - a real, separate defect
#: this wave did not introduce and does not fix.
_DISCIPLE_COMBINED_CARD_NAME = "Disciple of Freyalise // Garden of Freyalise"


def _decline_the_unrelated_land_face_replacement(scenario: Scenario) -> None:
    scenario.will_pay_the_life(False, source=_DISCIPLE_COMBINED_CARD_NAME)


# --------------------------------------------------------------------------
# Disciple of Freyalise: a real choice of *which* permanent, plus magnitude
# --------------------------------------------------------------------------


def test_taking_the_sacrifice_gains_life_and_draws_cards_equal_to_its_power():
    """Taking the "you may": Grizzly Bears (2/2) is sacrificed, and X = 2
    threads into both halves of the consequence, in the order printed.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Disciple of Freyalise"],
            battlefield=["Grizzly Bears"],
            library=["Grizzly Bears", "Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    bears = scenario.creature("Grizzly Bears")
    _decline_the_unrelated_land_face_replacement(scenario)
    scenario.will_take_the_may(True, source=DISCIPLE)
    scenario.will_discard(bears, username="alice")

    scenario.put_onto_battlefield("Disciple of Freyalise", "alice")
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()

    assert bears.zone is Zone.GRAVEYARD
    assert bears not in scenario.game.battlefield
    assert alice.life == 22
    assert len(alice.library) == 0, "drew both Grizzly Bears off the top"


def test_declining_the_sacrifice_leaves_the_board_and_life_total_untouched():
    """Declining is legal (CR 608.2d): nothing is sacrificed, no life, no draw."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Disciple of Freyalise"],
            battlefield=["Grizzly Bears"],
            library=["Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    bears = scenario.creature("Grizzly Bears")
    _decline_the_unrelated_land_face_replacement(scenario)
    scenario.will_take_the_may(False, source=DISCIPLE)

    scenario.put_onto_battlefield("Disciple of Freyalise", "alice")
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()

    assert bears.zone is Zone.BATTLEFIELD
    assert alice.life == 20
    assert len(alice.library) == 1


def test_no_other_creature_makes_the_choice_illegal_not_merely_declined():
    """Disciple of Freyalise itself is the only creature - "another creature"
    has no legal candidate, so CR 608.2d makes "yes" impossible, not just
    unappealing. The question is still put (so a scenario can tell "nothing
    to decide" from "never asked"), and nobody answering it defaults to "no"
    rather than raising.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Disciple of Freyalise"], battlefield=[], library=["Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    _decline_the_unrelated_land_face_replacement(scenario)

    disciple = scenario.put_onto_battlefield("Disciple of Freyalise", "alice")
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()

    asked = [q for q in scenario.questions_asked() if q.kind is DecisionKind.MAY]
    assert len(asked) == 1
    assert asked[0].affirmative_is_legal is False
    assert disciple.zone is Zone.BATTLEFIELD
    assert alice.life == 20
    assert len(alice.library) == 1


def test_the_sacrifice_defaults_to_taking_it_unscripted():
    """No answer queued: `default_answer` takes `MAY`'s affirmative branch
    whenever it is legal, the same default every other "you may" trigger
    uses - and the `CHOOSE_CARDS` question over one candidate defaults to
    that one candidate.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Disciple of Freyalise"],
            battlefield=["Grizzly Bears"],
            library=[],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    bears = scenario.creature("Grizzly Bears")
    _decline_the_unrelated_land_face_replacement(scenario)

    scenario.put_onto_battlefield("Disciple of Freyalise", "alice")
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()

    assert bears.zone is Zone.GRAVEYARD
    assert alice.life == 22


# --------------------------------------------------------------------------
# Sanctum of Ugin: "this land" - no choice of which, a mandatory search
# --------------------------------------------------------------------------


def test_taking_the_sacrifice_finds_a_colorless_creature_card():
    """Taking the "you may" after casting a colorless spell with mana value 7
    or greater (Devourer of Destiny): Sanctum of Ugin is sacrificed and the
    search finds Thought-Knot Seer - colorless, a creature - off the library.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Devourer of Destiny"],
            battlefield=["Sanctum of Ugin"] + ["Wastes"] * 7,
            library=["Thought-Knot Seer", "Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    sanctum = scenario.find("Sanctum of Ugin", Zone.BATTLEFIELD, "alice")
    scenario.will_take_the_may(True, source="Sanctum of Ugin")

    scenario.cast_onto_stack("Devourer of Destiny", *scenario.untapped_sources(*(["Wastes"] * 7)))
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()

    assert sanctum.zone is Zone.GRAVEYARD
    assert sanctum not in scenario.game.battlefield
    found = [state for state in alice.hand if state.name == "Thought-Knot Seer"]
    assert len(found) == 1
    assert all(state.name != "Thought-Knot Seer" for state in alice.library)
    assert any(state.name == "Grizzly Bears" for state in alice.library), "the miss stays put"


def test_declining_the_sacrifice_leaves_the_land_and_library_untouched():
    """Declining is legal (CR 608.2d): the land stays, the library is
    untouched, nothing is searched at all.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Devourer of Destiny"],
            battlefield=["Sanctum of Ugin"] + ["Wastes"] * 7,
            library=["Thought-Knot Seer"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    sanctum = scenario.find("Sanctum of Ugin", Zone.BATTLEFIELD, "alice")
    scenario.will_take_the_may(False, source="Sanctum of Ugin")

    scenario.cast_onto_stack("Devourer of Destiny", *scenario.untapped_sources(*(["Wastes"] * 7)))
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()

    assert sanctum.zone is Zone.BATTLEFIELD
    assert len(alice.library) == 1
    assert all(state.name != "Thought-Knot Seer" for state in alice.hand)
