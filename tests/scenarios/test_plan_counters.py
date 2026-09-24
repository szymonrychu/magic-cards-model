"""Scenario: Plan enchantments - plan counters and the Nth-counter payoff.

Plan is an enchantment type (CR 205.3h). Every Plan in Marvel Super Heroes
(msh) prints the same two-part shape, oracle text read off the Scryfall
printings in `data/printings`:

- a counter-adding trigger ending "... and put a plan counter on this
  enchantment", on one of several trigger events;
- "When the Nth plan counter is put on this enchantment, sacrifice it." then
  one of three payoff joins: ". When you do, <effect>" (a CR 603.12 reflexive
  ability - Claim the Kingdom, Death to Our Enemies, Doom Reigns Supreme,
  Rewrite History, Construct a Cosmic Cube), ", <effect>, and <effect>"
  (Political Triumph) or " and <effect>" (Robot Domination).

The Nth-counter condition is CR 122.6's "counters being put on an object"
read as a threshold: it fires on the event that takes the count from below N
to N or more, once, however many counters that one event put on - the same
reading CR 714.2b gives a Saga chapter for lore counters.

Plan counters and the Nth-counter template are printed only on msh cards;
acceptance (k) is met by the seven listed Plans themselves, whose payoff
joins and counter-adding events all differ (see MEMORY.md, 2026-09-24).

The counter-adding triggers read here beyond the ones the engine already had:

- "Whenever one or more creatures you control become tapped" (Rewrite
  History) - CR 603.2c's one event for a batch of permanents tapped
  together; proven off-msh on Deeproot Pilgrimage's "one or more nontoken
  Merfolk you control become tapped".
- "Whenever one or more creature cards are put into your graveyard from
  anywhere" (Robot Domination) - proven off-msh on Crawling Infestation's
  "... from anywhere during your turn ... This ability triggers only once
  each turn."
- "put a +1/+1 counter on target creature you control and a plan counter on
  this enchantment" (Claim the Kingdom) - one "put" governing two objects.

Doctor Doom's "As long as you control an artifact creature or a Plan, Doctor
Doom has indestructible." is here too, since a Plan is half of its
condition; Flutterfox's "As long as you control an artifact or enchantment,
this creature has flying." is its off-msh proof.

Rules, each read with `mise run rules:find` in the session that wrote this
file: CR 122.6, CR 205.3h, CR 603.2c, CR 603.3d, CR 603.12, CR 701.21a,
CR 113.7a, CR 400.7, CR 608.2b, CR 601.2d, CR 611.3a, CR 702.12b.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter

from .harness import Scenario


def _resolve_everything(scenario) -> None:
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.pass_until_resolved()
        scenario.game.put_triggers_on_stack()


def _plan(scenario, name: str, username: str = "alice"):
    return scenario.find(name, Zone.BATTLEFIELD, username)


# -- the Nth plan counter: a threshold, not a count (CR 122.6) ---------------


def _triumph_board():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Political Triumph", "Grizzly Bears", "Plains"],
            hand=["Savannah Lions"],
            library=["Plains"] * 6,
        )
        .player("bob", battlefield=["Grizzly Bears"], library=["Island"] * 6)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_the_fourth_plan_counter_sacrifices_political_triumph_and_pays_out():
    """Three counters on, a creature enters: its own trigger scries and puts
    the fourth counter on, which is the event the payoff watches - sacrifice
    it, draw a card, and a +1/+1 counter on each creature alice controls."""
    scenario = _triumph_board()
    triumph = _plan(scenario, "Political Triumph")
    scenario.game.add_counters(triumph, "plan", 3)
    _resolve_everything(scenario)
    hand_before = len(scenario.player("alice").hand)

    lions = scenario.put_onto_battlefield("Savannah Lions", "alice")
    _resolve_everything(scenario)

    assert triumph.zone is Zone.GRAVEYARD
    assert len(scenario.player("alice").hand) == hand_before  # Lions left, one drawn
    assert scenario.creature("Grizzly Bears", "alice").counters[Counter.PLUS_ONE] == 1
    assert lions.counters[Counter.PLUS_ONE] == 1
    assert scenario.creature("Grizzly Bears", "bob").counters[Counter.PLUS_ONE] == 0


def test_the_third_plan_counter_is_not_the_fourth():
    scenario = _triumph_board()
    triumph = _plan(scenario, "Political Triumph")
    scenario.game.add_counters(triumph, "plan", 2)
    _resolve_everything(scenario)

    scenario.put_onto_battlefield("Savannah Lions", "alice")
    _resolve_everything(scenario)

    assert triumph.zone is Zone.BATTLEFIELD
    assert triumph.counters["plan"] == 3


def test_two_counters_that_cross_the_threshold_together_trigger_once():
    """3 -> 5 in one event: the count was below four and became at least four
    once, so the payoff triggers once (CR 603.2c), not for the fifth too."""
    scenario = _triumph_board()
    triumph = _plan(scenario, "Political Triumph")
    scenario.game.add_counters(triumph, "plan", 3)
    scenario.game.add_counters(triumph, "plan", 2)

    assert [trigger.source_name for trigger in scenario.pending_triggers] == ["Political Triumph"]


def test_a_counter_past_the_threshold_does_not_retrigger():
    scenario = _triumph_board()
    triumph = _plan(scenario, "Political Triumph")
    scenario.game.add_counters(triumph, "plan", 4)
    scenario.game.pending_triggers.clear()

    scenario.game.add_counters(triumph, "plan", 1)

    assert scenario.pending_triggers == []


def test_another_kind_of_counter_is_not_a_plan_counter():
    scenario = _triumph_board()
    triumph = _plan(scenario, "Political Triumph")
    scenario.game.add_counters(triumph, "plan", 3)
    scenario.game.add_counters(triumph, Counter.PLUS_ONE, 1)

    assert scenario.pending_triggers == []


def test_plan_counters_on_another_plan_do_not_count():
    scenario = (
        Scenario().player("alice", battlefield=["Political Triumph", "Robot Domination"]).build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    domination = _plan(scenario, "Robot Domination")
    scenario.game.add_counters(domination, "plan", 2)

    assert scenario.pending_triggers == []


def test_a_plan_gone_before_its_payoff_resolves_is_not_sacrificed_but_the_rest_happens():
    """CR 113.7a: the payoff exists independently of the Plan once it has
    triggered. "Sacrifice it, draw a card, and put ..." has no "if you do",
    so the draw and the counters still happen with nothing to sacrifice."""
    scenario = _triumph_board()
    triumph = _plan(scenario, "Political Triumph")
    hand_before = len(scenario.player("alice").hand)
    scenario.game.add_counters(triumph, "plan", 4)
    scenario.game.put_triggers_on_stack()
    scenario.game.destroy(triumph)

    scenario.pass_until_resolved()

    assert triumph.zone is Zone.GRAVEYARD
    assert len(scenario.player("alice").hand) == hand_before + 1
    assert scenario.creature("Grizzly Bears", "alice").counters[Counter.PLUS_ONE] == 1


def test_robot_domination_sacrifices_itself_and_creates_three_robot_villains():
    scenario = Scenario().player("alice", battlefield=["Robot Domination"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    domination = _plan(scenario, "Robot Domination")

    scenario.game.add_counters(domination, "plan", 3)
    _resolve_everything(scenario)

    assert domination.zone is Zone.GRAVEYARD
    robots = [p for p in scenario.game.battlefield if p.name != "Robot Domination"]
    assert len(robots) == 3
    board = scenario.game.computed_board()
    for robot in robots:
        chars = board.of(robot)
        assert (chars.power, chars.toughness) == (2, 2)
        assert {"Robot", "Villain"} <= set(chars.subtypes)
        assert chars.colors == set() or not chars.colors


# -- "sacrifice it. When you do, <effect>" (CR 603.12) -----------------------


def _claim_board():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Claim the Kingdom", "Grizzly Bears", "Forest"],
            hand=["Forest", "Forest"],
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_landfall_puts_a_counter_on_the_target_and_a_plan_counter_on_claim():
    """One "put" governing two objects: the +1/+1 counter on the target, the
    plan counter on this enchantment."""
    scenario = _claim_board()
    claim = _plan(scenario, "Claim the Kingdom")
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.choose_trigger_targets("Claim the Kingdom", [bears])

    scenario.play_land("Forest")
    _resolve_everything(scenario)

    assert bears.counters[Counter.PLUS_ONE] == 1
    assert claim.counters["plan"] == 1


def test_the_fourth_counter_sacrifices_claim_and_the_reflexive_ability_targets():
    """The payoff sacrifices Claim; only then (CR 603.12) is the reflexive
    ability created, and it chooses its own target as it goes on the stack
    (CR 603.3d): an indestructible counter on target creature alice controls."""
    scenario = _claim_board()
    claim = _plan(scenario, "Claim the Kingdom")
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.game.add_counters(claim, "plan", 3)
    scenario.choose_trigger_targets("Claim the Kingdom", [bears])

    scenario.play_land("Forest")
    _resolve_everything(scenario)

    assert claim.zone is Zone.GRAVEYARD
    assert bears.counters[Counter.PLUS_ONE] == 1
    assert bears.counters["indestructible"] == 1


def test_no_sacrifice_no_reflexive_ability():
    """CR 603.12: the reflexive ability triggers only if the action was taken.
    Claim destroyed in response to its own payoff can't be sacrificed, so
    nothing gets the indestructible counter."""
    scenario = _claim_board()
    claim = _plan(scenario, "Claim the Kingdom")
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.game.add_counters(claim, "plan", 4)
    scenario.game.put_triggers_on_stack()
    scenario.game.destroy(claim)

    _resolve_everything(scenario)

    assert bears.counters["indestructible"] == 0
    assert scenario.game.stack == []


def test_death_to_our_enemies_deals_seven_damage_through_its_reflexive_ability():
    """ "It deals 7 damage" - "it" is the sacrificed Plan, dealing damage by
    its last known information (CR 113.7a) to one target here."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Death to Our Enemies"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    plan = _plan(scenario, "Death to Our Enemies")
    bob = scenario.player("bob")

    # CR 603.3d: the reflexive ability asks for its own target as it goes on
    # the stack, after the payoff has sacrificed the Plan.
    scenario.will_choose_targets("bob")

    scenario.game.add_counters(plan, "plan", 4)
    _resolve_everything(scenario)

    assert plan.zone is Zone.GRAVEYARD
    assert bob.life == 13


def test_rewrite_history_returns_up_to_two_instants_and_sorceries():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Rewrite History"],
            graveyard=["Lightning Bolt", "Opt", "Grizzly Bears"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    plan = _plan(scenario, "Rewrite History")
    bolt = scenario.find("Lightning Bolt", Zone.GRAVEYARD, "alice")
    opt = scenario.find("Opt", Zone.GRAVEYARD, "alice")
    scenario.will_choose_targets(bolt, opt)

    scenario.game.add_counters(plan, "plan", 4)
    _resolve_everything(scenario)

    assert plan.zone is Zone.GRAVEYARD
    assert bolt.zone is Zone.HAND
    assert opt.zone is Zone.HAND
    assert scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice").zone is Zone.GRAVEYARD


# -- "one or more creatures you control become tapped" (CR 603.2c) -----------


def _rewrite_board():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Rewrite History", "Grizzly Bears", "Savannah Lions", "Forest"],
            library=["Forest"] * 6,
        )
        .player("bob", battlefield=["Grizzly Bears"], library=["Island"] * 6)
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    return scenario


def test_two_attackers_tapping_together_trigger_rewrite_history_once():
    """Declaring two attackers taps both in one event (CR 508.1f), and "one or
    more ... become tapped" triggers once for it, not once per creature."""
    scenario = _rewrite_board()
    plan = _plan(scenario, "Rewrite History")

    scenario.attack_with(
        scenario.creature("Grizzly Bears", "alice"), scenario.creature("Savannah Lions", "alice")
    )
    scenario.game.put_triggers_on_stack()

    assert [a.source_name for a in scenario.game.stack] == ["Rewrite History"]
    _resolve_everything(scenario)
    assert plan.counters["plan"] == 1


def test_a_creature_tapped_as_a_cost_is_its_own_batch():
    """Tapping for mana is a tapped creature too - Llanowar Elves' {T}."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Rewrite History", "Llanowar Elves"], library=["Forest"] * 4)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    elves = scenario.creature("Llanowar Elves", "alice")

    scenario.activate(elves)
    scenario.game.put_triggers_on_stack()

    assert [a.source_name for a in scenario.pending_triggers + scenario.game.stack] == [
        "Rewrite History"
    ]


def test_an_opponents_creature_becoming_tapped_is_not_yours():
    scenario = _rewrite_board()
    scenario.turn.advance_to(Step.END_STEP)
    bears = scenario.creature("Grizzly Bears", "bob")

    bears.tap()
    scenario.game.put_triggers_on_stack()

    assert scenario.game.stack == []


def test_a_land_becoming_tapped_is_not_a_creature():
    scenario = _rewrite_board()
    forest = scenario.find("Forest", Zone.BATTLEFIELD, "alice")

    forest.tap()
    scenario.game.put_triggers_on_stack()

    assert scenario.game.stack == []


def _pilgrimage_board():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Deeproot Pilgrimage", "Merfolk Looter", "Merfolk Observer"],
            library=["Island"] * 6,
        )
        .player("bob", library=["Island"] * 6)
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    return scenario


def test_off_msh_deeproot_pilgrimage_triggers_once_for_two_merfolk():
    """The same batch, a different description: "one or more nontoken Merfolk
    you control become tapped" - one Merfolk token with hexproof."""
    scenario = _pilgrimage_board()
    looter = scenario.creature("Merfolk Looter", "alice")
    observer = scenario.creature("Merfolk Observer", "alice")

    scenario.attack_with(looter, observer)
    _resolve_everything(scenario)

    tokens = [p for p in scenario.game.battlefield if getattr(p, "token", False)]
    assert len(tokens) == 1
    assert "Merfolk" in scenario.game.computed_board().of(tokens[0]).subtypes


def test_off_msh_deeproot_pilgrimage_ignores_a_merfolk_token():
    scenario = _pilgrimage_board()
    looter = scenario.creature("Merfolk Looter", "alice")
    looter.tap()
    _resolve_everything(scenario)
    (token,) = [p for p in scenario.game.battlefield if getattr(p, "token", False)]

    token.tap()
    scenario.game.put_triggers_on_stack()

    assert scenario.game.stack == []


# -- "one or more creature cards are put into your graveyard from anywhere" ---


def _domination_board(*library: str):
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Robot Domination", "Island"],
            hand=["Thought Scour"],
            library=list(library) + ["Island"] * 4,
        )
        .player("bob", battlefield=["Grizzly Bears"], library=["Grizzly Bears"] * 4)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_two_creature_cards_milled_together_trigger_robot_domination_once():
    """Thought Scour mills two: one event (CR 603.2c) - one draw, one life,
    one plan counter."""
    scenario = _domination_board("Grizzly Bears", "Savannah Lions")
    plan = _plan(scenario, "Robot Domination")
    alice = scenario.player("alice")
    (island,) = scenario.untapped_sources("Island")

    scenario.cast_and_resolve("Thought Scour", island, targets=["alice"])
    _resolve_everything(scenario)

    assert plan.counters["plan"] == 1
    assert alice.life == 19


def test_milling_no_creature_card_does_not_trigger():
    scenario = _domination_board("Island", "Island")
    plan = _plan(scenario, "Robot Domination")
    (island,) = scenario.untapped_sources("Island")

    scenario.cast_and_resolve("Thought Scour", island, targets=["alice"])
    _resolve_everything(scenario)

    assert plan.counters["plan"] == 0


def test_a_creature_card_into_an_opponents_graveyard_is_not_yours():
    scenario = _domination_board("Island", "Island")
    plan = _plan(scenario, "Robot Domination")
    (island,) = scenario.untapped_sources("Island")

    scenario.cast_and_resolve("Thought Scour", island, targets=["bob"])
    _resolve_everything(scenario)

    assert plan.counters["plan"] == 0


def test_a_creature_dying_is_a_creature_card_put_into_your_graveyard():
    scenario = Scenario().player("alice", battlefield=["Robot Domination", "Grizzly Bears"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    plan = _plan(scenario, "Robot Domination")

    scenario.game.destroy(scenario.creature("Grizzly Bears", "alice"))
    _resolve_everything(scenario)

    assert plan.counters["plan"] == 1


def _infestation_board():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Crawling Infestation", "Grizzly Bears", "Savannah Lions"],
            library=["Island"] * 6,
        )
        .player("bob", battlefield=["Grizzly Bears"], library=["Island"] * 6)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _insects(scenario) -> int:
    return sum(1 for p in scenario.game.battlefield if getattr(p, "token", False))


def test_off_msh_crawling_infestation_triggers_during_your_turn():
    scenario = _infestation_board()

    scenario.game.destroy(scenario.creature("Grizzly Bears", "alice"))
    _resolve_everything(scenario)

    assert _insects(scenario) == 1


def test_off_msh_crawling_infestation_triggers_only_once_each_turn():
    scenario = _infestation_board()

    scenario.game.destroy(scenario.creature("Grizzly Bears", "alice"))
    _resolve_everything(scenario)
    scenario.game.destroy(scenario.creature("Savannah Lions", "alice"))
    _resolve_everything(scenario)

    assert _insects(scenario) == 1


def test_off_msh_crawling_infestation_ignores_the_opponents_turn():
    scenario = _infestation_board()
    scenario.turn.advance_to(Step.CLEANUP)
    scenario.advance()
    scenario.advance()
    assert scenario.turn.active_player == "bob"

    scenario.game.destroy(scenario.creature("Grizzly Bears", "alice"))
    _resolve_everything(scenario)

    assert _insects(scenario) == 0


# -- Doom Reigns Supreme: "target opponent exiles the top five cards of their
# library. You may cast up to two spells from among the exiled cards without
# paying their mana costs." (CR 603.12, CR 608.2g, CR 118.9) -----------------


def _doom_board():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Doom Reigns Supreme"],
            hand=["Doctor Doom"],
            library=["Swamp"] * 4,
        )
        .player(
            "bob",
            library=["Grizzly Bears", "Savannah Lions", "Grizzly Bears", "Island", "Opt", "Island"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_a_villain_entering_drains_and_adds_the_fifth_counter():
    """ "Whenever a Villain you control enters, each opponent loses 1 life and
    you gain 1 life. Put a plan counter on this enchantment." - Doctor Doom is
    a Villain, and so are the two Doombots he makes."""
    scenario = _doom_board()
    plan = _plan(scenario, "Doom Reigns Supreme")
    scenario.will_take_the_may(False, times=None)

    scenario.put_onto_battlefield("Doctor Doom", "alice")
    _resolve_everything(scenario)

    assert scenario.player("bob").life == 17
    assert scenario.player("alice").life == 23
    assert plan.counters["plan"] == 3


def test_the_fifth_counter_exiles_five_and_casts_up_to_two_of_them_free():
    scenario = _doom_board()
    plan = _plan(scenario, "Doom Reigns Supreme")
    bob = scenario.player("bob")
    top_five = list(bob.library[:5])
    scenario.will_choose_targets("bob")
    scenario.will_take_the_may(True, times=2)
    scenario.will_choose_cards(top_five[0])
    scenario.will_choose_cards(top_five[1])

    scenario.game.add_counters(plan, "plan", 5)
    _resolve_everything(scenario)

    assert plan.zone is Zone.GRAVEYARD
    assert [card.zone for card in top_five[:2]] == [Zone.BATTLEFIELD, Zone.BATTLEFIELD]
    assert all(card.controller == "alice" for card in top_five[:2])
    assert [card.zone for card in top_five[2:]] == [Zone.EXILE] * 3
    assert len(bob.library) == 1


def test_up_to_two_means_a_third_is_never_offered():
    """Two cast: the third castable card (another Grizzly Bears) is not
    offered at all - no third "you may" is asked."""
    scenario = _doom_board()
    plan = _plan(scenario, "Doom Reigns Supreme")
    top_five = list(scenario.player("bob").library[:5])
    scenario.will_choose_targets("bob")
    scenario.will_take_the_may(True, times=None)
    scenario.will_choose_cards(top_five[0])
    scenario.will_choose_cards(top_five[2])

    scenario.game.add_counters(plan, "plan", 5)
    _resolve_everything(scenario)

    assert top_five[1].zone is Zone.EXILE
    cast_prompts = [q for q in scenario.questions_asked() if "without paying" in (q.prompt or "")]
    assert len([q for q in cast_prompts if q.kind.name == "MAY"]) == 2


def test_declining_casts_nothing_and_the_cards_stay_exiled():
    scenario = _doom_board()
    plan = _plan(scenario, "Doom Reigns Supreme")
    top_five = list(scenario.player("bob").library[:5])
    scenario.will_choose_targets("bob")
    scenario.will_take_the_may(False)

    scenario.game.add_counters(plan, "plan", 5)
    _resolve_everything(scenario)

    assert [card.zone for card in top_five] == [Zone.EXILE] * 5


def test_off_msh_korvold_exiles_the_top_three_of_target_opponents_library():
    """Korvold and the Noble Thief's chapter III - "Exile the top three cards
    of target opponent's library. You may play those cards this turn." - the
    same targeted-library exile (`_EXILE_TOP_OF_OTHER_LIBRARIES_RE`) that now
    also reads Doom Reigns Supreme's "target opponent exiles the top five
    cards of their library"."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Korvold and the Noble Thief"], library=["Swamp"] * 4)
        .player("bob", library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    saga = _plan(scenario, "Korvold and the Noble Thief")
    bob = scenario.player("bob")
    top_three = list(bob.library[:3])
    scenario.game.add_counters(saga, Counter.LORE, 2 - saga.counters[Counter.LORE])
    _resolve_everything(scenario)
    scenario.will_choose_targets("bob")

    scenario.game.add_counters(saga, Counter.LORE, 1)
    _resolve_everything(scenario)

    assert [card.zone for card in top_three] == [Zone.EXILE] * 3
    assert len(bob.library) == 2


# -- "As long as you control an artifact creature or a Plan, Doctor Doom has
# indestructible." (CR 611.3a, CR 702.12b) ----------------------------------


def _has(scenario, permanent, keyword: str) -> bool:
    return keyword in scenario.game.computed_board().of(permanent).abilities


def test_doctor_doom_is_not_indestructible_alone():
    scenario = Scenario().player("alice", battlefield=["Doctor Doom", "Sol Ring"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    assert not _has(scenario, scenario.creature("Doctor Doom", "alice"), "Indestructible")


def test_doctor_doom_is_indestructible_with_an_artifact_creature():
    scenario = Scenario().player("alice", battlefield=["Doctor Doom", "Memnite"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    doom = scenario.creature("Doctor Doom", "alice")

    assert _has(scenario, doom, "Indestructible")
    scenario.game.destroy(doom)
    assert doom.zone is Zone.BATTLEFIELD


def test_doctor_doom_is_indestructible_with_a_plan():
    scenario = Scenario().player("alice", battlefield=["Doctor Doom", "Robot Domination"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    assert _has(scenario, scenario.creature("Doctor Doom", "alice"), "Indestructible")


def test_doctor_doom_loses_it_when_the_plan_leaves():
    """CR 611.3a: the condition is re-read continuously, never locked in."""
    scenario = Scenario().player("alice", battlefield=["Doctor Doom", "Robot Domination"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.destroy(_plan(scenario, "Robot Domination"))

    assert not _has(scenario, scenario.creature("Doctor Doom", "alice"), "Indestructible")


def test_an_opponents_plan_does_not_count_for_doctor_doom():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Doctor Doom"])
        .player("bob", battlefield=["Robot Domination", "Memnite"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    assert not _has(scenario, scenario.creature("Doctor Doom", "alice"), "Indestructible")


def test_a_noncreature_artifact_is_not_an_artifact_creature():
    scenario = Scenario().player("alice", battlefield=["Doctor Doom", "Sol Ring"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    assert not _has(scenario, scenario.creature("Doctor Doom", "alice"), "Indestructible")


def test_off_msh_flutterfox_flies_with_an_artifact_or_an_enchantment():
    """Flutterfox: "As long as you control an artifact or enchantment, this
    creature has flying." - two bare card types for one "a"."""
    for other, flies in (("Sol Ring", True), ("Robot Domination", True), ("Forest", False)):
        scenario = Scenario().player("alice", battlefield=["Flutterfox", other]).build()
        scenario.start_at(Step.PRECOMBAT_MAIN)

        assert _has(scenario, scenario.creature("Flutterfox", "alice"), "Flying") is flies
