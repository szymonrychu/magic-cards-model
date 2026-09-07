"""Every `DelayedEffectSpec` union member, round-tripped through
`Game.model_dump(mode="json")` / `Game.model_validate` while its trigger is
still pending, then resolved on the decoded copy.

Before this task, `DelayedTrigger.callback` was `Field(exclude=True)` - a bare
Python closure that a `model_dump` silently dropped - and the three hand-written
entries (`"warp:exile"`, `"grant_extra_turn"`, `"sacrifice"`) lived behind a
string-keyed `DELAYED_EFFECTS` registry that answered a miss with `None`.
Either way, a delayed trigger that survived a dump-and-reload resolved and did
nothing, with no error anywhere - the same "a wrong game state that looks
right is worse than an unimplemented one" shape `memory/silent-default-
dispatch-tables.md` names as the dominant defect class in this codebase.

`machines/delayed.py` now carries `DelayedEffectSpec`, a `kind`-discriminated
union of frozen pydantic models, each the exact body of the closure or
registry entry it replaces. Every test below proves the same shape: get a real
delayed (or CR 603.12 reflexive) trigger of one union member onto a real
`Game`, dump it, validate it back into a fresh `Game`, and show the effect
still actually happens on the decoded copy - not merely that decoding did not
raise. `test_an_unrecognised_effect_tag_refuses_at_decode` is the other half:
an effect this union does not know is a decode-time `ValidationError`, not a
silent `None`.

Every board below is real Scryfall printings from `tests/fixtures/cards`, and
every trigger is either staged the same direct way `tests/test_delayed.py`
and `tests/scenarios/test_delayed_triggered_abilities.py` already stage one
(a real board, a real permanent, `Game.create_delayed_trigger` called the way
a resolving spell's own effect function would call it), or produced by
actually casting/activating the real card that prints it.
"""

import pytest
from pydantic import ValidationError

from magic_cards_model.machines import Step
from magic_cards_model.machines.abilities import TriggerEvent
from magic_cards_model.machines.decisions import DecisionKind, ScriptedAnswer
from magic_cards_model.machines.delayed import (
    DelayedTrigger,
    GrantExtraTurn,
    SacrificeSubject,
    anaphoric_delayed_trigger,
    devourer_of_destiny_first_upkeep,
)
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from magic_cards_model.models.game import Game
from tests.scenarios.harness import PlayedScenario, Scenario


def _round_trip(game: Game) -> PlayedScenario:
    """Dump `game` to JSON and validate it back, wrapped for driving further.

    This is the whole point of every test in this file: whatever the trigger
    was about to do must still happen once the decoded copy runs it.
    """
    return PlayedScenario(Game.model_validate(game.model_dump(mode="json")))


def walk_to(scenario, step: Step) -> None:
    """Advance turn-by-turn - never jump - until `step`, resolving anything
    that fires along the way. `start_at` moves the turn machine without
    emitting CR 500.6's "a step began" event, which a delayed trigger waiting
    for a step can only ever see from a real `advance`.
    """
    while scenario.step is not step:
        scenario.advance()
        while not scenario.game.stack_is_empty:
            scenario.resolve_top()


def resolve_all(scenario) -> None:
    while scenario.game.stack:
        scenario.resolve_top()


# --------------------------------------------------------------------------
# warp:exile - Bygone Colossus (CR 702.185a)
# --------------------------------------------------------------------------


def test_exile_warped_survives_a_round_trip():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Bygone Colossus"], battlefield=["Island"] * 3)
        .player("bob", battlefield=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Island", "Island", "Island")
    casting = scenario.cast("Bygone Colossus")
    casting.use_keyword("Warp")
    scenario.pay_with(casting.begin_paying(), *sources)
    scenario.put_on_stack(casting)
    colossus = scenario.resolve_top()
    assert colossus.zone is Zone.BATTLEFIELD

    replay = _round_trip(scenario.game)
    colossus = replay.game.find_by_id(colossus.id)

    walk_to(replay, Step.END_STEP)

    assert colossus.zone is Zone.EXILE


# --------------------------------------------------------------------------
# grant_extra_turn - Emrakul, the Promised End's second sentence (CR 500.7)
# --------------------------------------------------------------------------


def test_grant_extra_turn_survives_a_round_trip():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Grizzly Bears"])
        .player("bob", battlefield=["Watchwolf"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.create_delayed_trigger(
        DelayedTrigger(
            text="After that turn, that player takes an extra turn.",
            effect=GrantExtraTurn(),
            event=TriggerEvent.BEGINNING_OF_STEP,
            step=Step.END_STEP,
            controller="alice",
            source_name="Emrakul, the Promised End",
            subject_player="bob",
            only_when_active="bob",
        )
    )

    replay = _round_trip(scenario.game)

    while replay.turn.active_player != "bob":
        replay.advance()
        while not replay.game.stack_is_empty:
            replay.resolve_top()
    walk_to(replay, Step.END_STEP)

    assert replay.turn.extra_turns == ["bob"]


# --------------------------------------------------------------------------
# sacrifice - "At the beginning of the next end step, sacrifice it."
# --------------------------------------------------------------------------


def test_sacrifice_subject_survives_a_round_trip():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Grizzly Bears"])
        .player("bob", battlefield=["Watchwolf"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.game.create_delayed_trigger(
        DelayedTrigger(
            text="At the beginning of the next end step, sacrifice it.",
            effect=SacrificeSubject(),
            event=TriggerEvent.BEGINNING_OF_STEP,
            step=Step.END_STEP,
            controller="alice",
            source_name="a resolving spell",
            subject_id=bears.id,
            expected_zone=Zone.BATTLEFIELD,
        )
    )

    replay = _round_trip(scenario.game)
    bears = replay.game.find_by_id(bears.id)

    walk_to(replay, Step.END_STEP)

    assert bears.zone is Zone.GRAVEYARD


# --------------------------------------------------------------------------
# exile_subject_at_next_end_step - Goryo's Vengeance's own third sentence
# --------------------------------------------------------------------------


def test_exile_subject_at_next_end_step_survives_a_round_trip():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Goryo's Vengeance"],
            graveyard=["Isamaru, Hound of Konda"],
            battlefield=["Swamp", "Swamp"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    isamaru = scenario.find("Isamaru, Hound of Konda", Zone.GRAVEYARD, "alice")

    casting = scenario.cast("Goryo's Vengeance")
    casting.game = scenario.game
    casting.choose_targets([isamaru])
    casting.determine_cost()
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Swamp", "Swamp"))
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert isamaru.zone is Zone.BATTLEFIELD
    assert "Haste" in scenario.game.characteristics_of(isamaru).abilities

    replay = _round_trip(scenario.game)
    isamaru = replay.game.find_by_id(isamaru.id)

    walk_to(replay, Step.END_STEP)

    assert isamaru.zone is Zone.EXILE


# --------------------------------------------------------------------------
# return_subject_to_battlefield_under_owner - Flickerwisp, no rider
# --------------------------------------------------------------------------


def test_return_subject_to_battlefield_under_owner_survives_a_round_trip():
    scenario = (
        Scenario()
        .player("alice", hand=["Flickerwisp"], battlefield=["Plains", "Plains", "Plains"])
        .player("bob", battlefield=["Watchwolf"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    watchwolf = scenario.creature("Watchwolf", "bob")
    scenario.choose_trigger_targets("Flickerwisp", [watchwolf])
    sources = scenario.untapped_sources("Plains", "Plains", "Plains")
    scenario.cast_and_resolve("Flickerwisp", *sources)
    resolve_all(scenario)

    assert watchwolf.zone is Zone.EXILE

    replay = _round_trip(scenario.game)
    watchwolf = replay.game.find_by_id(watchwolf.id)

    walk_to(replay, Step.END_STEP)

    assert watchwolf.zone is Zone.BATTLEFIELD
    assert watchwolf.controller == "bob"


# --------------------------------------------------------------------------
# return_subject_to_hand - Aether Membrane's own blocking trigger
# --------------------------------------------------------------------------


def test_return_subject_to_hand_survives_a_round_trip():
    scenario = (
        Scenario()
        .player("alice", library=["Forest"], battlefield=["Grizzly Bears"])
        .player("bob", library=["Island"], battlefield=["Aether Membrane", "Island"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    bears = scenario.creature("Grizzly Bears", "alice")
    membrane = scenario.creature("Aether Membrane", "bob")

    scenario.attack_with(bears)
    scenario.block(bears, membrane)
    scenario.pass_until_resolved()  # Aether Membrane's own trigger

    assert bears.zone is Zone.BATTLEFIELD

    replay = _round_trip(scenario.game)
    bears = replay.game.find_by_id(bears.id)

    walk_to(replay, Step.END_OF_COMBAT)

    assert bears.zone is Zone.HAND
    assert bears.owner == "alice"


# --------------------------------------------------------------------------
# rebound_recast - Ephemerate's own printed keyword (CR 702.88a)
# --------------------------------------------------------------------------


def test_rebound_recast_survives_a_round_trip():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("erin", hand=["Ephemerate"], battlefield=["White Orchid Phantom", "Plains"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    phantom = scenario.creature("White Orchid Phantom")
    (plains,) = scenario.untapped_sources("Plains")
    ephemerate = scenario.cast_and_resolve("Ephemerate", plains, targets=[phantom])
    assert ephemerate.zone is Zone.EXILE

    replay = _round_trip(scenario.game)
    ephemerate = replay.game.find_by_id(ephemerate.id)
    phantom = replay.game.find_by_id(phantom.id)

    replay.game.decisions.add(
        ScriptedAnswer(
            kind=DecisionKind.CHOOSE_TARGETS,
            value=(phantom.id,),
            player="erin",
            source=None,
            uses=1,
        )
    )
    turns = replay.turn.turns_taken
    while not (
        replay.turn.turns_taken > turns
        and replay.step is Step.UPKEEP
        and replay.game.active_player.username == "erin"
    ):
        while not replay.game.stack_is_empty:
            replay.resolve_top()
        replay.advance()
    replay.resolve_top()  # the delayed trigger itself: "you may cast ..."

    assert ephemerate.zone is Zone.STACK


# --------------------------------------------------------------------------
# draw_a_card_for_controller - Mishra's Bauble's second half
# --------------------------------------------------------------------------


def test_draw_a_card_for_controller_survives_a_round_trip():
    scenario = (
        Scenario()
        .player("alice", library=["Forest", "Forest"], battlefield=["Mishra's Bauble"])
        .player("bob", library=["Island"], battlefield=["Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bauble = scenario.creature("Mishra's Bauble", "alice")
    hand_before = len(scenario.player("alice").hand)

    scenario.activate(bauble, targets=["bob"])
    scenario.pass_until_resolved()
    assert len(scenario.player("alice").hand) == hand_before

    replay = _round_trip(scenario.game)

    walk_to(replay, Step.UPKEEP)
    while not replay.game.stack_is_empty:
        replay.resolve_top()

    assert len(replay.player("alice").hand) == hand_before + 1


# --------------------------------------------------------------------------
# destroy_subject / tap_subject - the anaphoric primitive's own two verbs
# with no printed card in the pool exercising either alone; staged directly
# the way `tests/test_delayed.py` already stages every anaphoric shape.
# --------------------------------------------------------------------------


def test_destroy_subject_survives_a_round_trip():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Grizzly Bears", "Mountain"])
        .player("bob", battlefield=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice")
    trigger = anaphoric_delayed_trigger(
        "Destroy that creature at end of combat.",
        subject=bears,
        controller="alice",
        source_id=None,
        source_name="a resolving spell",
    )
    assert trigger is not None
    scenario.game.create_delayed_trigger(trigger)

    replay = _round_trip(scenario.game)
    bears = replay.game.find_by_id(bears.id)

    replay.start_at(Step.DECLARE_ATTACKERS)
    walk_to(replay, Step.END_OF_COMBAT)

    assert bears.zone is Zone.GRAVEYARD


def test_tap_subject_survives_a_round_trip():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Grizzly Bears", "Mountain"])
        .player("bob", battlefield=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice")
    trigger = anaphoric_delayed_trigger(
        "Tap it at the beginning of the next turn's upkeep.",
        subject=bears,
        controller="alice",
        source_id=None,
        source_name="a resolving spell",
    )
    assert trigger is not None
    scenario.game.create_delayed_trigger(trigger)

    replay = _round_trip(scenario.game)
    bears = replay.game.find_by_id(bears.id)
    assert bears.untapped

    walk_to(replay, Step.UPKEEP)

    assert bears.tapped


# --------------------------------------------------------------------------
# return_earthbent_land - Badgermole Cub (CR 701.66a)
# --------------------------------------------------------------------------


def test_return_earthbent_land_survives_a_round_trip():
    scenario = (
        Scenario()
        .player("alice", hand=["Badgermole Cub"], battlefield=["Forest", "Forest", "Forest"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Forest", "Forest")
    # The third Forest, left untapped by the payment above, is earthbend's
    # own target.
    forests = [state for state in scenario.game.battlefield if state.name == "Forest"]
    target_forest = next(state for state in forests if state not in sources)
    scenario.choose_trigger_targets("Badgermole Cub", [target_forest])
    scenario.cast_and_resolve("Badgermole Cub", *sources)
    scenario.pass_until_resolved()

    scenario.game.destroy(target_forest)
    assert target_forest.zone is Zone.GRAVEYARD
    scenario.game.put_triggers_on_stack()  # CR 603.3

    replay = _round_trip(scenario.game)
    target_forest = replay.game.find_by_id(target_forest.id)
    assert target_forest.zone is Zone.GRAVEYARD

    replay.resolve_top()  # the delayed return

    assert target_forest.zone is Zone.BATTLEFIELD
    assert target_forest.tapped is True
    assert target_forest.controller == "alice"


# --------------------------------------------------------------------------
# devourer_of_destiny_first_upkeep - staged directly, real library cards
# --------------------------------------------------------------------------


def test_devourer_of_destiny_first_upkeep_survives_a_round_trip():
    scenario = (
        Scenario()
        .player("alice", library=["Forest"] * 6, battlefield=["Devourer of Destiny"])
        .player("bob", library=["Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    top_four_ids = [state.id for state in alice.library[:4]]
    # Through `Game.create_delayed_trigger`, not `.delayed_triggers.create`
    # directly: the former opens `_id_allocator_scope` and re-mints `trigger.
    # id` inside it (see its own docstring) - the latter is the container's
    # own bare method, called here with no scope open at all, which minted a
    # plain unreplayable `uuid4()` before T10's invariant caught it.
    scenario.game.create_delayed_trigger(
        DelayedTrigger(
            text=(
                "At the beginning of your first upkeep, look at the top four cards of "
                "your library. You may put one of those cards back on top of your "
                "library. Exile the rest."
            ),
            effect=devourer_of_destiny_first_upkeep,
            event=TriggerEvent.BEGINNING_OF_STEP,
            step=Step.UPKEEP,
            controller="alice",
            source_name="Devourer of Destiny",
            only_when_active="alice",
        )
    )

    replay = _round_trip(scenario.game)

    # `walk_to` alone would stop at bob's own upkeep first - `only_when_active`
    # correctly refuses to fire there, so this has to reach alice's own.
    while not (replay.step is Step.UPKEEP and replay.turn.active_player == "alice"):
        replay.advance()
        while not replay.game.stack_is_empty:
            replay.resolve_top()

    top_four = [replay.game.find_by_id(state_id) for state_id in top_four_ids]
    assert all(state.zone is Zone.EXILE for state in top_four), (
        "unscripted default declines the 'put one back' choice (CR 608.2d)"
    )


# --------------------------------------------------------------------------
# static_prison_return - Static Prison itself (CR 610.2)
# --------------------------------------------------------------------------


def test_static_prison_return_survives_a_round_trip():
    scenario = (
        Scenario()
        .player("alice", hand=["Static Prison"], battlefield=["Plains"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    (plains,) = scenario.untapped_sources("Plains")
    scenario.choose_trigger_targets("Static Prison", [bears])
    prison = scenario.cast_and_resolve("Static Prison", plains)
    scenario.pass_until_resolved()  # the ETB trigger: exile Grizzly Bears
    assert bears.zone is Zone.EXILE

    scenario.game.destroy(prison)

    replay = _round_trip(scenario.game)
    bears = replay.game.find_by_id(bears.id)
    prison = replay.game.find_by_id(prison.id)

    replay.pass_until_resolved()  # the delayed trigger: return Grizzly Bears

    assert prison.zone is Zone.GRAVEYARD
    assert bears.zone is Zone.BATTLEFIELD
    assert replay.game.controller_of(bears).username == "bob"


# --------------------------------------------------------------------------
# return_exiled_card_and_add_counters - Lagrella, the Magpie's second sentence
# --------------------------------------------------------------------------


def test_return_exiled_card_and_add_counters_survives_a_round_trip():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Lagrella, the Magpie"],
            battlefield=["Basking Broodscale", "Forest", "Plains", "Island"],
        )
        .player("bob", battlefield=["Hill Giant"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    broodscale = scenario.creature("Basking Broodscale", "alice")
    scenario.choose_trigger_targets("Lagrella, the Magpie", [broodscale])
    sources = scenario.untapped_sources("Forest", "Plains", "Island", username="alice")
    lagrella = scenario.cast_and_resolve("Lagrella, the Magpie", *sources, username="alice")
    while scenario.game.stack or scenario.pending_triggers:
        scenario.pass_until_resolved()
    assert broodscale.zone is Zone.EXILE

    scenario.game.destroy(lagrella)

    replay = _round_trip(scenario.game)
    broodscale = replay.game.find_by_id(broodscale.id)

    while replay.game.stack or replay.pending_triggers:
        replay.pass_until_resolved()

    assert broodscale.zone is Zone.BATTLEFIELD
    assert broodscale.counter_count("+1/+1") == 2
    assert "Eldrazi Spawn Token" in replay.battlefield_names()


# --------------------------------------------------------------------------
# create_attacking_tokens - Dalkovan Encampment's activated ability
# --------------------------------------------------------------------------


def test_create_attacking_tokens_survives_a_round_trip():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=["Dalkovan Encampment", "Plains", "Plains", "Plains", "Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    bears.summoning_sick = False
    encampment = scenario.find("Dalkovan Encampment", Zone.BATTLEFIELD)
    sources = scenario.untapped_sources("Plains", "Plains", "Plains", username="alice")
    scenario.activate(encampment, *sources, index=1, username="alice")
    resolve_all(scenario)

    replay = _round_trip(scenario.game)
    bears = replay.game.find_by_id(bears.id)

    replay.start_at(Step.DECLARE_ATTACKERS)
    replay.attack_with(bears, defending="bob")
    replay.game.put_triggers_on_stack()  # CR 603.3
    resolve_all(replay)

    warriors = [state for state in replay.game.battlefield if state.name == "Warrior Token"]
    assert len(warriors) == 2
    assert all(state.tapped and replay.game.is_attacking(state) for state in warriors)


# --------------------------------------------------------------------------
# pay_or_lose_the_game - Summoner's Pact (CR 104.3e)
# --------------------------------------------------------------------------


def test_pay_or_lose_the_game_survives_a_round_trip():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Summoner's Pact"],
            library=["Primeval Titan", "Forest", "Forest", "Forest", "Forest"],
        )
        .player("bob", battlefield=["Grizzly Bears"], library=["Forest"] * 6)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve("Summoner's Pact")

    replay = _round_trip(scenario.game)

    while not (replay.step is Step.UPKEEP and replay.turn.active_player == "alice"):
        replay.advance()
        while not replay.game.stack_is_empty:
            replay.resolve_top()

    assert not replay.game.is_in_game("alice"), "CR 104.3e: unpaid and unpayable (no mana floating)"
    assert replay.game.winner == "bob"


# --------------------------------------------------------------------------
# combat_damage_to_player_draw - Captain Howler, Sea Scourge's second sentence
# --------------------------------------------------------------------------


def test_combat_damage_to_player_draw_survives_a_round_trip():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Mind Rot", "Lava Dart", "Forest"],
            battlefield=[
                "Captain Howler, Sea Scourge",
                "Grizzly Bears",
                "Swamp",
                "Swamp",
                "Swamp",
            ],
            library=["Island"] * 5,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    sources = scenario.untapped_sources("Swamp", "Swamp", "Swamp")
    scenario.choose_trigger_targets("Captain Howler, Sea Scourge", [bears])
    scenario.cast_and_resolve("Mind Rot", *sources, targets=["alice"])
    resolve_all(scenario)

    replay = _round_trip(scenario.game)
    bears = replay.game.find_by_id(bears.id)
    hand_before = len(replay.player("alice").hand)

    replay.attack_with(bears)
    replay.no_blocks()
    replay.combat_damage()
    replay.game.put_triggers_on_stack()
    resolve_all(replay)

    assert len(replay.player("alice").hand) == hand_before + 1


# --------------------------------------------------------------------------
# copy_next_spell_you_cast - Flamehold Grappler
# --------------------------------------------------------------------------


def test_copy_next_spell_you_cast_survives_a_round_trip():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Flamehold Grappler", "Sol Ring"],
            battlefield=["Island", "Island", "Mountain", "Plains"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    lands = scenario.untapped_sources("Island", "Mountain", "Plains", username="alice")
    scenario.cast_and_resolve("Flamehold Grappler", *lands, username="alice")
    resolve_all(scenario)  # the enters trigger, creating the delayed one

    replay = _round_trip(scenario.game)

    (island,) = replay.untapped_sources("Island", username="alice")
    replay.cast_and_resolve("Sol Ring", island, username="alice")
    resolve_all(replay)

    from magic_cards_model.models.token import is_token

    tokens = [
        state
        for state in replay.game.battlefield
        if state.controller == "alice" and is_token(state)
    ]
    assert [token.name for token in tokens] == ["Sol Ring"]


# --------------------------------------------------------------------------
# delayed_blink_return_with_rider - Phelia, Exuberant Shepherd's own rider
# --------------------------------------------------------------------------


def test_delayed_blink_return_with_rider_survives_a_round_trip():
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Forest"],
            battlefield=["Phelia, Exuberant Shepherd", "Grizzly Bears"],
        )
        .player("bob", library=["Island"], battlefield=["Island"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    phelia = scenario.creature("Phelia, Exuberant Shepherd", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.choose_trigger_targets("Phelia, Exuberant Shepherd", [bears])
    scenario.attack_with(phelia)
    scenario.pass_until_resolved()
    assert bears.zone is Zone.EXILE

    replay = _round_trip(scenario.game)
    phelia = replay.game.find_by_id(phelia.id)
    bears = replay.game.find_by_id(bears.id)

    walk_to(replay, Step.END_STEP)

    assert bears.zone is Zone.BATTLEFIELD
    assert bears.controller == "alice"
    assert phelia.counters[Counter.PLUS_ONE] == 1


# --------------------------------------------------------------------------
# reflexive_consequence - Grist, the Hunger Tide's -2 (CR 603.12)
# --------------------------------------------------------------------------


def test_reflexive_consequence_survives_a_round_trip():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=[],
            library=["Forest"],
            battlefield=["Grist, the Hunger Tide", "Grizzly Bears"],
        )
        .player(
            "bob",
            hand=["Lightning Bolt"],
            library=["Mountain"],
            battlefield=["Hill Giant", "Mountain"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    giant = scenario.creature("Hill Giant", "bob")
    scenario.will_take_the_may(True, source="Grist, the Hunger Tide")
    scenario.choose_trigger_targets("Grist, the Hunger Tide", [giant])

    grist = scenario.find("Grist, the Hunger Tide", Zone.BATTLEFIELD, "alice")
    scenario.activate(grist, index=1, username="alice")
    scenario.pass_until_resolved()  # -2 itself: sacrifices, creates the reflexive ability
    assert scenario.stack_names() == ["Grist, the Hunger Tide's triggered ability"]

    replay = _round_trip(scenario.game)
    giant = replay.game.find_by_id(giant.id)

    replay.resolve_top()  # the reflexive ability itself

    assert giant.zone is Zone.GRAVEYARD


# --------------------------------------------------------------------------
# reflexive_pay_energy_consequence - Guide of Souls' attack trigger
# --------------------------------------------------------------------------


def test_reflexive_pay_energy_consequence_survives_a_round_trip():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Guide of Souls", "Grizzly Bears"])
        .player("bob", battlefield=["Hill Giant"])
        .build()
    )
    scenario.player("alice").add_counters(Counter.ENERGY, 3)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.start_at(Step.DECLARE_ATTACKERS)

    scenario.attack_with(bears)
    scenario.game.put_triggers_on_stack()
    scenario.choose_trigger_targets("Guide of Souls", [bears])
    scenario.will_pay_the_energy(True, source="Guide of Souls")
    scenario.resolve_top()  # "Whenever you attack": pays energy, creates the reflexive ability
    assert scenario.stack_names() == ["Guide of Souls's triggered ability"]

    replay = _round_trip(scenario.game)
    bears = replay.game.find_by_id(bears.id)

    replay.resolve_top()  # the reflexive ability itself

    assert bears.counters[Counter.PLUS_ONE] == 2
    assert bears.counters["flying"] == 1
    assert "Angel" in replay.game.characteristics_of(bears).subtypes


# --------------------------------------------------------------------------
# reflexive_mandatory_token_damage_consequence - Ajani, Nacatl Avenger's `0`
# --------------------------------------------------------------------------


def test_reflexive_mandatory_token_damage_consequence_survives_a_round_trip():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice", battlefield=["Ajani, Nacatl Pariah // Ajani, Nacatl Avenger", "Raging Goblin"]
        )
        .player("bob", battlefield=[])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ajani = scenario.find("Ajani, Nacatl Pariah", Zone.BATTLEFIELD, "alice")
    ajani.transform()
    ajani.add_counters(Counter.LOYALTY, 3)
    zero_ability = scenario.game.activated_abilities(ajani)[1]
    assert zero_ability.cost == "0"
    scenario.activate(ajani, index=1)
    scenario.choose_trigger_targets(ajani.name, ["bob"])
    scenario.resolve_top()  # "0": creates the token, checks the if, creates the reflexive ability
    assert scenario.stack_names() == [f"{ajani.name}'s triggered ability"]

    replay = _round_trip(scenario.game)
    bob = replay.player("bob")

    replay.resolve_top()  # the reflexive ability itself

    assert bob.life == 18, "2 creatures: Raging Goblin and the fresh token"


# --------------------------------------------------------------------------
# reflexive_exile_copied_card - Superior Spider-Man's Mind Swap (DDR#986)
# --------------------------------------------------------------------------


def test_reflexive_exile_copied_card_survives_a_round_trip():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Superior Spider-Man"],
            graveyard=["Grizzly Bears"],
            battlefield=["Island", "Island", "Swamp", "Swamp"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")
    sources = scenario.untapped_sources("Island", "Island", "Swamp", "Swamp", username="alice")
    scenario.cast_and_resolve("Superior Spider-Man", *sources, username="alice")
    assert scenario.stack_names() == ["Superior Spider-Man's triggered ability"]

    replay = _round_trip(scenario.game)
    bears = replay.game.find_by_id(bears.id)
    assert bears.zone is Zone.GRAVEYARD

    replay.resolve_top()  # the reflexive ability: exile that card

    assert bears.zone is Zone.EXILE


# --------------------------------------------------------------------------
# An unrecognised effect tag refuses at decode, rather than resolving to
# nothing the way `DELAYED_EFFECTS.get(...)` used to.
# --------------------------------------------------------------------------


def test_an_unrecognised_effect_tag_refuses_at_decode():
    with pytest.raises(ValidationError):
        DelayedTrigger.model_validate(
            {
                "text": "does something nobody wrote a spec for",
                "effect": {"kind": "not_a_real_effect"},
                "controller": "alice",
                "source_name": "a resolving spell",
            }
        )
