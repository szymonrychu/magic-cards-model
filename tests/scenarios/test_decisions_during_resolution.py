"""Scenario: a resolving effect stopping to ask its controller something.

CR 608.2d is the whole mechanic:

    If an effect of a spell or ability offers any choices other than choices
    already made as part of casting the spell, activating the ability, or
    otherwise putting the spell or ability on the stack, the player announces
    these while applying the effect. The player can't choose an option that's
    illegal or impossible, with the exception that having a library with no
    cards in it doesn't make drawing a card an impossible action (see rule
    121.3).

Two halves, and the second is the interesting one. "The player announces these
while applying the effect" is plumbing; "the player can't choose an option
that's illegal or impossible" is a rule with teeth, and it is what makes a
shockland enter tapped at 1 life without anybody deciding to tap it.

Every CR number here was looked up with `knowledge_search(q="...",
type="rules")` in the session that wrote this file, and read in full from the
`2026-08-19` Comprehensive Rules release that
`knowledge_search(type="cr_versions")` names as current, verified against its
published sha256.

- **CR 608.2d** - the choice, and its legality, quoted above.
- **CR 614.12a** - "If a replacement effect that modifies how a permanent enters
  the battlefield requires a choice, that choice is made before the permanent
  enters the battlefield." The shockland's question is asked while the land is
  still on its way in, which is why the answer can change what enters.
- **CR 614.1c** - "As [this permanent] enters ..." is a replacement effect.
- **CR 119.4** - "If a cost or effect allows a player to pay an amount of life
  greater than 0, the player may do so only if their life total is greater than
  or equal to the amount of the payment."
- **CR 119.4b** - "Players can always pay 0 life, no matter what their ... life
  total is."
- **CR 704.5a** - losing at 0 or less life is a state-based action, checked
  separately, which is why paying to exactly 0 is legal.
- **CR 701.9b** - "By default, effects that cause a player to discard a card
  allow the affected player to choose which card to discard." Seasoned
  Pyromancer's discard.
- **CR 701.23g** - "If an effect offers a player a choice to search a zone and
  take additional actions with the cards found, that player may choose to
  search even if the additional actions are illegal or impossible." Solemn
  Simulacrum's "you may search".

The scry and surveil halves of the same machinery live in `test_scry.py` and
`test_surveil.py`. This file is about the question itself.
"""

from uuid import uuid4

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import DecisionKind, ScriptedAnswer
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _shockland_in_hand(life: int = 20, name: str = "Steam Vents") -> Scenario:
    """One player holding a shockland, with a land drop available."""
    return Scenario().manual_turn_based_actions().player("alice", life=life, hand=[name])


# -- the shockland's choice, both branches ---------------------------------


def test_paying_the_two_life_leaves_the_shockland_untapped():
    """CR 614.12a: the choice is made before the permanent enters.

    Which is what lets the answer decide whether it arrives tapped at all -
    a permanent already on the battlefield could only be untapped afterwards,
    and that is a different game action.
    """
    scenario = _shockland_in_hand().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_pay_the_life(True)

    vents = scenario.play_land("Steam Vents")

    assert not vents.tapped
    assert scenario.player("alice").life == 18


def test_declining_the_two_life_makes_the_shockland_enter_tapped():
    """ "If you don't, it enters tapped" - the other branch of one CR 614.1c effect.

    The two printed sentences are one choice, not two effects, so refusing the
    payment is what taps the land rather than a second effect applying.
    """
    scenario = _shockland_in_hand().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_pay_the_life(False)

    vents = scenario.play_land("Steam Vents")

    assert vents.tapped
    assert scenario.player("alice").life == 20


def test_a_shockland_at_one_life_enters_tapped_without_being_asked():
    """CR 119.4 makes the payment illegal, and CR 608.2d then forbids choosing it.

    The whole point of modelling legality rather than preference: at 1 life
    there is exactly one legal option, so the answer is forced and the land taps
    itself. A player agent that "decided" here would be inventing a decision the
    rules never offered - which is why the recorded question says the
    affirmative was not available.
    """
    scenario = _shockland_in_hand(life=1).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    vents = scenario.play_land("Steam Vents")

    assert vents.tapped
    assert scenario.player("alice").life == 1

    (question,) = scenario.questions_asked()
    assert question.kind is DecisionKind.PAY_LIFE
    assert not question.affirmative_is_legal


def test_a_shockland_at_exactly_two_life_may_still_be_paid_for():
    """CR 119.4 allows paying when the life total is "greater than *or equal to*".

    Two life at 2 life is legal and lands on 0. Losing is CR 704.5a's separate
    state-based action, so nothing has happened yet at the moment the land
    enters - the boundary case that a naive "must stay above zero" check would
    get wrong.
    """
    scenario = _shockland_in_hand(life=2).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_pay_the_life(True)

    vents = scenario.play_land("Steam Vents")

    assert not vents.tapped
    assert scenario.player("alice").life == 0
    assert scenario.game.winner is None, "CR 704.5a has not been checked yet"


def test_a_player_at_one_life_cannot_be_scripted_into_paying():
    """CR 608.2d: "The player can't choose an option that's illegal or impossible."

    A scenario asking for the illegal branch is a bug in the scenario, and it is
    told so rather than being quietly given the legal one - which would make the
    test pass while asserting something that never happened.
    """
    scenario = _shockland_in_hand(life=1).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_pay_the_life(True)

    with pytest.raises(ValueError, match="608.2d"):
        scenario.play_land("Steam Vents")


def test_the_default_is_to_pay_and_it_is_documented_not_improvised():
    """No answer queued at all. The default belongs to the engine, not to luck.

    `machines/decisions.default_answer` takes the affirmative branch whenever
    CR 608.2d allows it, which is what keeps every already-registered "you may"
    behaving as it did before decisions existed.
    """
    scenario = _shockland_in_hand().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    vents = scenario.play_land("Steam Vents")

    assert not vents.tapped
    assert scenario.player("alice").life == 18


def test_a_shockland_asks_once_per_land_and_names_itself():
    """The question carries its asker, so two shocklands do not share an answer.

    CR 608.2d puts the choice to "the player" without saying how a program
    should route it; naming the source is how a scenario aims an answer at one
    card. Stomping Ground and Steam Vents print the same sentence, and only the
    one that was answered pays.
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Steam Vents"], battlefield=["Stomping Ground"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_pay_the_life(False, source="Steam Vents")

    vents = scenario.play_land("Steam Vents")

    assert vents.tapped
    (question,) = scenario.questions_asked()
    assert question.source == "Steam Vents"
    assert question.amount == 2


def test_a_plain_enters_tapped_land_asks_nothing():
    """Elegant Parlor prints "This land enters tapped" with no choice in it.

    CR 614.1c covers both shapes, and only one of them is a decision. A land
    that taps unconditionally must not start asking questions now that questions
    exist - and its `surveil 1` trigger is a separate ability, not part of the
    replacement effect.
    """
    scenario = _shockland_in_hand(name="Elegant Parlor").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    parlor = scenario.play_land("Elegant Parlor")

    assert parlor.tapped
    assert [
        question
        for question in scenario.questions_asked()
        if question.kind is DecisionKind.PAY_LIFE
    ] == []


def test_a_shockland_put_onto_the_battlefield_by_an_effect_still_asks():
    """CR 614.12 applies to every route onto the battlefield, not just to a land drop.

    "Some replacement effects modify how a permanent enters the battlefield ...
    Such effects may come from the permanent itself." Nothing in that sentence is
    about how the permanent got there, and a fetchland putting a shockland into
    play is the way this actually comes up in Modern.
    """
    scenario = (
        Scenario().manual_turn_based_actions().player("alice", library=["Steam Vents"]).build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_pay_the_life(False)
    vents = scenario.player("alice").library[0]

    scenario.game.put_onto_battlefield(vents, "alice")

    assert vents.zone is Zone.BATTLEFIELD
    assert vents.tapped
    assert scenario.player("alice").life == 20


# -- which card is discarded (CR 701.9b) -----------------------------------
#
# "By default, effects that cause a player to discard a card allow the
# affected player to choose which card to discard." Seasoned Pyromancer's
# enters trigger discards two cards and turns each *nonland* one into an
# Elemental token, so which two cards go changes how many tokens come back -
# a wrong default here is not cosmetic, it is the wrong number of bodies on
# the battlefield.


def _seasoned_pyromancer_board(*extra_hand: str) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            library=["Forest", "Island"],
            hand=["Seasoned Pyromancer", "Mountain", "Lightning Bolt", *extra_hand],
            battlefield=["Mountain", "Mountain", "Mountain"],
        )
        .player("bob")
    )


def test_choosing_which_two_cards_are_discarded_changes_the_token_count():
    """A four-card hand (Seasoned Pyromancer plus three others) leaves a real
    choice once the creature itself is cast: two of the remaining three go.
    The default (below, and in `test_tokens.py`) discards the front of hand -
    Mountain and the first Lightning Bolt, one nonland, one token. Naming both
    Lightning Bolts instead - a different, legal answer - discards zero lands
    and makes two tokens, proving the choice runs through `Game.ask` rather
    than only relabeling the default's own answer.
    """
    scenario = _seasoned_pyromancer_board("Lightning Bolt").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Mountain", "Mountain", "Mountain", username="alice")
    alice = scenario.player("alice")
    bolts = [state for state in alice.hand if state.name == "Lightning Bolt"]
    assert len(bolts) == 2
    scenario.will_discard(*bolts, username="alice")

    scenario.cast_and_resolve("Seasoned Pyromancer", *sources, username="alice")
    scenario.resolve_top()  # the enters trigger

    elementals = [state for state in scenario.game.battlefield if state.name == "Elemental Token"]
    assert len(elementals) == 2, "both discards were nonland, so both make a token"
    assert sorted(state.name for state in alice.hand) == ["Forest", "Island", "Mountain"]


def test_the_unscripted_default_still_discards_the_front_of_hand():
    """No script, no provider: the front-of-hand default from before `Game.ask`
    existed still applies, unchanged - `test_tokens.py` already asserts the
    same board end to end; this asserts on the question itself.
    """
    scenario = _seasoned_pyromancer_board("Lightning Bolt").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Mountain", "Mountain", "Mountain", username="alice")
    alice = scenario.player("alice")

    scenario.cast_and_resolve("Seasoned Pyromancer", *sources, username="alice")
    scenario.resolve_top()

    (question,) = [q for q in scenario.questions_asked() if q.kind is DecisionKind.CHOOSE_CARDS]
    assert question.source == "Seasoned Pyromancer"
    elementals = [state for state in scenario.game.battlefield if state.name == "Elemental Token"]
    assert len(elementals) == 1, "the front of hand is Mountain and one Lightning Bolt"
    assert sorted(state.name for state in alice.hand) == ["Forest", "Island", "Lightning Bolt"]


def test_an_illegal_discard_answer_is_refused_without_corrupting_the_hand():
    """`Game.ask` validates a `CHOOSE_CARDS` answer the same way for every
    caller: a card that was never offered is a `ValueError` and nothing moves.
    """
    scenario = _seasoned_pyromancer_board("Lightning Bolt").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Mountain", "Mountain", "Mountain", username="alice")
    alice = scenario.player("alice")
    scenario.cast_and_resolve("Seasoned Pyromancer", *sources, username="alice")
    hand_before = [state.id for state in alice.hand]
    scenario.game.decisions.add(
        ScriptedAnswer(
            kind=DecisionKind.CHOOSE_CARDS,
            value=(hand_before[0], uuid4()),  # the second card was never offered
            player="alice",
        )
    )

    with pytest.raises(ValueError, match="cannot choose a card that was not offered"):
        scenario.resolve_top()  # the enters trigger, which asks

    assert [state.id for state in alice.hand] == hand_before


# -- which card is taken among revealed cards (CR 608.2d) -------------------
#
# Malevolent Rumble reveals four and offers a plain "you may" over which
# permanent, if any, comes home. There is no more specific numbered rule than
# CR 608.2d for choosing among a group of revealed cards - CR 701.9b's discard
# default does not apply here, since nothing is being discarded.


def _malevolent_rumble_board(library: list[str]) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            library=library,
            hand=["Malevolent Rumble"],
            battlefield=["Forest", "Forest"],
        )
        .player("bob")
    )


def test_choosing_a_different_permanent_than_the_library_order_default():
    """Two permanents among the four revealed; the default (documented and
    tested in `test_tokens.py`) takes the first in library order, Grizzly
    Bears. Naming the other one instead - Wall of Omens - proves the choice is
    real, not a relabeling of the same answer.
    """
    scenario = _malevolent_rumble_board(
        ["Grizzly Bears", "Wall of Omens", "Forest", "Counterspell"]
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Forest", "Forest", username="alice")
    alice = scenario.player("alice")
    wall = alice.library[1]
    assert wall.name == "Wall of Omens"
    scenario.will_discard(wall, username="alice")

    scenario.cast_and_resolve("Malevolent Rumble", *sources, username="alice")

    assert [state.name for state in alice.hand] == ["Wall of Omens"]
    graveyard_names = {state.name for state in alice.graveyard}
    assert graveyard_names == {"Grizzly Bears", "Forest", "Counterspell", "Malevolent Rumble"}


def test_declining_the_may_puts_no_permanent_into_hand_but_still_makes_the_token():
    """Declining is legal (CR 608.2d): the rest of the effect - milling the
    other three, making the Eldrazi Spawn - still happens where the sentence
    puts it.
    """
    scenario = _malevolent_rumble_board(
        ["Grizzly Bears", "Wall of Omens", "Forest", "Counterspell"]
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Forest", "Forest", username="alice")
    alice = scenario.player("alice")
    scenario.will_take_the_may(False, source="Malevolent Rumble")

    scenario.cast_and_resolve("Malevolent Rumble", *sources, username="alice")

    assert [state.name for state in alice.hand] == []
    assert {state.name for state in alice.graveyard} == {
        "Grizzly Bears",
        "Wall of Omens",
        "Forest",
        "Counterspell",
        "Malevolent Rumble",
    }
    spawn = scenario.find("Eldrazi Spawn Token", Zone.BATTLEFIELD)
    assert spawn.name == "Eldrazi Spawn Token"


def test_no_permanent_among_the_four_asks_nothing():
    """CR 608.2d only asks when there is a real choice. Four nonland,
    nonpermanent cards leave nothing to put into hand, so no question is put at
    all - the same shape as "scry 0 does not scry".
    """
    scenario = _malevolent_rumble_board(["Lightning Bolt", "Counterspell", "Opt", "Shock"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Forest", "Forest", username="alice")
    alice = scenario.player("alice")

    scenario.cast_and_resolve("Malevolent Rumble", *sources, username="alice")

    assert alice.hand == []
    assert [q for q in scenario.questions_asked() if q.kind is DecisionKind.MAY] == []


def test_an_empty_choose_cards_answer_is_refused_without_losing_the_spell():
    """Regression: game 535264e8458e461d874d0d38f4b1866e, seq 115-122.

    carol accepted Malevolent Rumble's "you may put a permanent card into your
    hand" (CR 608.2d), then answered the follow-up "choose a permanent card"
    with an empty `card_ids: []` - not a legal answer, since that question's
    `Decision.amount` is 1 and `exact` defaults `True`
    (`machines/effects.py::malevolent_rumble`). `Game.ask`'s own `CHOOSE_CARDS`
    branch already refuses that exact shape (`needs 1 card(s) chosen, 0
    given`), which is CR 608.2d's "the player can't choose an option that's
    illegal or impossible" enforced.

    The bug was not that refusal - it is that `Game.resolve_top` pops the
    spell off the stack *before* calling its effect, so the raised `ValueError`
    unwound out of `resolve_top` with Malevolent Rumble already off the stack
    and nowhere else: not the graveyard, not exiled, not anywhere
    `Scenario.zones_containing` can find it. The reported game's decklist came
    up 59 of 60 cards for exactly this reason.

    CR 400.1: "A zone is a place where objects can be during a game" - normally
    one of seven, and every object not outside the game (CR 400.11) is in
    exactly one. CR 307.2 / CR 608.2n: a sorcery is put into its owner's
    graveyard as the final part of its own resolution, not some other point,
    and never nowhere. The fix (`Game.resolve_top`) catches the exception
    `effect(self, spell)` raises, sends the spell to its owner's graveyard the
    same way CR 608.2n already requires, and re-raises - so the caller still
    sees the refusal at the moment it was given (assertion (a) below), the same
    way `test_an_illegal_discard_answer_is_refused_without_corrupting_the_hand`
    already expects for a different `CHOOSE_CARDS` question, and the spell is
    never left in limbo while that exception unwinds (assertion (b)).
    """
    scenario = _malevolent_rumble_board(
        ["Grizzly Bears", "Wall of Omens", "Forest", "Counterspell"]
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Forest", "Forest", username="alice")
    alice = scenario.player("alice")
    revealed = list(alice.library[:4])
    before = list(scenario.all_card_states())

    scenario.cast_onto_stack("Malevolent Rumble", *sources, username="alice")
    rumble = scenario.find("Malevolent Rumble", Zone.STACK)
    scenario.will_take_the_may(True, source="Malevolent Rumble")
    scenario.will_choose_cards(source="Malevolent Rumble", username="alice")

    with pytest.raises(ValueError, match="needs 1 card"):
        scenario.resolve_top()

    # (a) refused at the point it was given: the `pytest.raises` above is the
    # assertion - `Game.ask` raised synchronously from inside `malevolent_
    # rumble`'s own `game.ask(decision)` call, not from some later, unrelated
    # action the way the reported game's opponent's `pass_priority` was.

    # (b) after the dust settles, every card involved is in exactly one zone,
    # and Malevolent Rumble specifically made it to alice's graveyard (CR
    # 307.2, CR 608.2n) rather than vanishing.
    scenario.assert_in_exactly_one_zone(rumble, *revealed, *before)
    assert rumble.zone is Zone.GRAVEYARD
    assert rumble in alice.graveyard
    # The effect never got past the refused question, so nothing it would
    # have done afterwards happened either - the revealed cards are still
    # sitting exactly where they were, untouched, not half-moved.
    assert all(state in alice.library for state in revealed)
    assert alice.hand == []


# -- optional triggers, the "you may" default (CR 608.2d) --------------------
#
# `default_answer` takes the affirmative for `MAY` whenever it is legal - the
# behaviour every "you may" clause in `machines/effects.py` had before
# `Game.ask` existed. Solemn Simulacrum's two triggers are a "you may search"
# (CR 701.23g) and a plain "you may draw a card"; both were unconditional
# before this session and are now real questions.


def _solemn_board(library: list[str]) -> Scenario:
    return Scenario().player("alice", library=library, hand=["Solemn Simulacrum"]).player("bob")


def test_declining_solemns_search_finds_no_land_and_shuffles_nothing_extra():
    scenario = _solemn_board(["Forest", "Island"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_take_the_may(False, source="Solemn Simulacrum")

    scenario.put_onto_battlefield("Solemn Simulacrum", "alice")
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    alice = scenario.player("alice")
    assert scenario.battlefield_names() == ["Solemn Simulacrum"]
    assert {state.name for state in alice.library} == {"Forest", "Island"}


def test_solemns_search_still_defaults_to_taking_it():
    """Unscripted, unprovided: the search still happens, matching the old
    unconditional behaviour (also covered end to end in
    `test_triggered_abilities.py`).
    """
    scenario = _solemn_board(["Forest", "Island"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.put_onto_battlefield("Solemn Simulacrum", "alice")
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert "Forest" in scenario.battlefield_names()


def test_declining_the_draw_on_death_leaves_the_hand_empty():
    scenario = (
        Scenario()
        .player("alice", hand=["Solemn Simulacrum"], library=["Island", "Forest"])
        .player("bob")
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    solemn = scenario.put_onto_battlefield("Solemn Simulacrum", "alice")
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()  # the enters search, taken by default (Island)

    scenario.will_take_the_may(False, source="Solemn Simulacrum")
    scenario.game.destroy(solemn)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert scenario.player("alice").hand == []


def test_the_draw_on_death_still_defaults_to_taking_it():
    scenario = (
        Scenario()
        .player("alice", hand=["Solemn Simulacrum"], library=["Island", "Forest"])
        .player("bob")
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    solemn = scenario.put_onto_battlefield("Solemn Simulacrum", "alice")
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()  # the enters search, taken by default (Island)

    scenario.game.destroy(solemn)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert [state.name for state in scenario.player("alice").hand] == ["Forest"]
