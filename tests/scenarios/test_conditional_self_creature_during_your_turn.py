"""Scenario: a permanent's own conditional type-changing static ability -
"[During your turn,] as long as `<condition>`, `<this>` is a `<P/T>`
`<subtypes>` creature [in addition to its other types] and has `<keywords>`."

Kaito, Bane of Nightmares: "During your turn, as long as Kaito has one or
more loyalty counters on him, he's a 3/4 Ninja creature and has hexproof."
Idol of False Gods (the second printing, different condition, different
retention, a numbered keyword): "As long as this artifact has eight or more
+1/+1 counters on it, it's a 0/0 creature in addition to its other types and
it has annihilator 2."

Verified this session with `mise run rules:find`:

- CR 604.2 / CR 611.3a: a static ability's continuous effect "isn't 'locked
  in'; it applies at any given moment to whatever its text indicates" - so
  the effect is on exactly while its condition holds.
- CR 613.1d (layer 4, types), CR 613.1f (layer 6, abilities), CR 613.4b
  (layer 7b, set power/toughness): the three layers the one sentence touches.
- CR 205.1a: a set card type "replaces any existing card types" and a set
  creature subtype replaces the existing subtypes - Kaito stops being a
  planeswalker while he is a creature (his own Scryfall ruling says the
  same). CR 205.1b: "in addition to its other types" keeps them (Idol).
- CR 120.3c: damage to a planeswalker removes loyalty counters - to a
  non-planeswalker creature it is only marked.
- CR 704.5i: "If a planeswalker has loyalty 0, it's put into its owner's
  graveyard."
- CR 702.11b: "'Hexproof' on a permanent means 'This permanent can't be the
  target of spells or abilities your opponents control.'"
- CR 606.3: a loyalty ability is activated by the permanent's controller -
  Kaito's ruling: "You can still activate Kaito's loyalty abilities" while
  he is a creature.
- CR 302.6: summoning sickness gates attacking by control since the turn
  began, not by being a creature since then.
- CR 702.86a: "Annihilator N" means "Whenever this creature attacks,
  defending player sacrifices N permanents."
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Supertype, Type, Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario

KAITO = "Kaito, Bane of Nightmares"


def _kaito_board(*, alice_hand: list[str] | None = None, bob_hand: list[str] | None = None):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=alice_hand or [],
            battlefield=[KAITO, "Island", "Swamp", "Mountain"],
            library=["Island"] * 6,
        )
        .player(
            "bob",
            hand=bob_hand or [],
            battlefield=["Grizzly Bears", "Mountain", "Mountain"],
            library=["Mountain"] * 6,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _kaito(scenario: Scenario):
    return scenario.find(KAITO, Zone.BATTLEFIELD, "alice")


def _to_bobs_turn(scenario: Scenario, step: Step = Step.PRECOMBAT_MAIN) -> None:
    while scenario.turn.active_player != "bob":
        scenario.advance()
        while not scenario.game.stack_is_empty:
            scenario.resolve_top()
    scenario.start_at(step)


# -- his controller's turn -----------------------------------------------------


def test_on_his_turn_kaito_is_a_3_4_hexproof_ninja_creature():
    scenario = _kaito_board()
    chars = scenario.game.characteristics_of(_kaito(scenario))

    assert chars.is_creature
    assert chars.power_toughness == (3, 4)
    assert "Ninja" in chars.subtypes
    assert "Hexproof" in chars.abilities
    assert scenario.game.continuous_effects.layer_notices == []


def test_as_a_creature_he_is_no_longer_a_planeswalker():
    """CR 205.1a: "a 3/4 Ninja creature" sets the card type (no "in addition",
    no "still a"), so the planeswalker type and its Kaito subtype go; the
    legendary supertype is not a card type and stays."""
    scenario = _kaito_board()
    chars = scenario.game.characteristics_of(_kaito(scenario))

    assert Type.PLANESWALKER not in chars.types
    assert "Kaito" not in chars.subtypes
    assert Supertype.LEGENDARY in chars.supertypes


def test_kaito_can_attack_on_his_turn():
    scenario = _kaito_board()
    kaito = _kaito(scenario)
    scenario.start_at(Step.DECLARE_ATTACKERS)

    assert scenario.can_attack(kaito)
    scenario.attack_with(kaito)
    assert kaito in scenario.attackers()


def test_combat_damage_to_creature_kaito_is_marked_not_taken_from_loyalty():
    """CR 120.3c only removes loyalty from a *planeswalker*."""
    scenario = _kaito_board()
    kaito = _kaito(scenario)
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(kaito)
    scenario.start_at(Step.DECLARE_BLOCKERS)
    scenario.block(kaito, bears)
    scenario.combat_damage()

    assert kaito.damage == 2
    assert kaito.counter_count(Counter.LOYALTY) == 4
    assert scenario.player("bob").life == 20


def test_opponent_cannot_target_kaito_on_his_turn():
    scenario = _kaito_board(bob_hand=["Lightning Bolt"])
    kaito = _kaito(scenario)

    assert scenario.game.hexproof_refusal(kaito, "bob", None) is not None
    casting = scenario.cast("Lightning Bolt", username="bob")
    with pytest.raises(ValueError, match="hexproof"):
        casting.choose_targets([kaito])


def test_his_controller_can_still_target_him():
    """Hexproof is "your opponents" only (CR 702.11b)."""
    scenario = _kaito_board(alice_hand=["Lightning Bolt"])
    kaito = _kaito(scenario)

    scenario.cast_and_resolve(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=[kaito]
    )
    assert kaito.damage == 3
    assert kaito.counter_count(Counter.LOYALTY) == 4


def test_loyalty_abilities_still_activate_while_he_is_a_creature():
    """His -2 needs two loyalty counters, not the planeswalker type (CR 606.3;
    Kaito's own ruling)."""
    scenario = _kaito_board()
    kaito = _kaito(scenario)
    bears = scenario.creature("Grizzly Bears", "bob")

    assert scenario.why_cannot_activate(kaito, 2, "alice") is None
    scenario.activate(kaito, index=2, username="alice", targets=[bears])
    scenario.pass_until_resolved()

    assert bears.tapped
    assert bears.counter_count(Counter.STUN) == 2
    assert kaito.counter_count(Counter.LOYALTY) == 2
    assert scenario.game.characteristics_of(kaito).is_creature


def test_his_own_emblem_pumps_him_after_his_base_is_set():
    """Layer 7b sets 3/4, then the emblem's "Ninjas you control get +1/+1"
    applies in layer 7c: a 4/5."""
    scenario = _kaito_board()
    kaito = _kaito(scenario)
    scenario.activate(kaito, index=0, username="alice")
    scenario.pass_until_resolved()

    assert scenario.game.characteristics_of(kaito).power_toughness == (4, 5)


# -- the opponent's turn ------------------------------------------------------


def test_on_the_opponents_turn_kaito_is_only_a_planeswalker():
    scenario = _kaito_board()
    _to_bobs_turn(scenario)
    chars = scenario.game.characteristics_of(_kaito(scenario))

    assert not chars.is_creature
    assert Type.PLANESWALKER in chars.types
    assert "Hexproof" not in chars.abilities
    assert chars.power_toughness == (None, None)


def test_on_the_opponents_turn_kaito_can_be_targeted_and_loses_loyalty():
    scenario = _kaito_board(bob_hand=["Lightning Bolt"])
    _to_bobs_turn(scenario)
    kaito = _kaito(scenario)

    assert scenario.game.hexproof_refusal(kaito, "bob", None) is None
    scenario.cast_and_resolve(
        "Lightning Bolt",
        *scenario.untapped_sources("Mountain", username="bob"),
        username="bob",
        targets=[kaito],
    )
    assert kaito.counter_count(Counter.LOYALTY) == 1
    assert kaito.damage == 0


def test_on_the_opponents_turn_kaito_can_be_attacked():
    scenario = _kaito_board()
    _to_bobs_turn(scenario, Step.DECLARE_ATTACKERS)
    kaito = _kaito(scenario)
    bears = scenario.creature("Grizzly Bears", "bob")

    scenario.attack_with(bears, defending=kaito)
    assert bears in scenario.attackers()


# -- the condition: one or more loyalty counters -------------------------------


def test_with_one_loyalty_counter_he_is_still_a_creature():
    scenario = _kaito_board()
    kaito = _kaito(scenario)
    kaito.remove_counters(Counter.LOYALTY, 3)

    assert scenario.game.characteristics_of(kaito).is_creature


def test_with_zero_loyalty_the_effect_stops_and_he_dies():
    """No loyalty counter: the condition fails, he is a planeswalker again, and
    CR 704.5i puts him into the graveyard."""
    scenario = _kaito_board()
    kaito = _kaito(scenario)
    kaito.remove_counters(Counter.LOYALTY, 4)

    chars = scenario.game.characteristics_of(kaito)
    assert not chars.is_creature
    assert Type.PLANESWALKER in chars.types
    assert "Hexproof" not in chars.abilities

    scenario.state_based_actions()
    assert kaito.zone is Zone.GRAVEYARD


# -- Idol of False Gods: counter threshold, "in addition", numbered keyword ----


def _idol_board(counters: int) -> Scenario:
    scenario = (
        Scenario()
        .player("alice", battlefield=["Idol of False Gods"], library=["Wastes"] * 6)
        .player("bob", battlefield=["Mountain", "Mountain", "Mountain"], library=["Mountain"] * 6)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    idol = scenario.find("Idol of False Gods", Zone.BATTLEFIELD, "alice")
    if counters:
        scenario.game.add_counters(idol, Counter.PLUS_ONE, counters)
    return scenario


def _idol(scenario: Scenario):
    return scenario.find("Idol of False Gods", Zone.BATTLEFIELD, "alice")


def test_idol_with_seven_counters_is_not_a_creature():
    scenario = _idol_board(7)
    chars = scenario.game.characteristics_of(_idol(scenario))

    assert not chars.is_creature
    assert not any(ability.startswith("Annihilator") for ability in chars.abilities)


def test_idol_with_eight_counters_is_an_8_8_artifact_creature_with_annihilator():
    """0/0 in layer 7b, eight +1/+1 counters in 7c; CR 205.1b keeps it an
    artifact and a kindred Eldrazi."""
    scenario = _idol_board(8)
    chars = scenario.game.characteristics_of(_idol(scenario))

    assert chars.is_creature
    assert Type.ARTIFACT in chars.types
    assert "Eldrazi" in chars.subtypes
    assert chars.power_toughness == (8, 8)
    assert "Annihilator 2" in chars.abilities
    assert scenario.game.continuous_effects.layer_notices == []


def test_idol_attacks_and_its_granted_annihilator_triggers():
    scenario = _idol_board(8)
    idol = _idol(scenario)
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(idol)
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == ["Idol of False Gods's triggered ability"]


def test_idol_losing_a_counter_stops_being_a_creature():
    """CR 611.3a: re-read the moment the count drops."""
    scenario = _idol_board(8)
    idol = _idol(scenario)
    idol.remove_counters(Counter.PLUS_ONE, 1)

    assert not scenario.game.characteristics_of(idol).is_creature
