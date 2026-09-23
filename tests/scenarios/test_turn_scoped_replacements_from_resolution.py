"""Replacement effects a resolving spell or ability leaves behind for the
rest of the turn: "Until end of turn, if `<event>` would happen, `<something
else>` instead."

CR 614.1a: "Effects that use the word 'instead' are replacement effects."
CR 614.6: "If an event is replaced, it never happens. A modified event occurs
instead, which may in turn trigger abilities." CR 614.5: "A replacement
effect doesn't invoke itself repeatedly; it gets only one opportunity to
affect an event or any modified events that may replace that event." CR 616.1:
the affected object's controller or the affected player orders several of
them. CR 611.2a: a continuous effect from a resolved spell or ability lasts as
long as it says - independent of the object that made it. CR 514.2 ends
"until end of turn" effects in the cleanup step.

The created effect is stored on `Game.created_replacements` as data (a
`kind`-tagged record, no callable) and read by the same shape readers the
printed static forms go through - so the proof printings are the static
twins: Notion Thief ("If an opponent would draw a card except the first one
they draw in each of their draw steps, instead that player skips that draw
and you draw a card.") for Plagiarize's draw redirection, and Hardened Scales
("... that many plus one +1/+1 counters are put on it instead.") for Prairie
Dog's. No other legal printing creates either effect at resolution.

Every CR number here was read with `mise run rules:find` in the session that
wrote this file.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import CardState, Counter
from magic_cards_model.models.game import Game
from tests.scenarios.harness import Scenario


def _to_next_turn(scenario) -> None:
    active = scenario.turn.active_player
    while scenario.turn.active_player == active:
        scenario.advance()


def _hand_names(scenario, username: str) -> list[str]:
    return [state.name for state in scenario.player(username).hand]


# --------------------------------------------------------------------------
# Plagiarize - "Until end of turn, if target player would draw a card,
# instead that player skips that draw and you draw a card."
# --------------------------------------------------------------------------


def _plagiarize_board(*, bob_library: tuple[str, ...] = ("Swamp",) * 5) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=["Plagiarize"],
            battlefield=["Island"] * 4,
            library=["Forest"] * 6,
        )
        .player("bob", hand=["Plagiarize"], battlefield=["Island"] * 4, library=list(bob_library))
    )


def _cast_plagiarize(scenario, target: str, username: str = "alice") -> None:
    scenario.cast_and_resolve("Plagiarize", username=username, targets=[target], auto=True)


def test_plagiarize_takes_every_draw_the_target_would_make():
    scenario = _plagiarize_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    _cast_plagiarize(scenario, "bob")
    scenario.draw(2, "bob")

    assert _hand_names(scenario, "alice") == ["Forest", "Forest"], "drawn from alice's own library"
    assert _hand_names(scenario, "bob") == ["Plagiarize"]
    assert len(scenario.player("bob").library) == 5


def test_plagiarize_leaves_its_casters_own_draws_alone():
    scenario = _plagiarize_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    _cast_plagiarize(scenario, "bob")
    scenario.draw(1, "alice")

    assert _hand_names(scenario, "alice") == ["Forest"]
    assert len(scenario.player("bob").library) == 5


def test_plagiarize_ends_with_the_turn():
    """CR 514.2: bob's own draw step next turn is his again."""
    scenario = _plagiarize_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    _cast_plagiarize(scenario, "bob")
    _to_next_turn(scenario)
    while scenario.step is not Step.PRECOMBAT_MAIN:
        scenario.advance()

    assert scenario.game.created_replacements == []
    assert "Swamp" in _hand_names(scenario, "bob")
    assert "Forest" not in _hand_names(scenario, "alice")


def test_plagiarize_on_yourself_draws_you_a_card_and_does_not_loop():
    """Ruling 2004-10-04: no useful effect, no infinite loop - CR 614.5: the
    draw it gives you is the modified event, which it cannot affect again."""
    scenario = _plagiarize_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    _cast_plagiarize(scenario, "alice")
    scenario.draw(1, "alice")

    assert _hand_names(scenario, "alice") == ["Forest"]


def test_two_plagiarizes_on_each_other_cancel_out():
    """Ruling 2007-07-15: each draws when they normally would. bob's draw
    becomes alice's (alice's effect), and that modified draw becomes bob's
    again (bob's effect); each effect has had its one chance (CR 614.5)."""
    scenario = _plagiarize_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    _cast_plagiarize(scenario, "bob")
    scenario.pass_priority()
    _cast_plagiarize(scenario, "alice", username="bob")
    scenario.draw(1, "bob")
    scenario.draw(1, "alice")

    assert _hand_names(scenario, "bob") == ["Swamp"]
    assert _hand_names(scenario, "alice") == ["Forest"]


def test_plagiarize_still_takes_a_draw_from_an_empty_library():
    """Ruling 2007-07-15: the target's empty library does not matter - CR
    121.6a applies the replacement even when no card could be drawn."""
    scenario = _plagiarize_board(bob_library=()).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    _cast_plagiarize(scenario, "bob")
    scenario.draw(1, "bob")
    scenario.game.check_state_based_actions()

    assert _hand_names(scenario, "alice") == ["Forest"]
    assert scenario.player("bob").life > 0 and scenario.game.is_in_game("bob")


def test_plagiarize_is_a_serialisable_record_that_still_applies_after_decode():
    scenario = _plagiarize_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _cast_plagiarize(scenario, "bob")

    dumped = scenario.game.model_dump(mode="json")
    (record,) = dumped["created_replacements"]
    assert record["spec"]["kind"] == "draw_skip"

    decoded = Game.model_validate(dumped)
    decoded.draw_cards("bob", 1)
    assert [state.name for state in decoded.player("alice").hand] == ["Forest"]


# --------------------------------------------------------------------------
# Notion Thief (proof printing, the static twin) - "If an opponent would draw
# a card except the first one they draw in each of their draw steps, instead
# that player skips that draw and you draw a card."
# --------------------------------------------------------------------------


def test_notion_thief_takes_an_opponents_extra_draw():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Notion Thief"], library=["Forest"] * 3)
        .player("bob", library=["Swamp"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.draw(2, "bob")

    assert _hand_names(scenario, "alice") == ["Forest", "Forest"]
    assert _hand_names(scenario, "bob") == []


def test_notion_thief_leaves_the_first_draw_step_draw_and_its_controllers_draws():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Notion Thief"], library=["Forest"] * 3)
        .player("bob", library=["Swamp"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.draw(1, "alice")
    assert _hand_names(scenario, "alice") == ["Forest"]

    _to_next_turn(scenario)
    while scenario.step is not Step.DRAW:
        scenario.advance()
    assert _hand_names(scenario, "bob") == ["Swamp"], "the draw step's own first draw"
    scenario.draw(1, "bob")

    assert _hand_names(scenario, "bob") == ["Swamp"]
    assert _hand_names(scenario, "alice") == ["Forest", "Forest"]


# --------------------------------------------------------------------------
# Prairie Dog - "{4}{W}: Until end of turn, if you would put one or more
# +1/+1 counters on a creature you control, put that many plus one +1/+1
# counters on it instead."
# --------------------------------------------------------------------------


def _prairie_board(*alice: str, bob: tuple[str, ...] = ()) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            battlefield=["Prairie Dog", "Grizzly Bears", *(["Plains"] * 10), *alice],
            hand=["Kalonian Hydra"],
        )
        .player("bob", battlefield=list(bob))
    )


def _activate_prairie_dog(scenario) -> None:
    dog = scenario.creature("Prairie Dog")
    scenario.activate(dog, *scenario.untapped_sources(*["Plains"] * 5), index=0)
    scenario.pass_until_resolved()


def test_prairie_dog_adds_one_to_counters_put_on_your_creature():
    scenario = _prairie_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _activate_prairie_dog(scenario)
    bears = scenario.creature("Grizzly Bears")

    scenario.game.add_counters(bears, Counter.PLUS_ONE, 1)

    assert bears.counter_count(Counter.PLUS_ONE) == 2


def test_two_activations_add_two():
    """Ruling 2024-04-12: resolved twice, two plus the original number."""
    scenario = _prairie_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _activate_prairie_dog(scenario)
    _activate_prairie_dog(scenario)
    bears = scenario.creature("Grizzly Bears")

    scenario.game.add_counters(bears, Counter.PLUS_ONE, 1)

    assert bears.counter_count(Counter.PLUS_ONE) == 3


def test_prairie_dog_reaches_counters_a_creature_enters_with():
    """Ruling 2024-04-12 / CR 122.6: Kalonian Hydra's four become five."""
    scenario = _prairie_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _activate_prairie_dog(scenario)

    hydra = scenario.put_onto_battlefield("Kalonian Hydra")

    assert hydra.counter_count(Counter.PLUS_ONE) == 5


def test_prairie_dog_leaves_an_opponents_creature_and_other_counters_alone():
    scenario = _prairie_board(bob=("Grizzly Bears",)).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _activate_prairie_dog(scenario)
    bobs_bears = scenario.creature("Grizzly Bears", "bob")
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.game.add_counters(bobs_bears, Counter.PLUS_ONE, 1)
    scenario.game.add_counters(bears, Counter.MINUS_ONE, 1)

    assert bobs_bears.counter_count(Counter.PLUS_ONE) == 1
    assert bears.counter_count(Counter.MINUS_ONE) == 1


def test_prairie_dog_stacks_with_hardened_scales():
    """CR 616.1: two effects modify one event, each applies once - one
    counter becomes three whichever alice applies first."""
    scenario = _prairie_board("Hardened Scales").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _activate_prairie_dog(scenario)
    bears = scenario.creature("Grizzly Bears")

    scenario.game.add_counters(bears, Counter.PLUS_ONE, 1)

    assert bears.counter_count(Counter.PLUS_ONE) == 3


def test_hardened_scales_alone_is_the_same_reader():
    scenario = _prairie_board("Hardened Scales").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears")

    scenario.game.add_counters(bears, Counter.PLUS_ONE, 2)

    assert bears.counter_count(Counter.PLUS_ONE) == 3


def test_prairie_dogs_effect_outlives_prairie_dog():
    """CR 611.2a: the resolved ability's effect does not depend on its source."""
    scenario = _prairie_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _activate_prairie_dog(scenario)
    dog = scenario.creature("Prairie Dog")
    scenario.game.put_into_graveyard(dog)
    assert dog.zone is Zone.GRAVEYARD
    bears = scenario.creature("Grizzly Bears")

    scenario.game.add_counters(bears, Counter.PLUS_ONE, 1)

    assert bears.counter_count(Counter.PLUS_ONE) == 2


def test_prairie_dogs_effect_ends_with_the_turn():
    scenario = _prairie_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _activate_prairie_dog(scenario)
    _to_next_turn(scenario)
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.game.add_counters(bears, Counter.PLUS_ONE, 1)

    assert bears.counter_count(Counter.PLUS_ONE) == 1


def _grim_affliction_board(caster: str) -> Scenario:
    """Two alice Bears, one already carrying a +1/+1 counter, and Grim
    Affliction ("Put a -1/-1 counter on target creature, then proliferate.")
    in `caster`'s hand."""
    alice_hand = ["Grim Affliction"] if caster == "alice" else []
    bob_hand = ["Grim Affliction"] if caster == "bob" else []
    return (
        Scenario()
        .player(
            "alice",
            battlefield=[
                "Prairie Dog",
                "Grizzly Bears",
                "Grizzly Bears",
                *(["Plains"] * 5),
                *(["Swamp"] * 3),
            ],
            hand=alice_hand,
        )
        .player("bob", battlefield=["Swamp"] * 3, hand=bob_hand)
    )


def _proliferate_onto_second_bears(scenario, caster: str) -> CardState:
    first, second = scenario.creatures("Grizzly Bears", "Grizzly Bears", username="alice")
    second.add_counters(Counter.PLUS_ONE, 1)
    _activate_prairie_dog(scenario)
    if caster == "bob":
        scenario.pass_priority("alice")
    sources = scenario.untapped_sources("Swamp", "Swamp", "Swamp", username=caster)
    scenario.will_choose_cards(second, source="Grim Affliction", username=caster)
    scenario.cast_and_resolve("Grim Affliction", *sources, username=caster, targets=[first])
    return second


def test_prairie_dog_ignores_counters_an_opponent_puts_on_your_creature():
    """ "If you would put": the +1 answers only counters alice herself puts.
    Bob's Grim Affliction proliferating alice's Bears is bob putting the
    counter (CR 701.34a), so it arrives as one, not two."""
    scenario = _grim_affliction_board("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    second = _proliferate_onto_second_bears(scenario, "bob")

    assert second.counter_count(Counter.PLUS_ONE) == 2


def test_prairie_dog_adds_one_to_your_own_proliferate():
    """The same proliferate cast by alice is alice putting the counter."""
    scenario = _grim_affliction_board("alice").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    second = _proliferate_onto_second_bears(scenario, "alice")

    assert second.counter_count(Counter.PLUS_ONE) == 3
