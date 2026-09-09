"""Scenario: a sentence that *opens* with "Then ...".

`_CLAUSE_SEPARATOR` (`machines/effects.py`) reads "then" only as an infix
joiner - "Scry 2, then draw a card" - so a "Then" standing at the head of its
own sentence survived `split_effect_clauses` and no per-clause parser
downstream could read the clause it was glued to. The whole card was then
refused (correctly: CR 608.2c has no notion of running half an effect) and
silently did nothing. Measured before the fix:

    'earthbend 2. Then search your library for a basic land card, ...' -> None
    'earthbend 2. search your library for a basic land card, ...'      -> parses

Every CR number below was read out of the Comprehensive Rules on disk this
session with `mise run rules:find <number>`:

- **CR 608.2c** - "The controller of the spell or ability follows its
  instructions in the order written." The word "then" is that order made
  explicit; it is not itself an instruction, so dropping it changes nothing
  about what is run.
- **CR 608.2d** - "The player can't choose an option that's illegal or
  impossible." Ancient Stirrings' "you may reveal a colorless card from among
  them" is exactly such a restriction, and it is the second half of this file:
  reading the sentence is not the same as reading the *quality* it names.
- **CR 105.2c** - "A colorless object has no color." A bare "colorless" with
  no card type after it is a whole quality on its own, which is what
  `_quality_word_matcher` could not read: it recognised a colour word only as
  an adjective in front of a type ("a colorless creature card").
- **CR 401.4** - "If an effect puts two or more cards in a specific position
  in a library at the same time, the owner of those cards may arrange them in
  any order" - Ancient Stirrings' own "in any order" tail.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import CardSplit, DecisionKind, ScriptedAnswer
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter

from .harness import Scenario


def _script_split(scenario: Scenario, *, username: str, moved) -> None:
    """Answer the next `DecisionKind.SCRY`-shaped split with `moved` as the
    taken half - the same helper `test_look_at_top_and_split.py` uses, since
    `Game.look_at_top_and_split` reuses `SCRY` for a non-scry effect."""
    scenario.game.decisions.add(
        ScriptedAnswer(kind=DecisionKind.SCRY, value=CardSplit(moved=tuple(moved)), player=username)
    )


# -- Ancient Stirrings: the whole card, not just the sentence --------------


def test_ancient_stirrings_takes_a_colorless_card():
    """`Look at the top five cards of your library. You may reveal a colorless
    card from among them and put it into your hand. Then put the rest on the
    bottom of your library in any order.`

    Two independent defects had to be fixed for this to pass, and each alone
    leaves the card looking handled while doing the wrong thing:

    1. the sentence-initial "Then" made the last clause unreadable, which
       (correctly) refused the whole effect;
    2. `_quality_matcher("colorless")` matched nothing at all, so with only
       (1) fixed the card looks at five cards, can legally take none of them,
       bottoms all five, and every sweep calls it handled.

    Chalice of the Void is a real colorless artifact printing from the pool;
    the other four cards are coloured, so it is the only legal choice.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Ancient Stirrings"],
            battlefield=["Forest"],
            library=[
                "Forest",
                "Chalice of the Void",
                "Grizzly Bears",
                "Mountain",
                "Lightning Bolt",
            ],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    top_five = scenario.top_of_library(5)
    chalice = next(state for state in top_five if state.name == "Chalice of the Void")
    _script_split(scenario, username="alice", moved=[chalice.id])

    (forest,) = scenario.untapped_sources("Forest")
    scenario.cast_and_resolve("Ancient Stirrings", forest)

    assert chalice.zone is Zone.HAND
    assert chalice in alice.hand
    # CR 401.4: the other four go to the bottom, in the order given back.
    assert [state.name for state in alice.library[-4:]] == [
        state.name for state in top_five if state is not chalice
    ]
    assert len(alice.library) == 4


def test_ancient_stirrings_may_take_nothing():
    """The "may" is real: taking zero is legal, and then all five go to the
    bottom (CR 608.2d offers the choice, it does not force it)."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Ancient Stirrings"],
            battlefield=["Forest"],
            library=[
                "Forest",
                "Chalice of the Void",
                "Grizzly Bears",
                "Mountain",
                "Lightning Bolt",
            ],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    _script_split(scenario, username="alice", moved=[])

    (forest,) = scenario.untapped_sources("Forest")
    scenario.cast_and_resolve("Ancient Stirrings", forest)

    assert alice.hand == []
    assert len(alice.library) == 5


def test_ancient_stirrings_refuses_a_coloured_card():
    """CR 608.2d: a green creature is not "a colorless card", so choosing it
    is an illegal option and the engine refuses rather than quietly allowing
    it. This is the assertion that fails if `_quality_matcher("colorless")`
    were "fixed" by making it match everything."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Ancient Stirrings"],
            battlefield=["Forest"],
            library=[
                "Forest",
                "Chalice of the Void",
                "Grizzly Bears",
                "Mountain",
                "Lightning Bolt",
            ],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    top_five = scenario.top_of_library(5)
    bears = next(state for state in top_five if state.name == "Grizzly Bears")
    _script_split(scenario, username="alice", moved=[bears.id])

    (forest,) = scenario.untapped_sources("Forest")
    with pytest.raises(ValueError, match="colorless"):
        scenario.cast_and_resolve("Ancient Stirrings", forest)


# -- Earthbender Ascension: the same separator defect on an ability --------


def test_earthbender_ascension_searches_after_earthbending():
    """`When this enchantment enters, earthbend 2. Then search your library
    for a basic land card, put it onto the battlefield tapped, then shuffle.`

    The trailing "then shuffle" was always read (`_rejoin_search_clauses`);
    the *leading* "Then" was not, and took the earthbend down with it - so
    neither half ran (CR 608.2c: no notion of running half an effect).

    CR 701.66a: "Earthbend N" means "Target land you control becomes a 0/0
    land creature with haste in addition to its other types. Put N +1/+1
    counters on it. ..." - so the earthbend half is checked on the *targeted*
    land, and the search half on what came out of the library.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Earthbender Ascension"],
            battlefield=["Forest", "Forest", "Mountain"],
            library=["Grizzly Bears", "Forest"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    fetched = next(state for state in alice.library if state.name == "Forest")
    mountain = scenario.find("Mountain", Zone.BATTLEFIELD)
    scenario.choose_trigger_targets("Earthbender Ascension", [mountain])

    sources = scenario.untapped_sources("Forest", "Forest", "Mountain")
    scenario.cast_and_resolve("Earthbender Ascension", *sources)
    scenario.pass_until_resolved()

    assert mountain.counters[Counter.PLUS_ONE] == 2
    assert scenario.game.characteristics_of(mountain).is_creature
    assert fetched.zone is Zone.BATTLEFIELD
    assert fetched.tapped
    assert [state.name for state in alice.library] == ["Grizzly Bears"]


# -- Ashiok, Dream Render: the same defect on a loyalty ability -------------


def test_ashiok_mills_then_exiles_every_opponents_graveyard():
    """`-1: Target player mills four cards. Then exile each opponent's
    graveyard.`

    "Each opponent" is each opponent of the *ability's controller* (CR 102.1),
    which is not the same set as "the milled player": Alice mills herself here
    and Bob's graveyard is still the one exiled.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Ashiok, Dream Render"],
            library=[
                "Forest",
                "Mountain",
                "Grizzly Bears",
                "Lightning Bolt",
                "Chalice of the Void",
            ],
            graveyard=["Swamp"],
        )
        .player("bob", graveyard=["Grizzly Bears", "Lightning Bolt"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    bob = scenario.player("bob")
    ashiok = scenario.find("Ashiok, Dream Render", Zone.BATTLEFIELD)

    scenario.activate(ashiok, index=0, targets=["alice"])
    scenario.pass_until_resolved()

    assert len(alice.library) == 1
    # Alice's own graveyard is untouched - she is not her own opponent.
    assert [state.name for state in alice.graveyard] == [
        "Swamp",
        "Forest",
        "Mountain",
        "Grizzly Bears",
        "Lightning Bolt",
    ]
    assert bob.graveyard == []


# -- Kaito, Bane of Nightmares' 0: a count read off the turn's ledger -------


def test_kaitos_zero_draws_one_card_per_opponent_who_lost_life():
    """`0: Surveil 2. Then draw a card for each opponent who lost life this
    turn.`

    The count is `Player.life_lost_this_turn`, the gross per-turn ledger the
    engine already keeps for Children of Korlis - one card *per opponent*, not
    per point of life. Bob has lost life this turn (Lightning Bolt), so Kaito
    draws exactly one.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Bolt"],
            battlefield=["Kaito, Bane of Nightmares", "Mountain"],
            library=["Forest", "Grizzly Bears", "Chalice of the Void"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    (mountain,) = scenario.untapped_sources("Mountain")
    scenario.cast_and_resolve("Lightning Bolt", mountain, targets=["bob"])
    assert scenario.player("bob").life == 17

    kaito = scenario.find("Kaito, Bane of Nightmares", Zone.BATTLEFIELD)
    scenario.surveil_keeping_everything_on_top()
    scenario.activate(kaito, index=1)
    scenario.pass_until_resolved()

    assert len(alice.hand) == 1


def test_kaitos_zero_draws_nothing_when_no_opponent_has_lost_life():
    """The same ability with an untouched opponent draws zero - the count is a
    real count, not "at least one"."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Kaito, Bane of Nightmares"],
            library=["Forest", "Grizzly Bears", "Chalice of the Void"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    kaito = scenario.find("Kaito, Bane of Nightmares", Zone.BATTLEFIELD)
    scenario.surveil_keeping_everything_on_top()
    scenario.activate(kaito, index=1)
    scenario.pass_until_resolved()

    assert alice.hand == []
