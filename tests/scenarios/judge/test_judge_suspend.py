"""Judge scenarios: whose suspend is it, once someone else did the exiling.

Sourced from the DDR judge transcripts. Episode covered:

- **DDR#979** - "Casting Another Player's Suspended Sentence". Amy resolves
  Nick's Suspended Sentence (a card she is casting from Nick's library through
  another effect). Its last line exiles it with three time counters, and Amy,
  as the spell's controller, is the player who carries that instruction out.
  Who then removes a time counter each upkeep, and who casts it when the last
  one comes off?

The ruling is **Nick, its owner** - and the reason is entirely general: CR
109.5 says "the words 'you' and 'your' on an object refer to the object's
controller, its would-be controller (if a player is attempting to play, cast,
or activate it), or its owner (if it has no controller)". A card sitting in
exile has no controller, so suspend's own second and third abilities - both
worded "at the beginning of **your** upkeep" and "**you** may play it" (CR
702.62a) - land on the owner. Nothing about how the card *got* there is read
at all. The episode contrasts this with adventure, where the permission to
cast the exiled half is handed to the player who controlled the adventure
spell as it resolved, so the answer there is the opposite.

Every CR number here was looked up with `knowledge_search(type="rules")` in
the session that wrote this file, and every card's text with `resolve_cards`.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.casting import (
    MarkedExile,
    annotate_exile,
    finish_suspend,
)
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter, ExileMarker
from tests.scenarios.harness import PlayedScenario, Scenario

# Suspended Sentence, verified with `resolve_cards`:
#   "Destroy target creature an opponent controls. That player loses 3 life.
#    Exile Suspended Sentence with three time counters on it.
#    Suspend 3—{1}{B}"
# Both halves matter here: the spell's own last line is what puts the card
# back into the suspended pile after somebody else has cast it, and the
# printed "Suspend 3—{1}{B}" keyword is what makes it suspended once there
# (CR 702.62b).


def test_suspended_sentences_own_self_exile_clause_is_executed():
    """The premise state is reachable through the card itself: its whole
    paragraph - "Destroy target creature an opponent controls. That player
    loses 3 life. Exile Suspended Sentence with three time counters on it." -
    is read, the last sentence by the self-exile-with-time-counters reader
    (`tests/scenarios/test_self_exile_with_time_counters.py`), so the
    resolving spell lands in exile suspended rather than in a graveyard.
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Suspended Sentence"], battlefield=["Swamp"] * 4)
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", username="bob")

    sentence = scenario.cast_and_resolve(
        "Suspended Sentence", *scenario.untapped_sources(*["Swamp"] * 4), targets=[bears]
    )

    assert bears.zone is Zone.GRAVEYARD
    assert sentence.zone is Zone.EXILE
    assert sentence.counter_count(Counter.TIME) == 3
    assert sentence.is_suspended


def _suspend_own_card(scenario: PlayedScenario, username: str) -> None:
    """The ordinary CR 116.2f route: a player suspends a card from their own
    hand, paying Suspended Sentence's own "Suspend 3—{1}{B}"."""
    sentence = scenario.find("Suspended Sentence", Zone.HAND, username)
    action = MarkedExile.suspend(scenario.game, sentence, username)
    payment = action.begin_paying()
    sources = scenario.untapped_sources("Swamp", "Swamp", username=username)
    scenario.pay_with(payment, *sources)
    action.take()


def test_the_owner_who_suspended_their_own_card_gets_the_free_cast():
    """The control case, and the half the engine already gets right.

    CR 116.2f: "A player who has a card with suspend in their hand may exile
    that card." When the player who takes that special action is also the
    card's owner - the only way CR 116.2f can ever fire - CR 109.5's "owner
    (if it has no controller)" and "whoever exiled it" name the same person,
    so `finish_suspend` casts it for bob either way (CR 608.2g).
    This is what makes the next test's failure a real disagreement rather
    than suspend being broken outright.
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Grizzly Bears"])
        .player("bob", hand=["Suspended Sentence"], battlefield=["Swamp", "Swamp"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _suspend_own_card(scenario, "bob")

    sentence = scenario.find("Suspended Sentence", Zone.EXILE, "bob")
    assert sentence.counter_count(Counter.TIME) == 3
    for _ in range(3):
        sentence.remove_counters(Counter.TIME, 1)

    spell = finish_suspend(scenario.game, sentence)
    assert spell is not None
    assert scenario.game.controller_of(spell).username == "bob"
    assert scenario.game.cast_record_of(spell).keyword == "Suspend"


def test_the_owner_casts_a_card_someone_else_suspended():
    """DDR#979: Amy exiles it, Nick removes the counters and casts it.

    The board is the state the episode's spell leaves behind: Suspended
    Sentence is in exile, owned by bob (CR 108.3 - the owner is the player who
    started the game with it, which is what `Scenario.player(exile=[...])`
    stamps), marked as CR 702.62b suspended with three time counters, and the
    player who *did* the exiling was alice, because she was the one carrying
    out the resolving spell's instructions. `annotate_exile` and
    `Game.add_counters` are the engine's own two halves of "exile it with N
    time counters on it" (`MarkedExile.take` calls exactly these), used
    directly here to stage the episode's exact split - alice exiling, bob
    owning - which casting the card from alice's own hand cannot produce.

    CR 400.7 does not rescue the wrong answer either: the card is a new object
    each time it changes zones, with no memory of who cast it - which is
    precisely why the episode says the answer never depends on the
    circumstances of how the card became suspended, and stays the same every
    subsequent time it comes off suspend.
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Swamp", "Grizzly Bears"])
        .player("bob", exile=["Suspended Sentence"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sentence = scenario.find("Suspended Sentence", Zone.EXILE, "bob")
    assert sentence.owner == "bob"

    # Alice controlled the spell as it resolved, so alice is the player who
    # exiled it (CR 608.2's "the spell's controller carries out its
    # instructions" - the episode's own opening point).
    annotate_exile(sentence, ExileMarker.SUSPENDED, "alice", scenario.game)
    scenario.game.add_counters(sentence, Counter.TIME, 3)
    assert sentence.is_suspended is True

    for _ in range(3):
        sentence.remove_counters(Counter.TIME, 1)

    spell = finish_suspend(scenario.game, sentence)
    assert spell is not None
    assert scenario.game.controller_of(spell).username == "bob", (
        "CR 109.5: the owner, not the player who exiled it"
    )


def test_the_answer_is_the_owner_whichever_side_of_the_table_exiled_it():
    """The mirror of the episode, so "the owner" cannot regress into "whoever is
    not the exiler", "the active player", or "the exiler" again.

    Same shape with the roles swapped: alice owns the card (CR 108.3) and bob
    performed the exile, so the CR 702.62a free cast is alice's. Together with
    `test_the_owner_who_suspended_their_own_card_gets_the_free_cast` - the
    ordinary CR 116.2f route, where the owner exiles their own card - the three
    cases pin the answer to the owner in every arrangement the engine can be
    handed.
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", exile=["Suspended Sentence"])
        .player("bob", battlefield=["Swamp", "Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sentence = scenario.find("Suspended Sentence", Zone.EXILE, "alice")
    assert sentence.owner == "alice"

    annotate_exile(sentence, ExileMarker.SUSPENDED, "bob", scenario.game)
    scenario.game.add_counters(sentence, Counter.TIME, 3)
    for _ in range(3):
        sentence.remove_counters(Counter.TIME, 1)

    spell = finish_suspend(scenario.game, sentence)
    assert spell is not None
    assert scenario.game.controller_of(spell).username == "alice", (
        "CR 109.5: the owner, not the player who exiled it"
    )
