"""Replacing a token *being created*: CR 701.7b, and Doubling Season's first half.

Every rule cited here was looked up with `knowledge_search(type="rules")` and
then read in full out of the 2026-08-19 Comprehensive Rules (sha256
`4381ad1b…423f`), because CR 701.7b is one sentence longer than its excerpt and
the second sentence is the one that draws the line this file is about.

**CR 701.7b, in full:** "If a replacement effect applies to a token being
created, that effect applies **before** considering any continuous effects that
will modify the characteristics of that token. If a replacement effect applies to
a token **entering the battlefield**, that effect applies **after** considering
any continuous effects that will modify the characteristics of that token."

Two events, not one. Doubling Season's first ability watches the first of them -
"If an effect would create one or more tokens under your control, it creates
twice that many of those tokens instead" - so it changes *how many*, at a moment
when the tokens are still nothing but a `TokenDefinition`. Everything a token
does on the way in is the second event, and it is the ordinary
`ENTERS_BATTLEFIELD` event every other permanent raises.

That is why this is a file of its own rather than cases in `test_tokens.py`:
the mechanic is the creation event, not the token.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Color, Type
from magic_cards_model.models.card_state import Counter
from magic_cards_model.models.token import TokenDefinition, create_tokens, token_copy_of
from tests.scenarios.harness import Scenario

SPIRIT = TokenDefinition(subtypes=("Spirit",), colors=(Color.WHITE,), power=1, toughness=1)


def _spirits(scenario) -> list:
    return [state for state in scenario.game.battlefield if state.name == "Spirit Token"]


def _procession(*extra: str) -> Scenario:
    """Six Plains, the sorcery that makes three Spirits, and whatever else."""
    return (
        Scenario()
        .player(
            "alice",
            hand=["Spectral Procession"],
            battlefield=["Plains"] * 6 + list(extra),
        )
        .player("bob")
    )


def _cast_procession(scenario) -> None:
    sources = scenario.untapped_sources(*["Plains"] * 6, username="alice")
    scenario.cast_and_resolve("Spectral Procession", *sources, username="alice")


# --------------------------------------------------------------------------
# The event exists, and it is the creation rather than the entering
# --------------------------------------------------------------------------


def test_without_a_replacement_effect_the_stated_number_is_created():
    """The control case. CR 701.7a: "To create one or more tokens with certain
    characteristics, put the specified number of tokens with the specified
    characteristics onto the battlefield."

    Three, because the card says three and nothing replaced the event.
    """
    scenario = _procession().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    _cast_procession(scenario)

    assert len(_spirits(scenario)) == 3


def test_doubling_season_doubles_a_creation_made_by_a_triggered_ability():
    """ "If an **effect** would create one or more tokens" - any effect, not only
    a spell's.

    Ajani, Nacatl Pariah reads "When Ajani enters, create a 2/1 white Cat Warrior
    creature token", which is a triggered ability (CR 603.2) whose resolution
    creates the token. CR 701.7b makes no distinction, so one Cat becomes two.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Ajani, Nacatl Pariah"],
            battlefield=["Plains", "Plains", "Doubling Season"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    sources = scenario.untapped_sources("Plains", "Plains", username="alice")
    scenario.cast_and_resolve("Ajani, Nacatl Pariah", *sources, username="alice")
    scenario.resolve_top()  # the enters trigger

    cats = [state for state in scenario.game.battlefield if state.name == "Cat Warrior Token"]
    assert len(cats) == 2


def test_doubling_season_doubles_a_token_copy():
    """CR 707.2 copying and CR 701.7a creating are two different things, and
    "create a token that's a copy of ..." does both. It is still a creation, so
    the count is still replaceable.

    Contrast CR 111.13, which is *not* creation: "a copy of a permanent spell
    becomes a token as it resolves", and the rule goes on to say such a token
    "isn't 'created'". A Doubling Season does not double that, and nothing here
    routes it through this event.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Grizzly Bears", "Doubling Season"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")

    copies = token_copy_of(scenario.game, bears, "alice")

    assert len(copies) == 2
    assert all(copy.name == "Grizzly Bears" for copy in copies)


# --------------------------------------------------------------------------
# Whose tokens: CR 111.2's "under your control"
# --------------------------------------------------------------------------


def test_an_opponents_doubling_season_does_not_double_your_tokens():
    """ "...create one or more tokens **under your control**".

    CR 111.2 says "the token enters the battlefield under that player's control",
    and the player in question is the one creating them. bob's Doubling Season
    has nothing to say about alice's Spirits.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Spectral Procession"], battlefield=["Plains"] * 6)
        .player("bob", battlefield=["Doubling Season"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    _cast_procession(scenario)

    assert len(_spirits(scenario)) == 3


def test_your_own_doubling_season_doubles_them():
    """The same board with the enchantment on the other side of the table, so the
    difference in the test above is the controller and nothing else.
    """
    scenario = _procession("Doubling Season").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    _cast_procession(scenario)

    assert len(_spirits(scenario)) == 6


# --------------------------------------------------------------------------
# CR 614.5 and CR 616.2: two effects on one event
# --------------------------------------------------------------------------


def test_two_doubling_seasons_quadruple():
    """CR 614.5: "a replacement effect doesn't invoke itself repeatedly; it gets
    only one opportunity to affect an event or any modified events that may
    replace that event."

    *One* opportunity each - and there are two of them, on two different
    permanents. CR 616.2 then re-runs the choice "taking into account only
    replacement or prevention effects that would now be applicable", so the second
    Doubling Season sees an event that already says six and makes it twelve. Not
    six, which is what a single-shot reading would give, and not an infinite loop,
    which is what CR 614.5 exists to prevent.
    """
    scenario = _procession("Doubling Season", "Doubling Season").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    _cast_procession(scenario)

    assert len(_spirits(scenario)) == 12


def test_the_counters_on_a_doubled_token_are_doubled_too():
    """CR 616.1g's "an event contained within the first event", and CR 122.6.

    Creating tokens with counters on them is two events one inside the other: the
    creation, which Doubling Season's first ability doubles, and the counters
    being put on each token as it arrives, which its second ability doubles.
    CR 122.6 is what makes the second one reach: "counters being put on an object
    ... refers to putting counters on that object while it's on the battlefield
    and also to an object that's given counters as it enters the battlefield."

    So two Spawn each carrying four counters, not one Spawn with two.
    """
    scenario = Scenario().player("alice", battlefield=["Doubling Season"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    spawn = TokenDefinition(subtypes=("Eldrazi", "Spawn"), power=0, toughness=1)
    created = create_tokens(scenario.game, spawn, "alice", counters={Counter.PLUS_ONE: 2})

    assert len(created) == 2
    assert all(token.counters[Counter.PLUS_ONE] == 4 for token in created)


# --------------------------------------------------------------------------
# The edges of the event
# --------------------------------------------------------------------------


def test_creating_no_tokens_is_not_an_event_to_double():
    """ "If an effect would create **one or more** tokens" - nought is not one or
    more, so there is nothing for the replacement effect to apply to and twice
    nought is still nought.
    """
    scenario = _procession("Doubling Season").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    assert create_tokens(scenario.game, SPIRIT, "alice", count=0) == []
    assert _spirits(scenario) == []


def test_every_doubled_token_enters_separately():
    """CR 701.7b's second sentence is a different event, once per token.

    Soul Warden reads "Whenever another creature enters, you gain 1 life". Six
    Spirits entering is six separate enters events (CR 603.6a), so alice gains
    six life rather than three - the doubling happened before any of them
    entered, which is exactly what CR 701.7b's ordering says.
    """
    scenario = _procession("Doubling Season", "Soul Warden").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    before = scenario.player("alice").life

    _cast_procession(scenario)
    while scenario.game.stack:
        scenario.resolve_top()

    assert len(_spirits(scenario)) == 6
    assert scenario.player("alice").life == before + 6


def test_a_doubling_season_that_arrives_after_the_creation_does_nothing():
    """CR 614.1: "replacement effects apply continuously as events happen - they
    aren't locked in ahead of time."

    Read the other way round, an effect that was not there when the event
    happened never applied to it. The Spirits are made first and the enchantment
    lands afterwards; nothing goes back and doubles them.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Doubling Season"],
            battlefield=["Plains"] * 6 + ["Forest"] * 5,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    create_tokens(scenario.game, SPIRIT, "alice", count=3)
    assert len(_spirits(scenario)) == 3

    sources = scenario.untapped_sources(*(["Forest"] * 5), username="alice")
    scenario.cast_and_resolve("Doubling Season", *sources, username="alice")

    assert scenario.find("Doubling Season", Zone.BATTLEFIELD, username="alice")
    assert len(_spirits(scenario)) == 3, "the creation had already happened"


# --------------------------------------------------------------------------
# How many: a multiplier read off the card, not a pinned "twice"
# --------------------------------------------------------------------------
#
# Doubling Season's "it creates twice that many of those tokens", Adrix and
# Nev's "twice that many of those tokens are created" and Ojer Taq's "three
# times that many of those tokens are created" are one replacement with a
# number in it (CR 614.1a, CR 614.16).

FOOD = TokenDefinition(types=(Type.ARTIFACT,), subtypes=("Food",))


def _named(scenario, name: str) -> list:
    return [state for state in scenario.game.battlefield if state.name == name]


def test_ojer_taq_triples_a_creature_token_creation():
    """ "...three times that many of those tokens are created instead." 3, 9."""
    scenario = _procession("Ojer Taq, Deepest Foundation").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    _cast_procession(scenario)

    assert len(_spirits(scenario)) == 9


def test_adrix_and_nev_double_with_the_passive_wording():
    """ "If one or more tokens would be created under your control, twice that
    many of those tokens are created instead" - Doubling Season's replacement
    in other words."""
    scenario = _procession("Adrix and Nev, Twincasters").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    _cast_procession(scenario)

    assert len(_spirits(scenario)) == 6


def test_ojer_taq_leaves_a_noncreature_token_alone():
    """ "If one or more **creature** tokens would be created" - Food is not one."""
    scenario = Scenario().player("alice", battlefield=["Ojer Taq, Deepest Foundation"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    create_tokens(scenario.game, FOOD, "alice", 2)

    assert len(_named(scenario, "Food Token")) == 2


def test_adrix_and_nev_double_a_noncreature_token_too():
    """No filter on "one or more tokens": Food doubles."""
    scenario = Scenario().player("alice", battlefield=["Adrix and Nev, Twincasters"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    create_tokens(scenario.game, FOOD, "alice", 2)

    assert len(_named(scenario, "Food Token")) == 4


def test_an_opponents_ojer_taq_does_not_triple_your_tokens():
    """CR 111.2: "under your control" is the creator's control."""
    scenario = (
        Scenario()
        .player("alice", hand=["Spectral Procession"], battlefield=["Plains"] * 6)
        .player("bob", battlefield=["Ojer Taq, Deepest Foundation"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    _cast_procession(scenario)

    assert len(_spirits(scenario)) == 3


def test_ojer_taq_and_doubling_season_multiply_in_either_order():
    """CR 616.1 orders the two, CR 614.5 applies each once: 3 * 3 * 2 = 18."""
    scenario = _procession("Ojer Taq, Deepest Foundation", "Doubling Season").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    _cast_procession(scenario)

    assert len(_spirits(scenario)) == 18


# --------------------------------------------------------------------------
# "those tokens plus <a count of> <token>": the addition's count is read
# --------------------------------------------------------------------------
#
# Stridehangar Automaton's "plus an additional 1/1 ... Thopter", Quina's "plus
# a 1/1 green Frog creature token" and Chatterfang's "plus that many 1/1 green
# Squirrel creature tokens". "That many" is the count of the event being
# replaced, as Doubling Season's own "twice that many" reads it.


def test_quina_adds_one_frog_to_a_creature_token_creation():
    scenario = _procession("Quina, Qu Gourmet").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    _cast_procession(scenario)

    assert len(_spirits(scenario)) == 3
    assert len(_named(scenario, "Frog Token")) == 1


def test_quina_adds_one_frog_to_a_noncreature_token_creation():
    """ "If one or more tokens would be created" names no type: Food counts."""
    scenario = Scenario().player("alice", battlefield=["Quina, Qu Gourmet"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    create_tokens(scenario.game, FOOD, "alice", 2)

    assert len(_named(scenario, "Food Token")) == 2
    assert len(_named(scenario, "Frog Token")) == 1


def test_chatterfang_adds_that_many_squirrels():
    """ "...those tokens plus that many 1/1 green Squirrel creature tokens." 3, 3."""
    scenario = _procession("Chatterfang, Squirrel General").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    _cast_procession(scenario)

    assert len(_spirits(scenario)) == 3
    squirrels = _named(scenario, "Squirrel Token")
    assert len(squirrels) == 3
    assert all(squirrel.power == 1 and squirrel.toughness == 1 for squirrel in squirrels)


def test_chatterfang_adds_one_squirrel_to_a_single_food():
    scenario = Scenario().player("alice", battlefield=["Chatterfang, Squirrel General"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    create_tokens(scenario.game, FOOD, "alice", 1)

    assert len(_named(scenario, "Food Token")) == 1
    assert len(_named(scenario, "Squirrel Token")) == 1
