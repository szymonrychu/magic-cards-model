"""EP-01 round 1, task T2: "As [this] enters, choose ..." (CR 614.1c, 614.12a).

The choice is made before the permanent enters (CR 614.12a) by its controller,
through the engine's own `CHOOSE_A_QUALITY` question, and recorded on the
permanent (`CardState.choice`). Proven per shape with real printings:

- "choose Khans or Dragons" (the Siege cycle) and the matching half active: a
  "* Khans - At the beginning of ..." bullet is a triggered ability the
  permanent has only while its chosen mode is that word.
- "choose a card type [other than creature [or land]]", "choose artifact,
  creature, enchantment, instant, or sorcery".
- "choose a number [between 1 and 10]", "choose a planeswalker type",
  "choose a color word", "choose a noncreature, nonland card name".
- "look at an opponent's hand, then choose any card name / a card type other
  than creature".

CR numbers (looked up with `mise run rules:find`): 614.1c, 614.12a, 603.2,
201.4a, 300.1.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import DecisionKind
from magic_cards_model.models.card_state import Choice, ChoiceKind
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _board(hand=(), battlefield=(), opp_hand=(), start=Step.PRECOMBAT_MAIN):
    scenario = (
        Scenario()
        .player("alice", hand=list(hand), battlefield=list(battlefield))
        .player("bob", hand=list(opp_hand))
        .build()
    )
    if start is not None:
        scenario.start_at(start)
    return scenario


def _question(scenario, source):
    (question,) = [
        d
        for d in scenario.questions_asked()
        if d.kind is DecisionKind.CHOOSE_A_QUALITY and d.source == source
    ]
    return question


def _enter(scenario, name, answer):
    scenario.will_choose(answer, source=name)
    return scenario.put_onto_battlefield(name)


# -- Sieges: the choice and the matching half ----------------------------------


@pytest.mark.parametrize("siege", ["Citadel Siege", "Palace Siege", "Frontier Siege"])
def test_a_siege_offers_exactly_its_two_modes_and_records_the_answer(siege):
    scenario = _board(hand=[siege])
    permanent = _enter(scenario, siege, "Dragons")
    assert _question(scenario, siege).options == ("Khans", "Dragons")
    assert permanent.choice == Choice(kind=ChoiceKind.MODE, value="Dragons")


def test_a_siege_refuses_a_mode_it_does_not_print():
    scenario = _board(hand=["Citadel Siege"])
    scenario.will_choose("Abzan", source="Citadel Siege")
    with pytest.raises(ValueError, match="Abzan"):
        scenario.put_onto_battlefield("Citadel Siege")


def _resolve_all(scenario):
    while scenario.stack_names() or scenario.pending_triggers:
        scenario.game.put_triggers_on_stack()
        scenario.pass_until_resolved()


def _siege_board(siege, mode):
    scenario = (
        Scenario()
        .player("alice", hand=[siege], battlefield=["Grizzly Bears"], library=["Forest"] * 5)
        .player("bob", library=["Forest"] * 5)
        .build()
    )
    _enter(scenario, siege, mode)
    return scenario


def test_citadel_siege_khans_half_puts_counters_on_your_combat_and_dragons_half_does_not():
    khans = _siege_board("Citadel Siege", "Khans")
    khans.start_at(Step.PRECOMBAT_MAIN)
    bears = khans.find("Grizzly Bears", Zone.BATTLEFIELD, "alice")
    khans.advance()
    khans.choose_trigger_targets("Citadel Siege", [bears])
    _resolve_all(khans)
    assert bears.counters == {"+1/+1": 2}

    dragons = _siege_board("Citadel Siege", "Dragons")
    dragons.start_at(Step.PRECOMBAT_MAIN)
    dragons.advance()
    assert dragons.pending_triggers == []
    assert dragons.find("Grizzly Bears", Zone.BATTLEFIELD, "alice").counters == {}


def test_palace_siege_dragons_half_drains_on_your_upkeep_and_khans_half_does_not():
    dragons = _siege_board("Palace Siege", "Dragons")
    dragons.advance()
    _resolve_all(dragons)
    assert (dragons.player("alice").life, dragons.player("bob").life) == (22, 18)

    khans = _siege_board("Palace Siege", "Khans")
    khans.advance()
    assert khans.pending_triggers == []
    assert (khans.player("alice").life, khans.player("bob").life) == (20, 20)


# -- card types ------------------------------------------------------------------


def test_serras_emissary_chooses_any_card_type():
    scenario = _board(hand=["Serra's Emissary"])
    emissary = _enter(scenario, "Serra's Emissary", "creature")
    assert "sorcery" in _question(scenario, "Serra's Emissary").options
    assert emissary.choice == Choice(kind=ChoiceKind.CARD_TYPE, value="creature")


def test_stenn_cannot_choose_creature_or_land():
    scenario = _board(hand=["Stenn, Paranoid Partisan"])
    options = None
    scenario.will_choose("artifact", source="Stenn, Paranoid Partisan")
    scenario.put_onto_battlefield("Stenn, Paranoid Partisan")
    options = _question(scenario, "Stenn, Paranoid Partisan").options
    assert "creature" not in options and "land" not in options and "artifact" in options

    refused = _board(hand=["Stenn, Paranoid Partisan"])
    refused.will_choose("land", source="Stenn, Paranoid Partisan")
    with pytest.raises(ValueError, match="land"):
        refused.put_onto_battlefield("Stenn, Paranoid Partisan")


def test_cloud_key_offers_only_its_five_printed_types():
    scenario = _board(hand=["Cloud Key"])
    _enter(scenario, "Cloud Key", "instant")
    assert _question(scenario, "Cloud Key").options == (
        "artifact",
        "creature",
        "enchantment",
        "instant",
        "sorcery",
    )


# -- numbers, planeswalker types, color words ------------------------------------


def test_sanctum_prelate_chooses_a_number_and_refuses_a_non_number():
    scenario = _board(hand=["Sanctum Prelate"])
    prelate = _enter(scenario, "Sanctum Prelate", "7")
    assert prelate.choice == Choice(kind=ChoiceKind.NUMBER, value="7")

    refused = _board(hand=["Sanctum Prelate"])
    refused.will_choose("lots", source="Sanctum Prelate")
    with pytest.raises(ValueError, match="not a number"):
        refused.put_onto_battlefield("Sanctum Prelate")


def test_talion_chooses_a_number_between_one_and_ten():
    scenario = _board(hand=["Talion, the Kindly Lord"])
    talion = _enter(scenario, "Talion, the Kindly Lord", "10")
    assert talion.choice == Choice(kind=ChoiceKind.NUMBER, value="10")
    assert _question(scenario, "Talion, the Kindly Lord").options == tuple(
        str(n) for n in range(1, 11)
    )

    refused = _board(hand=["Talion, the Kindly Lord"])
    refused.will_choose("11", source="Talion, the Kindly Lord")
    with pytest.raises(ValueError, match="11"):
        refused.put_onto_battlefield("Talion, the Kindly Lord")


def test_deification_chooses_a_planeswalker_type():
    scenario = _board(hand=["Deification"])
    deification = _enter(scenario, "Deification", "Jace")
    assert deification.choice == Choice(kind=ChoiceKind.PLANESWALKER_TYPE, value="Jace")


def test_swirl_the_mists_chooses_a_color_word():
    scenario = _board(hand=["Swirl the Mists"])
    swirl = _enter(scenario, "Swirl the Mists", "red")
    assert swirl.choice == Choice(kind=ChoiceKind.COLOR_WORD, value="red")
    assert _question(scenario, "Swirl the Mists").options == (
        "white",
        "blue",
        "black",
        "red",
        "green",
    )


# -- card names, with and without looking at a hand ------------------------------


def test_council_of_the_absolute_names_a_noncreature_nonland_card():
    scenario = _board(hand=["Council of the Absolute"])
    council = _enter(scenario, "Council of the Absolute", "Lightning Bolt")
    assert council.choice == Choice(kind=ChoiceKind.CARD_NAME, value="Lightning Bolt")

    refused = _board(hand=["Council of the Absolute"])
    refused.will_choose("Grizzly Bears", source="Council of the Absolute")
    with pytest.raises(ValueError):
        refused.put_onto_battlefield("Council of the Absolute")


def test_sorcerous_spyglass_looks_at_the_opponents_hand_then_names_a_card():
    scenario = _board(hand=["Sorcerous Spyglass"], opp_hand=["Lightning Bolt", "Mountain"])
    spyglass = _enter(scenario, "Sorcerous Spyglass", "Lightning Bolt")
    question = _question(scenario, "Sorcerous Spyglass")
    assert set(question.cards) == {
        card.id for card in scenario.game.player("bob").hand
    }
    assert spyglass.choice == Choice(kind=ChoiceKind.CARD_NAME, value="Lightning Bolt")


def test_arachne_looks_at_the_hand_then_chooses_a_type_other_than_creature():
    scenario = _board(hand=["Arachne, Psionic Weaver"], opp_hand=["Lightning Bolt"])
    arachne = _enter(scenario, "Arachne, Psionic Weaver", "instant")
    question = _question(scenario, "Arachne, Psionic Weaver")
    assert len(question.cards) == 1 and "creature" not in question.options
    assert arachne.choice == Choice(kind=ChoiceKind.CARD_TYPE, value="instant")


def test_anointed_peacekeeper_names_any_card_after_looking():
    scenario = _board(hand=["Anointed Peacekeeper"], opp_hand=["Mountain"])
    peacekeeper = _enter(scenario, "Anointed Peacekeeper", "Mountain")
    assert peacekeeper.choice == Choice(kind=ChoiceKind.CARD_NAME, value="Mountain")
