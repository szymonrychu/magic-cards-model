"""Scenario: counters as a printed condition - on the source, on the trigger
event's own subject, and looking back at a subject that has left.

Rules read whole with `mise run rules:find` in the session that wrote this:

- **CR 122.1** - "A counter is a marker placed on an object or player that
  modifies its characteristics and/or interacts with a rule, ability, or
  effect." Any name is a legal kind (brick, quest, oil, ki, tower, omen,
  arrowhead, unlock, soul, egg, revival).
- **CR 122.2** - counters are not retained when an object changes zones.
- **CR 603.10a** - leaves-the-battlefield abilities look back in time: "it
  had a +1/+1 counter on it" is asked of the permanent as it last existed
  on the battlefield, and stays that answer on resolution.
- **CR 603.4** - an intervening "if" is checked as the event occurs; the
  ability triggers only if it is true.
- **CR 608.2a** - it is checked again on resolution; false then, the ability
  is removed from the stack and does nothing.
- **CR 602.5b** - an activation restriction "continues to apply to that
  object even if its controller changes".
- **CR 607.2a** - "cards exiled with" an object are the ones its linked
  ability exiled.
"""

import pytest

from magic_cards_model.machines import Step, conditions
from magic_cards_model.machines.conditions import ConditionContext
from magic_cards_model.machines.triggers import GameEvent, TriggerEvent
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter, ExileAnnotation, ExileMarker
from tests.scenarios.harness import Scenario


def _board(alice=(), *, bob=(), hand=(), graveyard=(), library=None):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=list(alice),
            hand=list(hand),
            graveyard=list(graveyard),
            library=list(library or ["Plains"] * 5),
        )
        .player("bob", battlefield=list(bob), library=["Plains"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _step_begins(scenario, step: Step, player: str = "alice") -> None:
    scenario.game.emit(GameEvent(event=TriggerEvent.BEGINNING_OF_STEP, step=step, player=player))
    scenario.game.put_triggers_on_stack()


def _triggered(scenario) -> list[str]:
    return scenario.stack_names()


def _refused_as_unmet(refusal: str | None) -> None:
    """Refused because the restriction is read and false (CR 602.5b) - not
    because it could not be read."""
    assert refusal is not None
    assert "activation restriction is not met" in refusal
    assert "602.5b" in refusal
    assert "not read" not in refusal


def _next_turn(scenario) -> None:
    scenario.turn.advance_to(Step.CLEANUP)
    scenario.advance()
    scenario.advance()


def _read(scenario, clause: str, source, *, controller="alice", event=None) -> bool | None:
    return conditions.read_condition(
        ConditionContext(scenario.game, controller, source=source, event=event), clause
    )


# -- "there are N or more <kind> counters on this <type>" (activation) -------


def test_luxa_river_shrine_is_refused_below_three_bricks_with_the_condition():
    scenario = _board(["Luxa River Shrine"])
    shrine = scenario.find("Luxa River Shrine", Zone.BATTLEFIELD)
    for count in (0, 2):
        if count:
            shrine.add_counters("brick", count)
        _refused_as_unmet(scenario.why_cannot_activate(shrine, 1))


def test_luxa_river_shrine_activates_with_three_bricks():
    scenario = _board(["Luxa River Shrine"])
    shrine = scenario.find("Luxa River Shrine", Zone.BATTLEFIELD)
    shrine.add_counters("brick", 3)
    assert scenario.why_cannot_activate(shrine, 1) is None
    scenario.activate(shrine, index=1)
    scenario.pass_until_resolved()
    assert scenario.player("alice").life == 22


def test_the_shrines_own_ability_builds_the_bricks_it_counts():
    """{1}, {T}: "Put a brick counter on this artifact." - one brick is not
    three."""
    scenario = _board(["Luxa River Shrine", "Plains"])
    shrine = scenario.find("Luxa River Shrine", Zone.BATTLEFIELD)
    scenario.activate(shrine, *scenario.untapped_sources("Plains"), index=0)
    scenario.pass_until_resolved()
    assert shrine.counter_count("brick") == 1
    assert scenario.why_cannot_activate(shrine, 1) is not None


def test_oracles_vault_reads_the_same_template():
    """A second printing: Oracle's Vault, "Activate only if there are three or
    more brick counters on this artifact"."""
    scenario = _board(["Oracle's Vault"])
    vault = scenario.find("Oracle's Vault", Zone.BATTLEFIELD)
    vault.add_counters("brick", 2)
    assert scenario.why_cannot_activate(vault, 1) is not None
    vault.add_counters("brick", 1)
    assert scenario.why_cannot_activate(vault, 1) is None


# -- "this <type> has N or more <kind> counters on it" (activation) ----------


def test_tablet_of_compleation_mana_ability_needs_two_oil():
    """Tablet of Compleation's "{T}: Add {C}. Activate only if this artifact
    has two or more oil counters on it." - a mana ability (CR 605.1a) keeps
    its restriction."""
    scenario = _board(["Tablet of Compleation"])
    tablet = scenario.find("Tablet of Compleation", Zone.BATTLEFIELD)
    tablet.add_counters("oil", 1)
    _refused_as_unmet(scenario.why_cannot_activate(tablet, 1))
    tablet.add_counters("oil", 1)
    assert scenario.why_cannot_activate(tablet, 1) is None
    # The draw ability needs five.
    assert scenario.why_cannot_activate(tablet, 2) is not None
    tablet.add_counters("oil", 3)
    assert scenario.why_cannot_activate(tablet, 2) is None


def test_a_counter_restriction_follows_the_permanent_to_its_new_controller():
    """CR 602.5b: Skarrgan Hellkite's "Activate only if this creature has a
    +1/+1 counter on it" still applies after bob takes it with Act of
    Treason - and bob may activate it once it has one."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Skarrgan Hellkite"], library=["Plains"] * 5)
        .player(
            "bob",
            hand=["Act of Treason"],
            battlefield=["Mountain"] * 7,
            library=["Plains"] * 5,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    hellkite = scenario.creature("Skarrgan Hellkite", "alice")
    _refused_as_unmet(scenario.why_cannot_activate(hellkite, 0))
    _next_turn(scenario)
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve(
        "Act of Treason",
        *scenario.untapped_sources("Mountain", "Mountain", "Mountain", username="bob"),
        targets=[hellkite],
        username="bob",
    )
    assert scenario.game.controller_of(hellkite).username == "bob"
    _refused_as_unmet(scenario.why_cannot_activate(hellkite, 0, username="bob"))
    hellkite.add_counters(Counter.PLUS_ONE, 1)
    assert scenario.why_cannot_activate(hellkite, 0, username="bob") is None


# -- present-tense counters on the source (intervening "if") -----------------


def test_encumbered_reejerey_triggers_while_it_has_a_minus_counter():
    scenario = _board(["Encumbered Reejerey"])
    reejerey = scenario.creature("Encumbered Reejerey", "alice")
    reejerey.add_counters(Counter.MINUS_ONE, 3)
    scenario.game.tap_permanent(reejerey)
    scenario.game.put_triggers_on_stack()
    assert _triggered(scenario) == ["Encumbered Reejerey's triggered ability"]
    (trigger,) = scenario.game.stack
    assert scenario.game._intervening_if_still_true(trigger)  # noqa: SLF001
    assert scenario.game.intervening_if_notices == []


def test_encumbered_reejerey_without_counters_does_not_trigger():
    scenario = _board(["Encumbered Reejerey"])
    reejerey = scenario.creature("Encumbered Reejerey", "alice")
    scenario.game.tap_permanent(reejerey)
    scenario.game.put_triggers_on_stack()
    assert _triggered(scenario) == []
    assert scenario.game.intervening_if_notices == []


def test_the_last_counter_gone_before_resolution_removes_the_ability():
    """CR 608.2a: the counter it was tapped with is gone by resolution."""
    scenario = _board(["Encumbered Reejerey"])
    reejerey = scenario.creature("Encumbered Reejerey", "alice")
    reejerey.add_counters(Counter.MINUS_ONE, 1)
    scenario.game.tap_permanent(reejerey)
    scenario.game.put_triggers_on_stack()
    (trigger,) = scenario.game.stack
    reejerey.remove_counters(Counter.MINUS_ONE, 1)
    assert not scenario.game._intervening_if_still_true(trigger)  # noqa: SLF001
    scenario.pass_until_resolved()
    assert scenario.game.stack_is_empty


def test_bristlebane_battler_reads_the_same_while_clause_on_another_event():
    """A second printing: "Whenever another creature you control enters while
    this creature has a -1/-1 counter on it" - the counter is on the source,
    not on the creature that entered."""
    scenario = _board(["Bristlebane Battler"], hand=["Grizzly Bears"])
    battler = scenario.creature("Bristlebane Battler", "alice")
    battler.add_counters(Counter.MINUS_ONE, 1)
    scenario.put_onto_battlefield("Grizzly Bears", "alice")
    scenario.game.put_triggers_on_stack()
    assert _triggered(scenario) == ["Bristlebane Battler's triggered ability"]
    battler.remove_counters(Counter.MINUS_ONE, 1)
    (trigger,) = scenario.game.stack
    assert not scenario.game._intervening_if_still_true(trigger)  # noqa: SLF001


def test_shatterskull_charger_without_a_counter_returns_at_end_step():
    scenario = _board(["Shatterskull Charger"])
    charger = scenario.creature("Shatterskull Charger", "alice")
    _step_begins(scenario, Step.END_STEP)
    assert _triggered(scenario) == ["Shatterskull Charger's triggered ability"]
    scenario.pass_until_resolved()
    assert charger.zone is Zone.HAND


def test_shatterskull_charger_with_a_counter_stays():
    scenario = _board(["Shatterskull Charger"])
    charger = scenario.creature("Shatterskull Charger", "alice")
    charger.add_counters(Counter.PLUS_ONE, 1)
    _step_begins(scenario, Step.END_STEP)
    assert _triggered(scenario) == []
    assert charger.zone is Zone.BATTLEFIELD


def test_a_counter_gained_in_response_keeps_shatterskull_charger():
    """True as the step begins, false on resolution: removed (CR 608.2a)."""
    scenario = _board(["Shatterskull Charger"])
    charger = scenario.creature("Shatterskull Charger", "alice")
    _step_begins(scenario, Step.END_STEP)
    charger.add_counters(Counter.PLUS_ONE, 1)
    scenario.pass_until_resolved()
    assert charger.zone is Zone.BATTLEFIELD


def test_sarulf_names_itself_in_the_clause():
    """ "if Sarulf has one or more +1/+1 counters on it" - the source by its
    own short name (CR 201.5c)."""
    scenario = _board(["Sarulf, Realm Eater"])
    sarulf = scenario.creature("Sarulf, Realm Eater", "alice")
    _step_begins(scenario, Step.UPKEEP)
    assert _triggered(scenario) == []
    sarulf.add_counters(Counter.PLUS_ONE, 2)
    _step_begins(scenario, Step.UPKEEP)
    assert _triggered(scenario) == ["Sarulf, Realm Eater's triggered ability"]


def test_the_ozolith_has_counters_of_any_kind():
    scenario = _board(["The Ozolith"])
    ozolith = scenario.find("The Ozolith", Zone.BATTLEFIELD)
    clause = "The Ozolith has counters on it"
    assert _read(scenario, clause, ozolith) is False
    ozolith.add_counters("flying", 1)
    assert _read(scenario, clause, ozolith) is True


def test_helix_pinnacle_counts_to_one_hundred():
    scenario = _board(["Helix Pinnacle"])
    pinnacle = scenario.find("Helix Pinnacle", Zone.BATTLEFIELD)
    pinnacle.add_counters("tower", 99)
    _step_begins(scenario, Step.UPKEEP)
    assert _triggered(scenario) == []
    pinnacle.add_counters("tower", 1)
    _step_begins(scenario, Step.UPKEEP)
    assert _triggered(scenario) == ["Helix Pinnacle's triggered ability"]


def test_serrated_arrows_reads_no_arrowhead_counters():
    scenario = _board(["Serrated Arrows"])
    arrows = scenario.find("Serrated Arrows", Zone.BATTLEFIELD)
    arrows.add_counters("arrowhead", 1)
    _step_begins(scenario, Step.UPKEEP)
    assert _triggered(scenario) == []
    arrows.remove_counters("arrowhead", 1)
    _step_begins(scenario, Step.UPKEEP)
    assert _triggered(scenario) == ["Serrated Arrows's triggered ability"]
    scenario.pass_until_resolved()
    assert arrows.zone is Zone.GRAVEYARD


def test_risona_reads_a_negated_kind():
    scenario = _board(["Risona, Asari Commander"])
    risona = scenario.creature("Risona, Asari Commander", "alice")
    clause = "it doesn't have an indestructible counter on it"
    assert _read(scenario, clause, risona) is True
    risona.add_counters("indestructible", 1)
    assert _read(scenario, clause, risona) is False


def test_ki_counters_on_this_creature():
    """Quest for Ula's Temple's "there are three or more quest counters on
    this enchantment" - the `there are` form on an intervening "if"."""
    scenario = _board(["Quest for Ula's Temple"])
    quest = scenario.find("Quest for Ula's Temple", Zone.BATTLEFIELD)
    quest.add_counters("quest", 2)
    _step_begins(scenario, Step.END_STEP, "bob")
    assert _triggered(scenario) == []
    quest.add_counters("quest", 1)
    _step_begins(scenario, Step.END_STEP, "bob")
    assert _triggered(scenario) == ["Quest for Ula's Temple's triggered ability"]


# -- looking back: "it had ... counters on it" (CR 603.10a) ------------------


def test_promising_duskmage_that_died_with_a_counter_draws():
    scenario = _board(["Promising Duskmage"])
    duskmage = scenario.creature("Promising Duskmage", "alice")
    duskmage.add_counters(Counter.PLUS_ONE, 1)
    hand = len(scenario.player("alice").hand)
    scenario.game.destroy(duskmage)
    scenario.game.put_triggers_on_stack()
    assert _triggered(scenario) == ["Promising Duskmage's triggered ability"]
    scenario.pass_until_resolved()
    assert len(scenario.player("alice").hand) == hand + 1


def test_promising_duskmage_that_died_without_one_does_not_trigger():
    scenario = _board(["Promising Duskmage"])
    duskmage = scenario.creature("Promising Duskmage", "alice")
    scenario.game.destroy(duskmage)
    scenario.game.put_triggers_on_stack()
    assert _triggered(scenario) == []
    assert scenario.game.intervening_if_notices == []


def test_the_look_back_survives_the_card_leaving_the_graveyard():
    """CR 603.10a: the answer is about the permanent as it last existed on
    the battlefield - exiling the card from the graveyard in response does
    not change what it had."""
    scenario = _board(["Promising Duskmage"])
    duskmage = scenario.creature("Promising Duskmage", "alice")
    duskmage.add_counters(Counter.PLUS_ONE, 1)
    hand = len(scenario.player("alice").hand)
    scenario.game.destroy(duskmage)
    scenario.game.put_triggers_on_stack()
    scenario.game.exile_cards([duskmage])
    scenario.pass_until_resolved()
    assert len(scenario.player("alice").hand) == hand + 1


def test_basris_lieutenant_asks_the_creature_that_died_not_itself():
    """ "Whenever this creature or another creature you control dies, if it
    had a +1/+1 counter on it" - "it" is the creature that died."""
    scenario = _board(["Basri's Lieutenant", "Grizzly Bears", "Memnite"])
    lieutenant = scenario.creature("Basri's Lieutenant", "alice")
    lieutenant.add_counters(Counter.PLUS_ONE, 1)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.game.destroy(bears)
    scenario.game.put_triggers_on_stack()
    assert _triggered(scenario) == []
    memnite = scenario.creature("Memnite", "alice")
    memnite.add_counters(Counter.PLUS_ONE, 1)
    lieutenant.remove_counters(Counter.PLUS_ONE, 1)
    scenario.game.destroy(memnite)
    scenario.game.put_triggers_on_stack()
    assert _triggered(scenario) == ["Basri's Lieutenant's triggered ability"]


def test_blowfly_infestation_sees_any_players_creature():
    scenario = _board(["Blowfly Infestation"], bob=["Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears", "bob")
    bears.add_counters(Counter.MINUS_ONE, 1)
    scenario.game.destroy(bears)
    assert [a.name for a in scenario.pending_triggers] == [
        "Blowfly Infestation's triggered ability"
    ]


def test_deadly_grub_had_no_time_counters():
    scenario = _board(["Deadly Grub"])
    grub = scenario.creature("Deadly Grub", "alice")
    grub.add_counters(Counter.TIME, 1)
    event = GameEvent(event=TriggerEvent.DIES, subject_id=grub.id)
    scenario.game.destroy(grub)
    assert _read(scenario, "it had no time counters on it", grub, event=event) is False
    scenario2 = _board(["Deadly Grub"])
    grub2 = scenario2.creature("Deadly Grub", "alice")
    scenario2.game.destroy(grub2)
    scenario2.game.put_triggers_on_stack()
    assert _triggered(scenario2) == ["Deadly Grub's triggered ability"]


def test_unstoppable_slasher_had_no_counters_of_any_kind():
    scenario = _board(["Unstoppable Slasher"])
    slasher = scenario.creature("Unstoppable Slasher", "alice")
    slasher.add_counters("stun", 1)
    scenario.game.destroy(slasher)
    scenario.game.put_triggers_on_stack()
    assert _triggered(scenario) == []


def test_iron_apprentice_had_counters():
    scenario = _board(["Iron Apprentice", "Grizzly Bears"])
    apprentice = scenario.creature("Iron Apprentice", "alice")
    apprentice.add_counters(Counter.PLUS_ONE, 2)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.choose_trigger_targets("Iron Apprentice", [bears])
    scenario.game.destroy(apprentice)
    scenario.game.put_triggers_on_stack()
    assert _triggered(scenario) == ["Iron Apprentice's triggered ability"]


@pytest.mark.parametrize(("placed", "triggers"), [(1, False), (2, True)])
def test_ochre_jelly_needs_two_or_more(placed, triggers):
    scenario = _board(["Ochre Jelly"])
    jelly = scenario.creature("Ochre Jelly", "alice")
    jelly.add_counters(Counter.PLUS_ONE, placed)
    scenario.game.destroy(jelly)
    scenario.game.put_triggers_on_stack()
    assert bool(_triggered(scenario)) is triggers


# -- a spell's own mana value against the source's counters ------------------


def _cast_bolt_at_bob(scenario):
    scenario.cast_onto_stack(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=["bob"]
    )
    scenario.game.put_triggers_on_stack()


def test_obscura_ascendancy_compares_the_spells_mana_value_to_its_counters():
    """ "if its mana value is equal to 1 plus the number of soul counters on
    this enchantment" - "its" is the spell cast (CR 202.3e: its value on the
    stack). Lightning Bolt's 1 is 1 plus no soul counters."""
    scenario = _board(["Obscura Ascendancy", "Mountain"], hand=["Lightning Bolt"])
    _cast_bolt_at_bob(scenario)
    assert "Obscura Ascendancy's triggered ability" in _triggered(scenario)


def test_obscura_ascendancy_misses_a_different_mana_value():
    """One soul counter wants mana value 2; Lightning Bolt is 1."""
    scenario = _board(["Obscura Ascendancy", "Mountain"], hand=["Lightning Bolt"])
    scenario.find("Obscura Ascendancy", Zone.BATTLEFIELD).add_counters("soul", 1)
    _cast_bolt_at_bob(scenario)
    assert "Obscura Ascendancy's triggered ability" not in _triggered(scenario)


# -- "cards exiled with" the source (CR 607.2a) ------------------------------


def _exile_with(scenario, name: str, source, owner: str = "alice"):
    card = scenario.find(name, Zone.LIBRARY, owner)
    scenario.game.exile_cards([card])
    card.exile_annotation = ExileAnnotation(
        marker=ExileMarker.IMPRINTED,
        linked_permanent_id=source.id,
        linked_permanent_stamp=source.zone_change_stamp,
    )
    return card


def test_valakut_exploration_needs_cards_exiled_with_it():
    scenario = _board(["Valakut Exploration"], library=["Plains", "Island", "Swamp"])
    exploration = scenario.find("Valakut Exploration", Zone.BATTLEFIELD)
    _step_begins(scenario, Step.END_STEP)
    assert _triggered(scenario) == []
    _exile_with(scenario, "Plains", exploration)
    _step_begins(scenario, Step.END_STEP)
    assert _triggered(scenario) == ["Valakut Exploration's triggered ability"]


def test_colfenors_urn_counts_three_or_more():
    scenario = _board(["Colfenor's Urn"], library=["Plains", "Island", "Swamp", "Forest"])
    urn = scenario.find("Colfenor's Urn", Zone.BATTLEFIELD)
    clause = "three or more cards have been exiled with this artifact"
    _exile_with(scenario, "Plains", urn)
    _exile_with(scenario, "Island", urn)
    assert _read(scenario, clause, urn) is False
    _exile_with(scenario, "Swamp", urn)
    assert _read(scenario, clause, urn) is True


def test_spellweaver_helix_matches_the_cast_cards_name():
    scenario = _board(["Spellweaver Helix"], library=["Lightning Bolt", "Shock"])
    helix = scenario.find("Spellweaver Helix", Zone.BATTLEFIELD)
    bolt = _exile_with(scenario, "Lightning Bolt", helix)
    del bolt
    shock = scenario.find("Shock", Zone.LIBRARY, "alice")
    event = GameEvent(event=TriggerEvent.CAST_SPELL, subject_id=shock.id, subject_name="Shock")
    clause = "it has the same name as one of the cards exiled with this artifact"
    assert _read(scenario, clause, helix, event=event) is False
    _exile_with(scenario, "Shock", helix)
    assert _read(scenario, clause, helix, event=event) is True


# -- a card in exile with counters -------------------------------------------


def test_darigaaz_in_exile_with_an_egg_counter():
    scenario = _board(["Darigaaz Reincarnated"])
    darigaaz = scenario.creature("Darigaaz Reincarnated", "alice")
    clause = "this card is exiled with an egg counter on it"
    assert _read(scenario, clause, darigaaz) is False
    scenario.game.exile_permanent(darigaaz)
    darigaaz.add_counters("egg", 3)
    assert _read(scenario, clause, darigaaz) is True
    darigaaz.remove_counters("egg", 3)
    assert _read(scenario, clause, darigaaz) is False


# -- counters removed / put into a graveyard this turn (Churning Reservoir) --


def test_churning_reservoir_refused_until_an_oil_counter_comes_off():
    scenario = _board(["Churning Reservoir", "Memnite", "Plains", "Plains"])
    reservoir = scenario.find("Churning Reservoir", Zone.BATTLEFIELD)
    memnite = scenario.creature("Memnite", "alice")
    _refused_as_unmet(scenario.why_cannot_activate(reservoir, 0))
    memnite.add_counters("oil", 1)
    memnite.remove_counters("oil", 1)
    assert scenario.why_cannot_activate(reservoir, 0) is None


def test_churning_reservoir_counts_a_permanent_put_into_a_graveyard_with_oil():
    scenario = _board(["Churning Reservoir"], bob=["Memnite"])
    reservoir = scenario.find("Churning Reservoir", Zone.BATTLEFIELD)
    memnite = scenario.creature("Memnite", "bob")
    memnite.add_counters("oil", 1)
    scenario.game.destroy(memnite)
    assert scenario.why_cannot_activate(reservoir, 0) is None


def test_an_opponents_counter_removal_is_not_yours():
    scenario = _board(["Churning Reservoir"], bob=["Memnite"])
    reservoir = scenario.find("Churning Reservoir", Zone.BATTLEFIELD)
    memnite = scenario.creature("Memnite", "bob")
    memnite.add_counters("oil", 1)
    memnite.remove_counters("oil", 1)
    assert scenario.why_cannot_activate(reservoir, 0) is not None


# -- the probes ---------------------------------------------------------------


@pytest.mark.parametrize(
    "clause",
    [
        "there are three or more brick counters on this artifact",
        "this artifact has five or more unlock counters on it",
        "it had one or more counters on it",
        "it had counters on it",
        "it had no time counters on it",
        "it had a revival counter on it",
        "it doesn't have an indestructible counter on it",
        "this creature doesn't have a +1/+1 counter on it",
        "there are no arrowhead counters on this artifact",
        "there are cards exiled with this enchantment",
        "three or more cards have been exiled with this artifact",
        "this card is exiled with an egg counter on it",
        "its mana value is equal to 1 plus the number of soul counters on this enchantment",
        "an oil counter was removed from a permanent you controlled this turn",
        "a permanent with an oil counter on it was put into a graveyard this turn",
    ],
)
def test_every_template_is_claimed(clause):
    assert conditions.claims(clause)


def test_a_present_tense_clause_about_a_creature_that_just_died_looks_back():
    """ "it has a +1/+1 counter on it" asked of a dies event's own subject can
    only mean the creature as it last existed (CR 603.10a)."""
    scenario = _board(["Promising Duskmage"])
    duskmage = scenario.creature("Promising Duskmage", "alice")
    duskmage.add_counters(Counter.PLUS_ONE, 1)
    scenario.game.destroy(duskmage)
    event = GameEvent(event=TriggerEvent.DIES, subject_id=duskmage.id)
    assert _read(scenario, "it has a +1/+1 counter on it", duskmage, event=event) is True
    assert _read(scenario, "it has a +1/+1 counter on it", duskmage) is False
