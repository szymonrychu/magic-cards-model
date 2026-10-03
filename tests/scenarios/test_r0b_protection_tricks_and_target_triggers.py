"""R0b proofs: protection tricks and becomes-the-target triggers - Kami of
False Hope, Snakeskin Veil, Surrak, Elusive Hunter and Emberheart Challenger.

Every CR number below was looked up with `mise run rules:find` (on-disk CR
effective 2026-09-25) in the session that wrote this file:

- **CR 615.1** - prevention effects apply continuously as damage events
  happen and completely or partially replace that damage.
- **CR 702.11b** - hexproof: can't be the target of spells or abilities your
  opponents control.
- **CR 608.2b** - a spell or ability whose every target became illegal doesn't
  resolve (it "fizzles").
- **CR 702.108a** - prowess: whenever you cast a noncreature spell, +1/+1 until
  end of turn.
- **CR 601.2c** - targets are chosen as a spell is announced; a spell on the
  stack is itself a legal target of a counterspell.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import Keyword, has_keyword
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

KAMI = "Kami of False Hope"
VEIL = "Snakeskin Veil"
SURRAK = "Surrak, Elusive Hunter"
EMBERHEART = "Emberheart Challenger"


def _resolve_all(scenario):
    """Resolve the stack to empty, one object per pass (triggers included)."""
    while scenario.stack_names():
        scenario.pass_until_resolved()


def _to(scenario, username):
    """Hand priority to `username` with a single pass by whoever holds it."""
    holder = scenario.priority_holder
    if holder != username:
        scenario.pass_priority(holder)


def _hexproof(scenario, permanent):
    return scenario.game.hexproof_abilities(permanent)[0]


def _pt(scenario, permanent):
    state = scenario.game.computed_board().of(permanent)
    return state.power, state.toughness


# -- Kami of False Hope ------------------------------------------------------


def _combat_with_kami():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Grizzly Bears"])
        .player("bob", battlefield=[KAMI, "Savannah Lions", "Mountain"], hand=["Lightning Bolt"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    bears = scenario.creature("Grizzly Bears", "alice")
    lions = scenario.creature("Savannah Lions", "bob")
    kami = scenario.creature(KAMI, "bob")
    return scenario, bears, lions, kami


def _bob_sacrifices_kami(scenario, kami):
    _to(scenario, "bob")
    scenario.activate(kami, username="bob", sacrificing=[kami])
    _resolve_all(scenario)


def test_kami_sacrifice_prevents_all_combat_damage_to_a_player():
    scenario, bears, _lions, kami = _combat_with_kami()
    scenario.attack_with(bears)
    scenario.no_blocks()

    _bob_sacrifices_kami(scenario, kami)
    scenario.combat_damage()

    assert kami.zone is Zone.GRAVEYARD, "the sacrifice is the cost"
    assert scenario.player("bob").life == 20


def test_kami_sacrifice_prevents_combat_damage_both_ways_between_creatures():
    scenario, bears, lions, kami = _combat_with_kami()
    scenario.attack_with(bears)
    scenario.block(bears, lions)

    _bob_sacrifices_kami(scenario, kami)
    scenario.combat_damage()

    assert bears.damage == 0 and lions.damage == 0
    assert bears.zone is Zone.BATTLEFIELD and lions.zone is Zone.BATTLEFIELD


def test_kami_does_not_prevent_noncombat_damage():
    """CR 615.1: the effect watches for combat damage events only."""
    scenario, bears, _lions, kami = _combat_with_kami()
    scenario.attack_with(bears)
    scenario.no_blocks()
    _bob_sacrifices_kami(scenario, kami)
    _to(scenario, "bob")

    scenario.cast_and_resolve(
        "Lightning Bolt",
        *scenario.untapped_sources("Mountain", username="bob"),
        username="bob",
        targets=[bears],
    )

    assert bears.zone is Zone.GRAVEYARD, "3 damage from Bolt killed the 2/2: not prevented"


def test_kami_without_the_sacrifice_lets_combat_damage_through():
    scenario, bears, _lions, _kami = _combat_with_kami()
    scenario.attack_with(bears)
    scenario.no_blocks()

    scenario.combat_damage()

    assert scenario.player("bob").life == 18


def test_kami_prevention_ends_with_the_turn():
    scenario, bears, _lions, kami = _combat_with_kami()
    scenario.attack_with(bears)
    scenario.no_blocks()
    _bob_sacrifices_kami(scenario, kami)

    scenario.start_at(Step.CLEANUP)
    scenario.turn_based_actions()
    scenario.advance()  # bob's turn

    assert scenario.game.prevention_shields == []


# -- Snakeskin Veil ----------------------------------------------------------


def _veil_board(bob_hand=("Lightning Bolt",)):
    scenario = (
        Scenario()
        .player("alice", hand=[VEIL], battlefield=["Forest", "Forest", "Grizzly Bears"])
        .player("bob", hand=list(bob_hand), battlefield=["Mountain", "Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_veil_puts_a_counter_and_grants_hexproof():
    scenario = _veil_board()
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.cast_and_resolve(VEIL, *scenario.untapped_sources("Forest")[:1], targets=[bears])

    assert bears.counter_count("+1/+1") == 1
    assert _pt(scenario, bears) == (3, 3)
    assert _hexproof(scenario, bears)


def test_veil_in_response_fizzles_the_opponents_removal():
    """CR 702.11b + CR 608.2b: Bolt was legal when cast; once the Bears have
    hexproof it is an illegal target and the Bolt does nothing."""
    scenario = _veil_board()
    bears = scenario.creature("Grizzly Bears", "alice")
    _to(scenario, "bob")
    scenario.cast_onto_stack(
        "Lightning Bolt",
        *scenario.untapped_sources("Mountain", username="bob")[:1],
        username="bob",
        targets=[bears],
    )
    _to(scenario, "alice")
    scenario.cast_and_resolve(  # alice responds
        VEIL, *scenario.untapped_sources("Forest")[:1], username="alice", targets=[bears]
    )

    _resolve_all(scenario)

    assert bears.zone is Zone.BATTLEFIELD
    assert bears.damage == 0
    assert scenario.find("Lightning Bolt", Zone.GRAVEYARD, "bob").zone is Zone.GRAVEYARD


def test_veil_hexproof_refuses_a_later_opponent_target():
    scenario = _veil_board()
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.cast_and_resolve(VEIL, *scenario.untapped_sources("Forest")[:1], targets=[bears])
    _to(scenario, "bob")

    casting = scenario.cast("Lightning Bolt", username="bob")
    with pytest.raises(ValueError, match="hexproof"):
        casting.choose_targets([bears])


def test_veil_does_not_stop_its_controllers_own_targeting():
    """Hexproof is not shroud: a second Veil from the same controller can
    still target the hexproof creature."""
    scenario = (
        Scenario()
        .player("alice", hand=[VEIL, VEIL], battlefield=["Forest", "Forest", "Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    first, second = scenario.untapped_sources("Forest", "Forest")
    scenario.cast_and_resolve(VEIL, first, targets=[bears])

    scenario.cast_and_resolve(VEIL, second, targets=[bears])

    assert bears.counter_count("+1/+1") == 2


def test_veil_counter_stays_after_the_hexproof_ends():
    scenario = _veil_board()
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.cast_and_resolve(VEIL, *scenario.untapped_sources("Forest")[:1], targets=[bears])

    scenario.start_at(Step.CLEANUP)
    scenario.turn_based_actions()

    assert bears.counter_count("+1/+1") == 1, "the counter is permanent"
    assert not _hexproof(scenario, bears), "until end of turn only"


def test_veil_cannot_target_an_opponents_creature():
    scenario = (
        Scenario()
        .player("alice", hand=[VEIL], battlefield=["Forest"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    casting = scenario.cast(VEIL)

    with pytest.raises(ValueError):
        casting.choose_targets([scenario.creature("Grizzly Bears", "bob")])


# -- Surrak, Elusive Hunter --------------------------------------------------


def _surrak_board(alice_hand=(), bob_hand=("Lightning Bolt",), alice_battlefield=()):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=list(alice_hand),
            battlefield=[SURRAK, "Grizzly Bears", "Forest", "Forest", "Forest", *alice_battlefield],
            library=["Forest"] * 5,
        )
        .player("bob", hand=list(bob_hand), battlefield=["Mountain", "Island", "Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_surrak_is_a_4_3_trampler():
    scenario = _surrak_board()
    surrak = scenario.creature(SURRAK, "alice")

    assert _pt(scenario, surrak) == (4, 3)
    assert has_keyword(surrak, Keyword.TRAMPLE, scenario.game)


def test_surrak_cant_be_countered():
    scenario = (
        Scenario()
        .player("alice", hand=[SURRAK], battlefield=["Forest", "Forest", "Forest"])
        .player("bob", hand=["Counterspell"], battlefield=["Island", "Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_onto_stack(SURRAK, *scenario.untapped_sources("Forest", "Forest", "Forest"))
    spell = scenario.find(SURRAK, Zone.STACK)
    _to(scenario, "bob")

    scenario.cast_and_resolve(
        "Counterspell",
        *scenario.untapped_sources("Island", "Island", username="bob"),
        username="bob",
        targets=[spell],
    )
    _resolve_all(scenario)

    assert scenario.find(SURRAK, Zone.BATTLEFIELD).zone is Zone.BATTLEFIELD


def test_surrak_draws_when_an_opponent_targets_another_creature_you_control():
    scenario = _surrak_board()
    bears = scenario.creature("Grizzly Bears", "alice")
    hand_before = len(scenario.player("alice").hand)
    _to(scenario, "bob")

    scenario.cast_onto_stack(
        "Lightning Bolt",
        *scenario.untapped_sources("Mountain", username="bob"),
        username="bob",
        targets=[bears],
    )
    _resolve_all(scenario)  # Surrak's trigger resolves above the Bolt

    assert len(scenario.player("alice").hand) == hand_before + 1


def test_surrak_draws_when_an_opponent_targets_surrak_itself():
    scenario = _surrak_board()
    surrak = scenario.creature(SURRAK, "alice")
    hand_before = len(scenario.player("alice").hand)
    _to(scenario, "bob")

    scenario.cast_onto_stack(
        "Lightning Bolt",
        *scenario.untapped_sources("Mountain", username="bob"),
        username="bob",
        targets=[surrak],
    )
    _resolve_all(scenario)

    assert len(scenario.player("alice").hand) == hand_before + 1


def test_surrak_does_not_draw_for_your_own_targeting():
    scenario = _surrak_board(alice_hand=["Giant Growth"])
    bears = scenario.creature("Grizzly Bears", "alice")
    hand_before = len(scenario.player("alice").hand)

    scenario.cast_and_resolve(
        "Giant Growth", *scenario.untapped_sources("Forest")[:1], targets=[bears]
    )

    assert len(scenario.player("alice").hand) == hand_before - 1, "only the cast card left"


def test_surrak_does_not_draw_for_an_opponents_creature_being_targeted():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[SURRAK, "Mountain"],
            hand=["Lightning Bolt"],
            library=["Forest"] * 3,
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    hand_before = len(scenario.player("alice").hand)

    scenario.cast_and_resolve(
        "Lightning Bolt",
        *scenario.untapped_sources("Mountain"),
        targets=[scenario.creature("Grizzly Bears", "bob")],
    )

    assert len(scenario.player("alice").hand) == hand_before - 1


def test_surrak_draws_when_an_opponent_counters_a_creature_spell_you_control():
    """'A creature spell you control becomes the target of a spell ... an
    opponent controls' - the spell on the stack is the target (CR 601.2c)."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Grizzly Bears"],
            battlefield=[SURRAK, "Forest", "Forest"],
            library=["Forest"] * 3,
        )
        .player("bob", hand=["Counterspell"], battlefield=["Island", "Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_onto_stack("Grizzly Bears", *scenario.untapped_sources("Forest", "Forest"))
    bears_spell = scenario.find("Grizzly Bears", Zone.STACK)
    hand_before = len(scenario.player("alice").hand)
    _to(scenario, "bob")

    scenario.cast_onto_stack(
        "Counterspell",
        *scenario.untapped_sources("Island", "Island", username="bob"),
        username="bob",
        targets=[bears_spell],
    )
    _resolve_all(scenario)

    assert len(scenario.player("alice").hand) == hand_before + 1


def test_surrak_draws_once_per_targeting_event():
    scenario = _surrak_board(bob_hand=("Lightning Bolt", "Lightning Bolt"))
    bears = scenario.creature("Grizzly Bears", "alice")
    _to(scenario, "bob")
    mountains = scenario.untapped_sources("Mountain", username="bob")
    hand_before = len(scenario.player("alice").hand)

    scenario.cast_onto_stack("Lightning Bolt", mountains[0], username="bob", targets=[bears])
    _resolve_all(scenario)

    assert len(scenario.player("alice").hand) == hand_before + 1


# -- Emberheart Challenger ---------------------------------------------------


def _emberheart_board(**kw):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=kw.get("hand", ["Giant Growth", "Giant Growth"]),
            battlefield=[EMBERHEART, "Forest", "Forest", "Mountain"],
            library=kw.get("library", ["Mountain", "Lightning Bolt", "Forest"]),
        )
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain"], library=["Forest"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_emberheart_can_attack_the_turn_it_enters():
    scenario = (
        Scenario()
        .player("alice", hand=[EMBERHEART], battlefield=["Mountain", "Mountain"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    emberheart = scenario.cast_and_resolve(
        EMBERHEART, *scenario.untapped_sources("Mountain", "Mountain")
    )
    assert has_keyword(emberheart, Keyword.HASTE, scenario.game)

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(emberheart)

    assert emberheart in scenario.attackers()


def test_emberheart_prowess_pumps_on_a_noncreature_spell_and_not_a_creature_spell():
    """CR 702.108a. Opt targets nothing, so valiant stays out of the way."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Opt", "Grizzly Bears"],
            battlefield=[EMBERHEART, "Island", "Forest", "Forest"],
            library=["Forest"] * 4,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    emberheart = scenario.creature(EMBERHEART, "alice")
    assert _pt(scenario, emberheart) == (2, 2)

    scenario.cast_and_resolve("Grizzly Bears", *scenario.untapped_sources("Forest", "Forest"))
    _resolve_all(scenario)
    assert _pt(scenario, emberheart) == (2, 2), "a creature spell does not trigger prowess"

    scenario.cast_onto_stack("Opt", *scenario.untapped_sources("Island"))
    assert _pt(scenario, emberheart) == (2, 2), "the trigger is on the stack, not yet resolved"
    _resolve_all(scenario)
    assert _pt(scenario, emberheart) == (3, 3)


def test_emberheart_valiant_exiles_the_top_card_and_lets_you_play_it():
    scenario = _emberheart_board()
    emberheart = scenario.creature(EMBERHEART, "alice")
    scenario.will_take_the_may(True, username="alice", source=EMBERHEART)

    scenario.cast_onto_stack(
        "Giant Growth", scenario.untapped_sources("Forest")[0], targets=[emberheart]
    )
    _resolve_all(scenario)
    _resolve_all(scenario)

    exiled = [c for c in scenario.game.exile if c.name == "Mountain"]
    assert len(exiled) == 1, "the top card of the library was exiled"
    scenario.play_land("Mountain", from_zone=Zone.EXILE)
    assert exiled[0].zone is Zone.BATTLEFIELD


def test_emberheart_valiant_only_the_first_targeting_each_turn():
    scenario = _emberheart_board()
    emberheart = scenario.creature(EMBERHEART, "alice")

    scenario.cast_onto_stack(
        "Giant Growth", scenario.untapped_sources("Forest")[0], targets=[emberheart]
    )
    _resolve_all(scenario)
    _resolve_all(scenario)
    exiled_after_first = len(scenario.game.exile)
    library_after_first = len(scenario.player("alice").library)

    scenario.cast_onto_stack(
        "Giant Growth", scenario.untapped_sources("Forest")[0], targets=[emberheart]
    )
    _resolve_all(scenario)
    _resolve_all(scenario)

    assert exiled_after_first == 1
    assert len(scenario.game.exile) == 1, "the second targeting this turn exiles nothing"
    assert len(scenario.player("alice").library) == library_after_first


def test_emberheart_valiant_ignores_the_opponents_targeting():
    scenario = _emberheart_board(hand=[])
    emberheart = scenario.creature(EMBERHEART, "alice")
    _to(scenario, "bob")

    scenario.cast_and_resolve(
        "Lightning Bolt",
        *scenario.untapped_sources("Mountain", username="bob"),
        username="bob",
        targets=[emberheart],
    )

    assert scenario.game.exile == []
    assert len(scenario.player("alice").library) == 3


def test_emberheart_valiant_resets_on_the_next_turn():
    scenario = _emberheart_board()
    emberheart = scenario.creature(EMBERHEART, "alice")
    scenario.cast_onto_stack(
        "Giant Growth", scenario.untapped_sources("Forest")[0], targets=[emberheart]
    )
    _resolve_all(scenario)
    assert len(scenario.game.exile) == 1

    for _ in range(2):  # alice's turn ends, bob's turn passes, alice's returns
        scenario.start_at(Step.CLEANUP)
        scenario.turn_based_actions()
        scenario.advance()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    assert scenario.game.active_player.username == "alice"

    scenario.cast_onto_stack(
        "Giant Growth", scenario.untapped_sources("Forest")[0], targets=[emberheart]
    )
    _resolve_all(scenario)

    assert len(scenario.game.exile) == 2, "a new turn, a new first targeting"


# -- Battle Mammoth: the permanent-only sibling of Surrak's condition --------


def _mammoth_board():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Grizzly Bears"],
            battlefield=["Battle Mammoth", "Grizzly Bears", "Forest", "Forest"],
            library=["Forest"] * 4,
        )
        .player(
            "bob",
            hand=["Lightning Bolt", "Counterspell"],
            battlefield=["Mountain", "Island", "Island"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_battle_mammoth_draws_when_an_opponent_targets_a_permanent_you_control():
    """Generality proof for the object-subject reader on a second printing:
    'a permanent you control becomes the target of a spell or ability an
    opponent controls' - one subject, no 'or' alternative."""
    scenario = _mammoth_board()
    scenario.will_take_the_may(True, username="alice", source="Battle Mammoth")
    bears = scenario.creature("Grizzly Bears", "alice")
    hand_before = len(scenario.player("alice").hand)
    _to(scenario, "bob")

    scenario.cast_onto_stack(
        "Lightning Bolt",
        *scenario.untapped_sources("Mountain", username="bob"),
        username="bob",
        targets=[bears],
    )
    _resolve_all(scenario)

    assert len(scenario.player("alice").hand) == hand_before + 1


def test_battle_mammoth_does_not_see_a_creature_spell_as_a_permanent():
    """A spell on the stack is not a permanent (CR 110.1), so countering
    alice's creature spell does not trigger a permanent-only condition even
    though the same targeting event does trigger Surrak's 'creature spell'."""
    scenario = _mammoth_board()
    scenario.cast_onto_stack("Grizzly Bears", *scenario.untapped_sources("Forest", "Forest"))
    bears_spell = scenario.find("Grizzly Bears", Zone.STACK)
    hand_before = len(scenario.player("alice").hand)
    _to(scenario, "bob")

    scenario.cast_onto_stack(
        "Counterspell",
        *scenario.untapped_sources("Island", "Island", username="bob"),
        username="bob",
        targets=[bears_spell],
    )
    _resolve_all(scenario)

    assert len(scenario.player("alice").hand) == hand_before
