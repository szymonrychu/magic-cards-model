"""Proliferate - CR 701.34a, a keyword action new to this branch.

"To proliferate means to choose any number of permanents and/or players,
then give each another counter of each kind already there." `Game.
proliferate(chosen, chosen_players)` reads both halves of that sentence:
permanents through the existing `DecisionKind.CHOOSE_CARDS` question, and
players through a new `DecisionKind.CHOOSE_PLAYERS` question (`Decision.
players`, `Answer.usernames`) - CR 701.34a's own "and/or players" (poison,
experience, or any other counter kind a player happens to carry), asked as
a second, independent CR 608.2d question rather than folded into the same
one, since nothing in this store's own `DecisionKind` vocabulary answers a
single question with a mix of cards and usernames.

`machines/effects._parse_proliferate_clause` asks both questions fresh
before *each* repetition of a repeated proliferate - each skipped outright
when its own candidate list is empty - which is what would let a counter
added by one repetition make a permanent or player newly eligible for the
next.

Three real printings, all already in the pool:

- **Fuel for the Cause** (off-set instant): "Counter target spell, then
  proliferate." - a bare, one-shot proliferate, composed after an ordinary
  counterspell clause (CR 608.2c). Used for both the permanent half and the
  player half, staging a real poisoned/experienced player directly
  (`Game.add_player_counters`) the same way the permanent tests stage a
  real countered permanent (`Game.add_counters`) - CR 701.34a does not care
  where a counter came from, only that it is there to proliferate.
- **Tam, the Possibility**'s own `{W}{U}{B}{R}{G}, {T}: Proliferate X times,
  where X is the number of planeswalker types among planeswalkers you
  control.` - CR 107.3f's "where X is ..." tail, evaluated through
  `machines/effects.count_expression`/`amount_expression`.

CR numbers looked up with `knowledge_search(type="rules")` in this session:
CR 701.34, CR 701.34a, CR 122.1, CR 122.1f, CR 608.2c, CR 107.3f.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import DecisionKind
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from magic_cards_model.models.token import PREDEFINED, create_tokens
from tests.scenarios.harness import Scenario


def test_each_chosen_permanent_gets_one_more_of_each_counter_kind_it_already_has():
    """A creature with one `+1/+1` counter and a planeswalker with loyalty
    counters, both chosen, each get exactly one more of the *one* counter
    kind they already carry - not a counter of some other kind, and not more
    than one."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Fuel for the Cause"],
            library=["Island"] * 3,
            battlefield=[
                "Island",
                "Island",
                "Island",
                "Island",
                "Grizzly Bears",
                "Jace, Reality Sculptor",
            ],
        )
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain", "Grizzly Bears"], life=20)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bear = scenario.creature("Grizzly Bears", "alice")
    jace = scenario.creature("Jace, Reality Sculptor", "alice")
    untouched = scenario.creature("Grizzly Bears", "bob")
    scenario.game.add_counters(bear, Counter.PLUS_ONE, 1)
    assert jace.loyalty == 5
    assert untouched.counters.counts == {}

    scenario.pass_priority("alice")
    (mountain,) = scenario.untapped_sources("Mountain", username="bob")
    bolt = scenario.cast_onto_stack("Lightning Bolt", mountain, username="bob", targets=["alice"])
    scenario.pass_priority("bob")

    scenario.will_choose_cards(bear, jace, source="Fuel for the Cause")
    sources = scenario.untapped_sources("Island", "Island", "Island", "Island")
    scenario.cast_and_resolve("Fuel for the Cause", *sources, username="alice", targets=[bolt])

    assert bolt.zone is Zone.GRAVEYARD, "the spell was countered before it ever resolved"
    assert bear.counter_count(Counter.PLUS_ONE) == 2, "one more +1/+1, the kind it already had"
    assert jace.loyalty == 6, "one more loyalty, the kind it already had"

    [choice] = [
        question
        for question in scenario.questions_asked()
        if question.source == "Fuel for the Cause"
    ]
    assert untouched.id not in choice.cards, "a permanent with no counters is never a candidate"


def test_a_permanent_with_no_counters_at_all_is_never_offered():
    """The same proof as above, isolated: with nothing at all carrying a
    counter, the `CHOOSE_CARDS` question offers zero candidates and nothing
    is asked to choose among them."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Fuel for the Cause"],
            library=["Island"] * 3,
            battlefield=["Island", "Island", "Island", "Island"],
        )
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain", "Grizzly Bears"], life=20)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bear = scenario.creature("Grizzly Bears", "bob")
    assert bear.counters.counts == {}

    scenario.pass_priority("alice")
    (mountain,) = scenario.untapped_sources("Mountain", username="bob")
    bolt = scenario.cast_onto_stack("Lightning Bolt", mountain, username="bob", targets=["alice"])
    scenario.pass_priority("bob")

    sources = scenario.untapped_sources("Island", "Island", "Island", "Island")
    scenario.cast_and_resolve("Fuel for the Cause", *sources, username="alice", targets=[bolt])

    assert bolt.zone is Zone.GRAVEYARD
    questions = [q for q in scenario.questions_asked() if q.source == "Fuel for the Cause"]
    assert questions == [], "CR 701.34a: no permanent has a counter, so nothing is even asked"


def test_two_separate_proliferate_resolutions_each_independently_apply():
    """Two full, separate proliferate resolutions - two casts of Fuel for
    the Cause, each countering its own spell and then proliferating - each
    ask their own `CHOOSE_CARDS` question against the *then-current* board
    and apply their own result, adding one more loyalty counter each time.

    This is the fallback the mechanic's own corner case sanctions when the
    tighter version (one single repeated proliferate whose first repetition
    makes a permanent newly eligible for its second) is hard to stage:
    "two SEPARATE full proliferate passes each independently offer and
    apply to the then-current candidate set."
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Fuel for the Cause", "Fuel for the Cause"],
            library=["Island"] * 3,
            battlefield=["Island"] * 8,
        )
        .player(
            "bob",
            hand=["Lightning Bolt", "Lightning Bolt"],
            battlefield=["Mountain", "Mountain"],
            life=20,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (jace,) = create_tokens(scenario.game, PREDEFINED["Jace"], "alice", count=1)
    scenario.game.add_counters(jace, Counter.LOYALTY, 2)
    assert jace.loyalty == 2

    scenario.pass_priority("alice")
    (m1,) = scenario.untapped_sources("Mountain", username="bob")
    bolt1 = scenario.cast_onto_stack("Lightning Bolt", m1, username="bob", targets=["alice"])
    scenario.pass_priority("bob")
    scenario.will_choose_cards(jace, source="Fuel for the Cause")
    sources1 = scenario.untapped_sources("Island", "Island", "Island", "Island")
    scenario.cast_and_resolve("Fuel for the Cause", *sources1, username="alice", targets=[bolt1])

    assert bolt1.zone is Zone.GRAVEYARD
    assert jace.loyalty == 3, "the first pass's own proliferate landed"

    scenario.pass_priority("alice")
    (m2,) = scenario.untapped_sources("Mountain", username="bob")
    bolt2 = scenario.cast_onto_stack("Lightning Bolt", m2, username="bob", targets=["alice"])
    scenario.pass_priority("bob")
    scenario.will_choose_cards(jace, source="Fuel for the Cause")
    sources2 = scenario.untapped_sources("Island", "Island", "Island", "Island")
    scenario.cast_and_resolve("Fuel for the Cause", *sources2, username="alice", targets=[bolt2])

    assert bolt2.zone is Zone.GRAVEYARD
    assert jace.loyalty == 4, "the second, independent pass added its own loyalty counter too"


def test_tam_proliferates_once_per_planeswalker_type_among_planeswalkers_you_control():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[
                "Tam, the Possibility",
                "Jace, Reality Sculptor",
                "Ugin, Eye of the Storms",
                "Plains",
                "Island",
                "Swamp",
                "Mountain",
                "Forest",
            ],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    tam = scenario.creature("Tam, the Possibility", "alice")
    jace = scenario.creature("Jace, Reality Sculptor", "alice")
    ugin = scenario.creature("Ugin, Eye of the Storms", "alice")
    assert {subtype for subtype in (jace.subtypes[0], ugin.subtypes[0])} == {"Jace", "Ugin"}
    assert jace.loyalty == 5
    assert ugin.loyalty == 7

    sources = scenario.untapped_sources("Plains", "Island", "Swamp", "Mountain", "Forest")
    scenario.will_choose_cards(jace, ugin, source="Tam, the Possibility")
    scenario.will_choose_cards(jace, ugin, source="Tam, the Possibility")
    scenario.activate(tam, *sources)
    while scenario.game.stack:
        scenario.resolve_top()

    # CR 107.3f: X = 2 planeswalker types (Jace, Ugin) among planeswalkers
    # alice controls, so "Proliferate X times" should run the whole
    # choose-and-add step twice, adding two loyalty counters to each.
    assert jace.loyalty == 7
    assert ugin.loyalty == 9


def test_a_chosen_poisoned_player_gets_one_more_of_each_counter_kind_they_have():
    """CR 701.34a's own "and/or players" half. Bob is staged with one poison
    counter (CR 122.1f) and one experience counter directly - CR 122.1's own
    open set of counter kinds names no dedicated sub-rule for "experience",
    verified absent from the local Comprehensive Rules text this session -
    a real proliferate spell then chooses him alongside a permanent, and
    each of his own counter kinds goes up by exactly one, the identical
    "one more of each kind it already has" rule the permanent half already
    proves, over `Game.add_player_counters` instead of `Game.add_counters`.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Fuel for the Cause"],
            library=["Island"] * 3,
            battlefield=["Island", "Island", "Island", "Island", "Grizzly Bears"],
        )
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain"], life=20)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bear = scenario.creature("Grizzly Bears", "alice")
    bob = scenario.game.player("bob")
    scenario.game.add_player_counters(bob, Counter.POISON, 1)
    scenario.game.add_player_counters(bob, Counter.EXPERIENCE, 1)

    scenario.pass_priority("alice")
    (mountain,) = scenario.untapped_sources("Mountain", username="bob")
    bolt = scenario.cast_onto_stack("Lightning Bolt", mountain, username="bob", targets=["alice"])
    scenario.pass_priority("bob")

    scenario.will_choose_cards(source="Fuel for the Cause")
    scenario.will_choose_players(bob, source="Fuel for the Cause")
    sources = scenario.untapped_sources("Island", "Island", "Island", "Island")
    scenario.cast_and_resolve("Fuel for the Cause", *sources, username="alice", targets=[bolt])

    assert bolt.zone is Zone.GRAVEYARD, "the spell was countered before it ever resolved"
    assert bob.counter_count(Counter.POISON) == 2
    assert bob.counter_count(Counter.EXPERIENCE) == 2
    assert bear.counters.counts == {}, "a permanent with no counters is untouched either way"


def test_an_unpoisoned_player_is_never_offered_as_a_candidate():
    """CR 701.34a's own "that have a counter": with nobody carrying any
    counter at all, `CHOOSE_PLAYERS` is never even asked - the same
    "skip the impossible question" posture the permanent half already
    takes when no permanent on the battlefield carries one either
    (CR 608.2d)."""
    scenario = (
        Scenario()
        .player(
            "alice", hand=["Fuel for the Cause"], library=["Island"] * 3, battlefield=["Island"] * 4
        )
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain"], life=20)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.pass_priority("alice")
    (mountain,) = scenario.untapped_sources("Mountain", username="bob")
    bolt = scenario.cast_onto_stack("Lightning Bolt", mountain, username="bob", targets=["alice"])
    scenario.pass_priority("bob")

    sources = scenario.untapped_sources("Island", "Island", "Island", "Island")
    scenario.cast_and_resolve("Fuel for the Cause", *sources, username="alice", targets=[bolt])

    asked = [
        question
        for question in scenario.questions_asked()
        if question.source == "Fuel for the Cause" and question.kind is DecisionKind.CHOOSE_PLAYERS
    ]
    assert asked == [], "neither alice nor bob carries any counter at all"


def test_only_the_poisoned_player_is_offered_when_the_other_is_not():
    """CR 701.34a's own "that have a counter", the positive half: with bob
    poisoned and alice carrying no counter of her own, the `CHOOSE_PLAYERS`
    question offers bob alone."""
    scenario = (
        Scenario()
        .player(
            "alice", hand=["Fuel for the Cause"], library=["Island"] * 3, battlefield=["Island"] * 4
        )
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain"], life=20)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bob = scenario.game.player("bob")
    scenario.game.add_player_counters(bob, Counter.POISON, 1)

    scenario.pass_priority("alice")
    (mountain,) = scenario.untapped_sources("Mountain", username="bob")
    bolt = scenario.cast_onto_stack("Lightning Bolt", mountain, username="bob", targets=["alice"])
    scenario.pass_priority("bob")

    scenario.will_choose_players(bob, source="Fuel for the Cause")
    sources = scenario.untapped_sources("Island", "Island", "Island", "Island")
    scenario.cast_and_resolve("Fuel for the Cause", *sources, username="alice", targets=[bolt])

    [choice] = [
        question
        for question in scenario.questions_asked()
        if question.source == "Fuel for the Cause" and question.kind is DecisionKind.CHOOSE_PLAYERS
    ]
    assert choice.players == ("bob",), "alice carries no counter, so she is never a candidate"
    assert bob.counter_count(Counter.POISON) == 2
