"""Scenario: "put any number of `<type>` cards from your hand onto the
battlefield" - Ghalta, Stampede Tyrant's enters trigger and Last March of the
Ents' second instruction, read by `_parse_put_permanent_card_from_hand_clause`
(which already read "a" and "up to N"; "any number of" is the widening) - and
two independent "and/or" permanent-card groups from hand, each its own
CR 608.2d question (Michelangelo, Improviser).

Every CR number below was looked up with `mise run rules:find` in the
session that wrote this file:

- **CR 107.1c** - "If a rule or ability instructs a player to choose 'any
  number,' that player may choose any positive number or zero." Zero is a
  legal answer, and so is every creature card in hand.
- **CR 110.2a** - "If an effect instructs a player to put an object onto the
  battlefield, that object enters the battlefield under that player's
  control unless the effect states otherwise." Not a cast: no cost is paid
  and nothing that watches for a spell being cast sees it.
- **CR 603.6a** - the put creatures' own enters-the-battlefield abilities
  trigger.
- **CR 608.2d** - a card that is not a creature card is never a legal choice,
  and a hand with nothing to choose is never asked.
- **CR 608.2c** - "and/or" (Michelangelo, Improviser) is read as plain
  English: do the first thing, the second, both, or neither. Two independent
  questions, not one joint choice - unlike `_PUT_PERMANENT_CARD_FROM_HAND_RE`'s
  single "a permanent card" group (Kona, Rescue Beastie) or Ghalta's own "any
  number of creature cards", which each offer many cards out of *one* group
  at once.
- **CR 110.4a** - a creature card and a land card are each their own
  CR 205.2a card type; a card satisfying the first group is taken out of
  hand before the second group is asked, so nothing can be offered to both.
- **CR 601.2a/601.2i** - nothing here is cast: no cost is paid, no spell
  exists, and a "when you cast" trigger on either arriving card never fires.

Last March of the Ents is the off-pool proof (Modern-legal, not in any
`magic-cards-model-api` deck): a sorcery rather than an enters trigger, the
put printed after a ", then" behind a draw whose count is "the greatest
toughness among creatures you control" (`_parse_draw_cards_equal_to_count_
clause`, read here for the first time).

Michelangelo, Improviser's own "and/or" reader has no second legal printing
carrying its exact "... from your hand onto the battlefield" tail (dated
MEMORY.md line: every other "creature card and/or a land card" hit found
reveals four and offers the pair from among them, a different shape).
Generality for that reader is instead covered across every combination of
what the hand holds.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import DecisionKind
from magic_cards_model.models import Zone
from tests.scenarios.harness import PlayedScenario, Scenario

GHALTA = "Ghalta, Stampede Tyrant"


def _ghalta(*hand: str) -> PlayedScenario:
    scenario = (
        Scenario()
        .player("alice", hand=[GHALTA, *hand], library=["Forest"] * 5)
        .player("bob", library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _ghalta_enters(scenario: PlayedScenario) -> None:
    scenario.put_onto_battlefield(GHALTA, "alice")
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == [f"{GHALTA}'s triggered ability"]
    scenario.pass_until_resolved()


def _in_hand(scenario: PlayedScenario, name: str):
    return next(state for state in scenario.player("alice").hand if state.name == name)


def _questions(scenario: PlayedScenario):
    return [
        question
        for question in scenario.questions_asked()
        if question.kind is DecisionKind.CHOOSE_CARDS and question.source == GHALTA
    ]


def test_ghalta_puts_the_chosen_creature_cards_and_leaves_the_rest():
    scenario = _ghalta("Grizzly Bears", "Hill Giant", "Serra Angel", "Forest")
    bears = _in_hand(scenario, "Grizzly Bears")
    angel = _in_hand(scenario, "Serra Angel")
    scenario.will_choose_cards(bears, angel, username="alice", source=GHALTA)

    _ghalta_enters(scenario)

    assert bears.zone is Zone.BATTLEFIELD and angel.zone is Zone.BATTLEFIELD
    assert sorted(state.name for state in scenario.player("alice").hand) == [
        "Forest",
        "Hill Giant",
    ]
    assert scenario.game.spells_cast_this_turn.get("alice", []) == [], "CR 110.2a: not cast"


def test_ghalta_may_put_every_creature_card():
    scenario = _ghalta("Grizzly Bears", "Hill Giant", "Serra Angel")
    creatures = [
        _in_hand(scenario, name) for name in ("Grizzly Bears", "Hill Giant", "Serra Angel")
    ]
    scenario.will_choose_cards(*creatures, username="alice", source=GHALTA)

    _ghalta_enters(scenario)

    assert all(state.zone is Zone.BATTLEFIELD for state in creatures)
    assert scenario.player("alice").hand == []


def test_ghalta_may_put_none():
    """CR 107.1c: zero is a number."""
    scenario = _ghalta("Grizzly Bears", "Hill Giant")
    scenario.will_choose_cards(username="alice", source=GHALTA)

    _ghalta_enters(scenario)

    assert len(scenario.player("alice").hand) == 2
    (question,) = _questions(scenario)
    assert question.exact is False, "any number: a ceiling, not a count to meet"
    assert question.amount == 2


def test_ghalta_offers_only_creature_cards():
    scenario = _ghalta("Grizzly Bears", "Forest", "Opt", "Glorious Anthem")
    bears = _in_hand(scenario, "Grizzly Bears")
    scenario.will_choose_cards(bears, username="alice", source=GHALTA)

    _ghalta_enters(scenario)

    (question,) = _questions(scenario)
    assert question.cards == (bears.id,)
    assert bears.zone is Zone.BATTLEFIELD


def test_ghalta_with_no_creature_card_in_hand_asks_nothing():
    scenario = _ghalta("Forest", "Opt")

    _ghalta_enters(scenario)

    assert _questions(scenario) == []
    assert len(scenario.player("alice").hand) == 2


def test_the_put_creatures_enters_abilities_trigger():
    """CR 603.6a: Kitchen Finks entered, so its "When this creature enters,
    you gain 2 life" triggers and resolves."""
    scenario = _ghalta("Kitchen Finks")
    finks = _in_hand(scenario, "Kitchen Finks")
    scenario.will_choose_cards(finks, username="alice", source=GHALTA)
    life = scenario.player("alice").life

    _ghalta_enters(scenario)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert finks.zone is Zone.BATTLEFIELD
    assert scenario.player("alice").life == life + 2


def test_last_march_of_the_ents_draws_by_greatest_toughness_then_puts_any_number():
    """Hill Giant (3/3) and Grizzly Bears (2/2): the greatest toughness is 3,
    so three cards are drawn - one of them Serra Angel, which is then put
    straight from hand alongside the Craw Wurm already there."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Last March of the Ents", "Craw Wurm", "Opt"],
            battlefield=["Hill Giant", "Grizzly Bears", *(["Forest"] * 8)],
            library=["Serra Angel", "Island", "Forest", "Island"],
        )
        .player("bob", library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    wurm = _in_hand(scenario, "Craw Wurm")
    angel = alice.library[0]
    scenario.will_choose_cards(wurm, angel, username="alice", source="Last March of the Ents")
    forests = scenario.untapped_sources(*(["Forest"] * 8))

    scenario.cast_and_resolve("Last March of the Ents", *forests)

    assert wurm.zone is Zone.BATTLEFIELD and angel.zone is Zone.BATTLEFIELD
    assert sorted(state.name for state in alice.hand) == ["Forest", "Island", "Opt"]
    assert [state.name for state in alice.library] == ["Island"]


def test_last_march_of_the_ents_with_no_creatures_draws_nothing():
    """CR 107.2's empty extremum: no creature, greatest toughness 0 - no draw,
    and the put still offers the creature cards already in hand."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Last March of the Ents", "Craw Wurm"],
            battlefield=["Forest"] * 8,
            library=["Serra Angel"],
        )
        .player("bob", library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    wurm = _in_hand(scenario, "Craw Wurm")
    scenario.will_choose_cards(wurm, username="alice", source="Last March of the Ents")
    forests = scenario.untapped_sources(*(["Forest"] * 8))

    scenario.cast_and_resolve("Last March of the Ents", *forests)

    assert wurm.zone is Zone.BATTLEFIELD
    assert [state.name for state in scenario.player("alice").library] == ["Serra Angel"]


def test_ghalta_s_creatures_enter_simultaneously_and_see_each_other():
    """CR 603.6a: "Each time an event puts one or more permanents onto the
    battlefield, all permanents on the battlefield (including the newcomers)
    are checked" - one instruction is one event, so each Soul Warden's
    "whenever another creature enters" sees the other. Entered one at a
    time, only the first would see the second: one life, not two.
    """
    scenario = _ghalta("Soul Warden", "Soul Warden")
    wardens = [state for state in scenario.player("alice").hand if state.name == "Soul Warden"]
    scenario.will_choose_cards(*wardens, username="alice", source=GHALTA)

    _ghalta_enters(scenario)
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == ["Soul Warden's triggered ability"] * 2
    scenario.pass_until_resolved()
    scenario.pass_until_resolved()

    assert scenario.player("alice").life == 22


# -- Michelangelo, Improviser: "you may put a creature card and/or a land
# -- card from your hand onto the battlefield" ------------------------------

_MICHELANGELO_TRIGGER = "Michelangelo, Improviser's triggered ability"


def _michelangelo_board(*hand: str) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            battlefield=["Michelangelo, Improviser"],
            hand=list(hand),
            library=["Forest"] * 5,
        )
        .player("bob", library=["Island"] * 5)
    )


def _michelangelo_attacks_and_deals_combat_damage(scenario: PlayedScenario) -> None:
    scenario.start_at(Step.DECLARE_ATTACKERS)
    michelangelo = scenario.creature("Michelangelo, Improviser", "alice")
    scenario.attack_with(michelangelo, defending="bob")
    scenario.advance()
    scenario.no_blocks()
    scenario.combat_damage()


def test_both_groups_arrive_when_the_hand_offers_both():
    scenario = _michelangelo_board("Grizzly Bears", "Forest", "Lightning Bolt").build()
    _michelangelo_attacks_and_deals_combat_damage(scenario)
    assert scenario.stack_names() == [_MICHELANGELO_TRIGGER]
    scenario.pass_until_resolved()

    assert scenario.creature("Grizzly Bears", "alice").zone is Zone.BATTLEFIELD
    assert scenario.find("Forest", Zone.BATTLEFIELD, "alice").zone is Zone.BATTLEFIELD
    assert [state.name for state in scenario.player("alice").hand] == ["Lightning Bolt"]


def test_only_the_group_the_hand_actually_offers_is_asked():
    scenario = _michelangelo_board("Forest", "Lightning Bolt").build()
    _michelangelo_attacks_and_deals_combat_damage(scenario)
    scenario.pass_until_resolved()

    assert scenario.find("Forest", Zone.BATTLEFIELD, "alice").zone is Zone.BATTLEFIELD
    hand_names = [state.name for state in scenario.player("alice").hand]
    assert hand_names == ["Lightning Bolt"]
    # The land group asked twice (the "may" and then which card) - never
    # three times, which is what a spurious creature-group question would add.
    sources = [q.source for q in scenario.questions_asked()]
    assert sources.count("Michelangelo, Improviser") == 2


def test_declining_both_leaves_the_hand_untouched():
    scenario = _michelangelo_board("Grizzly Bears", "Forest").build()
    scenario.will_take_the_may(False, username="alice", times=None)
    _michelangelo_attacks_and_deals_combat_damage(scenario)
    scenario.pass_until_resolved()

    hand_names = {state.name for state in scenario.player("alice").hand}
    assert hand_names == {"Grizzly Bears", "Forest"}


def test_a_hand_with_neither_group_is_never_asked_anything():
    scenario = _michelangelo_board("Lightning Bolt", "Opt").build()
    _michelangelo_attacks_and_deals_combat_damage(scenario)
    scenario.pass_until_resolved()

    hand_names = {state.name for state in scenario.player("alice").hand}
    assert hand_names == {"Lightning Bolt", "Opt"}
    assert "Michelangelo, Improviser" not in [q.source for q in scenario.questions_asked()]
