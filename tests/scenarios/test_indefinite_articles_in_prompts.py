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


def test_a_subtype_cost_refusal_reads_is_not_an_ally():
    """Boiling Rock Rioter: "Tap an untapped Ally you control: Exile target card
    from a graveyard." The cost's quality is a subtype read from a capitalised
    noun, and a Grizzly Bears nominated for it is refused as "not an Ally"."""
    from magic_cards_model.machines.cost import cost_component_for_phrase

    scenario = (
        Scenario()
        .player("alice", battlefield=["Boiling Rock Rioter", "Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    rioter = scenario.creature("Boiling Rock Rioter", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    (printed,) = [line for line in rioter.card.oracle_text.split("\n") if line.startswith("Tap")]
    cost_phrase = printed.split(":", 1)[0]
    assert cost_phrase == "Tap an untapped Ally you control"

    component = cost_component_for_phrase(cost_phrase, "alice")
    assert component is not None and component.requirement is not None
    refusal = component.requirement.why_not(bears, scenario.game, "alice")

    assert refusal == "Grizzly Bears is not an Ally"
    assert component.requirement.why_not(rioter, scenario.game, "alice") is None


def test_an_animation_to_an_eight_eight_reads_becomes_an_8_8():
    """Jolrael, Voice of Zhalfir: "At the beginning of combat on your turn, up
    to one target land you control becomes an X/X green and blue Bird creature
    ... where X is the number of cards in your hand." With eight cards in hand
    the substituted P/T is 8/8, and the effect reads "becomes an 8/8"."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Island"] * 8,
            battlefield=["Jolrael, Voice of Zhalfir", "Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (forest,) = scenario.untapped_sources("Forest", username="alice")
    scenario.choose_trigger_targets("Jolrael, Voice of Zhalfir", [forest])
    scenario.advance()
    assert scenario.step is Step.BEGINNING_OF_COMBAT
    scenario.pass_until_resolved()
    assert scenario.game.characteristics_of(forest).power_toughness == (8, 8)

    descriptions = [effect.description for effect in scenario.game.continuous_effects.effects]
    assert any("becomes an 8/8 Bird" in description for description in descriptions), descriptions
    assert not any("becomes a 8/8" in description for description in descriptions)
