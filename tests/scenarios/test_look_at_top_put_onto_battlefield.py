"""Scenario: "Look at the top N cards of your library. [You may] put
`<quantity>` `<description>` from among them onto the battlefield. Put the
rest on the bottom of your library in a random/any order." -
`_merge_look_top_put_onto_battlefield_clauses`.

Aang, at the Crossroads' enters trigger is the reported shape ("You may put a
creature card with mana value 4 or less ... in a random order"). Collected
Company (Modern- and Pioneer-legal, in no `magic-cards-model-api` deck) is
the off-pool proof: a different count (six), an "up to two" with no "you
may", a different ceiling (3), an instant rather than a trigger, and "in any
order" rather than "in a random order". Birthing Ritual's sacrifice-gated
form of the same reader is in `test_sacrificed_mana_value_bound.py`.

Every CR number below was looked up with `mise run rules:find` in the
session that wrote this file:

- **CR 701.20e** - "Looking at a card follows the same rules as revealing a
  card, except that the card is shown only to the specified player."
- **CR 608.2d** - "The player can't choose an option that's illegal or
  impossible": a card outside the description is never offered, and "you
  may" / "up to two" both allow choosing none.
- **CR 202.3** - mana value; a card with exactly the ceiling qualifies.
- **CR 110.2a** - put onto the battlefield under that player's control, not
  cast.
- **CR 401.4** - "in any order" is the owner's arrangement; "in a random
  order" is nobody's.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import DecisionKind
from magic_cards_model.models import Zone
from tests.scenarios.harness import PlayedScenario, Scenario

AANG = "Aang, at the Crossroads"
COCO = "Collected Company"


def _offered(scenario: PlayedScenario, source: str) -> list[str] | None:
    """The cards the put question offered - the first `CHOOSE_CARDS` from
    `source`; an "in any order" bottoming asks a second one after it."""
    questions = [
        question
        for question in scenario.questions_asked()
        if question.kind is DecisionKind.CHOOSE_CARDS and question.source == source
    ]
    if not questions:
        return None
    offered = set(questions[0].cards)
    return sorted(state.name for state in scenario.all_card_states() if state.id in offered)


def _library(scenario: PlayedScenario) -> list[str]:
    return [state.name for state in scenario.player("alice").library]


def _card(scenario: PlayedScenario, name: str):
    return next(state for state in scenario.player("alice").library if state.name == name)


# --------------------------------------------------------------------------
# Aang, at the Crossroads
# --------------------------------------------------------------------------

_FIVE = ["Serra Angel", "Hill Giant", "Opt", "Grizzly Bears", "Forest"]


def _aang(library: list[str]) -> PlayedScenario:
    scenario = (
        Scenario()
        .player("alice", hand=[AANG], library=library)
        .player("bob", library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _aang_enters(scenario: PlayedScenario) -> None:
    scenario.put_onto_battlefield(AANG, "alice")
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()


def test_aang_puts_a_creature_card_with_mana_value_four_or_less():
    scenario = _aang([*_FIVE, "Island", "Island"])
    giant = _card(scenario, "Hill Giant")
    scenario.will_choose_cards(giant, username="alice", source=AANG)

    _aang_enters(scenario)

    assert giant.zone is Zone.BATTLEFIELD and giant.controller == "alice"
    assert _offered(scenario, AANG) == ["Grizzly Bears", "Hill Giant"], (
        "a 4 is 'four or less'; Serra Angel (5), Opt and Forest are never offered"
    )
    library = _library(scenario)
    assert library[:2] == ["Island", "Island"], "the unlooked-at cards are now on top"
    assert sorted(library[2:]) == sorted(name for name in _FIVE if name != "Hill Giant")


def test_aang_may_put_nothing_and_bottoms_all_five():
    scenario = _aang([*_FIVE, "Island"])
    scenario.will_choose_cards(username="alice", source=AANG)

    _aang_enters(scenario)

    assert all(state.zone is not Zone.BATTLEFIELD for state in scenario.player().library)
    library = _library(scenario)
    assert library[0] == "Island"
    assert sorted(library[1:]) == sorted(_FIVE)


def test_aang_with_no_qualifying_card_asks_nothing():
    scenario = _aang(["Serra Angel", "Opt", "Forest", "Forest", "Craw Wurm", "Island"])

    _aang_enters(scenario)

    assert _offered(scenario, AANG) is None
    assert _library(scenario)[0] == "Island"
    assert len(scenario.player("alice").library) == 6


def test_aang_with_a_short_library_looks_at_what_there_is():
    scenario = _aang(["Grizzly Bears", "Opt"])
    bears = _card(scenario, "Grizzly Bears")
    scenario.will_choose_cards(bears, username="alice", source=AANG)

    _aang_enters(scenario)

    assert bears.zone is Zone.BATTLEFIELD
    assert _library(scenario) == ["Opt"]


def test_aang_the_put_card_is_not_cast():
    """CR 110.2a: put, not cast - no spell was cast this turn."""
    scenario = _aang(["Grizzly Bears", "Island"])
    bears = _card(scenario, "Grizzly Bears")
    scenario.will_choose_cards(bears, username="alice", source=AANG)

    _aang_enters(scenario)

    assert bears.zone is Zone.BATTLEFIELD
    assert scenario.game.spells_cast_this_turn.get("alice", []) == []


# --------------------------------------------------------------------------
# Collected Company - the off-pool proof
# --------------------------------------------------------------------------

_SIX = ["Gray Ogre", "Hill Giant", "Grizzly Bears", "Opt", "Llanowar Elves", "Forest"]


def _coco(library: list[str]) -> PlayedScenario:
    scenario = (
        Scenario()
        .player("alice", hand=[COCO], battlefield=["Forest"] * 4, library=[*library, "Island"])
        .player("bob", library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _cast_coco(scenario: PlayedScenario) -> None:
    forests = scenario.untapped_sources(*(["Forest"] * 4))
    scenario.cast_and_resolve(COCO, *forests)


def test_collected_company_puts_up_to_two_with_mana_value_three_or_less():
    scenario = _coco(_SIX)
    ogre = _card(scenario, "Gray Ogre")
    elves = _card(scenario, "Llanowar Elves")
    scenario.will_choose_cards(ogre, elves, username="alice", source=COCO)

    _cast_coco(scenario)

    assert ogre.zone is Zone.BATTLEFIELD and elves.zone is Zone.BATTLEFIELD
    assert _offered(scenario, COCO) == ["Gray Ogre", "Grizzly Bears", "Llanowar Elves"], (
        "Hill Giant's 4 is over the ceiling; Opt and Forest are not creature cards"
    )
    library = _library(scenario)
    assert library[0] == "Island"
    assert sorted(library[1:]) == sorted(["Hill Giant", "Grizzly Bears", "Opt", "Forest"])


def test_collected_company_may_put_just_one():
    scenario = _coco(_SIX)
    bears = _card(scenario, "Grizzly Bears")
    scenario.will_choose_cards(bears, username="alice", source=COCO)

    _cast_coco(scenario)

    assert bears.zone is Zone.BATTLEFIELD
    assert len(scenario.player("alice").library) == 6


def test_collected_company_may_put_none():
    """ "Up to two" (CR 107.1c's range from zero) needs no "you may"."""
    scenario = _coco(_SIX)
    scenario.will_choose_cards(username="alice", source=COCO)

    _cast_coco(scenario)

    assert len(scenario.player("alice").library) == 7
    questions = [
        question
        for question in scenario.questions_asked()
        if question.kind is DecisionKind.CHOOSE_CARDS and question.source == COCO
    ]
    assert questions[0].exact is False and questions[0].amount == 2


def test_collected_company_bottoms_the_rest_in_the_owner_s_chosen_order():
    """CR 401.4: "in any order" is the owner's to arrange."""
    scenario = _coco(["Gray Ogre", "Opt", "Forest", "Hill Giant", "Serra Angel", "Craw Wurm"])
    ogre = _card(scenario, "Gray Ogre")
    order = [_card(scenario, name) for name in ("Craw Wurm", "Forest", "Serra Angel")]
    order += [_card(scenario, name) for name in ("Opt", "Hill Giant")]
    scenario.will_choose_cards(ogre, username="alice", source=COCO)
    scenario.will_choose_cards(*order, username="alice", source=COCO)

    _cast_coco(scenario)

    assert ogre.zone is Zone.BATTLEFIELD
    assert _library(scenario) == [
        "Island",
        "Craw Wurm",
        "Forest",
        "Serra Angel",
        "Opt",
        "Hill Giant",
    ]


def test_collected_company_s_creatures_enter_simultaneously_and_see_each_other():
    """CR 603.6a: both creatures are put by one instruction, one event, so
    each Soul Warden sees the other enter - two triggers, not the one a
    one-at-a-time entry would give."""
    scenario = _coco(["Soul Warden", "Soul Warden", "Opt", "Forest", "Hill Giant", "Forest"])
    wardens = [state for state in scenario.player("alice").library if state.name == "Soul Warden"]
    scenario.will_choose_cards(*wardens, username="alice", source=COCO)

    _cast_coco(scenario)
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == ["Soul Warden's triggered ability"] * 2
    scenario.pass_until_resolved()
    scenario.pass_until_resolved()

    assert scenario.player("alice").life == 22


# --------------------------------------------------------------------------
# R0a-T7: United Battlefront - the identical `_merge_look_top_put_onto_
# battlefield_clauses` reader, with a compound "noncreature, nonland
# permanent" quality (CR 205.2a's negation, more than one word deep) that
# used to send `_put_description` to `None` (`machines/effects.py`'s own
# `_parse_card_group_qualifier` widening).
# --------------------------------------------------------------------------

BATTLEFRONT = "United Battlefront"


def _battlefront(library: list[str]) -> PlayedScenario:
    scenario = (
        Scenario()
        .player("alice", hand=[BATTLEFRONT], battlefield=["Plains"] * 4, library=library)
        .player("bob", library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _cast_battlefront(scenario: PlayedScenario) -> None:
    plains = scenario.untapped_sources(*(["Plains"] * 4))
    scenario.cast_and_resolve(BATTLEFRONT, *plains)


def test_united_battlefront_puts_up_to_two_noncreature_nonland_permanents():
    """ "noncreature, nonland permanent cards with mana value 3 or less" -
    Grizzly Bears (a creature) and Forest (a land) are excluded outright;
    Bonesplitter and Prophetic Prism (both artifacts, mana value 1 and 2)
    qualify; Serra Angel's mana value 5 is over the ceiling even though it
    would otherwise be creature-excluded anyway."""
    scenario = _battlefront(
        [
            "Grizzly Bears",
            "Forest",
            "Bonesplitter",
            "Prophetic Prism",
            "Serra Angel",
            "Opt",
            "Island",
        ]
    )
    bonesplitter = _card(scenario, "Bonesplitter")
    prism = _card(scenario, "Prophetic Prism")
    scenario.will_choose_cards(bonesplitter, prism, username="alice", source=BATTLEFRONT)

    _cast_battlefront(scenario)

    assert bonesplitter.zone is Zone.BATTLEFIELD
    assert prism.zone is Zone.BATTLEFIELD
    assert _offered(scenario, BATTLEFRONT) == ["Bonesplitter", "Prophetic Prism"]


def test_united_battlefront_excludes_creatures_and_lands_even_when_cheap():
    """A one-mana-value creature and land are never offered, however cheap -
    the exclusion is on card type, not on cost."""
    scenario = _battlefront(
        ["Llanowar Elves", "Forest", "Opt", "Craw Wurm", "Island", "Island", "Island"]
    )

    _cast_battlefront(scenario)

    assert _offered(scenario, BATTLEFRONT) is None
    assert all(state.zone is not Zone.BATTLEFIELD for state in scenario.player("alice").library)


# --------------------------------------------------------------------------
# R0a-T7: Break Out - reveal one creature card, a mana-value-gated choice
# between the battlefield (with haste) and the hand, the rest to the bottom
# (`machines/spell_texts_r0a.py`'s `parse_look_top_reveal_conditional_
# battlefield_clause`)
# --------------------------------------------------------------------------

BREAK_OUT = "Break Out"


def _break_out(library: list[str]) -> PlayedScenario:
    scenario = (
        Scenario()
        .player("alice", hand=[BREAK_OUT], battlefield=["Mountain", "Forest"], library=library)
        .player("bob", library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _cast_break_out(scenario: PlayedScenario) -> None:
    sources = scenario.untapped_sources("Mountain", "Forest")
    scenario.cast_and_resolve(BREAK_OUT, *sources)


def test_break_out_puts_a_cheap_creature_onto_the_battlefield_with_haste():
    """ "If that card has mana value 2 or less, you may put it onto the
    battlefield and it gains haste until end of turn." - Llanowar Elves
    (mana value 1) revealed, put onto the battlefield, and able to attack
    the same turn (CR 702.10a)."""
    scenario = _break_out(
        ["Llanowar Elves", "Opt", "Island", "Forest", "Serra Angel", "Grizzly Bears"]
    )
    elves = _card(scenario, "Llanowar Elves")
    scenario.will_choose_cards(elves, username="alice", source=BREAK_OUT)
    scenario.will_take_the_may(True, username="alice", source=BREAK_OUT)

    _cast_break_out(scenario)

    assert elves.zone is Zone.BATTLEFIELD and elves.controller == "alice"
    assert "Haste" in scenario.game.characteristics_of(elves).abilities

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(elves)
    assert scenario.attackers() == [elves]


def test_break_out_declining_the_battlefield_puts_it_into_hand_instead():
    """CR 608.2d: declining the "you may" for a card that does qualify still
    leaves the fallback - "put it into your hand" - which is not itself
    optional."""
    scenario = _break_out(
        ["Llanowar Elves", "Opt", "Island", "Forest", "Serra Angel", "Grizzly Bears"]
    )
    elves = _card(scenario, "Llanowar Elves")
    scenario.will_choose_cards(elves, username="alice", source=BREAK_OUT)
    scenario.will_take_the_may(False, username="alice", source=BREAK_OUT)

    _cast_break_out(scenario)

    assert elves.zone is Zone.HAND


def test_break_out_puts_an_expensive_revealed_creature_into_hand():
    """Serra Angel's mana value 5 is over the ceiling: no battlefield
    question is even asked (CR 608.2d never offers an impossible choice),
    and it goes straight to hand."""
    scenario = _break_out(["Serra Angel", "Opt", "Island", "Forest", "Craw Wurm", "Grizzly Bears"])
    angel = _card(scenario, "Serra Angel")
    scenario.will_choose_cards(angel, username="alice", source=BREAK_OUT)

    _cast_break_out(scenario)

    assert angel.zone is Zone.HAND
    assert not any(
        question.kind is DecisionKind.MAY and question.source == BREAK_OUT
        for question in scenario.questions_asked()
    )
