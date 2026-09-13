"""Generated prompts and refusals use the right indefinite article.

Battle report B6-10: Karn, the Great Creator's -2 prompted "reveal a artifact
card you own from outside the game ..." and "choose a artifact card you own to
put into your hand". The fix is the shared phrase builder
(`magic_cards_model.phrases`), so the same noun phrase reads correctly wherever
the engine generates one, not only on Karn's prompt.

Karn's text (printing in the pool): "-2: You may reveal an artifact card you
own from outside the game or choose a face-up artifact card you own in exile.
Put that card into your hand."
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import DecisionKind
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

KARN_MINUS_TWO = 1


def test_karns_prompts_read_an_artifact_card():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            library=["Mountain"] * 5,
            battlefield=["Karn, the Great Creator"],
            sideboard=["Grafdigger's Cage"],
        )
        .player("bob", library=["Mountain"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    karn = scenario.find("Karn, the Great Creator", Zone.BATTLEFIELD)
    alice = scenario.player("alice")
    (cage,) = [state for state in alice.outside_the_game if state.name == "Grafdigger's Cage"]

    scenario.will_choose_cards(cage, username="alice")
    scenario.activate(karn, index=KARN_MINUS_TWO)
    scenario.pass_until_resolved()

    prompts = [
        question.prompt
        for question in scenario.questions_asked()
        if question.source == "Karn, the Great Creator"
    ]
    may = [
        q.prompt
        for q in scenario.questions_asked()
        if q.kind is DecisionKind.MAY and q.source == "Karn, the Great Creator"
    ]
    assert may and may[0].startswith("reveal an artifact card you own from outside the game")
    assert any(prompt.startswith("choose an artifact card you own") for prompt in prompts)
    assert not any(" a artifact" in prompt for prompt in prompts)


def test_a_target_refusal_reads_needs_an_artifact():
    """Wear // Tear's Wear: "Destroy target artifact." A creature is refused, and
    the refusal names the wanted type with its article."""
    scenario = Scenario().player("alice", battlefield=["Grizzly Bears"]).player("bob").build()
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD)
    from magic_cards_model.machines.targeting import profile_for_text

    profile = profile_for_text("Destroy target artifact.")
    refusal = profile.requirements[0].rejects(bears, "bob", scenario.game)

    assert refusal is not None
    assert "needs an artifact" in refusal
