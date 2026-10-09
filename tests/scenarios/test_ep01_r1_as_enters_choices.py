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

- "As ~ enters, it becomes your choice of ..." and the coin-flip body
  (Corrupted Shapeshifter, Primal Plasma, Aquamorph Entity, Molten Sentry), "as
  it enters or is turned face up" (CR 614.1e), face-down and copy-choice
  shapes (Ixidron, Crowd-Control Warden, Vesuvan Shapeshifter), exile from your
  graveyard as it enters (Sutured Ghoul, Living Lore), enters attached
  (Grifter's Blade) and "you get an emblem" (Tibalt).

CR numbers (looked up with `mise run rules:find`): 614.1c, 614.12a, 603.2,
201.4a, 300.1, 614.1e, 708.2, 708.8, 607.2a, 114.2, 305.6.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import DecisionKind
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Choice, ChoiceKind
from magic_cards_model.models.token import TokenDefinition, create_tokens
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


def test_frontier_siege_khans_half_adds_mana_each_main_phase_and_dragons_half_does_not():
    def floating_green(mode):
        scenario = (
            Scenario()
            .player("alice", hand=["Frontier Siege"], library=["Forest"] * 5)
            .player("bob", library=["Forest"] * 5)
            .build()
        )
        _enter(scenario, "Frontier Siege", mode)
        scenario.start_at(Step.UPKEEP)
        while scenario.step is not Step.PRECOMBAT_MAIN:
            scenario.advance()
        _resolve_all(scenario)
        pool = scenario.game.unspent_mana_of(scenario.player("alice")).floating
        return sum(amount for color, amount in pool.items() if color.value == "G")

    assert floating_green("Khans") == 2
    assert floating_green("Dragons") == 0


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
    assert set(question.cards) == {card.id for card in scenario.game.player("bob").hand}
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


# -- choosing a permanent -----------------------------------------------------------


def _object_choice(scenario, source_name):
    return scenario.find(source_name, Zone.BATTLEFIELD, "alice").choice


def test_dauntless_bodyguard_chooses_another_creature_you_control():
    scenario = _board(hand=["Dauntless Bodyguard"], battlefield=["Grizzly Bears"])
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice")
    scenario.will_choose_cards(bears, source="Dauntless Bodyguard")
    scenario.put_onto_battlefield("Dauntless Bodyguard")
    assert _object_choice(scenario, "Dauntless Bodyguard") == Choice(
        kind=ChoiceKind.OBJECT, value=str(bears.id)
    )


def test_tyrannical_pitlord_cannot_choose_itself_or_an_opponents_creature():
    scenario = _board(hand=["Tyrannical Pitlord"], battlefield=["Grizzly Bears"])
    theirs = (
        Scenario()
        .player("alice", hand=["Tyrannical Pitlord"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    theirs.start_at(Step.PRECOMBAT_MAIN)
    theirs.put_onto_battlefield("Tyrannical Pitlord")
    assert theirs.find("Tyrannical Pitlord", Zone.BATTLEFIELD, "alice").choice is None
    assert scenario.questions_asked() == []


def test_metamorphic_alteration_chooses_any_creature():
    scenario = (
        Scenario()
        .player("alice", hand=["Metamorphic Alteration"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    theirs = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "bob")
    scenario.will_choose_cards(theirs, source="Metamorphic Alteration")
    scenario.put_onto_battlefield("Metamorphic Alteration")
    assert _object_choice(scenario, "Metamorphic Alteration") == Choice(
        kind=ChoiceKind.OBJECT, value=str(theirs.id)
    )


def test_scheming_fence_may_decline_to_choose():
    scenario = _board(hand=["Scheming Fence"], battlefield=["Citadel Siege"])
    scenario.will_take_the_may(False)
    scenario.put_onto_battlefield("Scheming Fence")
    assert _object_choice(scenario, "Scheming Fence") is None


def test_scheming_fence_chooses_a_nonland_permanent_when_it_may():
    scenario = _board(hand=["Scheming Fence"], battlefield=["Citadel Siege", "Mountain"])
    siege = scenario.find("Citadel Siege", Zone.BATTLEFIELD, "alice")
    scenario.will_take_the_may(True)
    scenario.will_choose_cards(siege, source="Scheming Fence")
    scenario.put_onto_battlefield("Scheming Fence")
    assert _object_choice(scenario, "Scheming Fence") == Choice(
        kind=ChoiceKind.OBJECT, value=str(siege.id)
    )


# -- other as-enters actions --------------------------------------------------------


def test_phylactery_lich_puts_its_counter_on_an_artifact_you_control():
    scenario = _board(hand=["Phylactery Lich"], battlefield=["Smuggler's Copter"])
    scenario.put_onto_battlefield("Phylactery Lich")
    copter = scenario.find("Smuggler's Copter", Zone.BATTLEFIELD, "alice")
    assert copter.counters == {"phylactery": 1}


def test_phylactery_lich_with_no_artifact_puts_no_counter():
    scenario = _board(hand=["Phylactery Lich"], battlefield=["Grizzly Bears"])
    scenario.put_onto_battlefield("Phylactery Lich")
    assert scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice").counters == {}


def test_sigardas_splendor_notes_your_life_total_as_it_enters():
    scenario = _board(hand=["Sigarda's Splendor"])
    scenario.player("alice").life = 13
    splendor = scenario.put_onto_battlefield("Sigarda's Splendor")
    assert splendor.choice == Choice(kind=ChoiceKind.NUMBER, value="13")


def test_alhammarret_reveals_the_opponents_hand_and_names_a_nonland_card_from_it():
    scenario = _board(hand=["Alhammarret, High Arbiter"], opp_hand=["Lightning Bolt", "Mountain"])
    alhammarret = _enter(scenario, "Alhammarret, High Arbiter", "Lightning Bolt")
    assert _question(scenario, "Alhammarret, High Arbiter").options == ("Lightning Bolt",)
    assert sorted(shown.card_name for shown in scenario.game.reveals) == [
        "Lightning Bolt",
        "Mountain",
    ]
    assert alhammarret.choice == Choice(kind=ChoiceKind.CARD_NAME, value="Lightning Bolt")


def _cast_kicked(scenario, name, *, kicked):  # noqa: C901
    casting = scenario.cast(name)
    if kicked:
        casting.pay_kicker(which="{B}") if name == "Urborg Lhurgoyf" else casting.pay_kicker()
    payment = casting.begin_paying()
    scenario.auto_pay(payment)
    scenario.put_on_stack(casting)
    scenario.resolve_top()


@pytest.mark.parametrize(
    ("name", "kicked", "milled"),
    [
        ("Monstrous War-Leech", True, 4),
        ("Monstrous War-Leech", False, 0),
        ("Urborg Lhurgoyf", True, 3),
        ("Urborg Lhurgoyf", False, 0),
    ],
)
def test_kicker_mills_as_the_creature_enters(name, kicked, milled):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[name],
            battlefield=["Swamp"] * 8 + ["Island"] * 3 + ["Forest"] * 3,
            library=["Forest"] * 10,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _cast_kicked(scenario, name, kicked=kicked)
    assert len(scenario.player("alice").graveyard) == milled
    assert len(scenario.player("alice").library) == 10 - milled


# -- the entering permanent becomes your choice of a body (CR 614.1c, 613.4b) ----


def _chars(scenario, permanent):
    return scenario.game.computed_board().of(permanent)


def _keywords(scenario, permanent):
    return {k.lower() for k in _chars(scenario, permanent).abilities}


@pytest.mark.parametrize(
    ("name", "answer", "power_toughness", "keyword"),
    [
        ("Corrupted Shapeshifter", "3/3 creature with flying", (3, 3), "flying"),
        ("Corrupted Shapeshifter", "2/5 creature with vigilance", (2, 5), "vigilance"),
        ("Corrupted Shapeshifter", "0/12 creature with defender", (0, 12), "defender"),
        ("Primal Plasma", "3/3 creature", (3, 3), None),
        ("Primal Plasma", "2/2 creature with flying", (2, 2), "flying"),
        ("Primal Plasma", "1/6 creature with defender", (1, 6), "defender"),
        ("Aquamorph Entity", "5/1", (5, 1), None),
        ("Aquamorph Entity", "1/5", (1, 5), None),
    ],
)
def test_a_chosen_body_sets_base_power_toughness_and_abilities(
    name, answer, power_toughness, keyword
):
    scenario = _board(hand=[name])
    permanent = _enter(scenario, name, answer)
    assert (_chars(scenario, permanent).power, _chars(scenario, permanent).toughness) == (
        power_toughness
    )
    keywords = _keywords(scenario, permanent)
    for other in ("flying", "vigilance", "defender"):
        assert (other in keywords) == (other == keyword), other


def test_a_chosen_body_offers_exactly_the_printed_bodies_and_refuses_another():
    scenario = _board(hand=["Primal Plasma"])
    scenario.will_choose("9/9 creature", source="Primal Plasma")
    with pytest.raises(ValueError, match="9/9"):
        scenario.put_onto_battlefield("Primal Plasma")
    scenario = _board(hand=["Primal Plasma"])
    _enter(scenario, "Primal Plasma", "3/3 creature")
    assert _question(scenario, "Primal Plasma").options == (
        "3/3 creature",
        "2/2 creature with flying",
        "1/6 creature with defender",
    )


def test_a_chosen_body_keeps_counters_on_top_of_the_set_base():
    """Layer 7b sets the base, layer 7c adds counters on top (CR 613.4b-c)."""
    scenario = _board(hand=["Corrupted Shapeshifter"])
    permanent = _enter(scenario, "Corrupted Shapeshifter", "2/5 creature with vigilance")
    scenario.game.add_counters(permanent, "+1/+1", 2, putter="alice")
    assert (_chars(scenario, permanent).power, _chars(scenario, permanent).toughness) == (4, 7)


def test_molten_sentry_enters_as_one_of_two_bodies_by_the_coin():
    outcomes = {}
    for flips in range(8):
        scenario = _board(hand=["Molten Sentry"])
        scenario.game.coin_flips_performed = flips
        sentry = scenario.put_onto_battlefield("Molten Sentry")
        chars = _chars(scenario, sentry)
        keywords = _keywords(scenario, sentry)
        assert sentry.choice is not None
        assert sentry.choice.kind is ChoiceKind.COIN
        if sentry.choice.value == "heads":
            assert ((chars.power, chars.toughness), "haste" in keywords) == ((5, 2), True)
            assert "defender" not in keywords
        else:
            assert sentry.choice.value == "tails"
            assert ((chars.power, chars.toughness), "defender" in keywords) == ((2, 5), True)
            assert "haste" not in keywords
        outcomes[sentry.choice.value] = True
    assert set(outcomes) == {"heads", "tails"}


# -- as it enters or is turned face up (CR 614.1e, 708.8) --------------------------


def _face_down(scenario, name, keyword, *mana):
    casting = scenario.cast(name)
    casting.use_keyword(keyword)
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources(*mana))
    scenario.put_on_stack(casting)
    return scenario.resolve_top()


def _face_down_board(hand, lands, land="Island", extra=()):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=[hand], battlefield=[land] * lands + list(extra))
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_aquamorph_entity_chooses_again_when_it_is_turned_face_up():
    scenario = _face_down_board("Aquamorph Entity", 6)
    permanent = _face_down(scenario, "Aquamorph Entity", "Morph", "Island", "Island", "Island")
    assert permanent.face_down
    assert [d for d in scenario.questions_asked() if d.source == "Aquamorph Entity"] == []
    scenario.will_choose("1/5", source="Aquamorph Entity")
    turned = scenario.turn_face_up(
        permanent, *scenario.untapped_sources("Island", "Island", "Island")
    )
    assert (turned.power, turned.toughness) == (1, 5)
    assert _question(scenario, "Aquamorph Entity").options == ("5/1", "1/5")


def test_crowd_control_warden_enters_with_a_counter_per_other_creature():
    scenario = _board(
        hand=["Crowd-Control Warden"], battlefield=["Grizzly Bears", "Llanowar Elves"]
    )
    warden = scenario.put_onto_battlefield("Crowd-Control Warden")
    assert warden.counters == {"+1/+1": 2}


def test_crowd_control_warden_with_no_other_creature_enters_bare():
    scenario = _board(hand=["Crowd-Control Warden"], battlefield=["Mountain"])
    assert scenario.put_onto_battlefield("Crowd-Control Warden").counters == {}


def test_crowd_control_warden_counts_the_creatures_you_control_when_turned_face_up():
    scenario = _face_down_board(
        "Crowd-Control Warden", 8, land="Forest", extra=["Grizzly Bears", "Llanowar Elves"]
    )
    permanent = _face_down(
        scenario, "Crowd-Control Warden", "Disguise", "Forest", "Forest", "Forest"
    )
    assert permanent.counters == {}
    turned = scenario.turn_face_up(permanent, *scenario.untapped_sources(*["Forest"] * 5))
    assert turned.counters == {"+1/+1": 2}


# -- Vesuvan Shapeshifter: a copy until it is turned face down (CR 707.2, 708.8) --


def _vesuvan(*, take, choose=None):
    scenario = _board(hand=["Vesuvan Shapeshifter"], battlefield=["Serra Angel"])
    scenario.will_take_the_may(take, source="Vesuvan Shapeshifter")
    if choose is not None:
        scenario.will_choose_cards(
            scenario.find(choose, Zone.BATTLEFIELD, "alice"), source="Vesuvan Shapeshifter"
        )
    return scenario, scenario.put_onto_battlefield("Vesuvan Shapeshifter")


def test_vesuvan_shapeshifter_becomes_a_copy_of_the_creature_it_chooses():
    scenario, vesuvan = _vesuvan(take=True, choose="Serra Angel")
    chars = _chars(scenario, vesuvan)
    assert chars.name == "Serra Angel"
    assert (chars.power, chars.toughness) == (4, 4)
    assert "flying" in _keywords(scenario, vesuvan)
    assert any("turn this creature face down" in line for line in chars.abilities)


def test_vesuvan_shapeshifter_that_declines_stays_itself():
    scenario, vesuvan = _vesuvan(take=False)
    assert _chars(scenario, vesuvan).name == "Vesuvan Shapeshifter"
    assert vesuvan.choice is None


def test_vesuvan_shapeshifter_stops_being_a_copy_when_turned_face_down():
    scenario, vesuvan = _vesuvan(take=True, choose="Serra Angel")
    vesuvan.turn_face_down()
    chars = _chars(scenario, vesuvan)
    assert chars.name != "Serra Angel"
    assert (chars.power, chars.toughness) == (2, 2)
    assert "flying" not in _keywords(scenario, vesuvan)


def test_vesuvan_shapeshifter_chooses_again_when_turned_face_up():
    scenario = _face_down_board("Vesuvan Shapeshifter", 6, extra=["Serra Angel"])
    permanent = _face_down(scenario, "Vesuvan Shapeshifter", "Morph", "Island", "Island", "Island")
    assert _chars(scenario, permanent).name != "Serra Angel"
    scenario.will_take_the_may(True, source="Vesuvan Shapeshifter")
    scenario.will_choose_cards(
        scenario.find("Serra Angel", Zone.BATTLEFIELD, "alice"), source="Vesuvan Shapeshifter"
    )
    turned = scenario.turn_face_up(permanent, *scenario.untapped_sources("Island", "Island"))
    assert _chars(scenario, turned).name == "Serra Angel"


# -- Ixidron: turn all other nontoken creatures face down (CR 708.2) ---------------


def test_ixidron_turns_every_other_creature_face_down_and_counts_them():
    scenario = _board(
        hand=["Ixidron"],
        battlefield=["Grizzly Bears", "Mountain"],
        opp_hand=[],
    )
    ixidron = scenario.put_onto_battlefield("Ixidron")
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice")
    mountain = scenario.find("Mountain", Zone.BATTLEFIELD, "alice")
    assert bears.face_down
    assert not mountain.face_down
    assert not ixidron.face_down
    # One face-down creature: Ixidron is 1/1.
    assert (_chars(scenario, ixidron).power, _chars(scenario, ixidron).toughness) == (1, 1)
    assert (_chars(scenario, bears).power, _chars(scenario, bears).toughness) == (2, 2)


def test_ixidron_also_turns_the_opponents_creatures_face_down():
    scenario = (
        Scenario()
        .player("alice", hand=["Ixidron"])
        .player("bob", battlefield=["Serra Angel", "Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ixidron = scenario.put_onto_battlefield("Ixidron")
    assert all(
        state.face_down
        for state in scenario.game.battlefield
        if state.name != "Ixidron" or state.face_down
    )
    assert (_chars(scenario, ixidron).power, _chars(scenario, ixidron).toughness) == (2, 2)


def test_ixidron_leaves_tokens_face_up():
    """ "Nontoken": a token creature is not turned face down (CR 708.2)."""
    scenario = _board(hand=["Ixidron"], battlefield=["Grizzly Bears"])
    (token,) = create_tokens(
        scenario.game, TokenDefinition(power=1, toughness=1, subtypes=("Soldier",)), "alice"
    )
    scenario.put_onto_battlefield("Ixidron")
    assert not token.face_down
    assert scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice").face_down


# -- exile from your graveyard as it enters (CR 607.2a) ----------------------------


def test_sutured_ghoul_exiles_creature_cards_and_sums_their_power_and_toughness():
    scenario = _board(
        hand=["Sutured Ghoul"],
        battlefield=[],
    )
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Sutured Ghoul"],
            graveyard=["Grizzly Bears", "Serra Angel", "Lightning Bolt"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")
    angel = scenario.find("Serra Angel", Zone.GRAVEYARD, "alice")
    scenario.will_choose_cards(bears, angel, source="Sutured Ghoul")
    ghoul = scenario.put_onto_battlefield("Sutured Ghoul")
    assert bears.zone is Zone.EXILE and angel.zone is Zone.EXILE
    assert scenario.find("Lightning Bolt", Zone.GRAVEYARD, "alice")
    assert {c.id for c in scenario.game.cards_exiled_with(ghoul.id, None)} == {bears.id, angel.id}
    assert (_chars(scenario, ghoul).power, _chars(scenario, ghoul).toughness) == (6, 6)


def test_sutured_ghoul_offers_only_creature_cards_and_may_take_none():
    scenario = (
        Scenario()
        .player("alice", hand=["Sutured Ghoul"], graveyard=["Grizzly Bears", "Lightning Bolt"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_choose_cards(source="Sutured Ghoul")
    ghoul = scenario.put_onto_battlefield("Sutured Ghoul")
    assert scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")
    assert scenario.game.cards_exiled_with(ghoul.id, None) == []
    (question,) = [
        d
        for d in scenario.questions_asked()
        if d.kind is DecisionKind.CHOOSE_CARDS and d.source == "Sutured Ghoul"
    ]
    assert len(question.cards) == 1


def test_living_lore_exiles_one_instant_or_sorcery_and_takes_its_mana_value():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Living Lore"],
            graveyard=["Divination", "Lightning Bolt", "Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    divination = scenario.find("Divination", Zone.GRAVEYARD, "alice")
    scenario.will_choose_cards(divination, source="Living Lore")
    lore = scenario.put_onto_battlefield("Living Lore")
    assert divination.zone is Zone.EXILE
    assert [c.id for c in scenario.game.cards_exiled_with(lore.id, None)] == [divination.id]
    assert (_chars(scenario, lore).power, _chars(scenario, lore).toughness) == (3, 3)
    (question,) = [
        d
        for d in scenario.questions_asked()
        if d.kind is DecisionKind.CHOOSE_CARDS and d.source == "Living Lore"
    ]
    assert len(question.cards) == 2  # the Bears is not an instant or sorcery card


def test_living_lore_with_nothing_to_exile_enters_as_a_zero_zero():
    scenario = (
        Scenario()
        .player("alice", hand=["Living Lore"], graveyard=["Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    lore = scenario.put_onto_battlefield("Living Lore")
    assert scenario.game.cards_exiled_with(lore.id, None) == []
    assert (_chars(scenario, lore).power, _chars(scenario, lore).toughness) == (0, 0)


# -- Grifter's Blade: enters attached to the creature chosen (CR 614.12a, 301.5) ----


def test_grifters_blade_enters_attached_to_the_chosen_creature():
    scenario = _board(hand=["Grifter's Blade"], battlefield=["Grizzly Bears", "Llanowar Elves"])
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice")
    scenario.will_choose_cards(bears, source="Grifter's Blade")
    blade = scenario.put_onto_battlefield("Grifter's Blade")
    assert blade.attached_to == bears.id
    assert (_chars(scenario, bears).power, _chars(scenario, bears).toughness) == (3, 3)


def test_grifters_blade_offers_only_creatures_you_control():
    scenario = (
        Scenario()
        .player("alice", hand=["Grifter's Blade"], battlefield=["Grizzly Bears", "Mountain"])
        .player("bob", battlefield=["Serra Angel"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice")
    scenario.will_choose_cards(bears, source="Grifter's Blade")
    scenario.put_onto_battlefield("Grifter's Blade")
    (question,) = [
        d
        for d in scenario.questions_asked()
        if d.kind is DecisionKind.CHOOSE_CARDS and d.source == "Grifter's Blade"
    ]
    assert question.cards == (bears.id,)


def test_grifters_blade_without_a_creature_asks_nothing_and_enters_unattached():
    scenario = _board(hand=["Grifter's Blade"], battlefield=["Mountain"])
    blade = scenario.put_onto_battlefield("Grifter's Blade")
    assert blade.attached_to is None
    assert not [d for d in scenario.questions_asked() if d.source == "Grifter's Blade"]


# -- Tibalt: as it enters you get an emblem (CR 114.2) -----------------------------


def test_tibalt_gives_its_controller_an_emblem_as_it_enters():
    scenario = _board(hand=["Valki, God of Lies // Tibalt, Cosmic Impostor"])
    card = scenario.find("Valki, God of Lies // Tibalt, Cosmic Impostor", Zone.HAND, "alice")
    scenario.game.put_onto_battlefield(card, "alice", transformed=True)
    (emblem,) = scenario.game.emblems_of("alice")
    assert "You may play cards exiled with Tibalt, Cosmic Impostor" in emblem.card.oracle_text
    assert scenario.game.emblems_of("bob") == []


def test_valki_entering_as_the_front_face_gets_no_emblem():
    scenario = _board(hand=["Valki, God of Lies // Tibalt, Cosmic Impostor"])
    scenario.put_onto_battlefield("Valki, God of Lies // Tibalt, Cosmic Impostor")
    assert scenario.game.emblems_of("alice") == []


# -- Kolvori // The Ringhart Crest: the back face's creature-type choice -------------


def test_the_ringhart_crest_asks_for_a_creature_type_as_it_enters():
    scenario = _board(hand=["Kolvori, God of Kinship // The Ringhart Crest"])
    card = scenario.find("Kolvori, God of Kinship // The Ringhart Crest", Zone.HAND, "alice")
    scenario.will_choose("Elf")
    crest = scenario.game.put_onto_battlefield(card, "alice", transformed=True)
    assert crest.choice is not None
    assert crest.choice.kind is ChoiceKind.CREATURE_TYPE
    assert crest.choice.value.lower() == "elf"


def test_kolvori_front_face_asks_no_creature_type():
    scenario = _board(hand=["Kolvori, God of Kinship // The Ringhart Crest"])
    kolvori = scenario.put_onto_battlefield("Kolvori, God of Kinship // The Ringhart Crest")
    assert kolvori.choice is None


# -- Sieges: bullets of the other modes (CR 614.12a) --------------------------------


@pytest.mark.parametrize(
    ("siege", "modes"),
    [
        ("Frostcliff Siege", ("Jeskai", "Temur")),
        ("Windcrag Siege", ("Mardu", "Jeskai")),
        ("Hollowmurk Siege", ("Sultai", "Abzan")),
        ("Glacierwood Siege", ("Temur", "Sultai")),
        ("Barrensteppe Siege", ("Abzan", "Mardu")),
        ("Mirrodin Besieged", ("Mirran", "Phyrexian")),
    ],
)
def test_each_clan_siege_offers_its_two_printed_modes(siege, modes):
    scenario = _board(hand=[siege])
    permanent = _enter(scenario, siege, modes[0])
    assert _question(scenario, siege).options == modes
    assert permanent.choice == Choice(kind=ChoiceKind.MODE, value=modes[0])


def test_frostcliff_siege_jeskai_draws_when_creatures_connect_and_temur_does_not():
    def run(mode):
        scenario = (
            Scenario()
            .player(
                "alice",
                hand=["Frostcliff Siege"],
                battlefield=["Grizzly Bears"],
                library=["Forest"] * 5,
            )
            .player("bob", library=["Forest"] * 5)
            .build()
        )
        _enter(scenario, "Frostcliff Siege", mode)
        scenario.start_at(Step.PRECOMBAT_MAIN)
        before = len(scenario.player("alice").hand)
        scenario.attack_with(scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice"))
        scenario.no_blocks()
        scenario.combat_damage()
        _resolve_all(scenario)
        return len(scenario.player("alice").hand) - before

    assert run("Jeskai") == 1
    assert run("Temur") == 0


# -- the as-enters lines of The Rack, Umori and Sarpadian Empires, Vol. VII ----
# (their other lines belong to other rounds; each is proven where it lives)


def test_the_rack_with_one_opponent_chooses_them_without_asking():
    """Only one opponent to pick between: no question (Tribute's convention)."""
    scenario = _board(hand=["The Rack"])
    rack = scenario.put_onto_battlefield("The Rack")
    assert rack.chosen_player == "bob"
    assert not [d for d in scenario.questions_asked() if d.source == "The Rack"]


def test_umori_chooses_a_card_type_and_refuses_a_non_type():
    scenario = _board(hand=["Umori, the Collector"])
    umori = _enter(scenario, "Umori, the Collector", "artifact")
    assert umori.choice == Choice(kind=ChoiceKind.CARD_TYPE, value="artifact")
    refused = _board(hand=["Umori, the Collector"])
    refused.will_choose("goblin", source="Umori, the Collector")
    with pytest.raises(ValueError, match="goblin"):
        refused.put_onto_battlefield("Umori, the Collector")


def test_sarpadian_empires_chooses_one_of_its_five_color_and_type_pairs():
    scenario = _board(hand=["Sarpadian Empires, Vol. VII"])
    empires = _enter(scenario, "Sarpadian Empires, Vol. VII", "green Saproling")
    assert empires.choice is not None
    assert empires.choice.value == "green Saproling"
    offered = _question(scenario, "Sarpadian Empires, Vol. VII").options
    assert len(offered) == 5
    assert "white Citizen" in offered


def test_sarpadian_empires_refuses_a_pair_it_does_not_print():
    scenario = _board(hand=["Sarpadian Empires, Vol. VII"])
    scenario.will_choose("green Goblin", source="Sarpadian Empires, Vol. VII")
    with pytest.raises(ValueError, match="green Goblin"):
        scenario.put_onto_battlefield("Sarpadian Empires, Vol. VII")
