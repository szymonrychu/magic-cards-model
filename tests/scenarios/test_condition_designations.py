"""Scenario: designations as a printed condition - the city's blessing, a full
party, the Ring-bearer, completed dungeons, and a permanent's own monstrous,
renowned, suspected and saddled designations.

Rules read whole with `mise run rules:find` in the session that wrote this:

- **CR 702.131b** / **CR 702.131c** - ascend grants the city's blessing,
  "a designation that has no rules meaning other than to act as a marker".
- **CR 700.8** / **CR 700.8b** / **CR 700.8c** - a party is up to one each of
  Cleric, Rogue, Warrior and Wizard, counted the way that gets the highest
  result; a full party is four.
- **CR 701.54a** - the Ring tempts you: you choose a creature you control as
  your Ring-bearer.
- **CR 309.7** - a player completes a dungeon as it is removed from the game.
- **CR 701.37b** - monstrous; **CR 702.112b** - renowned; **CR 701.60b** -
  suspected; **CR 702.171b** - saddled: each a designation of the permanent,
  gone when it leaves the battlefield.
- **CR 602.5b** - an activation restriction.
- **CR 603.4** / **CR 608.2a** - an intervening "if".
"""

import pytest

from magic_cards_model.machines import Step, conditions
from magic_cards_model.machines.conditions import ConditionContext
from magic_cards_model.machines.designations import party_size
from magic_cards_model.machines.triggers import ExtraTriggerEvent, GameEvent, TriggerEvent
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _board(alice=(), *, bob=(), hand=(), library=None):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=list(alice),
            hand=list(hand),
            library=list(library or ["Plains"] * 8),
        )
        .player("bob", battlefield=list(bob), library=["Plains"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _read(scenario, clause, source, *, controller="alice", event=None):
    return conditions.read_condition(
        ConditionContext(scenario.game, controller, source=source, event=event), clause
    )


def _refused_as_unmet(refusal):
    assert refusal is not None
    assert "activation restriction is not met" in refusal
    assert "602.5b" in refusal


def _step_begins(scenario, step, player="alice"):
    scenario.game.emit(GameEvent(event=TriggerEvent.BEGINNING_OF_STEP, step=step, player=player))
    scenario.game.put_triggers_on_stack()


# -- the city's blessing ---------------------------------------------------------


def test_arch_of_orazca_refused_without_the_citys_blessing():
    scenario = _board(["Arch of Orazca"])
    arch = scenario.find("Arch of Orazca", Zone.BATTLEFIELD)
    _refused_as_unmet(scenario.why_cannot_activate(arch, 1))


def test_arch_of_orazca_activates_once_ascended():
    """CR 702.131b: ten permanents grant the blessing the moment an event is
    raised - Arch of Orazca and nine Plains."""
    scenario = _board(["Arch of Orazca", *["Plains"] * 8], hand=["Plains"])
    arch = scenario.find("Arch of Orazca", Zone.BATTLEFIELD)
    scenario.play_land("Plains")
    assert scenario.player("alice").has_citys_blessing
    assert scenario.why_cannot_activate(arch, 1) is None


def test_orazca_relic_reads_the_same_designation():
    scenario = _board(["Orazca Relic"])
    relic = scenario.find("Orazca Relic", Zone.BATTLEFIELD)
    _refused_as_unmet(scenario.why_cannot_activate(relic, 1))
    scenario.player("alice").has_citys_blessing = True
    assert scenario.why_cannot_activate(relic, 1) is None


def test_the_blessing_is_the_controllers_after_a_control_change():
    """CR 602.5b, CR 109.5: "you" is whoever controls Orazca Relic - bob,
    without the blessing, is refused even though alice has it."""
    scenario = _board(["Orazca Relic"])
    relic = scenario.find("Orazca Relic", Zone.BATTLEFIELD)
    scenario.player("alice").has_citys_blessing = True
    assert _read(scenario, "you have the city's blessing", relic, controller="bob") is False
    assert _read(scenario, "you have the city's blessing", relic) is True


def test_twilight_prophet_upkeep_with_the_blessing():
    scenario = _board(["Twilight Prophet"])
    _step_begins(scenario, Step.UPKEEP)
    assert scenario.stack_names() == []
    scenario.player("alice").has_citys_blessing = True
    _step_begins(scenario, Step.UPKEEP)
    assert scenario.stack_names() == ["Twilight Prophet's triggered ability"]


def test_mausoleum_harpy_and_resplendent_griffin():
    scenario = _board(["Mausoleum Harpy", "Resplendent Griffin", "Memnite"])
    harpy = scenario.creature("Mausoleum Harpy", "alice")
    scenario.player("alice").has_citys_blessing = True
    scenario.game.destroy(scenario.creature("Memnite", "alice"))
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == ["Mausoleum Harpy's triggered ability"]
    del harpy


# -- a full party (CR 700.8) --------------------------------------------------------


def test_four_roles_are_a_full_party():
    scenario = _board(
        ["Squad Commander", "Infernal Vessel", "Blackbloom Rogue", "Eccentric Apprentice"]
    )
    assert party_size(scenario.game, "alice") == 4
    commander = scenario.creature("Squad Commander", "alice")
    assert _read(scenario, "you have a full party", commander) is True


def test_three_roles_are_not():
    scenario = _board(["Squad Commander", "Infernal Vessel", "Blackbloom Rogue"])
    assert party_size(scenario.game, "alice") == 3
    commander = scenario.creature("Squad Commander", "alice")
    assert _read(scenario, "you have a full party", commander) is False


def test_a_changeling_fills_the_missing_role():
    """CR 700.8b: counted for the role that gets the highest result - Orvar,
    the All-Form (changeling) is the Wizard here."""
    scenario = _board(
        ["Squad Commander", "Infernal Vessel", "Blackbloom Rogue", "Orvar, the All-Form"]
    )
    assert party_size(scenario.game, "alice") == 4


def test_two_of_one_role_count_once():
    scenario = _board(["Squad Commander", "Squad Commander", "Infernal Vessel"])
    assert party_size(scenario.game, "alice") == 2


def test_squad_commander_full_party_at_beginning_of_combat():
    scenario = _board(
        ["Squad Commander", "Infernal Vessel", "Blackbloom Rogue", "Eccentric Apprentice"]
    )
    _step_begins(scenario, Step.BEGINNING_OF_COMBAT)
    assert scenario.stack_names() == ["Squad Commander's triggered ability"]
    scenario.game.destroy(scenario.creature("Eccentric Apprentice", "alice"))
    (trigger,) = [item for item in scenario.game.stack if item.name.startswith("Squad")]
    assert not scenario.game._intervening_if_still_true(trigger)  # noqa: SLF001


def test_archpriest_linvala_and_trapfinder_read_the_same_clause():
    for name in ("Archpriest of Iona", "Linvala, Shield of Sea Gate", "Nimble Trapfinder"):
        scenario = _board([name, "Squad Commander", "Infernal Vessel", "Blackbloom Rogue"])
        source = scenario.find(name, Zone.BATTLEFIELD)
        # Archpriest is a Cleric, Linvala a Wizard, Trapfinder a Rogue.
        expected = name == "Linvala, Shield of Sea Gate"
        assert _read(scenario, "you have a full party", source) is expected, name


# -- the Ring-bearer (CR 701.54) -----------------------------------------------------


def test_gandalf_draws_when_another_creature_is_chosen():
    scenario = _board(["Gandalf, Friend of the Shire", "Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.will_choose_cards(bears)
    scenario.game.ring_tempts("alice", source_name="test")
    scenario.game.put_triggers_on_stack()
    assert "Gandalf, Friend of the Shire's triggered ability" in scenario.stack_names()


def test_galadriel_chosen_herself_does_not_trigger():
    scenario = _board(["Galadriel of Lothlórien"])
    scenario.game.ring_tempts("alice", source_name="test")
    scenario.game.put_triggers_on_stack()
    assert "Galadriel of Lothlórien's triggered ability" not in scenario.stack_names()


def test_aragorn_and_gandalf_read_the_chosen_ring_bearer():
    scenario = _board(["Aragorn, Company Leader", "Gandalf, Friend of the Shire"])
    aragorn = scenario.creature("Aragorn, Company Leader", "alice")
    faramir = scenario.creature("Gandalf, Friend of the Shire", "alice")
    event = GameEvent(
        event=ExtraTriggerEvent.RING_TEMPTS_YOU, player="alice", subject_id=aragorn.id
    )
    assert (
        _read(
            scenario,
            "you chose a creature other than Aragorn as your Ring-bearer",
            aragorn,
            event=event,
        )
        is False
    )
    assert (
        _read(
            scenario,
            "you chose a creature other than Gandalf as your Ring-bearer",
            faramir,
            event=event,
        )
        is True
    )
    no_creature = GameEvent(event=ExtraTriggerEvent.RING_TEMPTS_YOU, player="alice")
    assert (
        _read(
            scenario,
            "you chose a creature other than Gandalf as your Ring-bearer",
            faramir,
            event=no_creature,
        )
        is False
    )


def test_dunedain_rangers_tempts_only_without_a_ring_bearer():
    scenario = _board(["Dúnedain Rangers"], hand=["Forest", "Forest"])
    rangers = scenario.creature("Dúnedain Rangers", "alice")
    assert _read(scenario, "you don't control a Ring-bearer", rangers) is True
    scenario.game.ring_tempts("alice", source_name="test")
    assert _read(scenario, "you don't control a Ring-bearer", rangers) is False


# -- a permanent's own designations ----------------------------------------------


def test_polis_crusher_is_monstrous():
    scenario = _board(["Polis Crusher"])
    crusher = scenario.creature("Polis Crusher", "alice")
    assert _read(scenario, "this creature is monstrous", crusher) is False
    crusher.monstrous = True
    assert _read(scenario, "this creature is monstrous", crusher) is True


def test_renowned_and_suspected_read_off_the_permanent():
    scenario = _board(["Consul's Lieutenant", "Frantic Scapegoat", "Rubblebelt Braggart"])
    lieutenant = scenario.creature("Consul's Lieutenant", "alice")
    scapegoat = scenario.creature("Frantic Scapegoat", "alice")
    braggart = scenario.creature("Rubblebelt Braggart", "alice")
    assert _read(scenario, "it's renowned", lieutenant) is False
    lieutenant.renowned = True
    assert _read(scenario, "it's renowned", lieutenant) is True
    assert _read(scenario, "this creature is suspected", scapegoat) is False
    scapegoat.suspected = True
    assert _read(scenario, "this creature is suspected", scapegoat) is True
    assert _read(scenario, "it's not suspected", braggart) is True
    braggart.suspected = True
    assert _read(scenario, "it's not suspected", braggart) is False


def test_a_designation_ends_when_the_permanent_leaves():
    scenario = _board(["Scab-Clan Berserker"])
    berserker = scenario.creature("Scab-Clan Berserker", "alice")
    berserker.renowned = True
    berserker.suspected = True
    scenario.game.destroy(berserker)
    assert not berserker.renowned and not berserker.suspected
    assert _read(scenario, "this creature is renowned", berserker) is False


# -- dungeons (CR 309.7) --------------------------------------------------------------


def test_no_dungeon_completed_at_the_start():
    scenario = _board(["Eccentric Apprentice"])
    apprentice = scenario.creature("Eccentric Apprentice", "alice")
    assert _read(scenario, "you've completed a dungeon", apprentice) is False
    assert _read(scenario, "you haven't completed Tomb of Annihilation", apprentice) is True


# -- the probes ---------------------------------------------------------------


@pytest.mark.parametrize(
    "clause",
    [
        "you have the city's blessing",
        "you have a full party",
        "you chose a creature other than aragorn as your ring-bearer",
        "you don't control a ring-bearer",
        "you've completed a dungeon",
        "you haven't completed tomb of annihilation",
        "this creature is monstrous",
        "it's renowned",
        "this creature is renowned",
        "this creature is suspected",
        "it's not suspected",
    ],
)
def test_every_template_is_claimed(clause):
    assert conditions.claims(clause)


# -- renown builds the renowned designation (CR 702.112a) --------------------------


def _combat_damage_to_bob(scenario, attacker):
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(attacker)
    scenario.start_at(Step.DECLARE_BLOCKERS)
    scenario.no_blocks()
    scenario.combat_damage()
    scenario.game.put_triggers_on_stack()


def test_renown_triggers_on_combat_damage_to_a_player_and_makes_it_renowned():
    """CR 702.112a: "When this creature deals combat damage to a player, if
    it isn't renowned, put N +1/+1 counters on it and it becomes renowned." """
    scenario = _board(["Scab-Clan Berserker"])
    berserker = scenario.creature("Scab-Clan Berserker", "alice")
    _combat_damage_to_bob(scenario, berserker)
    assert "Scab-Clan Berserker's triggered ability" in scenario.stack_names()
    scenario.pass_until_resolved()
    assert berserker.renowned
    assert berserker.counter_count("+1/+1") == 1


def test_a_renowned_creature_does_not_become_renowned_again():
    scenario = _board(["Consul's Lieutenant"])
    lieutenant = scenario.creature("Consul's Lieutenant", "alice")
    lieutenant.renowned = True
    _combat_damage_to_bob(scenario, lieutenant)
    names = scenario.stack_names()
    assert all("Consul's Lieutenant" not in name for name in names) or names == [
        "Consul's Lieutenant's triggered ability"
    ]
    scenario.pass_until_resolved()
    assert lieutenant.counter_count("+1/+1") == 0


def test_consuls_lieutenant_attack_trigger_needs_renowned():
    scenario = _board(["Consul's Lieutenant", "Grizzly Bears"])
    lieutenant = scenario.creature("Consul's Lieutenant", "alice")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(lieutenant, scenario.creature("Grizzly Bears", "alice"))
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == []
    assert scenario.game.intervening_if_notices == []


def test_renown_is_executed():
    from magic_cards_model.machines.keywords import executes

    assert executes("Renown")
