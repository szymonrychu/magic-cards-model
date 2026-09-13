"""Every "cast it without paying its mana cost" during resolution is one cast (CR 608.2g).

CR 608.2g: "If an effect specifically instructs or allows a player to cast a
spell during resolution, they do so by following the steps in rules 601.2a-i,
except no player receives priority after it's cast." Rebound (CR 702.88a,
702.88b), hideaway's play (CR 702.75a with its card's own "play the exiled
card"), Knowledge Pool, Isochron Scepter's copy (CR 707.12), Transcendent
Dragon's recast, suspend (CR 702.62a, 702.62d) and cascade all say it, so all
of them go through `Game.cast_during_resolution`: CR 611.1's prohibitions,
faces, modes (CR 700.2a), targets (CR 601.2c), X of 0 (CR 107.3b) and
additional costs (CR 601.2b, 601.2f) are asked the same way for each.

A land is played, never cast (CR 305.9): "play the exiled card" puts a land
onto the battlefield as a land play during resolution, which counts (CR
305.2a) and is refused when none is left (CR 305.2b) or it is not that
player's turn (CR 305.3).
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import DecisionKind
from magic_cards_model.machines.modes import modal_profile
from magic_cards_model.models import Zone
from tests.cards import card
from tests.scenarios.harness import Scenario
from tests.scenarios.test_scepter_chant_deck import imprint

COMMAND_MODES = [mode.text for mode in modal_profile(card("Kolaghan's Command")).modes]


def resolve_all(scenario) -> None:
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()


# -- rebound (CR 702.88a) ------------------------------------------------------


def test_a_rebound_recast_is_refused_by_a_cast_prohibition():
    """CR 611.1: bob's Orim's Chant ("Target player can't cast spells this
    turn") in response to rebound's trigger makes the free cast impossible, so
    the "may" cannot be taken (CR 608.2d) and Ephemerate stays exiled."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("erin", hand=["Ephemerate"], battlefield=["White Orchid Phantom", "Plains"])
        .player("bob", hand=["Orim's Chant"], battlefield=["Plains"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    phantom = scenario.creature("White Orchid Phantom")
    (plains,) = scenario.untapped_sources("Plains", username="erin")
    ephemerate = scenario.cast_and_resolve("Ephemerate", plains, targets=[phantom])
    turns = scenario.turn.turns_taken
    while not (
        scenario.turn.turns_taken > turns
        and scenario.step is Step.UPKEEP
        and scenario.game.active_player.username == "erin"
    ):
        resolve_all(scenario)
        scenario.advance()
    scenario.pass_priority("erin")
    (bob_plains,) = scenario.untapped_sources("Plains", username="bob")
    scenario.cast_onto_stack("Orim's Chant", bob_plains, username="bob", targets=["erin"])
    scenario.resolve_top()  # Orim's Chant

    scenario.resolve_top()  # rebound's trigger

    assert ephemerate.zone is Zone.EXILE
    assert scenario.game.stack_is_empty


# -- hideaway's play (Fight Rigging, Mosswort Bridge) --------------------------


def test_fight_rigging_casts_a_hidden_modal_spell_with_its_modes_announced():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Fight Rigging"],
            battlefield=["Forest", "Forest", "Forest", "Colossal Dreadmaw"],
            library=["Kolaghan's Command", "Forest", "Forest", "Forest", "Forest"],
        )
        .player("bob", hand=["Island"], battlefield=["Aether Spellbomb"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    command = scenario.player("alice").library[0]
    scenario.will_choose_cards(command, source="Fight Rigging")
    scenario.cast_and_resolve(
        "Fight Rigging", *scenario.untapped_sources("Forest", "Forest", "Forest")
    )
    resolve_all(scenario)
    dreadmaw = scenario.creature("Colossal Dreadmaw", "alice")
    spellbomb = scenario.find("Aether Spellbomb", Zone.BATTLEFIELD, "bob")

    scenario.will_take_the_may(True, source="Fight Rigging")
    scenario.choose_trigger_targets("Fight Rigging", [dreadmaw])
    scenario.will_choose_mode(COMMAND_MODES[1], source="Kolaghan's Command")
    scenario.will_choose_mode(COMMAND_MODES[2], source="Kolaghan's Command")
    scenario.will_choose_targets("bob", source="Kolaghan's Command")
    scenario.will_choose_targets(spellbomb, source="Kolaghan's Command")
    scenario.advance()  # combat begins
    scenario.resolve_top()  # Fight Rigging's trigger

    assert command.zone is Zone.STACK
    assert scenario.game.cast_record_of(command).modes == [2, 3]
    scenario.resolve_top()
    assert scenario.player("bob").hand == []
    assert spellbomb.zone is Zone.GRAVEYARD


def mosswort_board(hidden: str, extra: tuple[str, ...] = ()) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=["Mosswort Bridge"],
            library=[hidden, "Opt", "Lightning Bolt", "Craterous Stomp", *extra],
            battlefield=["Forest"] * 4 + ["Elder Gargaroth", "Ancient Adamantoise"],
        )
        .player("bob", library=["Island"] * 5)
        .build()
    )


def hide_with_the_bridge(scenario, hidden: str):
    scenario.start_at(Step.PRECOMBAT_MAIN)
    card_state = scenario.find(hidden, Zone.LIBRARY, "alice")
    scenario.will_choose_cards(card_state, source="Mosswort Bridge")
    bridge = scenario.play_land("Mosswort Bridge", "alice")
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()
    bridge.untap()
    return bridge, card_state


def test_mosswort_bridge_casts_the_hidden_spell_while_its_ability_resolves():
    scenario = mosswort_board("Goblin Guide")
    bridge, guide = hide_with_the_bridge(scenario, "Goblin Guide")
    scenario.will_take_the_may(True, source="Mosswort Bridge")

    scenario.activate(bridge, scenario.untapped_sources("Forest")[0], index=1)
    scenario.resolve_top()

    assert guide.zone is Zone.STACK
    assert scenario.game.play_permissions == []


def test_a_hidden_land_is_played_not_cast_and_counts_as_the_land_play():
    """CR 305.2b: the Bridge itself was this turn's land play, so the hidden
    Forest cannot be played now and stays exiled."""
    scenario = mosswort_board("Forest")
    bridge, forest = hide_with_the_bridge(scenario, "Forest")

    scenario.activate(bridge, scenario.untapped_sources("Forest")[0], index=1)
    scenario.resolve_top()

    (question,) = [
        q
        for q in scenario.questions_asked()
        if q.source == "Mosswort Bridge" and q.kind is DecisionKind.MAY
    ]
    assert question.affirmative_is_legal is False
    assert forest.zone is Zone.EXILE
    assert scenario.stack_names() == []


def test_a_hidden_land_is_played_on_a_later_turn():
    scenario = mosswort_board("Forest")
    bridge, forest = hide_with_the_bridge(scenario, "Forest")
    turns = scenario.turn.turns_taken
    while not (
        scenario.turn.turns_taken >= turns + 2
        and scenario.step is Step.PRECOMBAT_MAIN
        and scenario.game.active_player.username == "alice"
    ):
        resolve_all(scenario)
        scenario.advance()
    scenario.will_take_the_may(True, source="Mosswort Bridge")

    scenario.activate(bridge, scenario.untapped_sources("Forest")[0], index=1)
    scenario.resolve_top()

    assert forest.zone is Zone.BATTLEFIELD
    assert scenario.game.lands_played["alice"] == 1


# -- Knowledge Pool ------------------------------------------------------------


def test_knowledge_pool_casts_a_modal_spell_with_its_modes_announced():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Knowledge Pool", "Lightning Bolt"],
            library=["Kolaghan's Command", "Forest", "Forest"],
            battlefield=["Forest"] * 6 + ["Mountain"],
        )
        .player("bob", hand=["Island"], battlefield=["Aether Spellbomb"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve("Knowledge Pool", *scenario.untapped_sources(*["Forest"] * 6))
    scenario.resolve_top()  # the ETB
    command = scenario.find("Kolaghan's Command", Zone.EXILE, "alice")
    spellbomb = scenario.find("Aether Spellbomb", Zone.BATTLEFIELD, "bob")
    (mountain,) = scenario.untapped_sources("Mountain")
    scenario.cast_onto_stack("Lightning Bolt", mountain, targets=["bob"])
    scenario.game.put_triggers_on_stack()
    scenario.will_take_the_may(True, source="Knowledge Pool")
    scenario.will_choose_cards(command, source="Knowledge Pool")
    scenario.will_choose_mode(COMMAND_MODES[1], source="Kolaghan's Command")
    scenario.will_choose_mode(COMMAND_MODES[2], source="Kolaghan's Command")
    scenario.will_choose_targets("bob", source="Kolaghan's Command")
    scenario.will_choose_targets(spellbomb, source="Kolaghan's Command")

    scenario.resolve_top()  # Knowledge Pool's trigger

    assert command.zone is Zone.STACK
    assert scenario.game.cast_record_of(command).modes == [2, 3]
    scenario.resolve_top()
    assert scenario.player("bob").hand == []
    assert spellbomb.zone is Zone.GRAVEYARD


# -- Isochron Scepter's copy (CR 707.12) ---------------------------------------


def test_the_scepters_copy_is_offered_its_kicker():
    """CR 601.2b: the copy of Orim's Chant is cast (CR 707.12), so its kicker
    ({W}) may be paid on top of "without paying its mana cost" - with a
    Plains left after the activation."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Isochron Scepter", "Orim's Chant"],
            battlefield=["Island", "Plains", "Island", "Island", "Plains"],
        )
        .player("bob", hand=["Counterspell"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scepter = imprint(scenario)
    scenario.will_take_the_may(True, source="Isochron Scepter", times=None)
    scenario.will_take_the_may(True, source="Orim's Chant")
    scenario.will_choose_targets("bob", source="Orim's Chant")

    scenario.activate(
        scepter,
        *scenario.untapped_sources("Island", "Island"),
        username="alice",
    )
    scenario.resolve_top()  # the activation

    copy = next(
        state for state in scenario.game.stack if getattr(state, "name", "") == "Orim's Chant"
    )
    assert copy.is_copy
    assert scenario.game.cast_record_of(copy).kicked == 1


# -- Transcendent Dragon -------------------------------------------------------


def test_transcendent_dragon_recasts_the_countered_spell_during_its_trigger():
    scenario = (
        Scenario()
        .player("alice", hand=["Transcendent Dragon"], battlefield=["Island"] * 6)
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (mountain,) = scenario.untapped_sources("Mountain", username="bob")
    scenario.pass_priority("alice")
    bolt = scenario.cast_onto_stack("Lightning Bolt", mountain, username="bob", targets=["alice"])
    scenario.pass_priority("bob")
    scenario.choose_trigger_targets("Transcendent Dragon", [bolt])
    scenario.will_take_the_may(True, source="Transcendent Dragon")
    scenario.will_choose_targets("bob", source="Lightning Bolt")
    dragon = scenario.cast_onto_stack(
        "Transcendent Dragon", *scenario.untapped_sources(*["Island"] * 6)
    )

    scenario.resolve_top()  # Transcendent Dragon enters
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()  # its enters trigger: counter, exile, cast it

    assert bolt.zone is Zone.STACK
    assert scenario.game.controller_of(bolt).username == "alice"
    assert scenario.game.play_permissions == []
    assert scenario.stack_names() == ["Lightning Bolt"]
    assert dragon.zone is Zone.BATTLEFIELD
    scenario.resolve_top()
    assert scenario.player("bob").life == 17


# -- suspend (CR 702.62a, 702.62d) ---------------------------------------------


def test_suspends_last_counter_casts_living_end_during_the_upkeep_trigger():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Living End"],
            graveyard=["Grizzly Bears"],
            battlefield=["Swamp", "Swamp", "Swamp", "Swamp"],
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    from magic_cards_model.machines.casting import MarkedExile, remove_suspend_time_counter

    scenario.start_at(Step.PRECOMBAT_MAIN)
    living_end = scenario.find("Living End", Zone.HAND)
    action = MarkedExile.suspend(scenario.game, living_end, "alice")
    payment = action.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Swamp", "Swamp", "Swamp", "Swamp"))
    action.take()
    living_end = scenario.find("Living End", Zone.EXILE)
    for _ in range(3):
        remove_suspend_time_counter(scenario.game, living_end)
    scenario.game.put_triggers_on_stack()

    scenario.resolve_top()  # the last-counter trigger

    assert living_end.zone is Zone.STACK
    assert scenario.game.play_permissions == []
    record = scenario.game.cast_record_of(living_end)
    assert record is not None and record.keyword == "Suspend"


def test_a_creature_cast_off_suspend_has_haste_without_anyone_granting_it():
    """CR 702.62a: "If you cast a creature spell this way, it gains haste"."""
    from magic_cards_model.machines.casting import MarkedExile, remove_suspend_time_counter

    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Greater Gargadon"], battlefield=["Mountain"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    gargadon = scenario.find("Greater Gargadon", Zone.HAND)
    action = MarkedExile.suspend(scenario.game, gargadon, "alice")
    payment = action.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Mountain"))
    action.take()
    gargadon = scenario.find("Greater Gargadon", Zone.EXILE)
    for _ in range(10):
        remove_suspend_time_counter(scenario.game, gargadon)
    scenario.game.put_triggers_on_stack()

    scenario.resolve_top()  # the last-counter trigger casts it
    permanent = scenario.resolve_top()  # Greater Gargadon

    assert permanent.zone is Zone.BATTLEFIELD
    assert scenario.can_attack(permanent) is True
