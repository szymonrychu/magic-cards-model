"""The trigger's event player and event subject as the actor of a rider (NW-06, T3).

- Fevered Visions: "that player draws a card. If the player is your opponent and
  has four or more cards in hand, this enchantment deals 2 damage to that
  player." - the hand is read after the draw (CR 608.2c: in the order written).
- Relic Robber / Bloodvial Purveyor: "that player creates <token>" - the
  damaged (or spell-casting) player is the token's owner and controller
  (CR 111.2), not the ability's controller; the token's own quoted "you" is that
  player's too.
- Quicksmith Rebel / Quicksmith Spy: a quoted ability granted "for as long as you
  control this creature" (CR 611.2b), so it ends when the source leaves.
- The Emperor of Palamecia / Thing in the Ice: "put (remove) a counter. Then if it
  has N or more (no) counters on it, transform it." - checked as the ability
  resolves, and only a double-faced permanent transforms (CR 701.27a, 701.27c).
- Anthem of Rakdos: "it gets +2/+0 until end of turn and this enchantment deals 1
  damage to you." - the pump of the event subject plus the source's own damage.

CR numbers checked with `mise run rules:find` (rules effective 2026-09-25).
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.abilities import TriggerEvent
from magic_cards_model.machines.effects import transform_permanent
from magic_cards_model.machines.effects.registries import trigger_effect_for
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from magic_cards_model.models.token import PREDEFINED, create_tokens
from magic_cards_model.support import card_support
from tests.cards import card

from .harness import Scenario

LANDS = ["Island"] * 4


def _drain(scenario) -> None:
    scenario.game.put_triggers_on_stack()
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()


def _notices(scenario) -> list[object]:
    game = scenario.game
    found: list[object] = list(game.continuous_effects.layer_notices)
    for name in type(game).model_fields:
        if name.endswith("_notices"):
            found.extend(getattr(game, name))
    return found


def _outcomes(name: str) -> list[str]:
    return [c.outcome for c in card_support(card(name)).clauses if c.kind != "keyword"]


def _walk_to(scenario, step: Step) -> None:
    while scenario.step is not step:
        scenario.advance()
        _drain(scenario)


def _tokens(scenario, username, name_fragment="") -> list:
    return [
        p
        for p in scenario.game.battlefield
        if p.token and p.controller == username and name_fragment in p.name
    ]


def test_every_listed_and_proof_card_reads_handled():
    for name in (
        "Fevered Visions",
        "Relic Robber",
        "Quicksmith Rebel",
        "Quicksmith Spy",
        "Bloodvial Purveyor",
        "Thing in the Ice // Awoken Horror",
    ):
        assert set(_outcomes(name)) == {"handled"}, name
    # The Emperor's back face (Starfall) is T2's clause; its front one is this task's.
    assert _outcomes("The Emperor of Palamecia // The Lord Master of Hell")[0] == "handled"


# -- Fevered Visions ------------------------------------------------------------


def _visions(bob_hand, *, alice_hand=(), active="bob"):
    """`active`'s end step, Fevered Visions on alice's side."""
    builders = {
        "alice": dict(
            battlefield=["Fevered Visions"], hand=list(alice_hand), library=["Plains"] * 6
        ),
        "bob": dict(hand=list(bob_hand), library=["Mountain"] * 6),
    }
    scenario = Scenario()
    order = [active] + [name for name in ("alice", "bob") if name != active]
    for name in order:
        scenario = scenario.player(name, **builders[name])
    built = scenario.build()
    _walk_to(built, Step.END_STEP)
    return built


def test_an_opponent_with_four_cards_after_the_draw_takes_two():
    scenario = _visions(["Shock"] * 3)
    assert len(scenario.player("bob").hand) == 4
    assert scenario.player("bob").life == 18
    assert _notices(scenario) == []


def test_the_hand_is_counted_after_the_draw_not_before():
    """Three cards before the draw is four after it: that is the qualifying size."""
    scenario = _visions(["Shock"] * 3)
    assert scenario.player("bob").life == 18


def test_an_opponent_who_stays_under_four_takes_nothing_but_still_draws():
    scenario = _visions(["Shock"] * 2)
    assert len(scenario.player("bob").hand) == 3
    assert scenario.player("bob").life == 20


def test_a_bigger_hand_is_hit_as_well():
    scenario = _visions(["Shock"] * 5)
    assert len(scenario.player("bob").hand) == 6
    assert scenario.player("bob").life == 18


def test_the_controller_s_own_end_step_draws_but_never_damages_them():
    scenario = _visions(["Shock"], alice_hand=["Shock"] * 6, active="alice")
    assert len(scenario.player("alice").hand) == 7
    assert scenario.player("alice").life == 20
    assert scenario.player("bob").life == 20


def test_only_the_player_whose_end_step_it_is_draws():
    scenario = _visions(["Shock"] * 3, alice_hand=["Shock"] * 2)
    assert len(scenario.player("alice").hand) == 2


def test_the_rider_never_drops_a_condition_it_does_not_read():
    effect = trigger_effect_for(
        "Some Card",
        TriggerEvent.BEGINNING_OF_STEP,
        "that player draws a card. If the player is your opponent and has four or more cards in "
        "hand, this enchantment deals 2 damage to that player unless the moon is full.",
    )
    assert effect is None or effect.__name__.endswith("notice_only")


# -- "that player creates" (Relic Robber, Bloodvial Purveyor) ------------------------


def _robber_hits(bob_battlefield=()):
    scenario = (
        Scenario()
        .player("alice", battlefield=["Relic Robber"], library=["Mountain"] * 5)
        .player("bob", battlefield=list(bob_battlefield), library=["Mountain"] * 5)
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(scenario.creature("Relic Robber", "alice"))
    scenario.advance()  # declare blockers
    scenario.no_blocks()
    _walk_to(scenario, Step.END_OF_COMBAT)
    return scenario


def test_the_damaged_player_creates_and_controls_the_goblin_construct():
    scenario = _robber_hits()
    (token,) = _tokens(scenario, "bob")
    assert token.name == "Goblin Construct Token" or "Goblin Construct" in token.name
    assert _tokens(scenario, "alice") == []
    assert scenario.game.power_of(token) == 0 and scenario.game.toughness_of(token) == 1
    assert scenario.player("bob").life == 18  # Relic Robber is a 2/2
    assert _notices(scenario) == []


def test_the_construct_deals_one_to_its_own_controller_at_their_upkeep():
    scenario = _robber_hits()
    assert len(_tokens(scenario, "bob")) == 1
    _walk_to(scenario, Step.UPKEEP)
    assert scenario.turn.active_player == "bob"
    assert scenario.player("bob").life == 17
    assert scenario.player("alice").life == 20


def test_the_construct_cannot_block():
    scenario = _robber_hits()
    (token,) = _tokens(scenario, "bob")
    while not (scenario.step is Step.DECLARE_ATTACKERS and scenario.turn.active_player == "alice"):
        scenario.advance()
        _drain(scenario)
    robber = scenario.creature("Relic Robber", "alice")
    scenario.attack_with(robber)
    scenario.advance()  # declare blockers
    with pytest.raises(ValueError, match="can't block"):
        scenario.block(robber, token)


def _bloodvial_board(*, bob_hand=("Shock",), alice_hand=("Shock",)):
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Bloodvial Purveyor", "Mountain"],
            hand=list(alice_hand),
        )
        .player("bob", battlefield=["Mountain"], hand=list(bob_hand))
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_an_opponent_casting_a_spell_creates_a_blood_token_for_themselves():
    scenario = _bloodvial_board()
    scenario.pass_priority("alice")
    scenario.cast_onto_stack("Shock", username="bob", targets=["alice"], auto=True)
    _drain(scenario)
    blood = _tokens(scenario, "bob", "Blood")
    assert len(blood) == 1
    assert _tokens(scenario, "alice", "Blood") == []
    assert _notices(scenario) == []


def test_the_controller_casting_a_spell_makes_no_blood():
    scenario = _bloodvial_board()
    scenario.cast_onto_stack("Shock", username="alice", targets=["bob"], auto=True)
    _drain(scenario)
    assert _tokens(scenario, "alice", "Blood") == []
    assert _tokens(scenario, "bob", "Blood") == []


def test_blood_creation_does_not_drop_a_trailing_condition():
    effect = trigger_effect_for(
        "Some Card",
        TriggerEvent.CAST_SPELL,
        "that player creates a Blood token if you control a Vampire.",
    )
    assert effect is None or effect.__name__.endswith("notice_only")


def _attack_with_bloodvial(blood_for_bob, blood_for_alice=0):
    scenario = (
        Scenario()
        .player("alice", battlefield=["Bloodvial Purveyor"])
        .player("bob", battlefield=["Mountain"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    if blood_for_bob:
        create_tokens(scenario.game, PREDEFINED["Blood"], "bob", blood_for_bob)
    if blood_for_alice:
        create_tokens(scenario.game, PREDEFINED["Blood"], "alice", blood_for_alice)
    purveyor = scenario.creature("Bloodvial Purveyor", "alice")
    scenario.attack_with(purveyor)
    _drain(scenario)
    return scenario, purveyor


def test_bloodvial_attack_pump_counts_the_defending_players_blood_tokens():
    scenario, purveyor = _attack_with_bloodvial(2, blood_for_alice=3)
    assert scenario.game.power_of(purveyor) == 5 + 2  # printed 5, +1 per Blood bob controls
    assert _notices(scenario) == []


def test_bloodvial_attack_pump_with_no_blood_is_no_pump():
    scenario, purveyor = _attack_with_bloodvial(0, blood_for_alice=3)
    assert scenario.game.power_of(purveyor) == 5


# -- Quicksmith Rebel / Quicksmith Spy ------------------------------------------------


def _quick_board(creature, hand_extra=()):
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Mind Stone", "Island", "Island", "Island", "Island", "Mountain"],
            hand=[creature, *hand_extra],
            library=["Plains"] * 5,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _granted_index(scenario, stone, fragment):
    scenario.game.characteristics_of(stone)  # the board sweep that syncs granted text
    for index, ability in enumerate(scenario.game.activated_abilities(stone)):
        if fragment in ability.effect:
            return index
    return None


def _enter(scenario, creature, stone):
    colour = "Mountain" if creature == "Quicksmith Rebel" else "Island"
    lands = scenario.untapped_sources(colour, "Island", "Island", "Island", username="alice")
    scenario.cast_onto_stack(creature, *lands[:4], username="alice")
    scenario.resolve_top()  # the creature spell
    scenario.choose_trigger_targets(creature, [stone])
    scenario.resolve_top()  # the enters trigger


def test_the_rebel_gives_the_artifact_a_tap_ability_that_deals_two():
    scenario = _quick_board("Quicksmith Rebel")
    stone = scenario.find("Mind Stone", Zone.BATTLEFIELD, "alice")
    assert _granted_index(scenario, stone, "deals 2 damage") is None
    _enter(scenario, "Quicksmith Rebel", stone)
    index = _granted_index(scenario, stone, "deals 2 damage")
    assert index is not None
    scenario.activate(stone, index=index, targets=["bob"])
    scenario.resolve_top()
    assert scenario.player("bob").life == 18
    assert stone.tapped
    assert _notices(scenario) == []


def test_the_grant_ends_when_the_rebel_leaves_the_battlefield():
    scenario = _quick_board("Quicksmith Rebel")
    stone = scenario.find("Mind Stone", Zone.BATTLEFIELD, "alice")
    _enter(scenario, "Quicksmith Rebel", stone)
    assert _granted_index(scenario, stone, "deals 2 damage") is not None
    scenario.game.sacrifice(scenario.creature("Quicksmith Rebel", "alice"))
    assert _granted_index(scenario, stone, "deals 2 damage") is None


def test_the_grant_survives_end_of_turn_while_the_rebel_stays():
    scenario = _quick_board("Quicksmith Rebel")
    stone = scenario.find("Mind Stone", Zone.BATTLEFIELD, "alice")
    _enter(scenario, "Quicksmith Rebel", stone)
    scenario.advance()
    _walk_to(scenario, Step.UPKEEP)  # the next turn, bob's
    assert _granted_index(scenario, stone, "deals 2 damage") is not None


def test_a_rebel_that_left_before_its_trigger_resolved_grants_nothing():
    """CR 611.2b: a "for as long as" duration that never starts does nothing."""
    scenario = _quick_board("Quicksmith Rebel")
    stone = scenario.find("Mind Stone", Zone.BATTLEFIELD, "alice")
    lands = scenario.untapped_sources("Mountain", "Island", "Island", "Island", username="alice")
    scenario.cast_onto_stack("Quicksmith Rebel", *lands, username="alice")
    scenario.resolve_top()
    scenario.choose_trigger_targets("Quicksmith Rebel", [stone])
    scenario.game.sacrifice(scenario.creature("Quicksmith Rebel", "alice"))
    scenario.resolve_top()
    assert _granted_index(scenario, stone, "deals 2 damage") is None


def test_the_spy_grants_a_draw_for_as_long_as_it_is_controlled():
    scenario = _quick_board("Quicksmith Spy")
    stone = scenario.find("Mind Stone", Zone.BATTLEFIELD, "alice")
    _enter(scenario, "Quicksmith Spy", stone)
    index = _granted_index(scenario, stone, "Draw a card")
    # Mind Stone prints its own sacrifice-to-draw ability; the granted one is the {T} one.
    granted = [
        i
        for i, ability in enumerate(scenario.game.activated_abilities(stone))
        if ability.cost.strip() == "{T}" and "Draw a card" in ability.effect
    ]
    assert index is not None and granted
    hand_before = len(scenario.player("alice").hand)
    scenario.activate(stone, index=granted[0])
    scenario.resolve_top()
    assert len(scenario.player("alice").hand) == hand_before + 1
    scenario.game.sacrifice(scenario.creature("Quicksmith Spy", "alice"))
    assert not [
        a
        for a in scenario.game.activated_abilities(stone)
        if a.cost.strip() == "{T}" and "Draw a card" in a.effect
    ]


def test_a_trailing_duration_it_does_not_read_is_refused():
    effect = trigger_effect_for(
        "Some Card",
        TriggerEvent.ENTERS_THE_BATTLEFIELD,
        'target artifact you control gains "{T}: Draw a card" for as long as the moon is full.',
    )
    assert effect is None or effect.__name__.endswith("notice_only")


# -- The Emperor of Palamecia / Thing in the Ice ---------------------------------------


def _emperor_board(counters):
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["The Emperor of Palamecia", *LANDS],
            hand=["Mnemonic Nexus", "Divination", "Shock"],
            library=["Plains"] * 5,
        )
        .player("bob", library=["Plains"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    emperor = scenario.find("The Emperor of Palamecia", Zone.BATTLEFIELD, "alice")
    if counters:
        scenario.game.add_counters(emperor, Counter.PLUS_ONE, counters)
    return scenario, emperor


def test_a_four_mana_noncreature_spell_adds_a_counter_and_the_third_transforms():
    scenario, emperor = _emperor_board(2)
    scenario.cast_onto_stack("Mnemonic Nexus", auto=True)
    scenario.game.put_triggers_on_stack()
    _drain(scenario)
    assert emperor.counter_count(Counter.PLUS_ONE) == 3
    assert emperor.up_face_name == "The Lord Master of Hell"
    assert _notices(scenario) == []


def test_under_the_threshold_it_only_gains_the_counter():
    scenario, emperor = _emperor_board(0)
    scenario.cast_onto_stack("Mnemonic Nexus", auto=True)
    _drain(scenario)
    assert emperor.counter_count(Counter.PLUS_ONE) == 1
    assert emperor.up_face_name == "The Emperor of Palamecia"


def test_a_cheaper_spell_does_not_trigger_the_counter_at_all():
    """The intervening "if" reads the mana spent to cast it (CR 603.4)."""
    scenario, emperor = _emperor_board(2)
    scenario.cast_onto_stack("Divination", auto=True)
    _drain(scenario)
    assert emperor.counter_count(Counter.PLUS_ONE) == 2
    assert emperor.up_face_name == "The Emperor of Palamecia"


def test_the_threshold_is_checked_at_resolution_a_fourth_counter_still_transforms_once():
    scenario, emperor = _emperor_board(3)
    scenario.cast_onto_stack("Mnemonic Nexus", auto=True)
    _drain(scenario)
    assert emperor.counter_count(Counter.PLUS_ONE) == 4
    assert emperor.up_face_name == "The Lord Master of Hell"


def test_transform_only_changes_a_double_faced_permanent():
    """CR 701.27c: asked to transform a single-faced permanent, nothing happens."""
    scenario = Scenario().player("alice", battlefield=["Grizzly Bears"]).player("bob").build()
    bears = scenario.creature("Grizzly Bears", "alice")
    before = bears.up_face_name
    transform_permanent(scenario.game, bears)
    assert bears.up_face_name == before


def _thing_board(counters):
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Thing in the Ice", "Island", "Island", "Island"],
            hand=["Divination"],
            library=["Island"] * 5,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    thing = scenario.find("Thing in the Ice", Zone.BATTLEFIELD, "alice")
    scenario.game.add_counters(thing, "ice", counters - thing.counter_count("ice"))
    return scenario, thing


def test_thing_in_the_ice_removes_a_counter_and_transforms_at_none():
    scenario, thing = _thing_board(1)
    scenario.cast_onto_stack("Divination", auto=True)
    _drain(scenario)
    assert thing.counter_count("ice") == 0
    assert thing.up_face_name == "Awoken Horror"


def test_thing_in_the_ice_keeps_counting_down_without_transforming_early():
    scenario, thing = _thing_board(3)
    scenario.cast_onto_stack("Divination", auto=True)
    _drain(scenario)
    assert thing.counter_count("ice") == 2
    assert thing.up_face_name == "Thing in the Ice"


# -- Anthem of Rakdos' compound (cross-task clause) ------------------------------------


def test_anthem_of_rakdos_pump_plus_self_damage_reads_on_attack():
    effect = trigger_effect_for(
        "Some Card",
        TriggerEvent.ATTACKS,
        "it gets +2/+0 until end of turn and this enchantment deals 1 damage to you.",
    )
    assert effect is not None and not effect.__name__.endswith("notice_only")


@pytest.mark.parametrize(
    "text",
    [
        "it gets +2/+0 until end of turn and this enchantment deals 1 damage to you "
        "unless you control a Demon.",
        "it gets +2/+0 until end of turn and target creature deals 1 damage to you.",
    ],
)
def test_the_compound_never_drops_a_condition_or_guesses_a_dealer(text):
    effect = trigger_effect_for("Some Card", TriggerEvent.ATTACKS, text)
    assert effect is None or effect.__name__.endswith("notice_only")
