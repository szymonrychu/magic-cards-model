"""Devour (CR 702.82), read off the keyword itself.

CR 702.82a: "'Devour N' means 'As this object enters, you may sacrifice any
number of creatures. This permanent enters with N +1/+1 counters on it for
each creature sacrificed this way.'" CR 702.82c: "'Devour [quality] N' means
'As this object enters, you may sacrifice any number of [quality]
permanents. ...'"

The keyword line is expanded into exactly that pair of sentences and read by
the same CR 614.12a "[you may ]sacrifice any number of `<description>` ...
enters with `<multiplier>` that many `<kind>` counters" replacement that
Devouring Hellion's and Shimatsu's printed text already go through
(`scenarios/test_as_enters_sacrifice_that_many.py`) - no card name is read.

- Famished Worldsire, "Devour land 3" - the quality variant (CR 702.82c).
- Thunder-Thrash Elder, "Devour 3" - the plain creature form (CR 702.82a),
  a second printing added only for this proof.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import DecisionKind
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from magic_cards_model.support import ignored_keywords
from tests.cards import card

from .harness import Scenario

WORLDSIRE = "Famished Worldsire"
ELDER = "Thunder-Thrash Elder"


def test_devour_is_an_executed_keyword_on_both_forms():
    assert ignored_keywords(card(WORLDSIRE)) == []
    assert ignored_keywords(card(ELDER)) == []


def test_devour_land_sacrifices_lands_for_three_counters_each():
    """CR 702.82c: two lands devoured, three counters for each - six."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[WORLDSIRE],
            battlefield=["Forest", "Forest", "Grizzly Bears"],
            library=["Forest"] * 10,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    forests = [s for s in scenario.game.battlefield if s.name == "Forest"]
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice")
    scenario.will_choose_cards(*forests, source=WORLDSIRE)

    worldsire = scenario.put_onto_battlefield(WORLDSIRE, "alice")

    (asked,) = [
        q
        for q in scenario.questions_asked()
        if q.kind is DecisionKind.CHOOSE_CARDS and q.source == WORLDSIRE
    ]
    # CR 702.82c: only lands are offered - the Bears is not a land.
    assert set(asked.cards) == {forest.id for forest in forests}
    assert all(forest.zone is Zone.GRAVEYARD for forest in forests)
    assert bears.zone is Zone.BATTLEFIELD
    assert worldsire.counters[Counter.PLUS_ONE] == 6


def test_devouring_nothing_leaves_no_counters():
    """CR 107.1c: "any number of" includes zero."""
    scenario = (
        Scenario()
        .player("alice", hand=[ELDER], battlefield=["Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice")
    scenario.will_choose_cards(source=ELDER)

    elder = scenario.put_onto_battlefield(ELDER, "alice")

    assert bears.zone is Zone.BATTLEFIELD
    assert elder.counters[Counter.PLUS_ONE] == 0


def test_plain_devour_sacrifices_creatures_only():
    """CR 702.82a: creatures, three counters each; the Forest is never
    offered."""
    scenario = (
        Scenario()
        .player("alice", hand=[ELDER], battlefield=["Grizzly Bears", "Memnite", "Forest"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice")
    memnite = scenario.find("Memnite", Zone.BATTLEFIELD, "alice")
    forest = scenario.find("Forest", Zone.BATTLEFIELD, "alice")
    scenario.will_choose_cards(bears, memnite, source=ELDER)

    elder = scenario.put_onto_battlefield(ELDER, "alice")

    (asked,) = [
        q
        for q in scenario.questions_asked()
        if q.kind is DecisionKind.CHOOSE_CARDS and q.source == ELDER
    ]
    assert set(asked.cards) == {bears.id, memnite.id}
    assert forest.zone is Zone.BATTLEFIELD
    assert elder.counters[Counter.PLUS_ONE] == 6
