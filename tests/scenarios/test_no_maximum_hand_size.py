"""Scenario: "you have no maximum hand size", from three different sources.

- **Sea Gate Restoration** (a spell): "Draw cards equal to the number of
  cards in your hand plus one. You have no maximum hand size for the rest of
  the game." A one-shot effect with an unbounded duration, recorded on the
  player it names.
- **Reliquary Tower** (off-pool proof printing, a land): "You have no maximum
  hand size." A static ability of a permanent, which applies only while that
  permanent is on the battlefield under that player's control (CR 604.2).
- Tamiyo, Seasoned Scholar's emblem is the third source, proved in
  `test_half_library_counts.py` beside the -7 that grants it.

Every CR number below was read with `mise run rules:find` in the session
that wrote this file:

- **CR 402.2** - "Each player has a maximum hand size, which is normally
  seven cards. A player may have any number of cards in their hand, but as
  part of their cleanup step, the player must discard excess cards down to
  the maximum hand size."
- **CR 514.1** - "if the active player's hand contains more cards than their
  maximum hand size (normally seven), they discard enough cards to reduce
  their hand size to that number."
- **CR 613.11** - "Some continuous effects affect game rules rather than
  objects. For example, effects may modify a player's maximum hand size".
- **CR 604.2** - a static ability's effect applies only while its object is
  on the battlefield (for a permanent).
- **CR 608.2h** - the hand is counted when the effect applies.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Game, Zone
from tests.scenarios.harness import Scenario

SEA_GATE = "Sea Gate Restoration"


def _advance_to(scenario, username: str, step: Step) -> None:
    for _ in range(200):
        if scenario.turn.active_player == username and scenario.step is step:
            return
        scenario.advance()
    raise AssertionError(f"never reached {username}'s {step}")


def _sea_gate(
    *, hand: list[str], library: int = 20, bobs_hand: list[str] | None = None, automatic=False
):
    builder = Scenario()
    if automatic:
        builder = builder.automatic_turn_based_actions()
    scenario = (
        builder.player(
            "alice",
            hand=[SEA_GATE, *hand],
            battlefield=["Island"] * 7,
            library=["Island"] * library,
        )
        .player("bob", hand=bobs_hand or [], library=["Forest"] * 20)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _cast_sea_gate(scenario) -> None:
    islands = scenario.untapped_sources(*["Island"] * 7, username="alice")
    scenario.cast_onto_stack(SEA_GATE, *islands)


# -- the draw: the number of cards in your hand plus one --------------------


def test_sea_gate_draws_one_more_than_the_cards_left_in_hand():
    """Three other cards in hand once Sea Gate Restoration is on the stack:
    three plus one is four."""
    scenario = _sea_gate(hand=["Mountain"] * 3)
    alice = scenario.player("alice")

    _cast_sea_gate(scenario)
    scenario.resolve_top()

    assert len(alice.hand) == 3 + 4
    assert len(alice.library) == 16


def test_sea_gate_with_an_empty_hand_draws_one():
    """The spell itself is on the stack, not in hand: zero plus one."""
    scenario = _sea_gate(hand=[])
    alice = scenario.player("alice")

    _cast_sea_gate(scenario)
    scenario.resolve_top()

    assert len(alice.hand) == 1


def test_sea_gate_counts_the_hand_as_it_resolves():
    """CR 608.2h: two cards drawn in response make the hand five, so it
    draws six."""
    scenario = _sea_gate(hand=["Mountain"] * 3)
    alice = scenario.player("alice")

    _cast_sea_gate(scenario)
    scenario.game.draw_cards("alice", 2)
    scenario.resolve_top()

    assert len(alice.hand) == 5 + 6


def test_sea_gate_draws_what_is_left_of_a_short_library():
    """Four to draw from a two-card library: both are drawn and the failed
    draw is recorded for CR 704.5b."""
    scenario = _sea_gate(hand=["Mountain"] * 3, library=2)
    alice = scenario.player("alice")

    _cast_sea_gate(scenario)
    scenario.resolve_top()

    assert len(alice.hand) == 5
    assert alice.library == []
    assert alice.tried_to_draw_from_empty_library


# -- "for the rest of the game" ---------------------------------------------


def test_sea_gate_removes_the_casters_maximum_hand_size():
    scenario = _sea_gate(hand=["Mountain"] * 6)
    alice = scenario.player("alice")
    assert not alice.has_no_maximum_hand_size

    _cast_sea_gate(scenario)
    scenario.resolve_top()

    assert alice.has_no_maximum_hand_size
    assert len(alice.hand) == 13
    assert alice.cards_over_maximum_hand_size == 0


def test_after_sea_gate_the_cleanup_step_discards_nothing_this_turn_or_next():
    """CR 514.1 finds no maximum to discard down to - in this cleanup step,
    and in alice's next one a full turn cycle later."""
    scenario = _sea_gate(hand=["Mountain"] * 6, automatic=True)
    alice = scenario.player("alice")
    _cast_sea_gate(scenario)
    scenario.resolve_top()

    _advance_to(scenario, "alice", Step.CLEANUP)
    assert len(alice.hand) == 13
    assert alice.graveyard == [scenario.find(SEA_GATE, Zone.GRAVEYARD, "alice")]

    _advance_to(scenario, "bob", Step.CLEANUP)
    _advance_to(scenario, "alice", Step.CLEANUP)
    assert len(alice.hand) == 14  # plus her next draw step
    assert [state.name for state in alice.graveyard] == [SEA_GATE]


def test_sea_gate_leaves_the_opponents_maximum_hand_size_alone():
    """ "You have no maximum hand size" is the caster's; bob still discards
    down to seven in his own cleanup step."""
    scenario = _sea_gate(hand=[], bobs_hand=["Forest"] * 8, automatic=True)
    _cast_sea_gate(scenario)
    scenario.resolve_top()
    bob = scenario.player("bob")

    _advance_to(scenario, "bob", Step.CLEANUP)

    assert not bob.has_no_maximum_hand_size
    assert len(bob.hand) == 7
    assert len(bob.graveyard) == 2  # eight, plus his draw, down to seven


def test_the_rest_of_the_game_effect_survives_a_save_and_reload():
    """The effect is game state, not something re-derived from a card that
    is long gone: a decoded game still knows alice has no maximum."""
    scenario = _sea_gate(hand=["Mountain"] * 6)
    _cast_sea_gate(scenario)
    scenario.resolve_top()

    decoded = Game.model_validate(scenario.game.model_dump(mode="json"))

    assert decoded.player("alice").has_no_maximum_hand_size
    assert not decoded.player("bob").has_no_maximum_hand_size


# -- Reliquary Tower: the static ability (off-pool proof) ------------------


def _tower(*, alices_battlefield: list[str], bobs_battlefield: list[str] = ()):
    scenario = (
        Scenario()
        .automatic_turn_based_actions()
        .player(
            "alice",
            hand=["Mountain"] * 9,
            battlefield=alices_battlefield,
            library=["Island"] * 20,
        )
        .player(
            "bob",
            hand=["Forest"] * 9,
            battlefield=list(bobs_battlefield),
            library=["Forest"] * 20,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_reliquary_tower_keeps_its_controllers_whole_hand_through_cleanup():
    scenario = _tower(alices_battlefield=["Reliquary Tower"])
    alice = scenario.player("alice")

    assert alice.has_no_maximum_hand_size
    _advance_to(scenario, "alice", Step.CLEANUP)

    assert len(alice.hand) == 9
    assert alice.graveyard == []


def test_reliquary_tower_does_nothing_for_the_player_who_does_not_control_it():
    """Bob controls the Tower; alice still discards down to seven."""
    scenario = _tower(alices_battlefield=[], bobs_battlefield=["Reliquary Tower"])
    alice = scenario.player("alice")

    assert not alice.has_no_maximum_hand_size
    assert scenario.player("bob").has_no_maximum_hand_size
    _advance_to(scenario, "alice", Step.CLEANUP)

    assert len(alice.hand) == 7
    assert len(alice.graveyard) == 2


def test_reliquary_tower_stops_applying_once_it_leaves_the_battlefield():
    """CR 604.2: the static ability applies only while the Tower is on the
    battlefield. Sacrificed before cleanup, it keeps nothing."""
    scenario = _tower(alices_battlefield=["Reliquary Tower"])
    alice = scenario.player("alice")
    tower = scenario.find("Reliquary Tower", Zone.BATTLEFIELD, "alice")

    scenario.game.sacrifice(tower)
    assert not alice.has_no_maximum_hand_size
    _advance_to(scenario, "alice", Step.CLEANUP)

    assert len(alice.hand) == 7
    assert sorted(state.name for state in alice.graveyard) == [
        "Mountain",
        "Mountain",
        "Reliquary Tower",
    ]


def test_reliquary_tower_that_lost_its_abilities_keeps_nothing():
    """CR 613.1f: a land that lost all abilities has no static ability left
    to apply. Blood Moon makes the Tower a Mountain with only "{T}: Add {R}"
    (CR 305.7), so its controller is back to a maximum of seven."""
    scenario = _tower(alices_battlefield=["Reliquary Tower"], bobs_battlefield=["Blood Moon"])
    alice = scenario.player("alice")

    assert not alice.has_no_maximum_hand_size
    _advance_to(scenario, "alice", Step.CLEANUP)

    assert len(alice.hand) == 7
