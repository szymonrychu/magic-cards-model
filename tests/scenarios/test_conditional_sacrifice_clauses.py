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


# --------------------------------------------------------------------------
# A counted restriction: "you may sacrifice two Islands" / "three other
# nonland permanents" (CR 118.3, CR 118.12, CR 701.21a)
# --------------------------------------------------------------------------
#
# Looked up with `mise run rules:find` in the session that wrote these:
#
# - CR 118.3 - "A player can't pay a cost without having the necessary
#   resources to pay it fully." The sacrifice before "If you do" is a cost
#   (CR 118.12), so one Island short is not a smaller payment: "yes" is not a
#   legal answer at all.
# - CR 701.21a - "A player can't sacrifice something that isn't a permanent,
#   or something that's a permanent they don't control" - an opponent's
#   Islands never count toward the two.

LEVIATHAN = "Leviathan"
TALENT = "Scavenger's Talent"


def _leviathan_upkeep(scenario) -> None:
    scenario.start_at(Step.UNTAP)
    scenario.advance()  # upkeep: "At the beginning of your upkeep" triggers
    scenario.game.put_triggers_on_stack()


def test_leviathan_sacrifices_exactly_the_two_chosen_islands_and_untaps():
    """Leviathan: "At the beginning of your upkeep, you may sacrifice two
    Islands. If you do, untap this creature." Three Islands, two chosen: the
    question asks for exactly two, the third Island stays."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Leviathan", "Island", "Island", "Island"])
        .player("bob")
        .build()
    )
    leviathan = scenario.creature(LEVIATHAN)
    leviathan.tap()
    first, second, third = scenario.untapped_sources("Island", "Island", "Island")
    scenario.will_take_the_may(True, source=LEVIATHAN)
    scenario.will_choose_cards(first, third, source=LEVIATHAN)

    _leviathan_upkeep(scenario)
    scenario.resolve_top()

    assert first.zone is Zone.GRAVEYARD
    assert third.zone is Zone.GRAVEYARD
    assert second.zone is Zone.BATTLEFIELD
    assert not leviathan.tapped
    (choose,) = [q for q in scenario.questions_asked() if q.kind is DecisionKind.CHOOSE_CARDS]
    assert choose.player == "alice"
    assert choose.amount == 2
    assert set(choose.cards) == {first.id, second.id, third.id}
    assert scenario.game.conditional_clause_notices == []


def test_leviathan_one_island_short_cannot_pay_and_stays_tapped():
    """CR 118.3: one Island cannot pay "sacrifice two Islands", so "yes" is
    not a legal answer and nothing is sacrificed."""
    scenario = Scenario().player("alice", battlefield=["Leviathan", "Island"]).player("bob").build()
    leviathan = scenario.creature(LEVIATHAN)
    leviathan.tap()
    island = scenario.find("Island", Zone.BATTLEFIELD, "alice")

    _leviathan_upkeep(scenario)
    scenario.resolve_top()

    (may,) = [q for q in scenario.questions_asked() if q.kind is DecisionKind.MAY]
    assert may.affirmative_is_legal is False
    assert island.zone is Zone.BATTLEFIELD
    assert leviathan.tapped
    assert scenario.game.conditional_clause_notices == []


def test_leviathan_cannot_count_an_opponents_islands():
    """CR 701.21a: a player sacrifices only permanents they control - bob's
    two Islands do not make up alice's second one."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Leviathan", "Island"])
        .player("bob", battlefield=["Island", "Island"])
        .build()
    )
    leviathan = scenario.creature(LEVIATHAN)
    leviathan.tap()

    _leviathan_upkeep(scenario)
    scenario.resolve_top()

    (may,) = [q for q in scenario.questions_asked() if q.kind is DecisionKind.MAY]
    assert may.affirmative_is_legal is False
    assert leviathan.tapped
    assert len([p for p in scenario.game.battlefield if p.name == "Island"]) == 3


def test_leviathan_declining_keeps_both_islands_and_stays_tapped():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Leviathan", "Island", "Island"])
        .player("bob")
        .build()
    )
    leviathan = scenario.creature(LEVIATHAN)
    leviathan.tap()
    scenario.will_take_the_may(False, source=LEVIATHAN)

    _leviathan_upkeep(scenario)
    scenario.resolve_top()

    assert leviathan.tapped
    assert len([p for p in scenario.game.battlefield if p.name == "Island"]) == 2


def _talent_end_step(scenario) -> None:
    talent = scenario.find(TALENT, Zone.BATTLEFIELD, "alice")
    talent.class_level = 3
    scenario.start_at(Step.POSTCOMBAT_MAIN)
    scenario.advance()  # end step: "At the beginning of your end step" triggers
    scenario.game.put_triggers_on_stack()


def test_scavengers_talent_sacrifices_three_other_nonland_permanents_and_returns_a_creature():
    """Scavenger's Talent, level 3: "At the beginning of your end step, you
    may sacrifice three other nonland permanents. If you do, return a
    creature card from your graveyard to the battlefield with a finality
    counter on it." Four candidates, three chosen; the Talent itself and the
    lands are never offered."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[TALENT, "Goblin Guide", "Sol Ring", "Grizzly Bears", "Memnite", "Swamp"],
            graveyard=["Thought-Knot Seer"],
        )
        .player("bob")
        .build()
    )
    talent = scenario.find(TALENT, Zone.BATTLEFIELD, "alice")
    goblin = scenario.creature("Goblin Guide")
    ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears")
    memnite = scenario.creature("Memnite")
    swamp = scenario.find("Swamp", Zone.BATTLEFIELD, "alice")
    seer = scenario.find("Thought-Knot Seer", Zone.GRAVEYARD, "alice")
    scenario.will_take_the_may(True, source=TALENT)
    scenario.will_choose_cards(goblin, ring, bears, source=TALENT)
    scenario.will_choose_cards(seer, source=TALENT)

    _talent_end_step(scenario)
    scenario.resolve_top()

    assert {goblin.zone, ring.zone, bears.zone} == {Zone.GRAVEYARD}
    assert memnite.zone is Zone.BATTLEFIELD
    assert talent.zone is Zone.BATTLEFIELD
    assert swamp.zone is Zone.BATTLEFIELD
    assert seer.zone is Zone.BATTLEFIELD
    assert seer.counters["finality"] == 1
    sacrifice_question = next(
        q for q in scenario.questions_asked() if q.kind is DecisionKind.CHOOSE_CARDS
    )
    assert sacrifice_question.amount == 3
    assert set(sacrifice_question.cards) == {goblin.id, ring.id, bears.id, memnite.id}
    assert scenario.game.conditional_clause_notices == []


def test_scavengers_talent_two_others_cannot_pay_even_counting_itself_and_lands():
    """Two other nonland permanents: the Talent is a third nonland permanent
    but not an *other* one, and the Swamp is not nonland, so CR 118.3 leaves
    no legal "yes"."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[TALENT, "Goblin Guide", "Sol Ring", "Swamp"],
            graveyard=["Thought-Knot Seer"],
        )
        .player("bob")
        .build()
    )
    goblin = scenario.creature("Goblin Guide")
    seer = scenario.find("Thought-Knot Seer", Zone.GRAVEYARD, "alice")

    _talent_end_step(scenario)
    scenario.resolve_top()

    (may,) = [q for q in scenario.questions_asked() if q.kind is DecisionKind.MAY]
    assert may.affirmative_is_legal is False
    assert goblin.zone is Zone.BATTLEFIELD
    assert seer.zone is Zone.GRAVEYARD


def test_scavengers_talent_with_no_creature_card_still_sacrifices_the_three():
    """CR 118.12: "If you do" checks the payment, not what the consequence
    finds - three noncreature permanents are gone even with no creature card
    in the graveyard to return."""
    scenario = (
        Scenario()
        .player("alice", battlefield=[TALENT, "Sol Ring", "Mishra's Bauble", "Pithing Needle"])
        .player("bob")
        .build()
    )
    ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "alice")
    bauble = scenario.find("Mishra's Bauble", Zone.BATTLEFIELD, "alice")
    needle = scenario.find("Pithing Needle", Zone.BATTLEFIELD, "alice")
    scenario.will_take_the_may(True, source=TALENT)

    _talent_end_step(scenario)
    scenario.resolve_top()

    assert {ring.zone, bauble.zone, needle.zone} == {Zone.GRAVEYARD}
    assert not [p for p in scenario.game.battlefield if p.counters["finality"]]
    assert not [q for q in scenario.questions_asked() if "return" in q.prompt]


def test_scavengers_talent_may_return_a_creature_it_just_sacrificed():
    """The sacrifice is paid before the consequence runs (CR 118.12), so a
    creature sacrificed to pay is already a creature card in the graveyard
    when "return a creature card" looks - and it comes back with the
    finality counter."""
    scenario = (
        Scenario()
        .player("alice", battlefield=[TALENT, "Memnite", "Sol Ring", "Mishra's Bauble"])
        .player("bob")
        .build()
    )
    memnite = scenario.creature("Memnite")
    scenario.will_take_the_may(True, source=TALENT)
    scenario.will_choose_cards(
        memnite,
        scenario.find("Sol Ring", Zone.BATTLEFIELD, "alice"),
        scenario.find("Mishra's Bauble", Zone.BATTLEFIELD, "alice"),
        source=TALENT,
    )
    scenario.will_choose_cards(memnite, source=TALENT)

    _talent_end_step(scenario)
    scenario.resolve_top()

    assert memnite.zone is Zone.BATTLEFIELD
    assert memnite.counters["finality"] == 1
