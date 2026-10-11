"""Scenario: an object's own state as a printed condition - attacking, power
and toughness, keywords, colour and type, what is attached to it, where it
is, and how it compares with the source.

Rules read whole with `mise run rules:find` in the session that wrote this:

- **CR 506.4** - a permanent is attacking from its declaration until it is
  removed from combat or combat ends.
- **CR 208.1** / **CR 613.5** - power and toughness are the computed values.
- **CR 603.10a** - a leaves-the-battlefield ability looks back: "it was a
  Human", "its power was 3 or greater" are asked of the permanent as it last
  existed on the battlefield.
- **CR 303.4** / **CR 301.5** - "enchanted creature" and "equipped creature"
  are the object the Aura or Equipment is attached to.
- **CR 700.6** - "historic" is an artifact, a legendary or a Saga.
- **CR 603.4** / **CR 608.2a** - an intervening "if" is checked as the event
  occurs and again on resolution.
- **CR 602.5b** - an activation restriction follows the permanent to a new
  controller.
- **CR 202.3e** - a spell's mana value on the stack.
"""

import pytest

from magic_cards_model.machines import Step, conditions
from magic_cards_model.machines.conditions import ConditionContext
from magic_cards_model.machines.triggers import GameEvent, TriggerEvent
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def _board(alice=(), *, bob=(), hand=(), graveyard=(), library=None, bob_hand=()):
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
        .player("bob", battlefield=list(bob), hand=list(bob_hand), library=["Plains"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _read(scenario, clause: str, source, *, controller="alice", event=None, ability=None):
    return conditions.read_condition(
        ConditionContext(scenario.game, controller, source=source, event=event, ability=ability),
        clause,
    )


def _refused_as_unmet(refusal: str | None) -> None:
    assert refusal is not None
    assert "activation restriction is not met" in refusal
    assert "602.5b" in refusal


def _step_begins(scenario, step: Step, player: str = "alice") -> None:
    scenario.game.emit(GameEvent(event=TriggerEvent.BEGINNING_OF_STEP, step=step, player=player))
    scenario.game.put_triggers_on_stack()


def _next_turn(scenario) -> None:
    scenario.turn.advance_to(Step.CLEANUP)
    scenario.advance()
    scenario.advance()


# -- "this creature is attacking" --------------------------------------------


def test_forgestoker_dragon_activates_only_while_attacking():
    scenario = _board(["Forgestoker Dragon", "Mountain", "Mountain"], bob=["Grizzly Bears"])
    dragon = scenario.creature("Forgestoker Dragon", "alice")
    _refused_as_unmet(scenario.why_cannot_activate(dragon, 0))
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(dragon)
    assert scenario.why_cannot_activate(dragon, 0) is None


def test_glint_horn_buccaneer_reads_the_same_template():
    scenario = _board(["Glint-Horn Buccaneer"])
    buccaneer = scenario.creature("Glint-Horn Buccaneer", "alice")
    _refused_as_unmet(scenario.why_cannot_activate(buccaneer, 0))
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(buccaneer)
    assert scenario.why_cannot_activate(buccaneer, 0) is None


def test_fire_lord_azula_names_itself_attacking():
    scenario = _board(["Fire Lord Azula"])
    azula = scenario.creature("Fire Lord Azula", "alice")
    clause = "Fire Lord Azula is attacking"
    assert _read(scenario, clause, azula) is False
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(azula)
    assert _read(scenario, clause, azula) is True


def test_a_name_that_is_not_the_source_is_not_attacking():
    scenario = _board(["Fire Lord Azula", "Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(scenario.creature("Fire Lord Azula", "alice"))
    assert _read(scenario, "Fire Lord Azula is attacking", bears) is False


# -- power and toughness -----------------------------------------------------


def test_bloodshot_trainee_needs_power_four():
    scenario = _board(["Bloodshot Trainee"], bob=["Grizzly Bears"])
    trainee = scenario.creature("Bloodshot Trainee", "alice")
    _refused_as_unmet(scenario.why_cannot_activate(trainee, 0))
    trainee.add_counters(Counter.PLUS_ONE, 2)
    assert scenario.why_cannot_activate(trainee, 0) is None


def test_greenhilt_trainee_reads_the_computed_power():
    scenario = _board(["Greenhilt Trainee", "Forest"], hand=["Giant Growth"])
    trainee = scenario.creature("Greenhilt Trainee", "alice")
    _refused_as_unmet(scenario.why_cannot_activate(trainee, 0))
    scenario.cast_and_resolve(
        "Giant Growth", *scenario.untapped_sources("Forest"), targets=[trainee]
    )
    assert scenario.why_cannot_activate(trainee, 0) is None


def test_kitsa_names_itself_by_its_short_name():
    scenario = _board(["Kitsa, Otterball Elite"])
    kitsa = scenario.creature("Kitsa, Otterball Elite", "alice")
    _refused_as_unmet(scenario.why_cannot_activate(kitsa, 1))
    kitsa.add_counters(Counter.PLUS_ONE, 2)
    assert scenario.why_cannot_activate(kitsa, 1) is None


def test_the_power_restriction_follows_the_creature_to_its_new_controller():
    """CR 602.5b: bob steals Bloodshot Trainee; still power 2, still
    refused."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Bloodshot Trainee"], library=["Plains"] * 5)
        .player(
            "bob", hand=["Act of Treason"], battlefield=["Mountain"] * 3, library=["Plains"] * 5
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    trainee = scenario.creature("Bloodshot Trainee", "alice")
    _next_turn(scenario)
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve(
        "Act of Treason",
        *scenario.untapped_sources("Mountain", "Mountain", "Mountain", username="bob"),
        targets=[trainee],
        username="bob",
    )
    _refused_as_unmet(scenario.why_cannot_activate(trainee, 0, username="bob"))
    trainee.add_counters(Counter.PLUS_ONE, 2)
    assert scenario.why_cannot_activate(trainee, 0, username="bob") is None


def test_deathknell_berserker_looks_back_at_its_power():
    """ "When this creature dies, if its power was 3 or greater" - a
    pumped Berserker dying keeps the power it died with (CR 603.10a)."""
    scenario = _board(["Deathknell Berserker", "Forest"], hand=["Giant Growth"])
    berserker = scenario.creature("Deathknell Berserker", "alice")
    scenario.cast_and_resolve(
        "Giant Growth", *scenario.untapped_sources("Forest"), targets=[berserker]
    )
    scenario.game.destroy(berserker)
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == ["Deathknell Berserker's triggered ability"]


def test_deathknell_berserker_at_power_two_does_not_trigger():
    scenario = _board(["Deathknell Berserker"])
    scenario.game.destroy(scenario.creature("Deathknell Berserker", "alice"))
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == []
    assert scenario.game.intervening_if_notices == []


def test_massacre_girl_reads_a_dead_creatures_toughness():
    """ "Whenever a creature an opponent controls dies, if its toughness was
    less than 1" - a -1/-1 counter killed it."""
    scenario = _board(["Massacre Girl, Known Killer"], bob=["Memnite"])
    memnite = scenario.creature("Memnite", "bob")
    memnite.add_counters(Counter.MINUS_ONE, 1)
    scenario.state_based_actions()
    scenario.game.put_triggers_on_stack()
    assert "Massacre Girl, Known Killer's triggered ability" in scenario.stack_names()


def test_massacre_girl_does_not_trigger_on_a_destroyed_creature():
    scenario = _board(["Massacre Girl, Known Killer"], bob=["Memnite"])
    scenario.game.destroy(scenario.creature("Memnite", "bob"))
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == []


def test_writ_of_passage_asks_the_attacking_creature():
    """ "Whenever enchanted creature attacks, if its power is 2 or less" -
    "its" is the creature that attacked."""
    scenario = _board(["Writ of Passage", "Grizzly Bears", "Hill Giant"])
    writ = scenario.find("Writ of Passage", Zone.BATTLEFIELD)
    bears = scenario.creature("Grizzly Bears", "alice")
    writ.attach_to(bears)
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(bears)
    scenario.game.put_triggers_on_stack()
    assert "Writ of Passage's triggered ability" in scenario.stack_names()


def test_writ_of_passage_on_a_three_power_creature_does_not_trigger():
    scenario = _board(["Writ of Passage", "Hill Giant"])
    writ = scenario.find("Writ of Passage", Zone.BATTLEFIELD)
    giant = scenario.creature("Hill Giant", "alice")
    writ.attach_to(giant)
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(giant)
    scenario.game.put_triggers_on_stack()
    assert "Writ of Passage's triggered ability" not in scenario.stack_names()


def test_arachnus_web_reads_enchanted_creatures_power():
    scenario = _board(["Arachnus Web"], bob=["Hill Giant", "Serra Angel"])
    web = scenario.find("Arachnus Web", Zone.BATTLEFIELD)
    web.attach_to(scenario.creature("Hill Giant", "bob"))
    _step_begins(scenario, Step.END_STEP)
    assert scenario.stack_names() == []
    web.attach_to(scenario.creature("Serra Angel", "bob"))
    _step_begins(scenario, Step.END_STEP)
    assert scenario.stack_names() == ["Arachnus Web's triggered ability"]


def test_syr_vondam_while_its_power_is_four():
    scenario = _board(["Syr Vondam, Sunstar Exemplar"])
    vondam = scenario.creature("Syr Vondam, Sunstar Exemplar", "alice")
    vondam.add_counters(Counter.PLUS_ONE, 2)
    scenario.game.destroy(vondam)
    event = GameEvent(event=TriggerEvent.DIES, subject_id=vondam.id)
    assert _read(scenario, "its power is 4 or greater", vondam, event=event) is True


# -- keywords -----------------------------------------------------------------


def test_surge_engine_refused_while_it_has_defender_and_is_not_blue():
    scenario = _board(["Surge Engine"])
    engine = scenario.creature("Surge Engine", "alice")
    _refused_as_unmet(scenario.why_cannot_activate(engine, 1))
    _refused_as_unmet(scenario.why_cannot_activate(engine, 2))


def test_defender_and_blue_read_off_the_computed_creature():
    """The same two clauses asked of a creature without defender, and of a
    blue one (Kitsa, Otterball Elite)."""
    scenario = _board(["Grizzly Bears", "Kitsa, Otterball Elite"])
    bears = scenario.creature("Grizzly Bears", "alice")
    kitsa = scenario.creature("Kitsa, Otterball Elite", "alice")
    assert _read(scenario, "this creature doesn't have defender", bears) is True
    assert _read(scenario, "this creature is blue", bears) is False
    assert _read(scenario, "this creature is blue", kitsa) is True


def test_guardian_of_the_ages_has_defender():
    scenario = _board(["Guardian of the Ages"])
    guardian = scenario.creature("Guardian of the Ages", "alice")
    assert _read(scenario, "this creature has defender", guardian) is True
    assert _read(scenario, "this creature doesn't have defender", guardian) is False


@pytest.mark.parametrize(
    ("clause", "expected"), [("it has first strike", False), ("it doesn't have first strike", True)]
)
def test_momentum_rumbler_reads_first_strike(clause, expected):
    scenario = _board(["Momentum Rumbler"])
    rumbler = scenario.creature("Momentum Rumbler", "alice")
    assert _read(scenario, clause, rumbler) is expected
    rumbler.add_counters("first strike", 1)
    assert _read(scenario, clause, rumbler) is (not expected)


# -- colour, type and state of the enchanted object --------------------------


def test_howl_of_the_hunt_reads_a_subtype_list():
    scenario = _board(["Howl of the Hunt", "Grizzly Bears", "Werewolf Pack Leader"])
    howl = scenario.find("Howl of the Hunt", Zone.BATTLEFIELD)
    clause = "enchanted creature is a Wolf or Werewolf"
    howl.attach_to(scenario.creature("Grizzly Bears", "alice"))
    assert _read(scenario, clause, howl) is False
    howl.attach_to(scenario.creature("Werewolf Pack Leader", "alice"))
    assert _read(scenario, clause, howl) is True


def test_narcolepsy_taps_an_untapped_creature_at_upkeep():
    scenario = _board(["Narcolepsy"], bob=["Grizzly Bears"])
    narcolepsy = scenario.find("Narcolepsy", Zone.BATTLEFIELD)
    bears = scenario.creature("Grizzly Bears", "bob")
    narcolepsy.attach_to(bears)
    _step_begins(scenario, Step.UPKEEP, "bob")
    assert scenario.stack_names() == ["Narcolepsy's triggered ability"]
    scenario.pass_until_resolved()
    assert bears.tapped, "the trigger's 'tap it' taps the enchanted creature (CR 303.4b)"
    _step_begins(scenario, Step.UPKEEP, "bob")
    assert scenario.stack_names() == []


def test_narcolepsy_removed_when_tapped_in_response():
    scenario = _board(["Narcolepsy"], bob=["Grizzly Bears"])
    narcolepsy = scenario.find("Narcolepsy", Zone.BATTLEFIELD)
    bears = scenario.creature("Grizzly Bears", "bob")
    narcolepsy.attach_to(bears)
    _step_begins(scenario, Step.UPKEEP, "bob")
    (trigger,) = scenario.game.stack
    scenario.game.tap_permanent(bears)
    assert not scenario.game._intervening_if_still_true(trigger)  # noqa: SLF001


def test_ray_of_frost_reads_enchanted_creatures_color_and_state():
    scenario = _board(["Ray of Frost"], bob=["Goblin Guide", "Grizzly Bears"])
    ray = scenario.find("Ray of Frost", Zone.BATTLEFIELD)
    ray.attach_to(scenario.creature("Goblin Guide", "bob"))
    assert _read(scenario, "enchanted creature is red", ray) is True
    bears = scenario.creature("Grizzly Bears", "bob")
    ray.attach_to(bears)
    assert _read(scenario, "enchanted creature is red", ray) is False
    assert _read(scenario, "enchanted permanent is tapped", ray) is False
    bears.tap()
    assert _read(scenario, "enchanted permanent is tapped", ray) is True


def test_artificers_hex_reads_what_the_equipment_is_attached_to():
    scenario = _board(["Artificer's Hex", "Bonesplitter"], bob=["Grizzly Bears"])
    hex_ = scenario.find("Artificer's Hex", Zone.BATTLEFIELD)
    bonesplitter = scenario.find("Bonesplitter", Zone.BATTLEFIELD)
    hex_.attach_to(bonesplitter)
    clause = "enchanted Equipment is attached to a creature"
    assert _read(scenario, clause, hex_) is False
    bonesplitter.attach_to(scenario.creature("Grizzly Bears", "bob"))
    assert _read(scenario, clause, hex_) is True


# -- where the source is -------------------------------------------------------


def test_myr_servitor_and_astral_drift_on_the_battlefield():
    scenario = _board(["Myr Servitor", "Astral Drift"])
    servitor = scenario.creature("Myr Servitor", "alice")
    drift = scenario.find("Astral Drift", Zone.BATTLEFIELD)
    assert _read(scenario, "this creature is on the battlefield", servitor) is True
    assert _read(scenario, "this enchantment is on the battlefield", drift) is True
    scenario.game.destroy(servitor)
    assert _read(scenario, "this creature is on the battlefield", servitor) is False


def test_senu_in_exile():
    scenario = _board(["Senu, Keen-Eyed Protector"])
    senu = scenario.creature("Senu, Keen-Eyed Protector", "alice")
    assert _read(scenario, "this card is exiled", senu) is False
    scenario.game.exile_permanent(senu)
    assert _read(scenario, "this card is exiled", senu) is True


def test_stalking_yeti_is_on_the_battlefield():
    scenario = _board(["Stalking Yeti"])
    yeti = scenario.creature("Stalking Yeti", "alice")
    assert _read(scenario, "it's on the battlefield", yeti) is True


# -- what it was (CR 603.10a) -------------------------------------------------


def test_avacyns_collar_asks_whether_it_was_a_human():
    scenario = _board(["Avacyn's Collar", "Savannah Lions", "Raging Goblin"])
    collar = scenario.find("Avacyn's Collar", Zone.BATTLEFIELD)
    goblin = scenario.creature("Raging Goblin", "alice")
    collar.attach_to(goblin)
    scenario.game.destroy(goblin)
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == []
    assert scenario.game.intervening_if_notices == []


def test_slayers_plate_triggers_on_a_human():
    """A second printing of "if it was a Human": Infernal Vessel is a Human
    Cleric."""
    scenario = _board(["Slayer's Plate", "Infernal Vessel"])
    plate = scenario.find("Slayer's Plate", Zone.BATTLEFIELD)
    vessel = scenario.creature("Infernal Vessel", "alice")
    plate.attach_to(vessel)
    scenario.game.destroy(vessel)
    scenario.game.put_triggers_on_stack()
    assert "Slayer's Plate's triggered ability" in scenario.stack_names()


def test_infernal_vessel_wasnt_a_demon():
    scenario = _board(["Infernal Vessel"])
    vessel = scenario.creature("Infernal Vessel", "alice")
    scenario.game.destroy(vessel)
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == ["Infernal Vessel's triggered ability"]


def test_curators_ward_on_a_historic_permanent():
    scenario = _board(["Curator's Ward", "Bonesplitter", "Grizzly Bears"])
    ward = scenario.find("Curator's Ward", Zone.BATTLEFIELD)
    bonesplitter = scenario.find("Bonesplitter", Zone.BATTLEFIELD)
    ward.attach_to(bonesplitter)
    event = GameEvent(event=TriggerEvent.LEAVES_THE_BATTLEFIELD, subject_id=bonesplitter.id)
    scenario.game.destroy(bonesplitter)
    assert _read(scenario, "it was historic", ward, event=event) is True
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.game.destroy(bears)
    event = GameEvent(event=TriggerEvent.LEAVES_THE_BATTLEFIELD, subject_id=bears.id)
    assert _read(scenario, "it was historic", ward, event=event) is False


def test_koll_returns_a_creature_that_was_equipped():
    scenario = _board(["Koll, the Forgemaster", "Grizzly Bears", "Bonesplitter", "Memnite"])
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.find("Bonesplitter", Zone.BATTLEFIELD).attach_to(bears)
    scenario.game.destroy(bears)
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == ["Koll, the Forgemaster's triggered ability"]
    scenario.pass_until_resolved()
    assert bears.zone is Zone.HAND


def test_koll_ignores_a_creature_that_was_neither():
    scenario = _board(["Koll, the Forgemaster", "Memnite"])
    scenario.game.destroy(scenario.creature("Memnite", "alice"))
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == []


# -- enchanted or equipped: the source itself ---------------------------------


def test_warchanter_skald_enchanted_or_equipped():
    scenario = _board(["Warchanter Skald", "Bonesplitter"])
    skald = scenario.creature("Warchanter Skald", "alice")
    scenario.game.tap_permanent(skald)
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == []
    skald.untap()
    scenario.find("Bonesplitter", Zone.BATTLEFIELD).attach_to(skald)
    scenario.game.tap_permanent(skald)
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == ["Warchanter Skald's triggered ability"]


def test_kitsune_mystic_counts_auras():
    scenario = _board(["Kitsune Mystic", "Rancor", "Writ of Passage"])
    mystic = scenario.creature("Kitsune Mystic", "alice")
    clause = "this creature is enchanted by two or more Auras"
    scenario.find("Rancor", Zone.BATTLEFIELD).attach_to(mystic)
    assert _read(scenario, clause, mystic) is False
    scenario.find("Writ of Passage", Zone.BATTLEFIELD).attach_to(mystic)
    assert _read(scenario, clause, mystic) is True


# -- its type now ---------------------------------------------------------------


def test_opal_guardian_is_an_enchantment():
    scenario = _board(["Opal Guardian"], bob_hand=[])
    guardian = scenario.find("Opal Guardian", Zone.BATTLEFIELD)
    assert _read(scenario, "this permanent is an enchantment", guardian) is True


def test_phyrexian_totem_is_a_creature_only_while_animated():
    """ "Whenever this permanent is dealt damage, if it's a creature" - "it"
    is the permanent dealt the damage."""
    scenario = _board(["Phyrexian Totem"])
    totem = scenario.find("Phyrexian Totem", Zone.BATTLEFIELD)
    from magic_cards_model.machines.abilities import TriggeredAbility, parse_abilities

    (ability,) = [a for a in parse_abilities(totem.card) if isinstance(a, TriggeredAbility)]
    event = GameEvent(event=TriggerEvent.DEALS_DAMAGE, subject_id=None, target_id=totem.id)
    assert _read(scenario, "it's a creature", totem, event=event, ability=ability) is False


# -- comparisons with the source ---------------------------------------------


def test_pelt_collector_compares_the_entering_creatures_power():
    scenario = _board(["Pelt Collector"], hand=["Grizzly Bears"])
    scenario.put_onto_battlefield("Grizzly Bears", "alice")
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == ["Pelt Collector's triggered ability"]


def test_evolving_adaptive_greater_power_or_toughness():
    """Evolving Adaptive with no oil counters is 0/0; a 1/1 is greater."""
    scenario = _board(["Evolving Adaptive"], hand=["Memnite"])
    adaptive = scenario.creature("Evolving Adaptive", "alice")
    clause = "that creature has greater power or toughness than this creature"
    memnite = scenario.put_onto_battlefield("Memnite", "alice")
    event = GameEvent(event=TriggerEvent.ENTERS_THE_BATTLEFIELD, subject_id=memnite.id)
    assert _read(scenario, clause, adaptive, event=event) is True


def test_a_smaller_creature_is_not_greater():
    """Hulkling, Burgeoning Bruiser is 2/3: Memnite's 1/1 is neither."""
    scenario = _board(["Hulkling, Burgeoning Bruiser"], hand=["Memnite"])
    hulkling = scenario.creature("Hulkling, Burgeoning Bruiser", "alice")
    memnite = scenario.put_onto_battlefield("Memnite", "alice")
    event = GameEvent(event=TriggerEvent.ENTERS_THE_BATTLEFIELD, subject_id=memnite.id)
    clause = "it has greater power or toughness than Hulkling"
    assert _read(scenario, clause, hulkling, event=event) is False


def test_hulkling_names_itself_in_the_comparison():
    scenario = _board(["Hulkling, Burgeoning Bruiser"], hand=["Hill Giant"])
    hulkling = scenario.creature("Hulkling, Burgeoning Bruiser", "alice")
    giant = scenario.put_onto_battlefield("Hill Giant", "alice")
    event = GameEvent(event=TriggerEvent.ENTERS_THE_BATTLEFIELD, subject_id=giant.id)
    assert _read(scenario, "it has greater power or toughness than Hulkling", hulkling, event=event)


def test_sharp_eyed_rookie_compound_comparison():
    scenario = _board(["Sharp-Eyed Rookie"], hand=["Memnite", "Hill Giant"])
    rookie = scenario.creature("Sharp-Eyed Rookie", "alice")
    clause = (
        "its power is greater than this creature's power or its toughness is greater than "
        "this creature's toughness"
    )
    memnite = scenario.put_onto_battlefield("Memnite", "alice")
    event = GameEvent(event=TriggerEvent.ENTERS_THE_BATTLEFIELD, subject_id=memnite.id)
    assert _read(scenario, clause, rookie, event=event) is False
    giant = scenario.put_onto_battlefield("Hill Giant", "alice")
    event = GameEvent(event=TriggerEvent.ENTERS_THE_BATTLEFIELD, subject_id=giant.id)
    assert _read(scenario, clause, rookie, event=event) is True


def test_sigil_captain_that_creature_is_one_one():
    scenario = _board(["Sigil Captain"], hand=["Grizzly Bears", "Memnite"])
    scenario.put_onto_battlefield("Memnite", "alice")
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == ["Sigil Captain's triggered ability"]
    scenario.pass_until_resolved()
    scenario.put_onto_battlefield("Grizzly Bears", "alice")
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == []


# -- how it came -----------------------------------------------------------------


def test_rocket_powered_goblin_glider_was_not_cast_from_a_graveyard():
    scenario = _board(["Mountain"] * 3, hand=["Rocket-Powered Goblin Glider"])
    scenario.cast_and_resolve(
        "Rocket-Powered Goblin Glider", *scenario.untapped_sources(*["Mountain"] * 3)
    )
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == []


def test_twilight_diviner_they_entered_from_a_graveyard():
    scenario = _board(["Twilight Diviner"], graveyard=["Grizzly Bears"], hand=["Memnite"])
    diviner = scenario.creature("Twilight Diviner", "alice")
    clause = "they entered or were cast from a graveyard"
    memnite = scenario.put_onto_battlefield("Memnite", "alice")
    event = GameEvent(
        event=TriggerEvent.ENTERS_THE_BATTLEFIELD, subject_id=memnite.id, origin_zone=Zone.HAND
    )
    assert _read(scenario, clause, diviner, event=event) is False
    bears = scenario.put_onto_battlefield("Grizzly Bears", "alice", Zone.GRAVEYARD)
    event = GameEvent(
        event=TriggerEvent.ENTERS_THE_BATTLEFIELD, subject_id=bears.id, origin_zone=Zone.GRAVEYARD
    )
    assert _read(scenario, clause, diviner, event=event) is True


def test_cemetery_gatekeeper_shares_a_card_type_with_the_exiled_card():
    scenario = _board(["Cemetery Gatekeeper"], graveyard=["Grizzly Bears"], hand=["Forest"])
    gatekeeper = scenario.creature("Cemetery Gatekeeper", "alice")
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")
    from magic_cards_model.models.card_state import ExileAnnotation, ExileMarker

    scenario.game.exile_cards([bears])
    bears.exile_annotation = ExileAnnotation(
        marker=ExileMarker.IMPRINTED,
        linked_permanent_id=gatekeeper.id,
        linked_permanent_stamp=gatekeeper.zone_change_stamp,
    )
    forest = scenario.find("Forest", Zone.HAND, "alice")
    clause = "it shares a card type with the exiled card"
    event = GameEvent(event=TriggerEvent.CAST_SPELL, subject_id=forest.id)
    assert _read(scenario, clause, gatekeeper, event=event) is False
    event = GameEvent(event=TriggerEvent.CAST_SPELL, subject_id=gatekeeper.id)
    assert _read(scenario, clause, gatekeeper, event=event) is True


# -- equipped creature's combat damage this turn -------------------------------


def test_thirsting_axe_sacrificed_unless_equipped_creature_hit_a_creature():
    scenario = _board(["Thirsting Axe", "Grizzly Bears"], bob=["Memnite", "Grizzly Bears"])
    axe = scenario.find("Thirsting Axe", Zone.BATTLEFIELD)
    axe.attach_to(scenario.creature("Grizzly Bears", "alice"))
    clause = "equipped creature didn't deal combat damage to a creature this turn"
    assert _read(scenario, clause, axe) is True
    scenario.game.deal_damage(
        scenario.creature("Memnite", "bob"), 2, source=scenario.creature("Grizzly Bears", "alice")
    )
    assert _read(scenario, clause, axe) is True, "noncombat damage does not count"
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(bears)
    scenario.start_at(Step.DECLARE_BLOCKERS)
    scenario.block(bears, scenario.creature("Grizzly Bears", "bob"))
    scenario.combat_damage()
    assert _read(scenario, clause, axe) is False


# -- the probes ---------------------------------------------------------------


@pytest.mark.parametrize(
    "clause",
    [
        "this creature is attacking",
        "fire lord azula is attacking",
        "it's attacking",
        "this creature's power is 4 or greater",
        "kitsa's power is 3 or greater",
        "its power was 3 or greater",
        "its toughness was less than 1",
        "its power is 2 or less",
        "enchanted creature's power is 4 or greater",
        "this creature doesn't have defender",
        "this creature is blue",
        "it has mutate",
        "enchanted creature has toxic",
        "enchanted creature is a wolf or werewolf",
        "enchanted creature is untapped",
        "enchanted permanent is tapped",
        "enchanted equipment is attached to a creature",
        "this card is exiled",
        "it was a human",
        "it wasn't a demon",
        "it was historic",
        "it was enchanted or equipped",
        "it's enchanted or equipped",
        "this creature is enchanted by two or more auras",
        "this permanent is an enchantment",
        "it's a creature",
        "that creature has greater power or toughness than this creature",
        "that creature's power is greater than this creature's",
        "that creature is 1/1",
        "it was cast from your graveyard",
        "they entered or were cast from a graveyard",
        "it shares a card type with the exiled card",
        "equipped creature didn't deal combat damage to a creature this turn",
    ],
)
def test_every_template_is_claimed(clause):
    assert conditions.claims(clause)


# -- an effect's own "if" keeps its anaphor unread (CR 608.2c) ----------------


@pytest.mark.parametrize(
    ("clause", "readable"),
    [
        ("that creature is a Bear", False),  # Little Bear: the target it untapped
        ("it's a creature", False),  # Teyo: the target permanent
        ("its power is 3 or greater", False),  # Tribute to the World Tree
        ("this creature has a +1/+1 counter on it", True),
        ("you have the city's blessing", True),
    ],
)
def test_an_effect_level_anaphor_is_not_asked_of_the_source(clause, readable):
    """Inside a resolving effect, "it" is whatever an earlier instruction
    named - a target, not the trigger event's subject or the source - so the
    object readers do not gate an effect on it (`effects._effect_condition_
    is_readable`); an intervening "if" still reads it."""
    from magic_cards_model.machines.effects import _effect_condition_is_readable

    assert _effect_condition_is_readable(clause) is readable
    assert conditions.claims(clause)
