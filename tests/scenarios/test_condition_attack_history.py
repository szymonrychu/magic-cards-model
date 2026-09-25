"""Turn-history conditions about attacking and crewing (EC4 cluster H1): an
intervening "if" (CR 603.4) that asks who attacked this turn or this combat,
how many creatures attacked alongside, which creature types attacked, and
which creature crewed a Vehicle.

Rules verified with `mise run rules:find` in the session that wrote this file:

- **CR 603.4** - "When the trigger event occurs, the ability checks whether
  the stated condition is true. The ability triggers only if it is; otherwise
  it does nothing."
- **CR 508.1** / **CR 508.1a** - declaring attackers is how a creature
  attacks; the whole declaration is made at once, so "X attacked this combat"
  is true for every creature in it by the time any attack trigger is checked.
- **CR 500.8** - effects can add phases, so a turn can have more than one combat phase, which is why
  "this combat" is not "this turn".
- **CR 702.122a** / **CR 702.122b** - "A creature 'crews a Vehicle' when it's
  tapped to pay the cost to activate a Vehicle's crew ability."
- **CR 511.2** - "Abilities that trigger 'at end of combat' trigger as the end
  of combat step begins."
- **CR 608.2a** / **CR 400.7** - an intervening "if" is rechecked on
  resolution. What attacked this turn or this combat never un-happens, and no
  attack can be declared while a trigger waits on the stack (CR 500.2, CR
  508.1), so no H1 clause - negated or not - turns false by resolution on its
  own; the one way the ability is left with nothing is its source becoming a
  new object in response (Riders of the Mark flickered: it does nothing).

Every clause here failed closed (`InterveningIfNotice`, never triggering)
before `machines/conditions/history.py` read it.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.keywords import crew_activation
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _to_end_step(scenario) -> None:
    """From wherever the turn is, into the end step with its triggers stacked."""
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.pass_until_resolved()
    if scenario.step is not Step.POSTCOMBAT_MAIN:
        scenario.turn.advance_to(Step.POSTCOMBAT_MAIN)
        scenario.game.sync_priority_with_step()
    scenario.advance()  # the end step begins (CR 513.1)
    scenario.game.put_triggers_on_stack()


def _triggered(scenario, name: str) -> bool:
    return f"{name}'s triggered ability" in scenario.stack_names()


def _printed_triggers(printing):
    """Every triggered ability the printing's text parses to."""
    from magic_cards_model.machines.abilities import TriggeredAbility, parse_abilities
    from magic_cards_model.machines.triggers import triggered_abilities_of

    found = [each for each in parse_abilities(printing) if isinstance(each, TriggeredAbility)]
    return found + [each for each in triggered_abilities_of(printing) if each not in found]


def _clause_holds(scenario, source, event=None) -> bool | None:
    """The source's own intervening "if", read now against the real board
    (`machines/triggers.intervening_if_answer`) - for a trigger whose event
    `machines/triggers.py` does not raise yet, so the reader is proven on the
    printing's own parsed ability rather than through the trigger."""
    from magic_cards_model.machines.triggers import intervening_if_answer

    (ability,) = [each for each in _printed_triggers(source.card) if each.intervening_if][:1]
    return intervening_if_answer(scenario.game, ability, source, event, source.zone_change_stamp)


# -- "this creature attacked this turn" / "didn't attack this turn" ------------


def _riders_board():
    return (
        Scenario()
        .player("alice", battlefield=["Riders of the Mark"], library=["Plains"] * 3)
        .player("bob", library=["Plains"] * 3)
        .build()
    )


def test_a_creature_that_attacked_this_turn_triggers_at_the_end_step():
    """Riders of the Mark: "At the beginning of your end step, if this creature
    attacked this turn, return it to its owner's hand. ..." """
    scenario = _riders_board()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    riders = scenario.creature("Riders of the Mark", "alice")
    scenario.attack_with(riders)
    scenario.no_blocks()
    scenario.combat_damage()

    _to_end_step(scenario)

    assert _triggered(scenario, "Riders of the Mark")
    assert scenario.game.intervening_if_notices == []

    # True at both checks (CR 608.2a): it resolves - back to hand, and as
    # many 1/1 Human Soldiers as its toughness (CR 608.2h: the last known
    # toughness of the object that left).
    scenario.pass_until_resolved()
    assert scenario.find("Riders of the Mark", Zone.HAND, "alice") is not None
    soldiers = [state for state in scenario.game.battlefield if state.token]
    assert len(soldiers) == 4
    assert all({"Human", "Soldier"} <= set(state.subtypes) for state in soldiers)


def test_a_creature_that_left_and_came_back_is_not_returned():
    """Riders of the Mark attacked and triggered; in response it is exiled and
    returned - a new object (CR 400.7). The ability finds nothing to return,
    so "if you do" is false and no Soldier is made (CR 608.2a, CR 118.12)."""
    scenario = _riders_board()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(scenario.creature("Riders of the Mark", "alice"))
    scenario.no_blocks()
    scenario.combat_damage()
    _to_end_step(scenario)
    assert _triggered(scenario, "Riders of the Mark")

    riders = scenario.creature("Riders of the Mark", "alice")
    exiled = scenario.game.exile_permanent(riders)
    scenario.game.put_onto_battlefield(exiled, "alice")
    scenario.pass_until_resolved()

    assert "Riders of the Mark" in scenario.battlefield_names()
    assert not [state for state in scenario.game.battlefield if state.token]


def test_a_creature_that_did_not_attack_never_triggers():
    scenario = _riders_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    _to_end_step(scenario)

    assert not _triggered(scenario, "Riders of the Mark")
    assert scenario.game.intervening_if_notices == []


def test_another_creatures_attack_is_not_this_creatures():
    """ "this creature" is the source - a different creature
    attacking does not satisfy it."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Riders of the Mark", "Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(scenario.creature("Grizzly Bears", "alice"))
    scenario.no_blocks()
    scenario.combat_damage()

    _to_end_step(scenario)

    assert not _triggered(scenario, "Riders of the Mark")


def _brute_board():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Civilized Scholar // Homicidal Brute"])
        .player("bob")
        .build()
    )
    brute = scenario.find("Civilized Scholar", Zone.BATTLEFIELD, "alice")
    brute.transformed = True
    return scenario, brute


def test_the_negated_form_triggers_when_the_creature_did_not_attack():
    """Homicidal Brute: "At the beginning of your end step, if this creature
    didn't attack this turn, tap this creature, then transform it." - a second
    printing on the same reader, negated."""
    scenario, _brute = _brute_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    _to_end_step(scenario)

    assert _triggered(scenario, "Homicidal Brute")
    assert scenario.game.intervening_if_notices == []


def test_the_negated_form_does_not_trigger_after_the_creature_attacked():
    scenario, brute = _brute_board()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(brute)
    scenario.no_blocks()
    scenario.combat_damage()

    _to_end_step(scenario)

    assert not _triggered(scenario, "Homicidal Brute")
    assert scenario.game.intervening_if_notices == []


# -- "<name> attacked this combat" ----------------------------------------------


def _tolsimir_board():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Tolsimir, Midnight's Light", "Bounding Wolf"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.choose_trigger_targets(
        "Tolsimir, Midnight's Light", [scenario.creature("Grizzly Bears", "bob")]
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    return scenario


def test_a_named_source_that_attacked_this_combat_lets_the_wolf_trigger():
    """Tolsimir: "Whenever a Wolf you control attacks, if Tolsimir attacked this
    combat, ..." - the whole declaration is one (CR 508.1a), so Tolsimir's own
    attack counts however the two are ordered."""
    scenario = _tolsimir_board()
    wolf = scenario.creature("Bounding Wolf", "alice")
    tolsimir = scenario.creature("Tolsimir, Midnight's Light", "alice")

    scenario.attack_with(wolf, tolsimir)

    assert _triggered(scenario, "Tolsimir, Midnight's Light")
    assert scenario.game.intervening_if_notices == []


def test_a_wolf_attacking_without_the_named_source_does_not_trigger():
    scenario = _tolsimir_board()

    scenario.attack_with(scenario.creature("Bounding Wolf", "alice"))

    assert not _triggered(scenario, "Tolsimir, Midnight's Light")
    assert scenario.game.intervening_if_notices == []


# -- "you attacked with exactly N other creature(s) this combat" ----------------


def _puppeteer_attack(bears: int):
    scenario = (
        Scenario()
        .player("alice", battlefield=["Creepy Puppeteer"] + ["Grizzly Bears"] * bears)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    attackers = [scenario.creature("Creepy Puppeteer", "alice")] + [
        state for state in scenario.game.battlefield if state.name == "Grizzly Bears"
    ]
    scenario.attack_with(*attackers)
    return scenario


def test_exactly_one_other_attacker_triggers():
    """Creepy Puppeteer: "Whenever this creature attacks, if you attacked with
    exactly one other creature this combat, ..." """
    scenario = _puppeteer_attack(1)
    assert _triggered(scenario, "Creepy Puppeteer")
    assert scenario.game.intervening_if_notices == []


def test_two_other_attackers_is_not_exactly_one():
    scenario = _puppeteer_attack(2)
    assert not _triggered(scenario, "Creepy Puppeteer")
    assert scenario.game.intervening_if_notices == []


def test_attacking_alone_is_not_exactly_one_other():
    scenario = _puppeteer_attack(0)
    assert not _triggered(scenario, "Creepy Puppeteer")


# -- "you didn't attack with a creature this turn" ------------------------------


def _aura_board(aura: str):
    scenario = (
        Scenario()
        .player("alice", battlefield=["Grizzly Bears", aura], library=["Island"] * 4)
        .player("bob")
        .build()
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.find(aura, Zone.BATTLEFIELD, "alice").attach_to(bears)
    return scenario, bears


def test_see_red_is_sacrificed_after_a_turn_with_no_attack():
    """See Red: "At the beginning of your end step, if you didn't attack with a
    creature this turn, sacrifice this Aura." """
    scenario, _bears = _aura_board("See Red")
    scenario.start_at(Step.PRECOMBAT_MAIN)

    _to_end_step(scenario)

    assert _triggered(scenario, "See Red")
    assert scenario.game.intervening_if_notices == []

    scenario.pass_until_resolved()  # true at both checks (CR 608.2a): it resolves
    assert "See Red" not in scenario.battlefield_names()
    assert scenario.find("See Red", Zone.GRAVEYARD, "alice") is not None


def test_see_red_stays_after_an_attack():
    scenario, bears = _aura_board("See Red")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(bears)
    scenario.no_blocks()
    scenario.combat_damage()

    _to_end_step(scenario)

    assert not _triggered(scenario, "See Red")
    assert scenario.game.intervening_if_notices == []


def test_curious_obsession_reads_the_same_clause():
    """A second printing of the same clause: Curious Obsession."""
    scenario, bears = _aura_board("Curious Obsession")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _to_end_step(scenario)
    assert _triggered(scenario, "Curious Obsession")

    scenario, bears = _aura_board("Curious Obsession")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(bears)
    scenario.no_blocks()
    scenario.combat_damage()
    _to_end_step(scenario)
    assert not _triggered(scenario, "Curious Obsession")


# -- "a <quality> and a <quality> attacked this combat" -------------------------


def _swashbuckler_board():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Fearless Swashbuckler", "Adrestia", "Swab Goblin"],
            library=["Island"] * 6,
            hand=["Island", "Island"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _crew(scenario, vehicle_name: str, crew_name: str) -> None:
    vehicle = scenario.find(vehicle_name, Zone.BATTLEFIELD, "alice")
    crew = scenario.creature(crew_name, "alice")
    activation = crew_activation(scenario.game, vehicle, [crew], "alice")
    activation.begin_paying()
    activation.payment.pay()
    activation.activate()
    scenario.pass_until_resolved()


def test_a_pirate_and_a_vehicle_attacking_together_triggers():
    """Fearless Swashbuckler: "Whenever you attack, if a Pirate and a Vehicle
    attacked this combat, draw three cards, then discard two cards." """
    scenario = _swashbuckler_board()
    _crew(scenario, "Adrestia", "Swab Goblin")
    scenario.start_at(Step.DECLARE_ATTACKERS)

    scenario.attack_with(
        scenario.creature("Fearless Swashbuckler", "alice"),
        scenario.find("Adrestia", Zone.BATTLEFIELD, "alice"),
    )

    assert _triggered(scenario, "Fearless Swashbuckler")
    assert scenario.game.intervening_if_notices == []


def test_a_pirate_attacking_without_a_vehicle_does_not_trigger():
    scenario = _swashbuckler_board()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    scenario.attack_with(scenario.creature("Fearless Swashbuckler", "alice"))

    assert not _triggered(scenario, "Fearless Swashbuckler")
    assert scenario.game.intervening_if_notices == []


# -- "<name> and at least N other creatures attacked this combat" ---------------


def _kytheon_attack(bears: int):
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Kytheon, Hero of Akros // Gideon, Battle-Forged"]
            + ["Grizzly Bears"] * bears,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    kytheon = scenario.find("Kytheon, Hero of Akros", Zone.BATTLEFIELD, "alice")
    others = [state for state in scenario.game.battlefield if state.name == "Grizzly Bears"]
    scenario.attack_with(kytheon, *others)
    scenario.no_blocks()
    scenario.combat_damage()
    scenario.turn.advance_to(Step.COMBAT_DAMAGE)
    scenario.game.sync_priority_with_step()
    scenario.advance()  # the end of combat step begins (CR 511.1)
    scenario.game.put_triggers_on_stack()
    return scenario


def test_kytheon_and_two_others_attacking_this_combat():
    """Kytheon: "At end of combat, if Kytheon and at least two other creatures
    attacked this combat, exile Kytheon, then return him ... transformed." -
    CR 511.2: an "at end of combat" ability triggers as the end of combat
    step begins."""
    scenario = _kytheon_attack(2)
    kytheon = scenario.find("Kytheon, Hero of Akros", Zone.BATTLEFIELD, "alice")
    assert _clause_holds(scenario, kytheon) is True
    assert _triggered(scenario, "Kytheon, Hero of Akros")
    assert scenario.game.intervening_if_notices == []

    scenario.pass_until_resolved()

    gideon = scenario.find("Gideon, Battle-Forged", Zone.BATTLEFIELD, "alice")
    assert gideon.transformed


def test_kytheon_and_one_other_attacking_is_not_enough():
    scenario = _kytheon_attack(1)
    kytheon = scenario.find("Kytheon, Hero of Akros", Zone.BATTLEFIELD, "alice")
    assert _clause_holds(scenario, kytheon) is False
    assert not _triggered(scenario, "Kytheon, Hero of Akros")
    assert scenario.game.intervening_if_notices == []


def test_kytheon_not_attacking_is_not_enough():
    """The named source itself must be among the attackers."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Kytheon, Hero of Akros // Gideon, Battle-Forged"] + ["Grizzly Bears"] * 3,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(*[s for s in scenario.game.battlefield if s.name == "Grizzly Bears"])
    kytheon = scenario.find("Kytheon, Hero of Akros", Zone.BATTLEFIELD, "alice")
    assert _clause_holds(scenario, kytheon) is False


# -- "a <quality> crewed it this turn" ------------------------------------------


def _adrestia_board(crew: str):
    scenario = (
        Scenario()
        .player("alice", battlefield=["Adrestia", crew], library=["Island"] * 4)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _crew(scenario, "Adrestia", crew)
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(scenario.find("Adrestia", Zone.BATTLEFIELD, "alice"))
    return scenario


def test_a_vehicle_crewed_by_an_assassin_triggers_on_attack():
    """Adrestia: "Whenever Adrestia attacks, if an Assassin crewed it this turn,
    draw a card." - CR 702.122b's crewing creature is the one tapped to pay the
    crew cost."""
    scenario = _adrestia_board("Hired Poisoner")
    assert _triggered(scenario, "Adrestia")
    assert scenario.game.intervening_if_notices == []


def test_a_vehicle_crewed_by_a_non_assassin_does_not_trigger():
    scenario = _adrestia_board("Grizzly Bears")
    assert not _triggered(scenario, "Adrestia")
    assert scenario.game.intervening_if_notices == []
