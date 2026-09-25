"""Board-count conditions: "you control N or more / a / another / no / exactly
<quality>", read against the computed board.

Rules verified with `mise run rules:find` in the session that wrote this file:

- **CR 603.4** - an intervening "if" is checked as the trigger event occurs;
  false then, the ability does not trigger.
- **CR 608.2a** - the same clause is rechecked as the ability resolves; false
  then, the ability is removed from the stack and does nothing.
- **CR 602.5b** - "Activate only if ..." keeps applying to the object after
  its controller changes, and "you" is whoever activates it (**CR 109.5**).
- **CR 613.5** - every count reads the board with every continuous effect
  applied.
- **CR 700.9** - a permanent is modified if it has a counter on it, is
  equipped, or is enchanted by an Aura its controller controls.
- **CR 700.12** - "outlaw" is an Assassin, Mercenary, Pirate, Rogue and/or
  Warlock.
- **CR 208.4b** - a creature's base power is its power after
  characteristic-defining and setting effects, ignoring effects and counters
  that only modify it.
- **CR 108.3** - the owner of a permanent is the player who started the game
  with it (or created it).

Each template is proven on at least two printings: the one listed as unread
and a second carrying the same words.
"""

import pytest

from magic_cards_model.machines import Step, conditions
from magic_cards_model.machines.conditions import ConditionContext
from magic_cards_model.machines.triggers import (
    GameEvent,
    TriggerEvent,
    intervening_if_answer,
    triggered_abilities_of,
)
from tests.cards import card
from tests.scenarios.harness import Scenario

RESTRICTION_NOT_MET = "{}'s activation restriction is not met (CR 602.5b)"


def _board(
    alice: list[str],
    bob: list[str] | None = None,
    *,
    hand=None,
    bob_hand=None,
    step: Step = Step.PRECOMBAT_MAIN,
):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=alice, hand=hand or [], library=["Plains"] * 6)
        .player("bob", battlefield=bob or [], hand=bob_hand or [], library=["Plains"] * 6)
        .build()
    )
    scenario.start_at(step)
    return scenario


def _condition(name: str) -> tuple:
    """The printing's one triggered ability with a condition, and that
    condition's text (an intervening "if" or the event's "while" qualifier)."""
    (ability,) = [
        each
        for each in triggered_abilities_of(card(name))
        if each.intervening_if or each.event_qualifier
    ]
    return ability, ability.intervening_if or ability.event_qualifier


def _holds(scenario, name: str, owner: str = "alice", event: GameEvent | None = None):
    """The printed condition, asked on this board of the permanent carrying
    it - the intervening "if" through the triggered chain, a "while"
    qualifier through the shared reader."""
    source = scenario.creature(name, owner)
    ability, _ = _condition(name)
    if ability.intervening_if:
        return intervening_if_answer(scenario.game, ability, source, event)
    return conditions.read_condition(
        ConditionContext(scenario.game, owner, source=source, event=event, ability=ability),
        ability.event_qualifier,
    )


def _step(scenario, step: Step, player: str = "alice") -> None:
    scenario.start_at(step)
    scenario.game.emit(GameEvent(event=TriggerEvent.BEGINNING_OF_STEP, step=step, player=player))
    scenario.game.put_triggers_on_stack()


# -- "Activate only if you control a <X> or a <Y>" (every Verge) --------------


def test_a_verge_second_ability_is_refused_without_either_land():
    """Gloomlake Verge: "{T}: Add {B}. Activate only if you control an Island
    or a Swamp." A Plains is neither."""
    scenario = _board(["Gloomlake Verge", "Plains"])
    verge = scenario.creature("Gloomlake Verge")
    assert scenario.why_cannot_activate(verge, index=1) == RESTRICTION_NOT_MET.format(
        "Gloomlake Verge"
    )
    assert scenario.why_cannot_activate(verge, index=0) is None


@pytest.mark.parametrize("land", ["Island", "Swamp"])
def test_a_verge_second_ability_is_activatable_with_either_land(land):
    scenario = _board(["Gloomlake Verge", land])
    verge = scenario.creature("Gloomlake Verge")
    assert scenario.why_cannot_activate(verge, index=1) is None


def test_a_verge_makes_its_second_color_once_the_land_is_there():
    """The restriction met, the ability resolves like any mana ability."""
    scenario = _board(["Gloomlake Verge", "Swamp"])
    verge = scenario.creature("Gloomlake Verge")
    scenario.activate(verge, index=1)
    assert sum(scenario.player("alice").mana_pool.floating.values()) == 1


def test_a_second_verge_reads_its_own_pair():
    """Thornspire Verge: "Activate only if you control a Mountain or a
    Forest." - an Island does not satisfy it, a Forest does."""
    scenario = _board(["Thornspire Verge", "Island"])
    verge = scenario.creature("Thornspire Verge")
    assert scenario.why_cannot_activate(verge, index=1) == RESTRICTION_NOT_MET.format(
        "Thornspire Verge"
    )
    scenario = _board(["Thornspire Verge", "Forest"])
    assert scenario.why_cannot_activate(scenario.creature("Thornspire Verge"), index=1) is None


def test_the_land_is_counted_as_its_subtype_not_its_name():
    """A Verge itself is no basic land type, so two Verges alone do not
    satisfy each other."""
    scenario = _board(["Thornspire Verge", "Gloomlake Verge"])
    verge = scenario.creature("Thornspire Verge")
    assert scenario.why_cannot_activate(verge, index=1) is not None


# -- "Activate only if you control a creature with flying" --------------------


def test_a_creature_with_flying_is_needed_to_activate():
    """Celestial Enforcer: "{1}{W}, {T}: Tap target creature. Activate only if
    you control a creature with flying." """
    scenario = _board(["Celestial Enforcer", "Grizzly Bears", "Plains", "Plains"])
    enforcer = scenario.creature("Celestial Enforcer")
    assert scenario.why_cannot_activate(enforcer) == RESTRICTION_NOT_MET.format(
        "Celestial Enforcer"
    )
    scenario = _board(["Celestial Enforcer", "Wind Drake", "Plains", "Plains"])
    assert scenario.why_cannot_activate(scenario.creature("Celestial Enforcer")) is None


def test_the_restriction_follows_the_activator_after_a_control_change():
    """CR 602.5b / CR 109.5: bob takes Celestial Enforcer with Act of Treason.
    Alice's Wind Drake is not his, so he cannot activate it."""
    scenario = _board(
        ["Celestial Enforcer", "Wind Drake"],
        ["Mountain", "Mountain", "Mountain", "Plains", "Plains"],
        bob_hand=["Act of Treason"],
    )
    enforcer = scenario.creature("Celestial Enforcer")
    assert scenario.why_cannot_activate(enforcer) is None
    scenario.turn.advance_to(Step.CLEANUP)
    scenario.advance()  # bob's untap step
    scenario.start_at(Step.PRECOMBAT_MAIN)
    assert scenario.turn.active_player == "bob"
    scenario.cast_and_resolve(
        "Act of Treason",
        *scenario.untapped_sources("Mountain", "Mountain", "Mountain", username="bob"),
        targets=[enforcer],
        username="bob",
    )
    assert scenario.game.controller_of(enforcer).username == "bob"
    assert scenario.why_cannot_activate(enforcer, username="bob") == (
        RESTRICTION_NOT_MET.format("Celestial Enforcer")
    )


def test_a_creature_with_flying_on_a_second_printing():
    """Goblin Bird-Grabber: "{R}: This creature gains flying until end of turn.
    Activate only if you control a creature with flying." - once it flies
    itself, it satisfies its own restriction."""
    scenario = _board(["Goblin Bird-Grabber", "Mountain", "Mountain"])
    grabber = scenario.creature("Goblin Bird-Grabber")
    assert scenario.why_cannot_activate(grabber) == RESTRICTION_NOT_MET.format(
        "Goblin Bird-Grabber"
    )
    scenario = _board(["Goblin Bird-Grabber", "Wind Drake", "Mountain", "Mountain"])
    grabber = scenario.creature("Goblin Bird-Grabber")
    assert scenario.why_cannot_activate(grabber) is None
    scenario.activate(grabber, *scenario.untapped_sources("Mountain"))
    scenario.pass_until_resolved()
    scenario.game.sacrifice(scenario.creature("Wind Drake"))
    assert scenario.why_cannot_activate(grabber) is None


# -- "Activate only if you control no creatures" -----------------------------


def test_no_creatures_is_a_zero_count():
    """Haunted Plate Mail: "{0}: ... becomes a 4/4 Spirit artifact creature
    ... Activate only if you control no creatures." """
    scenario = _board(["Haunted Plate Mail", "Grizzly Bears"])
    mail = scenario.creature("Haunted Plate Mail")
    assert scenario.why_cannot_activate(mail, index=0) == RESTRICTION_NOT_MET.format(
        "Haunted Plate Mail"
    )
    # An opponent's creature is not one alice controls.
    scenario = _board(["Haunted Plate Mail"], ["Grizzly Bears"])
    mail = scenario.creature("Haunted Plate Mail")
    assert scenario.why_cannot_activate(mail, index=0) is None


# -- "if you control a tapped creature" / "two or more tapped creatures" -----


def _tap(scenario, *names: str) -> None:
    for name in names:
        scenario.game.tap_permanent(scenario.creature(name))


def _caravan_board():
    return _board(
        ["Grizzly Bears", "Mountain", *["Plains"] * 5],
        hand=["Supply Caravan", "Lightning Bolt"],
    )


def _cast_caravan(scenario) -> None:
    scenario.cast_onto_stack("Supply Caravan", *scenario.untapped_sources(*["Plains"] * 5))
    scenario.resolve_top()


def _warriors(scenario) -> list:
    return [s for s in scenario.game.permanents_controlled_by("alice") if "Warrior" in s.name]


def test_false_when_the_creature_enters_never_triggers():
    """CR 603.4: Supply Caravan - "When this creature enters, if you control a
    tapped creature, create a 1/1 white Warrior creature token with
    vigilance." Nothing is tapped."""
    scenario = _caravan_board()
    _cast_caravan(scenario)
    assert scenario.stack_names() == []
    assert scenario.game.intervening_if_notices == []


def test_true_then_false_by_resolution_does_nothing():
    """CR 608.2a: the tapped Grizzly Bears is killed with the trigger on the
    stack."""
    scenario = _caravan_board()
    _tap(scenario, "Grizzly Bears")
    _cast_caravan(scenario)
    assert scenario.stack_names() == ["Supply Caravan's triggered ability"]
    scenario.cast_and_resolve(
        "Lightning Bolt",
        *scenario.untapped_sources("Mountain"),
        targets=[scenario.creature("Grizzly Bears")],
    )
    scenario.pass_until_resolved()
    assert scenario.game.stack_is_empty
    assert _warriors(scenario) == []


def test_true_at_both_times_resolves():
    scenario = _caravan_board()
    _tap(scenario, "Grizzly Bears")
    _cast_caravan(scenario)
    scenario.pass_until_resolved()
    assert len(_warriors(scenario)) == 1


def test_tapped_creatures_on_a_second_printing():
    """Sunstar Chaplain prints the same clause."""
    scenario = _board(["Sunstar Chaplain", "Grizzly Bears", "Llanowar Elves"])
    assert _holds(scenario, "Sunstar Chaplain") is False
    _tap(scenario, "Grizzly Bears", "Llanowar Elves")
    assert _holds(scenario, "Sunstar Chaplain") is True


def test_a_tapped_creature_and_a_tapped_land_are_not_two_tapped_creatures():
    scenario = _board(["Sunstar Chaplain", "Grizzly Bears", "Forest"])
    _tap(scenario, "Grizzly Bears", "Forest")
    assert _holds(scenario, "Sunstar Chaplain") is False


def test_a_tapped_creature():
    """Supply Caravan: "if you control a tapped creature"."""
    scenario = _board(["Supply Caravan", "Grizzly Bears"])
    assert _holds(scenario, "Supply Caravan") is False
    _tap(scenario, "Grizzly Bears")
    assert _holds(scenario, "Supply Caravan") is True


# -- counters on a creature --------------------------------------------------


def test_another_creature_with_a_plus_one_counter():
    """Zegana, Utopian Speaker: "if you control another creature with a +1/+1
    counter on it" - Zegana's own counter is not another creature's."""
    scenario = _board(["Zegana, Utopian Speaker", "Grizzly Bears"])
    zegana = scenario.creature("Zegana, Utopian Speaker")
    scenario.game.add_counters(zegana, "+1/+1", 1)
    assert _holds(scenario, "Zegana, Utopian Speaker") is False
    scenario.game.add_counters(scenario.creature("Grizzly Bears"), "+1/+1", 1)
    assert _holds(scenario, "Zegana, Utopian Speaker") is True


def test_a_creature_with_a_plus_one_counter_counts_the_source():
    """Foundry Hornet: "if you control a creature with a +1/+1 counter on it"
    - no "another", so its own counter would do; a -1/-1 counter would not."""
    scenario = _board(["Foundry Hornet", "Grizzly Bears"])
    assert _holds(scenario, "Foundry Hornet") is False
    scenario.game.add_counters(scenario.creature("Grizzly Bears"), "-1/-1", 1)
    assert _holds(scenario, "Foundry Hornet") is False
    scenario.game.add_counters(scenario.creature("Foundry Hornet"), "+1/+1", 1)
    assert _holds(scenario, "Foundry Hornet") is True


def test_a_creature_with_a_counter_of_any_kind():
    """Delta Bloodflies: "if you control a creature with a counter on it" -
    any kind of counter."""
    scenario = _board(["Delta Bloodflies", "Grizzly Bears"])
    assert _holds(scenario, "Delta Bloodflies") is False
    scenario.game.add_counters(scenario.creature("Grizzly Bears"), "-1/-1", 1)
    assert _holds(scenario, "Delta Bloodflies") is True


# -- "three or more creatures with different powers" (coven) -----------------


def test_different_powers_counts_distinct_values():
    """Dawnhart Wardens (3 power), Grizzly Bears (2) and Llanowar Elves (1)
    are three different powers; a second Grizzly Bears adds none."""
    scenario = _board(["Dawnhart Wardens", "Grizzly Bears", "Grizzly Bears"])
    assert _holds(scenario, "Dawnhart Wardens") is False
    scenario = _board(["Dawnhart Wardens", "Grizzly Bears", "Llanowar Elves"])
    assert _holds(scenario, "Dawnhart Wardens") is True


def test_different_powers_read_the_computed_board():
    """CR 613.5: Candlelit Cavalry (5), Grizzly Bears (2) and Llanowar Elves
    (1) differ until a +1/+1 counter makes the Elves a second 2."""
    scenario = _board(["Candlelit Cavalry", "Grizzly Bears", "Llanowar Elves"])
    assert _holds(scenario, "Candlelit Cavalry") is True
    scenario.game.add_counters(scenario.creature("Llanowar Elves"), "+1/+1", 1)
    assert _holds(scenario, "Candlelit Cavalry") is False


def test_coven_trigger_at_beginning_of_combat():
    """Dawnhart Wardens' coven resolves: creatures alice controls get +1/+0."""
    scenario = _board(["Dawnhart Wardens", "Grizzly Bears", "Llanowar Elves"])
    _step(scenario, Step.BEGINNING_OF_COMBAT)
    assert scenario.stack_names() == ["Dawnhart Wardens's triggered ability"]
    scenario.pass_until_resolved()
    assert scenario.game.power_of(scenario.creature("Grizzly Bears")) == 3


# -- "no" / "don't control" --------------------------------------------------


def test_no_other_creatures_excludes_the_source():
    scenario = _board(["Lone Revenant"])
    assert _holds(scenario, "Lone Revenant") is True
    scenario = _board(["Lone Revenant", "Grizzly Bears"])
    assert _holds(scenario, "Lone Revenant") is False


def test_no_subtype_reads_plural_subtypes():
    """Ophiomancer: "At the beginning of each upkeep, if you control no Snakes,
    create a 1/1 black Snake creature token with deathtouch." - the token it
    made stops the next one."""
    scenario = _board(["Ophiomancer"], step=Step.UNTAP)
    _step(scenario, Step.UPKEEP)
    scenario.pass_until_resolved()
    snakes = [s for s in scenario.game.permanents_controlled_by("alice") if "Snake" in s.name]
    assert len(snakes) == 1
    assert _holds(scenario, "Ophiomancer") is False


def test_no_subtype_on_a_second_printing():
    """Stenchskipper: "if you control no Goblins, sacrifice this creature"."""
    scenario = _board(["Stenchskipper"])
    assert _holds(scenario, "Stenchskipper") is True
    scenario = _board(["Stenchskipper", "Goblin Bird-Grabber"])
    assert _holds(scenario, "Stenchskipper") is False


def test_no_tapped_lands():
    """Martyr's Soul: "if you control no tapped lands"."""
    scenario = _board(["Martyr's Soul", "Plains"])
    assert _holds(scenario, "Martyr's Soul") is True
    _tap(scenario, "Plains")
    assert _holds(scenario, "Martyr's Soul") is False


def test_no_artifacts():
    """Glimmervoid: "if you control no artifacts, sacrifice this land"."""
    scenario = _board(["Glimmervoid"])
    assert _holds(scenario, "Glimmervoid") is True
    scenario = _board(["Glimmervoid", "Ornithopter"])
    assert _holds(scenario, "Glimmervoid") is False


def test_no_other_colorless_creatures():
    """Dust Stalker (devoid, so colorless itself): "if you control no other
    colorless creatures"."""
    scenario = _board(["Dust Stalker", "Grizzly Bears"])
    assert _holds(scenario, "Dust Stalker") is True
    scenario = _board(["Dust Stalker", "Ornithopter"])
    assert _holds(scenario, "Dust Stalker") is False


def test_dont_control_a_named_creature():
    """Rufus Shinra: "if you don't control a creature named Darkstar" - a
    creature of another name does not count, one named Darkstar does."""
    scenario = _board(["Rufus Shinra", "Grizzly Bears"])
    assert _holds(scenario, "Rufus Shinra") is True


def test_dont_control_a_food():
    """Butterbur, Bree Innkeeper: "if you don't control a Food, create a Food
    token" - its own Food stops the second."""
    scenario = _board(["Butterbur, Bree Innkeeper"])
    _step(scenario, Step.END_STEP)
    scenario.pass_until_resolved()
    foods = [s for s in scenario.game.permanents_controlled_by("alice") if "Food" in s.name]
    assert len(foods) == 1
    assert _holds(scenario, "Butterbur, Bree Innkeeper") is False


def test_while_you_dont_control_another_dinosaur():
    """Pugnacious Hammerskull: "Whenever this creature attacks while you don't
    control another Dinosaur" - itself is not another."""
    scenario = _board(["Pugnacious Hammerskull"])
    assert _holds(scenario, "Pugnacious Hammerskull") is True
    scenario = _board(["Pugnacious Hammerskull", "Colossal Dreadmaw"])
    assert _holds(scenario, "Pugnacious Hammerskull") is False


def test_while_you_control_a_token():
    """Seasoned Warrenguard: "attacks while you control a token"."""
    scenario = _board(["Seasoned Warrenguard", "Grizzly Bears"])
    assert _holds(scenario, "Seasoned Warrenguard") is False
    scenario = _board(["Butterbur, Bree Innkeeper", "Seasoned Warrenguard"])
    _step(scenario, Step.END_STEP)
    scenario.pass_until_resolved()
    assert _holds(scenario, "Seasoned Warrenguard") is True


def test_dont_control_a_devil_token():
    """Maestros Diabolist's "if you don't control a Devil token", read
    through the shared reader: Footlight Fiend is a Devil but not a token."""
    scenario = _board(["Footlight Fiend"])
    clause = "you don't control a devil token"
    assert scenario.game.condition_holds("alice", clause) is True
    assert scenario.game.condition_holds("alice", "you don't control a devil") is False


# -- "exactly one" -----------------------------------------------------------


def test_exactly_one_creature():
    """Demonic Rising: "if you control exactly one creature"."""
    scenario = _board(["Demonic Rising"])
    assert _holds(scenario, "Demonic Rising") is False
    scenario = _board(["Demonic Rising", "Grizzly Bears"])
    assert _holds(scenario, "Demonic Rising") is True
    scenario = _board(["Demonic Rising", "Grizzly Bears", "Llanowar Elves"])
    assert _holds(scenario, "Demonic Rising") is False


# -- groups: shared type, names, toughness over power ------------------------


def test_three_creatures_sharing_a_creature_type():
    """Littjara Kinseekers is a changeling - every creature type (CR 702.73a) -
    so it shares one with any two creatures that share one with each other."""
    scenario = _board(["Littjara Kinseekers", "Grizzly Bears", "Llanowar Elves"])
    assert _holds(scenario, "Littjara Kinseekers") is False
    scenario = _board(["Littjara Kinseekers", "Llanowar Elves", "Elvish Mystic"])
    assert _holds(scenario, "Littjara Kinseekers") is True


def test_creatures_named_the_same():
    """Biovisionary's "four or more creatures named Biovisionary" read on
    Grizzly Bears, and Faerie Miscreant's "another creature named Faerie
    Miscreant" on its own printing."""
    clause = "you control four or more creatures named grizzly bears"
    scenario = _board(["Grizzly Bears"] * 3)
    assert scenario.game.condition_holds("alice", clause) is False
    scenario = _board(["Grizzly Bears"] * 4)
    assert scenario.game.condition_holds("alice", clause) is True
    scenario = _board(["Faerie Miscreant"])
    assert _holds(scenario, "Faerie Miscreant") is False
    scenario = _board(["Faerie Miscreant", "Faerie Miscreant"])
    assert _holds(scenario, "Faerie Miscreant") is True


def test_toughness_greater_than_power():
    """Catapult Fodder: "three or more creatures that each have toughness
    greater than their power" - Wall of Omens 0/4 and Catapult Fodder 1/5
    are two; a Grizzly Bears 2/2 is not a third."""
    scenario = _board(["Catapult Fodder", "Wall of Omens", "Grizzly Bears"])
    assert _holds(scenario, "Catapult Fodder") is False
    scenario = _board(["Catapult Fodder", "Wall of Omens", "Celestial Enforcer"])
    assert _holds(scenario, "Catapult Fodder") is True


def test_permanents_you_dont_own():
    """Agent of Treachery: "if you control three or more permanents you don't
    own" (CR 108.3) - its own ETB takes one."""
    scenario = _board(["Agent of Treachery"], ["Grizzly Bears", "Plains", "Forest"])
    assert _holds(scenario, "Agent of Treachery") is False


# -- superlatives -----------------------------------------------------------


def test_the_greatest_power_among_creatures_on_the_battlefield_includes_a_tie():
    """Éomer of the Riddermark (5 power): "if you control a creature with the
    greatest power among creatures on the battlefield" - bob's Craw Wurm (6)
    beats it; a 5-power creature of bob's only ties it."""
    scenario = _board(["Éomer of the Riddermark"], ["Craw Wurm"])
    assert _holds(scenario, "Éomer of the Riddermark") is False
    scenario = _board(["Éomer of the Riddermark"], ["Serra Angel", "Grizzly Bears"])
    assert _holds(scenario, "Éomer of the Riddermark") is True


def test_the_artifact_with_the_greatest_mana_value_or_tied():
    """Padeem, Consul of Innovation: "if you control the artifact with the
    greatest mana value or tied for the greatest mana value"."""
    scenario = _board(["Padeem, Consul of Innovation", "Ornithopter"], ["Mind Stone"])
    assert _holds(scenario, "Padeem, Consul of Innovation") is False
    scenario = _board(["Padeem, Consul of Innovation", "Mind Stone"], ["Mind Stone"])
    assert _holds(scenario, "Padeem, Consul of Innovation") is True
    scenario = _board(["Padeem, Consul of Innovation"])
    assert _holds(scenario, "Padeem, Consul of Innovation") is False


def test_power_greater_than_base_power():
    """Baird, Argivian Recruiter: CR 208.4b - a +1/+1 counter raises power, not
    base power."""
    scenario = _board(["Baird, Argivian Recruiter", "Grizzly Bears"])
    assert _holds(scenario, "Baird, Argivian Recruiter") is False
    scenario.game.add_counters(scenario.creature("Grizzly Bears"), "+1/+1", 1)
    assert _holds(scenario, "Baird, Argivian Recruiter") is True


def test_another_creature_with_power_four_or_greater():
    """Nessian Hornbeetle and Turret Ogre (itself 4 power) - "another"."""
    scenario = _board(["Turret Ogre", "Grizzly Bears"])
    assert _holds(scenario, "Turret Ogre") is False
    scenario = _board(["Nessian Hornbeetle", "Serra Angel"])
    assert _holds(scenario, "Nessian Hornbeetle") is True


def test_other_creatures_that_spell_could_target():
    """Beamsplitter Mage: "Whenever you cast an instant or sorcery spell that
    targets only this creature, if you control one or more other creatures
    that spell could target, ..." - Giant Growth could target Grizzly Bears;
    an opponent's creature is not one alice controls, and a Mind Stone is not
    a creature Giant Growth could target."""
    scenario = _board(
        ["Beamsplitter Mage", "Mind Stone", "Forest"], ["Grizzly Bears"], hand=["Giant Growth"]
    )
    mage = scenario.creature("Beamsplitter Mage")
    spell = scenario.cast_onto_stack(
        "Giant Growth", *scenario.untapped_sources("Forest"), targets=[mage]
    )
    event = GameEvent(event=TriggerEvent.CAST_SPELL, subject_id=spell.id, player="alice")
    assert _holds(scenario, "Beamsplitter Mage", event=event) is False
    scenario = _board(["Beamsplitter Mage", "Llanowar Elves", "Forest"], hand=["Giant Growth"])
    mage = scenario.creature("Beamsplitter Mage")
    spell = scenario.cast_onto_stack(
        "Giant Growth", *scenario.untapped_sources("Forest"), targets=[mage]
    )
    event = GameEvent(event=TriggerEvent.CAST_SPELL, subject_id=spell.id, player="alice")
    assert _holds(scenario, "Beamsplitter Mage", event=event) is True


# -- state adjectives ---------------------------------------------------------


def test_an_attacking_modified_creature():
    """Goro-Goro: "Activate only if you control an attacking modified
    creature." (CR 700.9)."""
    scenario = _board(["Goro-Goro, Disciple of Ryusei", "Grizzly Bears"] + ["Mountain"] * 5)
    goro = scenario.creature("Goro-Goro, Disciple of Ryusei")
    assert scenario.why_cannot_activate(goro, index=1) == RESTRICTION_NOT_MET.format(
        "Goro-Goro, Disciple of Ryusei"
    )
    bears = scenario.creature("Grizzly Bears")
    bears.summoning_sick = False
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(bears)
    assert scenario.why_cannot_activate(goro, index=1) is not None  # attacking, unmodified
    scenario.game.add_counters(bears, "+1/+1", 1)
    assert scenario.why_cannot_activate(goro, index=1) is None


def test_an_enchanted_creature():
    """Lord Skitter's Blessing: "if you control an enchanted creature"."""
    scenario = _board(["Lord Skitter's Blessing", "Grizzly Bears"])
    assert _holds(scenario, "Lord Skitter's Blessing") is False


def test_creatures_with_decayed():
    """Jadar: "if you control no creatures with decayed" - Rot-Curse Rakshasa
    has decayed printed (CR 702.147a)."""
    scenario = _board(["Jadar, Ghoulcaller of Nephalia", "Grizzly Bears"])
    assert _holds(scenario, "Jadar, Ghoulcaller of Nephalia") is True
    scenario = _board(["Jadar, Ghoulcaller of Nephalia", "Rot-Curse Rakshasa"])
    assert _holds(scenario, "Jadar, Ghoulcaller of Nephalia") is False


def test_another_outlaw():
    """Mine Raider (a Rogue): "if you control another outlaw" (CR 700.12)."""
    scenario = _board(["Mine Raider", "Grizzly Bears"])
    assert _holds(scenario, "Mine Raider") is False
    scenario = _board(["Mine Raider", "Faerie Miscreant"])  # a Faerie Rogue
    assert _holds(scenario, "Mine Raider") is True


def test_an_artifact_or_enchantment():
    """Moonlit Scavengers: "if you control an artifact or enchantment"."""
    scenario = _board(["Moonlit Scavengers"])
    assert _holds(scenario, "Moonlit Scavengers") is False
    scenario = _board(["Moonlit Scavengers", "Demonic Rising"])
    assert _holds(scenario, "Moonlit Scavengers") is True


def test_a_blue_or_red_permanent():
    """Wandering Champion: "if you control a blue or red permanent"."""
    scenario = _board(["Wandering Champion", "Grizzly Bears"])
    assert _holds(scenario, "Wandering Champion") is False
    scenario = _board(["Wandering Champion", "Goblin Bird-Grabber"])
    assert _holds(scenario, "Wandering Champion") is True


def test_another_wolf_or_werewolf():
    """Packsong Pup's "if you control another Wolf or Werewolf", read with
    Apex Witchstalker (a Wolf) as the source: itself is not another."""
    scenario = _board(["Apex Witchstalker", "Grizzly Bears"])
    source = scenario.creature("Apex Witchstalker")
    clause = "you control another wolf or werewolf"
    assert scenario.game.condition_holds("alice", clause, source) is False
    scenario = _board(["Apex Witchstalker", "Duskwatch Hunter"])
    source = scenario.creature("Apex Witchstalker")
    assert scenario.game.condition_holds("alice", clause, source) is True


def test_multicolored_permanents():
    """Scuttling Butler: "if you control two or more multicolored permanents"."""
    scenario = _board(["Scuttling Butler", "Dawnhart Wardens"])
    assert _holds(scenario, "Scuttling Butler") is False
    scenario = _board(["Scuttling Butler", "Dawnhart Wardens", "Zegana, Utopian Speaker"])
    assert _holds(scenario, "Scuttling Butler") is True


def test_every_reader_here_claims_its_clause():
    """The shared registry claims each template's words - the probe the
    support classifier asks."""
    for text in (
        "you control a plains or a swamp",
        "you control three or more creatures with different powers",
        "you control two or more tapped creatures",
        "you control another creature with a +1/+1 counter on it",
        "you control no creatures",
        "you don't control a creature named keimi",
        "you control exactly one creature",
        "you control three or more creatures that share a creature type",
        "you control seven or more lands with different names",
        "you control three or more permanents you don't own",
        "you control an attacking modified creature",
        "you control three or more wolves and/or werewolves",
        "you control five or more blood tokens",
    ):
        assert conditions.claims(text), text
