""" "Look at the top N cards of your library. Put one into your hand and the
other into your graveyard." - `_merge_look_top_split_hand_graveyard_clauses`
in `machines/effects.py`, which reads `Game.look_at_top_and_split`'s own CR
608.2d question (the same one `scry`/`surveil` already ask, generalised past
their fixed pair of destinations - see `test_off_battlefield_activation.py`'s
own Waker of Waves coverage for that primitive's origin).

Codecracker Hound is the vehicle here rather than Waker of Waves: its own
printed sentence elides "of them" ("Put one into your hand", not "Put one of
them into your hand"), which `_PUT_N_OF_THEM_INTO_YOUR_HAND_RE` has to read
as the same shape - the fix this file is here to prove, and the reason it
exists as its own scenario rather than only extending Waker of Waves'.

Verified this session with `knowledge_search(q="...", type="rules")`:

- **CR 608.2d** - "The player can't choose an option that's illegal or
  impossible" - an exactly-one-to-hand, rest-to-graveyard split is the only
  legal answer, which is what `look_at_top_and_split`'s caller enforces.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import CardSplit, DecisionKind, ScriptedAnswer
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_codecracker_hound_puts_one_card_in_hand_and_the_other_in_the_graveyard():
    """Both halves of one CR 608.2c instruction, off Codecracker Hound's own
    "of them"-less wording."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Codecracker Hound"],
            library=["Lightning Bolt", "Forest"],
            battlefield=["Island", "Island", "Island"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bolt, forest = scenario.top_of_library(2)
    sources = scenario.untapped_sources("Island", "Island", "Island")

    scenario.game.decisions.add(
        ScriptedAnswer(kind=DecisionKind.SCRY, value=CardSplit(moved=(bolt.id,)), player="alice")
    )

    scenario.cast_and_resolve("Codecracker Hound", *sources)
    scenario.pass_until_resolved()

    alice = scenario.player("alice")
    assert bolt.zone is Zone.HAND
    assert bolt in alice.hand
    assert forest.zone is Zone.GRAVEYARD
    assert forest in alice.graveyard
    assert alice.library == []


def test_choosing_the_other_card_for_hand_sends_the_first_one_to_the_graveyard():
    """The controller's own unstated choice (CR 608.2d) - the split is not
    fixed to "first card looked at goes to hand"."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Codecracker Hound"],
            library=["Lightning Bolt", "Forest"],
            battlefield=["Island", "Island", "Island"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bolt, forest = scenario.top_of_library(2)
    sources = scenario.untapped_sources("Island", "Island", "Island")

    scenario.game.decisions.add(
        ScriptedAnswer(kind=DecisionKind.SCRY, value=CardSplit(moved=(forest.id,)), player="alice")
    )

    scenario.cast_and_resolve("Codecracker Hound", *sources)
    scenario.pass_until_resolved()

    assert forest.zone is Zone.HAND
    assert bolt.zone is Zone.GRAVEYARD
