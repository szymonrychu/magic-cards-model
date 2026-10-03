"""Scenario: "exile any number of other nonland permanents you own and
control. Return those cards to the battlefield at the beginning of the next
end step." (Yorion, Sky Nomad's enters trigger.)

No targets: the permanents are chosen as the ability resolves (CR 107.1c's
"any number", zero included), only among those the controller both owns and
controls, never the source itself ("other"). Each is exiled; a token exiled
this way ceases to exist (CR 111.8, 704.5d) and never returns. An Aura
attached to an exiled permanent is put into its owner's graveyard by
state-based actions. A delayed triggered ability (CR 603.7a) returns the
cards together at the beginning of the next end step (CR 603.6a), under
their owner's control (CR 610.3c), as new objects (CR 400.7) - so an
enters ability triggers again. A returning Aura enchants what its
controller chooses as it enters (CR 303.4f), never a permanent returning
alongside it, and with nothing legal to enchant it stays in exile (CR
303.4g). A card that left exile before then is not returned (CR 603.7c).

Companion is Yorion's other ability and is handled by `machines/
companion.py`; it is not part of this file.

No second Modern/Pioneer/Standard printing carries the untargeted "exile
any number of other `<quality>` permanents you own and control" (Scryfall
full-text search, 2026-10-03); the return half is shared with Eerie
Interlude's targeted "Return those cards to the battlefield under their
owner's control at the beginning of the next end step", proven here too.

CR numbers verified with `mise run rules:find`: 107.1c, 111.8, 704.5d,
603.7a, 603.6a, 610.3c, 400.7, 303.4f, 303.4g, 603.7c.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import DecisionKind
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from magic_cards_model.models.token import is_token, token_copy_of
from magic_cards_model.support import card_support
from tests.cards import card

from .harness import Scenario

YORION = "Yorion, Sky Nomad"


def _settle(scenario):
    scenario.game.put_triggers_on_stack()
    while scenario.stack_names():
        scenario.pass_until_resolved()
        scenario.game.put_triggers_on_stack()


def _to_end_step(scenario):
    while scenario.step is not Step.END_STEP:
        _settle(scenario)
        scenario.advance()
    _settle(scenario)


def _board(*battlefield, bob_battlefield=()):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[YORION],
            battlefield=["Plains", *battlefield],
            library=["Plains"] * 10,
        )
        .player("bob", battlefield=list(bob_battlefield), library=["Plains"] * 10)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _yorion_enters(scenario):
    yorion = scenario.find(YORION, Zone.HAND)
    scenario.game.put_onto_battlefield(yorion, "alice")
    _settle(scenario)
    return yorion


def _yorion_question(scenario):
    return [
        q
        for q in scenario.questions_asked()
        if q.kind is DecisionKind.CHOOSE_CARDS and q.source == YORION
    ]


def test_yorion_and_the_return_half_are_handled():
    for name in (YORION, "Eerie Interlude"):
        bad = [c for c in card_support(card(name)).clauses if c.outcome != "handled"]
        assert not bad, (name, bad)


def test_exiled_permanents_return_together_as_new_objects_at_the_end_step():
    scenario = _board("Grizzly Bears", "Mind Stone")
    bears = scenario.creature("Grizzly Bears")
    stone = scenario.find("Mind Stone", Zone.BATTLEFIELD)
    scenario.game.add_counters(bears, Counter.PLUS_ONE, 1)
    stone.tap()
    scenario.will_choose_cards(bears, stone, source=YORION)
    _yorion_enters(scenario)
    assert bears.zone is Zone.EXILE and stone.zone is Zone.EXILE
    _to_end_step(scenario)
    bears_now = scenario.creature("Grizzly Bears")
    stone_now = scenario.find("Mind Stone", Zone.BATTLEFIELD)
    assert bears_now.controller == "alice" and stone_now.controller == "alice"
    # CR 400.7: new objects - no counters, untapped.
    assert bears_now.counter_count(Counter.PLUS_ONE) == 0
    assert not stone_now.tapped
    assert scenario.game.delayed_triggers.triggers == []


def test_only_other_nonland_permanents_you_own_and_control_are_offered():
    scenario = _board("Grizzly Bears", bob_battlefield=["Hill Giant"])
    bears = scenario.creature("Grizzly Bears")
    yorion = _yorion_enters(scenario)
    (question,) = _yorion_question(scenario)
    assert set(question.cards) == {bears.id}
    assert not question.exact  # CR 107.1c: any number, zero included
    assert yorion.id not in question.cards
    assert scenario.find("Plains", Zone.BATTLEFIELD).id not in question.cards


def test_exiling_zero_permanents_does_nothing_and_creates_no_delayed_trigger():
    scenario = _board("Grizzly Bears")
    bears = scenario.creature("Grizzly Bears")
    scenario.will_choose_cards(source=YORION)
    _yorion_enters(scenario)
    assert bears.zone is Zone.BATTLEFIELD
    assert scenario.game.delayed_triggers.triggers == []


def test_no_other_permanent_asks_nothing():
    scenario = _board()
    _yorion_enters(scenario)
    assert not _yorion_question(scenario)
    assert scenario.game.delayed_triggers.triggers == []


def test_an_exiled_token_ceases_to_exist_and_does_not_return():
    scenario = _board("Grizzly Bears")
    bears = scenario.creature("Grizzly Bears")
    (token,) = token_copy_of(scenario.game, bears, "alice")
    scenario.will_choose_cards(token, bears, source=YORION)
    _yorion_enters(scenario)
    assert not [c for c in scenario.game.battlefield if is_token(c)]
    _to_end_step(scenario)
    returned = [c for c in scenario.game.battlefield if c.name == "Grizzly Bears"]
    assert len(returned) == 1 and not is_token(returned[0])


def test_a_returning_enters_creature_triggers_again():
    scenario = _board("Wall of Omens")
    wall = scenario.find("Wall of Omens", Zone.BATTLEFIELD)
    hand_before = len(scenario.player("alice").hand)
    scenario.will_choose_cards(wall, source=YORION)
    _yorion_enters(scenario)
    assert len(scenario.player("alice").hand) == hand_before - 1  # Yorion left the hand
    _to_end_step(scenario)
    assert scenario.find("Wall of Omens", Zone.BATTLEFIELD)
    assert len(scenario.player("alice").hand) == hand_before  # drew off the new Wall


def test_a_returning_aura_enchants_a_permanent_already_there_not_one_returning_with_it():
    """CR 303.4f: the Aura's controller chooses as it enters; the creature
    returning in the same event is not on the battlefield yet to choose."""
    scenario = _board("Grizzly Bears", "Rancor")
    bears = scenario.creature("Grizzly Bears")
    rancor = scenario.find("Rancor", Zone.BATTLEFIELD)
    rancor.attach_to(bears)
    scenario.will_choose_cards(bears, rancor, source=YORION)
    yorion = _yorion_enters(scenario)
    assert rancor.zone is Zone.EXILE
    _to_end_step(scenario)
    rancor_now = scenario.find("Rancor", Zone.BATTLEFIELD)
    yorion_now = scenario.creature(YORION)
    assert yorion_now.id == yorion.id
    assert rancor_now.attached_to == yorion.id


def test_a_returning_aura_with_nothing_to_enchant_stays_in_exile():
    """CR 303.4g: no legal object, so the Aura remains in exile."""
    scenario = _board("Grizzly Bears", "Rancor")
    bears = scenario.creature("Grizzly Bears")
    rancor = scenario.find("Rancor", Zone.BATTLEFIELD)
    rancor.attach_to(bears)
    scenario.will_choose_cards(bears, rancor, source=YORION)
    yorion = _yorion_enters(scenario)
    scenario.game.exile_permanent(yorion)
    _to_end_step(scenario)
    assert scenario.creature("Grizzly Bears")
    assert scenario.find("Rancor", Zone.EXILE)


def test_an_aura_on_an_exiled_creature_goes_to_the_graveyard():
    """Rancor stays behind, is put into the graveyard by state-based actions
    once its creature is gone, and its own trigger returns it to hand."""
    scenario = _board("Grizzly Bears", "Rancor")
    bears = scenario.creature("Grizzly Bears")
    rancor = scenario.find("Rancor", Zone.BATTLEFIELD)
    rancor.attach_to(bears)
    scenario.will_choose_cards(bears, source=YORION)
    _yorion_enters(scenario)
    assert rancor.zone is Zone.HAND
    _to_end_step(scenario)
    assert scenario.creature("Grizzly Bears")


def test_a_card_that_left_exile_is_not_returned():
    scenario = _board("Grizzly Bears", "Mind Stone")
    bears = scenario.creature("Grizzly Bears")
    stone = scenario.find("Mind Stone", Zone.BATTLEFIELD)
    scenario.will_choose_cards(bears, stone, source=YORION)
    _yorion_enters(scenario)
    scenario.game.put_into_graveyard(bears)
    _to_end_step(scenario)
    assert bears.zone is Zone.GRAVEYARD
    assert scenario.find("Mind Stone", Zone.BATTLEFIELD)
