"""Tom Bombadil: "Whenever the final chapter ability of a Saga you control
resolves, reveal cards from the top of your library until you reveal a Saga
card. Put that card onto the battlefield and the rest on the bottom of your
library in a random order. This ability triggers only once each turn."
(EP-01 R2, T2 residual clause).

CR numbers verified with `mise run rules:find`:

- CR 714.2e: a Saga's final chapter ability is the one with its final chapter
  number in its chapter symbol (History of Benalia's is III).
- CR 603.2h: "this ability triggers only if its source's controller has not
  yet taken the indicated action that turn" - one trigger per turn however
  many final chapters resolve.
- CR 701.20a: a reveal moves nothing; the cards stay on top until placed.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def _board(library, alice=("Tom Bombadil", "History of Benalia"), bob=()):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=list(alice), library=list(library))
        .player("bob", battlefield=list(bob), library=["Plains"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _drain(scenario) -> None:
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()


def _lore_step(scenario) -> None:
    scenario.game.saga_lore_step()
    _drain(scenario)


def _names(cards) -> list[str]:
    return [card.name for card in cards]


def _benalias(scenario, username="alice"):
    return [
        permanent
        for permanent in scenario.game.permanents_controlled_by(username)
        if permanent.name == "History of Benalia"
    ]


def test_the_final_chapter_resolving_reveals_to_a_saga_and_puts_it_onto_the_battlefield():
    scenario = _board(["Forest", "Island", "History of Benalia", "Plains", "Swamp"])
    _lore_step(scenario)  # chapter II
    assert len(_benalias(scenario)) == 1
    _lore_step(scenario)  # chapter III: the final chapter ability resolves

    benalias = _benalias(scenario)
    assert len(benalias) == 1, "the first Saga is sacrificed; the revealed one entered"
    assert benalias[0].counters[Counter.LORE] == 1
    library = scenario.player("alice").library
    assert _names(library)[:2] == ["Plains", "Swamp"]
    assert sorted(_names(library)[2:]) == ["Forest", "Island"], "the rest went to the bottom"


def test_a_lower_chapter_resolving_does_not_trigger_it():
    scenario = _board(["Forest", "History of Benalia", "Plains"])
    _lore_step(scenario)  # chapter II only

    assert len(_benalias(scenario)) == 1
    assert _names(scenario.player("alice").library) == ["Forest", "History of Benalia", "Plains"]


def test_it_triggers_only_once_each_turn_with_two_final_chapters():
    scenario = _board(
        ["Forest", "History of Benalia", "History of Benalia", "Plains"],
        alice=("Tom Bombadil", "History of Benalia", "History of Benalia"),
    )
    _lore_step(scenario)
    _lore_step(scenario)  # both Sagas reach chapter III this turn

    names = _names(scenario.player("alice").library)
    assert names.count("History of Benalia") == 1, "only one of the two triggers happened"
    assert len(_benalias(scenario)) == 1


def test_an_opponents_saga_reaching_its_final_chapter_does_not_trigger_it():
    scenario = _board(
        ["Forest", "History of Benalia", "Plains"],
        alice=("Tom Bombadil",),
        bob=("History of Benalia",),
    )
    saga = _benalias(scenario, "bob")[0]
    for _ in range(2):
        scenario.game.add_counters(saga, Counter.LORE, 1)
        _drain(scenario)

    assert saga.zone is Zone.GRAVEYARD
    assert _names(scenario.player("alice").library) == ["Forest", "History of Benalia", "Plains"]


def test_a_library_with_no_saga_reveals_everything_and_puts_nothing_onto_the_battlefield():
    scenario = _board(["Forest", "Island"])
    _lore_step(scenario)
    _lore_step(scenario)

    assert not _benalias(scenario)
    assert sorted(_names(scenario.player("alice").library)) == ["Forest", "Island"]
