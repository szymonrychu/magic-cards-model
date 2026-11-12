"""Entering as a copy "except it isn't legendary" - a copy exception that
*removes* a supertype, and a copy that "enters with additional counters on it
equal to the same number and kinds of counters the copied permanent has on it".

Dominion Saboteur is the reported card: "You may have this creature enter as a
copy of any artifact or creature on the battlefield, except it isn't legendary.
If you do, it enters with additional counters on it equal to the same number and
kinds of counters the copied permanent has on it."

`replacement.parse._parse_copy_exception` had no way to say "isn't legendary"
(`CopyException` could only *add* supertypes), so the whole tail was left
unread and the copy fell to a notice. The counters sentence was read as a bare
`ENTERS_WITH` that no reader performs. Both now live on the one
`CopyException` (`not_legendary`, `copies_counters`) that `_apply_copy_of`
turns into the layer 1 copy effect and the entering counters.

Spark Double (a differently worded real printing: "...enter as a copy of a
creature or planeswalker you control, except it enters with an additional +1/+1
counter on it if it's a creature, it enters with an additional loyalty counter on
it if it's a planeswalker, and it isn't legendary.") is the second proof: the
same removal, plus two exceptions each gated on its own card type
(`if_type_counters`).

Every CR number below was looked up with `mise run rules:find` in the session
that wrote this file:

- **CR 707.9b** - a copy effect that modifies a characteristic: the final value
  becomes part of the copiable values ("isn't legendary" is the supertype set
  without legendary).
- **CR 707.9e** - an exception that is an additional effect ("it enters with ...
  counters"), not a characteristic: it is applied by the replacement, not
  written into the copiable values.
- **CR 707.5** - the copy is a copy as it enters; it does not enter and then
  become one.
- **CR 614.12** / **CR 614.12a** - the enters replacement and its choice, made
  before the permanent enters.
- **CR 704.5j** - the legend rule, which an "isn't legendary" copy escapes.
- **CR 707.2** - a copy gets copiable values, never the original's counters
  (so the counters here are the exception's own additional effect).
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Supertype, Type, Zone
from magic_cards_model.support import HANDLED, classify_clauses
from tests.cards import card
from tests.scenarios.harness import Scenario

SABOTEUR = "Dominion Saboteur"
SPARK = "Spark Double"
LILIANA = "Liliana of the Veil"  # legendary planeswalker, loyalty 3
ISAMARU = "Isamaru, Hound of Konda"  # legendary creature, 2/2


def _chars(scenario, permanent):
    return scenario.game.characteristics_of(permanent)


def _board(copier, *, alice=(), bob=(), hand=()):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=[copier, *hand],
            battlefield=["Island"] * 5 + list(alice),
            library=["Island"] * 5,
        )
        .player("bob", battlefield=list(bob), library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _cast(scenario, copier, copied=None):
    if copied is None:
        scenario.will_take_the_may(False, source=copier)
    else:
        scenario.will_choose_cards(copied, username="alice", source=copier)
    return scenario.cast_and_resolve(copier, *scenario.untapped_sources(*["Island"] * 5))


def test_both_cards_are_handled():
    for name in (SABOTEUR, SPARK):
        outcomes = [c for c in classify_clauses(card(name)) if c.text]
        assert {c.category for c in outcomes} == {HANDLED}, (name, outcomes)


# -- Dominion Saboteur ----------------------------------------------------------


def test_the_copy_of_a_legendary_creature_is_not_legendary():
    scenario = _board(SABOTEUR, bob=[ISAMARU])
    isamaru = scenario.creature(ISAMARU, "bob")

    copy = _cast(scenario, SABOTEUR, isamaru)

    chars = _chars(scenario, copy)
    assert chars.name == ISAMARU
    assert Supertype.LEGENDARY not in chars.supertypes
    assert Supertype.LEGENDARY in _chars(scenario, isamaru).supertypes, "the original is untouched"
    assert scenario.game.unreadable_copy_exception_notices == []


def test_a_nonlegendary_copy_escapes_the_legend_rule_when_you_control_the_original():
    """CR 704.5j: two legendary permanents with one name under one player are
    the rule's business; the copy is not legendary, so both stay."""
    scenario = _board(SABOTEUR, alice=[ISAMARU])
    isamaru = scenario.creature(ISAMARU, "alice")

    copy = _cast(scenario, SABOTEUR, isamaru)
    scenario.state_based_actions()

    assert copy.zone is Zone.BATTLEFIELD and isamaru.zone is Zone.BATTLEFIELD


def test_counters_of_the_copied_permanent_are_copied_by_number_and_kind():
    scenario = _board(SABOTEUR, bob=["Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.game.add_counters(bears, "+1/+1", 2)
    scenario.game.add_counters(bears, "shield", 1)

    copy = _cast(scenario, SABOTEUR, bears)

    assert copy.counter_count("+1/+1") == 2
    assert copy.counter_count("shield") == 1
    assert (copy.power, copy.toughness) == (4, 4), "the copied Bears' 2/2 plus two +1/+1 counters"
    assert bears.counter_count("+1/+1") == 2, "the original keeps its own"


def test_an_artifact_with_counters_can_be_copied_too():
    scenario = _board(SABOTEUR, bob=["Sol Ring"])
    ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "bob")
    scenario.game.add_counters(ring, "charge", 3)

    copy = _cast(scenario, SABOTEUR, ring)

    chars = _chars(scenario, copy)
    assert chars.name == "Sol Ring" and Type.ARTIFACT in chars.types
    assert copy.counter_count("charge") == 3


def test_a_copy_of_a_permanent_with_no_counters_enters_with_none():
    scenario = _board(SABOTEUR, bob=["Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears", "bob")

    copy = _cast(scenario, SABOTEUR, bears)

    assert not copy.counters.counts
    assert (copy.power, copy.toughness) == (2, 2)


def test_declining_the_copy_enters_as_itself_with_no_counters():
    """ "If you do": without the copy there is nothing to copy the counters
    from, so the Saboteur is its own printed 3/3... with none."""
    scenario = _board(SABOTEUR, bob=["Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.game.add_counters(bears, "+1/+1", 2)

    saboteur = _cast(scenario, SABOTEUR)

    assert _chars(scenario, saboteur).name == SABOTEUR
    assert not saboteur.counters.counts


def test_a_noncreature_nonartifact_permanent_is_not_a_candidate():
    scenario = _board(SABOTEUR, bob=["Island"])
    scenario.will_choose_cards(
        scenario.find("Island", Zone.BATTLEFIELD, "bob"), username="alice", source=SABOTEUR
    )

    saboteur = scenario.cast_and_resolve(SABOTEUR, *scenario.untapped_sources(*["Island"] * 5))

    assert _chars(scenario, saboteur).name == SABOTEUR, "a land is not an artifact or creature"


def test_copying_a_copy_takes_the_counters_it_has_now():
    """The second Saboteur copies the first (a Bears copy holding one +1/+1
    counter): the counters are read off the permanent copied as it is, once."""
    scenario = _board(SABOTEUR, bob=["Grizzly Bears"], hand=[SABOTEUR])
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.game.add_counters(bears, "+1/+1", 1)
    first = _cast(scenario, SABOTEUR, bears)
    assert first.counter_count("+1/+1") == 1

    for source in scenario.game.permanents_controlled_by("alice"):
        source.untap()
    scenario.will_choose_cards(first, username="alice", source=SABOTEUR)
    second = scenario.cast_and_resolve(SABOTEUR, *scenario.untapped_sources(*["Island"] * 5))

    assert _chars(scenario, second).name == "Grizzly Bears"
    assert second.counter_count("+1/+1") == 1


# -- Spark Double -----------------------------------------------------------------


def test_spark_double_copies_a_creature_with_a_plus_one_counter_and_not_legendary():
    scenario = _board(SPARK, alice=[ISAMARU])
    isamaru = scenario.creature(ISAMARU, "alice")

    copy = _cast(scenario, SPARK, isamaru)
    scenario.state_based_actions()

    chars = _chars(scenario, copy)
    assert chars.name == ISAMARU and Supertype.LEGENDARY not in chars.supertypes
    assert copy.counter_count("+1/+1") == 1
    assert (copy.power, copy.toughness) == (3, 3)
    assert copy.zone is Zone.BATTLEFIELD and isamaru.zone is Zone.BATTLEFIELD


def test_spark_double_copying_a_planeswalker_gets_one_extra_loyalty_not_a_plus_one_counter():
    scenario = _board(SPARK, alice=[LILIANA])
    liliana = scenario.find(LILIANA, Zone.BATTLEFIELD, "alice")

    copy = _cast(scenario, SPARK, liliana)
    scenario.state_based_actions()

    assert copy.counter_count("loyalty") == 4, "printed 3 (CR 306.5b) plus the additional one"
    assert copy.counter_count("+1/+1") == 0
    assert Supertype.LEGENDARY not in _chars(scenario, copy).supertypes
    assert liliana.zone is Zone.BATTLEFIELD, "no legend rule: the copy is not legendary"


def test_spark_double_cannot_copy_an_opponents_creature():
    scenario = _board(SPARK, bob=["Grizzly Bears"])
    scenario.will_choose_cards(
        scenario.creature("Grizzly Bears", "bob"), username="alice", source=SPARK
    )

    spark = scenario.cast_and_resolve(SPARK, *scenario.untapped_sources(*["Island"] * 5))

    assert _chars(scenario, spark).name == SPARK, "'you control' leaves bob's Bears out"


# -- the exception reader itself ---------------------------------------------------


@pytest.mark.parametrize(
    "tail",
    ["it isn't legendary", "it isn’t legendary", "it's not legendary", "it is not legendary"],
)
def test_the_exception_reader_takes_each_spelling_of_not_legendary(tail):
    from magic_cards_model.machines.replacement import _parse_copy_exception

    exception = _parse_copy_exception(tail)
    assert exception is not None and exception.not_legendary


def test_the_exception_reader_combines_it_with_the_other_exceptions():
    from magic_cards_model.machines.replacement import _parse_copy_exception

    exception = _parse_copy_exception("it has flying and it isn't legendary")
    assert exception is not None
    assert exception.not_legendary and exception.added_abilities == ("Flying",)


def test_the_exception_reader_still_refuses_an_unknown_tail():
    from magic_cards_model.machines.replacement import _parse_copy_exception

    assert _parse_copy_exception("it isn't legendary and it is purple-ish") is None
    assert _parse_copy_exception("it isn't blue") is None
