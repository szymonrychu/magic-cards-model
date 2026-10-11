"""Untap-step statics: what untaps, for whom, and which steps happen at all.

CR 502.3: "Third, the active player determines which permanents they control
will untap. Then they untap them all simultaneously. ... Normally, all of a
player's permanents untap, but effects can keep one or more of a player's
permanents from untapping." CR 614.10: "Skip [something]" is "Instead of
doing [something], do nothing."

Every family below is read off the printed line by `machines/untap_statics.py`
and performed by `Game.untap_step_rule`/`Game._untap_step_impl` (and, for the
skipped upkeep, `Game._advance_past_checks`):

- **untap during each other player's untap step** - self (Thousand Moons
  Infantry, Bender's Waterskin), a group you control (Seedborn Muse's
  permanents, Prophet of Kruphix's creatures and lands, Unwinding Clock's
  artifacts, Ivorytusk Fortress's creatures with a +1/+1 counter, Dazzling
  Theater // Prop Room's creatures), and Quest for Renewal's "as long as";
- **group doesn't untap** - "<Quality> don't untap during their
  controllers' untap steps." (Choke's Islands, Marble Titan's power 3 or
  greater, Rimescale Dragon's ice counters, Freyalise's Radiance's snow
  permanents);
- **conditional doesn't untap** - Steel Dromedary's "if it has a +1/+1
  counter on it", Alirios's "if you control a Reflection", Winter's Rest's
  "As long as you control another snow permanent, enchanted creature ...",
  (the plain "Enchanted creature doesn't untap ..." is the existing layer
  reader's, `test_aura_animation_and_doesnt_untap.py`);
- **may choose not to untap** - a CR 502.3 choice of the active player
  (Deserter's Quarters, Giant Oyster);
- **can't untap more than one <quality>** - the active player chooses which
  one (Stoic Angel, Imi Statue, Winter Moon);
- **skip the upkeep step** - Eon Hub's "Players skip their upkeep steps."
  and Gibbering Descent's Hellbent "Skip your upkeep step if you have no
  cards in hand."
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from magic_cards_model.support import card_support
from tests.cards import card
from tests.scenarios.harness import Scenario


def build(alice: list[str], bob: list[str] | None = None, *, alice_hand=None):
    scenario = (
        Scenario()
        .player("alice", battlefield=alice, hand=alice_hand or [], library=["Island"] * 10)
        .player("bob", battlefield=bob or [], library=["Island"] * 10)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def tap(scenario, name: str, username: str = "alice"):
    state = scenario.find(name, Zone.BATTLEFIELD, username)
    state.tapped = True
    return state


def to_untap_step_of(scenario, username: str) -> None:
    """Advance turn by turn until `username`'s untap step has run - the
    real CR 502.3 turn-based action, not a direct call."""
    game = scenario.game
    start_turns = game.turn.turns_taken
    while not (game.turn.active_player == username and game.turn.turns_taken > start_turns):
        _advance(scenario)
    while game.turn.step is Step.UNTAP:
        _advance(scenario)


def _advance(scenario) -> None:
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.pass_until_resolved()
        scenario.game.put_triggers_on_stack()
    scenario.advance()


def tapped(states) -> list[bool]:
    return [state.tapped for state in states]


# -- untap during each other player's untap step ---------------------------


def test_seedborn_muse_untaps_everything_you_control_on_an_opponents_untap_step():
    scenario = build(["Seedborn Muse", "Forest", "Grizzly Bears", "Ornithopter"])
    states = [tap(scenario, n) for n in ("Forest", "Grizzly Bears", "Ornithopter", "Seedborn Muse")]

    to_untap_step_of(scenario, "bob")

    assert tapped(states) == [False, False, False, False]


def test_prophet_of_kruphix_untaps_creatures_and_lands_but_not_other_artifacts():
    scenario = build(["Prophet of Kruphix", "Forest", "Grizzly Bears", "Deserter's Quarters"])
    states = [tap(scenario, n) for n in ("Forest", "Grizzly Bears", "Prophet of Kruphix")]
    quarters = tap(scenario, "Deserter's Quarters")

    to_untap_step_of(scenario, "bob")

    assert tapped(states) == [False, False, False]
    assert quarters.tapped


def test_unwinding_clock_untaps_artifacts_you_control_and_nothing_else():
    scenario = build(["Unwinding Clock", "Ornithopter", "Forest"])
    clock, thopter, forest = (
        tap(scenario, n) for n in ("Unwinding Clock", "Ornithopter", "Forest")
    )

    to_untap_step_of(scenario, "bob")

    assert tapped([clock, thopter, forest]) == [False, False, True]


def test_ivorytusk_fortress_untaps_only_creatures_with_a_plus_one_counter():
    scenario = build(["Ivorytusk Fortress", "Grizzly Bears", "Ornithopter"])
    bears, thopter = tap(scenario, "Grizzly Bears"), tap(scenario, "Ornithopter")
    bears.add_counters(Counter.PLUS_ONE)

    to_untap_step_of(scenario, "bob")

    assert tapped([bears, thopter]) == [False, True]


def test_thousand_moons_infantry_untaps_itself_and_only_itself():
    scenario = build(["Thousand Moons Infantry", "Grizzly Bears"])
    infantry, bears = tap(scenario, "Thousand Moons Infantry"), tap(scenario, "Grizzly Bears")

    to_untap_step_of(scenario, "bob")

    assert tapped([infantry, bears]) == [False, True]


def test_benders_waterskin_untaps_itself_on_each_other_players_untap_step():
    scenario = build(["Bender's Waterskin"])
    skin = tap(scenario, "Bender's Waterskin")

    to_untap_step_of(scenario, "bob")

    assert not skin.tapped


def test_the_other_players_untap_grant_does_not_reach_an_opponents_permanents():
    """ "you control": bob's Seedborn Muse untaps nothing of alice's."""
    scenario = build(["Forest"], ["Seedborn Muse"])
    to_untap_step_of(scenario, "bob")
    forest = tap(scenario, "Forest")

    to_untap_step_of(scenario, "alice")
    forest.tapped = True
    to_untap_step_of(scenario, "bob")

    assert forest.tapped


def test_quest_for_renewal_needs_four_quest_counters():
    scenario = build(["Quest for Renewal", "Grizzly Bears"])
    quest = scenario.find("Quest for Renewal", Zone.BATTLEFIELD, "alice")
    quest.add_counters("quest", 3)
    bears = tap(scenario, "Grizzly Bears")

    to_untap_step_of(scenario, "bob")
    assert bears.tapped

    quest.add_counters("quest", 1)
    to_untap_step_of(scenario, "alice")
    bears.tapped = True
    to_untap_step_of(scenario, "bob")
    assert not bears.tapped


def test_prop_room_untaps_each_creature_you_control_once_its_door_is_unlocked():
    scenario = build(["Dazzling Theater", "Grizzly Bears"])
    room = scenario.find("Dazzling Theater // Prop Room", Zone.BATTLEFIELD, "alice")
    bears = tap(scenario, "Grizzly Bears")

    to_untap_step_of(scenario, "bob")
    assert bears.tapped  # neither door unlocked: Prop Room's ability is not there

    room.unlocked_doors = ("Prop Room",)
    bears.tapped = True
    to_untap_step_of(scenario, "alice")
    bears.tapped = True
    to_untap_step_of(scenario, "bob")
    assert not bears.tapped


# -- group doesn't untap ----------------------------------------------------


def test_choke_keeps_islands_tapped_and_nothing_else():
    scenario = build(["Island", "Forest"], ["Choke"])
    island, forest = tap(scenario, "Island"), tap(scenario, "Forest")

    to_untap_step_of(scenario, "alice")

    assert tapped([island, forest]) == [True, False]


def test_marble_titan_keeps_power_three_or_greater_tapped_itself_included():
    scenario = build(["Marble Titan", "Grizzly Bears"])
    titan, bears = tap(scenario, "Marble Titan"), tap(scenario, "Grizzly Bears")

    to_untap_step_of(scenario, "alice")

    assert tapped([titan, bears]) == [True, False]


def test_rimescale_dragon_keeps_creatures_with_ice_counters_tapped():
    scenario = build(["Grizzly Bears", "Ornithopter"], ["Rimescale Dragon"])
    bears, thopter = tap(scenario, "Grizzly Bears"), tap(scenario, "Ornithopter")
    bears.add_counters("ice")

    to_untap_step_of(scenario, "alice")

    assert tapped([bears, thopter]) == [True, False]


def test_freyalises_radiance_keeps_snow_permanents_tapped():
    scenario = build(["Snow-Covered Forest", "Forest", "Freyalise's Radiance"])
    snow, forest = tap(scenario, "Snow-Covered Forest"), tap(scenario, "Forest")

    to_untap_step_of(scenario, "alice")

    assert tapped([snow, forest]) == [True, False]


def test_a_group_restriction_is_only_for_its_controllers_untap_step():
    """ "their controllers' untap steps": Prophet of Kruphix untaps alice's
    Island on bob's untap step even under Choke."""
    scenario = build(["Prophet of Kruphix", "Island"], ["Choke"])
    island = tap(scenario, "Island")

    to_untap_step_of(scenario, "bob")

    assert not island.tapped


# -- conditional doesn't untap ----------------------------------------------


def test_steel_dromedary_stays_tapped_only_while_it_has_a_counter():
    scenario = build(["Steel Dromedary"])
    camel = tap(scenario, "Steel Dromedary")
    camel.add_counters(Counter.PLUS_ONE, 2)

    to_untap_step_of(scenario, "alice")
    assert camel.tapped

    camel.counters.remove(Counter.PLUS_ONE, 2)
    to_untap_step_of(scenario, "alice")
    assert not camel.tapped


def test_alirios_stays_tapped_while_you_control_a_reflection():
    scenario = build(["Island"] * 3, alice_hand=["Alirios, Enraptured"])
    alirios = scenario.cast_and_resolve(
        "Alirios, Enraptured", *scenario.untapped_sources(*["Island"] * 3)
    )
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()
    (reflection,) = [s for s in scenario.game.battlefield if "Reflection" in s.subtypes]
    alirios.tapped = True

    to_untap_step_of(scenario, "alice")
    assert alirios.tapped

    scenario.game.battlefield.remove(reflection)
    to_untap_step_of(scenario, "alice")
    assert not alirios.tapped


def test_winters_rest_needs_another_snow_permanent():
    scenario = build(["Grizzly Bears", "Snow-Covered Forest"], alice_hand=["Winter's Rest"])
    bears = scenario.creature("Grizzly Bears")
    rest = scenario.put_onto_battlefield("Winter's Rest")
    rest.attach_to(bears)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()
    bears.tapped = True

    to_untap_step_of(scenario, "alice")
    assert bears.tapped

    snow = scenario.find("Snow-Covered Forest", Zone.BATTLEFIELD, "alice")
    scenario.game.battlefield.remove(snow)
    to_untap_step_of(scenario, "alice")
    assert not bears.tapped


# -- may choose not to untap -------------------------------------------------


def test_deserters_quarters_untaps_unless_its_controller_chooses_not_to():
    scenario = build(["Deserter's Quarters"])
    quarters = tap(scenario, "Deserter's Quarters")

    to_untap_step_of(scenario, "alice")
    assert not quarters.tapped

    quarters.tapped = True
    scenario.will_take_the_may(True, username="alice", source="Deserter's Quarters")
    to_untap_step_of(scenario, "alice")
    assert quarters.tapped


def test_giant_oyster_choice_is_per_permanent():
    scenario = build(["Giant Oyster", "Grizzly Bears"])
    oyster, bears = tap(scenario, "Giant Oyster"), tap(scenario, "Grizzly Bears")

    scenario.will_take_the_may(True, username="alice", source="Giant Oyster")
    to_untap_step_of(scenario, "alice")

    assert tapped([oyster, bears]) == [True, False]


def test_an_untapped_permanent_is_never_asked_about():
    scenario = build(["Giant Oyster"])

    to_untap_step_of(scenario, "alice")

    assert not any("choose not to untap" in q.prompt for q in scenario.questions_asked())


# -- can't untap more than one ---------------------------------------------


def test_stoic_angel_lets_only_the_chosen_creature_untap():
    scenario = build(["Stoic Angel", "Grizzly Bears", "Ornithopter"])
    bears, thopter = tap(scenario, "Grizzly Bears"), tap(scenario, "Ornithopter")

    scenario.will_choose_cards(thopter, username="alice")
    to_untap_step_of(scenario, "alice")

    assert tapped([bears, thopter]) == [True, False]


def test_imi_statue_limits_artifacts_and_leaves_lands_alone():
    scenario = build(["Imi Statue", "Ornithopter", "Memnite", "Forest", "Island"])
    statue, thopter, memnite = (tap(scenario, n) for n in ("Imi Statue", "Ornithopter", "Memnite"))
    forest, island = tap(scenario, "Forest"), tap(scenario, "Island")

    to_untap_step_of(scenario, "alice")

    assert sum(not s.tapped for s in (statue, thopter, memnite)) == 1
    assert tapped([forest, island]) == [False, False]


def test_winter_moon_limits_nonbasic_lands_only():
    scenario = build(["Winter Moon", "Watery Grave", "Watery Grave", "Island"])
    graves = [s for s in scenario.game.battlefield if s.name == "Watery Grave"]
    for grave in graves:
        grave.tapped = True
    island = tap(scenario, "Island")

    to_untap_step_of(scenario, "alice")

    assert sorted(tapped(graves)) == [False, True]
    assert not island.tapped


def test_one_tapped_creature_under_stoic_angel_untaps_without_a_question():
    scenario = build(["Stoic Angel", "Grizzly Bears"])
    bears = tap(scenario, "Grizzly Bears")

    to_untap_step_of(scenario, "alice")

    assert not bears.tapped


# -- skip the upkeep step ---------------------------------------------------


def test_eon_hub_skips_every_players_upkeep():
    scenario = build(["Eon Hub"])
    game = scenario.game
    seen = []
    while not (game.turn.active_player == "bob" and game.turn.step is Step.DRAW):
        _advance(scenario)
        seen.append((game.turn.active_player, game.turn.step))

    assert ("bob", Step.UPKEEP) not in seen


def test_gibbering_descent_skips_its_controllers_upkeep_only_while_hellbent():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Gibbering Descent"], library=["Island"] * 10)
        .player(
            "bob",
            battlefield=["Gibbering Descent"],
            hand=["Island", "Island"],
            library=["Island"] * 10,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    game = scenario.game
    scenario.player("alice").hand.clear()
    to_untap_step_of(scenario, "bob")
    assert game.turn.step is Step.UPKEEP  # bob holds two cards: not hellbent

    seen = []
    while not (game.turn.active_player == "alice" and game.turn.step is Step.DRAW):
        _advance(scenario)
        seen.append((game.turn.active_player, game.turn.step))
    assert ("alice", Step.UPKEEP) not in seen  # hellbent: her upkeep never happens
    assert scenario.player("alice").life == 20  # so neither Descent's upkeep trigger fires
    assert scenario.player("bob").life == 18


# -- the audit credits what the step performs -------------------------------


def test_every_listed_untap_line_reads_handled():
    for name in (
        "Seedborn Muse",
        "Unwinding Clock",
        "Ivorytusk Fortress",
        "Thousand Moons Infantry",
        "Bender's Waterskin",
        "Quest for Renewal",
        "Choke",
        "Marble Titan",
        "Freyalise's Radiance",
        "Steel Dromedary",
        "Winter's Rest",
        "Stoic Angel",
        "Imi Statue",
        "Winter Moon",
        "Eon Hub",
        "Prophet of Kruphix",
    ):
        support = card_support(card(name))
        assert support.status == "handled", (
            name,
            [c for c in support.clauses if c.status != "handled"],
        )
