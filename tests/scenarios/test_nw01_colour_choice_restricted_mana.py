"""NW01-F3: a colour-choice "Add ..." instruction followed by CR 106.6's
"Spend this mana only to <restriction>." sentence, on any ability that adds
mana - a loyalty ability included.

Rules looked up this session (`mise run rules:find`):

- **CR 106.6** - "Some spells or abilities that produce mana restrict how that
  mana can be spent ..." The tag rides on the mana, not on its source.
- **CR 605.1a** - an activated ability is a mana ability only if "it's not a
  loyalty ability", so Narset's `+1` goes on the stack and adds its mana as it
  resolves (CR 606.3 for when it may be activated at all).
- **CR 608.2d** - the colour is a choice the effect offers, announced "while
  applying the effect", i.e. as the ability resolves.
- **CR 105.1 / 106.1a** - "any color" is one of the five colours.
- **CR 109.2b** - "a noncreature spell" is a spell on the stack matching that
  description.

Narset of the Ancient Way's `+1` ("You gain 2 life. Add {U}, {R}, or {W}.
Spend this mana only to cast a noncreature spell.") is the reported card: its
three sentences were read by nothing, because the restriction sentence was its
own clause and only the any-combination instruction knew how to take it.

Off-template proof found by a pool scan of every Modern/Pioneer/Standard card
whose text prints "Add <colour choice>. Spend this mana only ...":

- **Tournament Grounds** - the same listed-colour choice (`{R}, {W}, or {B}`),
  on a `{T}` mana ability (CR 605.3b, no stack) and with a subtype-list
  restriction ("a Knight or Equipment spell").
- **Ancient Ziggurat** - "one mana of any color", the other colour-choice
  wording, with a card-type restriction ("a creature spell").
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import DecisionKind
from magic_cards_model.machines.effects import activated_effect_for
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Color
from magic_cards_model.support import card_support
from tests.cards import card
from tests.scenarios.harness import Scenario

NARSET = "Narset of the Ancient Way"
NARSET_RESTRICTION = "Spend this mana only to cast a noncreature spell."


def _narset_board(*hand: str) -> Scenario:
    scenario = (
        Scenario().player("alice", hand=list(hand), battlefield=[NARSET]).player("bob").build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _activate_narset_plus_one(scenario: Scenario, color: Color) -> None:
    scenario.will_choose(color.value, source=NARSET)
    narset = scenario.find(NARSET, Zone.BATTLEFIELD)
    scenario.activate(narset, index=0)
    scenario.pass_until_resolved()


def _restrictions(scenario: Scenario) -> list[str]:
    return [entry.restriction.text for entry in scenario.player("alice").mana_pool.restricted]


# --------------------------------------------------------------------------
# Narset of the Ancient Way (the reported card)
# --------------------------------------------------------------------------


def test_narset_plus_one_gains_life_and_adds_the_chosen_colour_restricted():
    scenario = _narset_board()
    alice = scenario.player("alice")
    life_before = alice.life

    _activate_narset_plus_one(scenario, Color.RED)

    assert alice.life == life_before + 2
    assert alice.mana_pool.floating == {Color.RED: 1}
    assert _restrictions(scenario) == [NARSET_RESTRICTION]
    narset = scenario.find(NARSET, Zone.BATTLEFIELD)
    assert narset.counters.counts.get("loyalty") == 5


def test_narset_plus_one_offers_exactly_blue_red_and_white():
    scenario = _narset_board()

    _activate_narset_plus_one(scenario, Color.WHITE)

    colour_questions = [
        decision
        for decision in scenario.questions_asked()
        if decision.kind is DecisionKind.CHOOSE_A_QUALITY and decision.source == NARSET
    ]
    assert len(colour_questions) == 1
    assert set(colour_questions[0].options) == {"U", "R", "W"}
    assert scenario.player("alice").mana_pool.floating == {Color.WHITE: 1}


def test_narset_mana_refuses_a_creature_spell_in_the_engines_words():
    scenario = _narset_board("Raging Goblin")
    _activate_narset_plus_one(scenario, Color.RED)

    casting = scenario.cast("Raging Goblin", "alice")
    with pytest.raises(ValueError, match="Spend this mana only to cast a noncreature spell"):
        casting.begin_paying().pay()

    casting.cancel()  # CR 601.6
    assert scenario.find("Raging Goblin", Zone.HAND).zone is Zone.HAND
    assert scenario.player("alice").mana_pool.floating == {Color.RED: 1}


def test_narset_mana_pays_for_a_noncreature_spell():
    scenario = _narset_board("Opt")
    _activate_narset_plus_one(scenario, Color.BLUE)

    scenario.cast("Opt", "alice").begin_paying().pay()

    assert scenario.player("alice").mana_pool.floating == {}


def test_narset_is_handled_by_the_support_oracle():
    support = card_support(card(NARSET))

    plus_one = [clause for clause in support.clauses if clause.text.startswith("+1:")]
    assert [clause.status for clause in plus_one] == ["handled"]
    assert support.status == "handled"


# --------------------------------------------------------------------------
# Tournament Grounds - the listed-colour choice on a {T} mana ability
# --------------------------------------------------------------------------


def _tournament_grounds_board(*hand: str) -> Scenario:
    scenario = (
        Scenario()
        .player("alice", hand=list(hand), battlefield=["Tournament Grounds"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_tournament_grounds_mana_casts_a_knight():
    scenario = _tournament_grounds_board("Knight of the Ebon Legion")
    grounds = scenario.find("Tournament Grounds", Zone.BATTLEFIELD)

    scenario.game.activate_ability(grounds, 1, "alice", color=Color.BLACK)
    assert _restrictions(scenario) == ["Spend this mana only to cast a Knight or Equipment spell."]

    knight = scenario.cast_and_resolve("Knight of the Ebon Legion")
    assert knight.zone is Zone.BATTLEFIELD


def test_tournament_grounds_mana_refuses_a_creature_that_is_not_a_knight():
    scenario = _tournament_grounds_board("Raging Goblin")
    grounds = scenario.find("Tournament Grounds", Zone.BATTLEFIELD)
    scenario.game.activate_ability(grounds, 1, "alice", color=Color.RED)

    with pytest.raises(ValueError, match="Spend this mana only to cast a Knight or Equipment"):
        scenario.cast("Raging Goblin", "alice").begin_paying().pay()


def test_tournament_grounds_cannot_add_a_colour_it_does_not_list():
    scenario = _tournament_grounds_board()
    grounds = scenario.find("Tournament Grounds", Zone.BATTLEFIELD)

    with pytest.raises(ValueError):
        scenario.game.activate_ability(grounds, 1, "alice", color=Color.GREEN)
    assert scenario.player("alice").mana_pool.floating == {}


# --------------------------------------------------------------------------
# Ancient Ziggurat - "one mana of any color"
# --------------------------------------------------------------------------


def _ziggurat_board(*hand: str) -> Scenario:
    scenario = (
        Scenario()
        .player("alice", hand=list(hand), battlefield=["Ancient Ziggurat"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_ancient_ziggurat_mana_casts_a_creature_spell():
    scenario = _ziggurat_board("Llanowar Elves")
    ziggurat = scenario.find("Ancient Ziggurat", Zone.BATTLEFIELD)

    scenario.game.activate_ability(ziggurat, 0, "alice", color=Color.GREEN)
    assert _restrictions(scenario) == ["Spend this mana only to cast a creature spell."]

    elves = scenario.cast_and_resolve("Llanowar Elves")
    assert elves.zone is Zone.BATTLEFIELD


def test_ancient_ziggurat_mana_refuses_a_noncreature_spell():
    scenario = _ziggurat_board("Opt")
    ziggurat = scenario.find("Ancient Ziggurat", Zone.BATTLEFIELD)
    scenario.game.activate_ability(ziggurat, 0, "alice", color=Color.BLUE)

    with pytest.raises(ValueError, match="Spend this mana only to cast a creature spell"):
        scenario.cast("Opt", "alice").begin_paying().pay()


# --------------------------------------------------------------------------
# The resolving-ability reader takes every colour-choice wording
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "effect_text",
    [
        # Narset's own three sentences.
        "You gain 2 life. Add {U}, {R}, or {W}. Spend this mana only to cast a noncreature spell.",
        # The two-colour list (The Emperor of Palamecia's wording).
        "Add {U} or {R}. Spend this mana only to cast a noncreature spell.",
        # "one mana of any color" behind another instruction.
        "You gain 2 life. Add one mana of any color. Spend this mana only to cast a creature "
        "spell.",
        # A literal symbol behind another instruction (Chandra's shape, preceded).
        "You gain 2 life. Add {U}. Spend this mana only to cast a noncreature spell.",
    ],
)
def test_a_resolving_ability_reads_the_colour_choice_with_its_restriction(effect_text):
    assert activated_effect_for("Probe", 0, effect_text) is not None


def test_an_unreadable_restriction_still_fails_the_ability_closed():
    text = "You gain 2 life. Add {U}, {R}, or {W}. Spend this mana only on costs that contain {X}."
    assert activated_effect_for("Probe", 0, text) is None
