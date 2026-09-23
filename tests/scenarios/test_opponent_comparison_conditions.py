"""Scenario: "an opponent controls more <permanents> than you" / "an opponent
has more life than you" / "an opponent has more cards in hand than you" -
`Game.condition_holds`'s comparison vocabulary, asked from three differently
shaped cards.

Beza, the Bounding Spring prints four sentences, each "<effect> if <comparison>"
(the trailing-if order). CR 608.2c: they are followed in the order written, and
each condition is read when its own sentence is applied (CR 608.2h: information
from the game "is determined only once, when the effect is applied"), so an
earlier sentence's result can change a later sentence's answer.

Sunset Revelry prints three of the same comparisons in the leading order ("If
<comparison>, <effect>.") on a sorcery - the second printing proving the reader
is the template, not Beza's sentence.

Ticket Tortoise prints the lands comparison as an intervening if (CR 603.4):
checked when the trigger event occurs and again on resolution.

"More ... than you" is strict: a tie is not "more".
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

# -- Beza, the Bounding Spring ------------------------------------------------


def _beza(
    *,
    alice_lands: int = 4,
    bob_lands: int = 0,
    alice_life: int = 20,
    bob_life: int = 20,
    bob_creatures: int = 0,
    alice_hand: list[str] | None = None,
    bob_hand: list[str] | None = None,
) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            life=alice_life,
            hand=["Beza, the Bounding Spring", *(alice_hand or [])],
            battlefield=["Plains"] * alice_lands,
            library=["Plains"] * 3,
        )
        .player(
            "bob",
            life=bob_life,
            hand=list(bob_hand or []),
            battlefield=["Island"] * bob_lands + ["Grizzly Bears"] * bob_creatures,
            library=["Island"] * 3,
        )
        .build()
    )


def _cast_beza_and_resolve_trigger(scenario: Scenario) -> None:
    scenario.start_at(Step.PRECOMBAT_MAIN)
    plains = scenario.untapped_sources("Plains", "Plains", "Plains", "Plains", username="alice")
    scenario.cast_and_resolve("Beza, the Bounding Spring", *plains, username="alice")
    assert scenario.stack_names() == ["Beza, the Bounding Spring's triggered ability"]
    scenario.resolve_top()


def _names(scenario: Scenario, username: str) -> list[str]:
    """Each permanent's name, a token's read by its subtype - "Treasure",
    "Fish", "Human" - so a token counts the same however it is named."""
    return [
        state.subtypes[0] if state.token and state.subtypes else state.name
        for state in scenario.game.permanents_controlled_by(username)
    ]


def test_beza_does_nothing_when_no_opponent_is_ahead_on_anything():
    """Alice has more lands (4 to 0), equal life, and Beza already gives her
    more creatures (1 to 0); after casting Beza her hand is empty, and so is
    Bob's - no comparison holds."""
    scenario = _beza()
    _cast_beza_and_resolve_trigger(scenario)

    alice = scenario.player("alice")
    assert "Treasure" not in _names(scenario, "alice")
    assert "Fish" not in _names(scenario, "alice")
    assert alice.life == 20
    assert len(alice.hand) == 0


def test_beza_treasure_only_when_an_opponent_controls_more_lands():
    scenario = _beza(bob_lands=5)
    _cast_beza_and_resolve_trigger(scenario)

    assert _names(scenario, "alice").count("Treasure") == 1
    assert scenario.player("alice").life == 20
    assert "Fish" not in _names(scenario, "alice")
    assert len(scenario.player("alice").hand) == 0


def test_beza_a_tie_on_lands_is_not_more_lands():
    scenario = _beza(bob_lands=4)
    _cast_beza_and_resolve_trigger(scenario)

    assert "Treasure" not in _names(scenario, "alice")


def test_beza_gains_four_only_when_an_opponent_has_more_life():
    scenario = _beza(alice_life=15, bob_life=16)
    _cast_beza_and_resolve_trigger(scenario)

    assert scenario.player("alice").life == 19
    assert "Treasure" not in _names(scenario, "alice")


def test_beza_a_tie_on_life_gains_nothing():
    scenario = _beza(alice_life=16, bob_life=16)
    _cast_beza_and_resolve_trigger(scenario)

    assert scenario.player("alice").life == 16


def test_beza_fish_only_when_an_opponent_controls_more_creatures():
    """Beza herself is on the battlefield when the trigger resolves, so she
    counts: Bob needs two creatures to be ahead of Alice's one."""
    scenario = _beza(bob_creatures=2)
    _cast_beza_and_resolve_trigger(scenario)

    assert _names(scenario, "alice").count("Fish") == 2


def test_beza_counts_herself_so_one_opposing_creature_is_only_a_tie():
    scenario = _beza(bob_creatures=1)
    _cast_beza_and_resolve_trigger(scenario)

    assert "Fish" not in _names(scenario, "alice")


def test_beza_draws_only_when_an_opponent_has_more_cards_in_hand():
    scenario = _beza(bob_hand=["Island"])
    _cast_beza_and_resolve_trigger(scenario)

    assert len(scenario.player("alice").hand) == 1


def test_beza_a_tie_on_cards_in_hand_draws_nothing():
    scenario = _beza(alice_hand=["Plains"], bob_hand=["Island"])
    _cast_beza_and_resolve_trigger(scenario)

    assert len(scenario.player("alice").hand) == 1  # only the Plains she kept


def test_beza_all_four_sentences_apply_when_all_four_comparisons_hold():
    scenario = _beza(bob_lands=5, alice_life=10, bob_life=20, bob_creatures=3, bob_hand=["Island"])
    _cast_beza_and_resolve_trigger(scenario)

    alice = scenario.player("alice")
    assert _names(scenario, "alice").count("Treasure") == 1
    assert alice.life == 14
    assert _names(scenario, "alice").count("Fish") == 2
    assert len(alice.hand) == 1


def test_beza_each_sentence_applies_once_even_when_it_flips_its_own_comparison():
    """CR 608.2c: the sentences are followed once each, in order. Bob is 3
    life ahead, so Alice gains 4 and ends ahead of him - which does not undo
    the gain. Bob has three creatures to Alice's one: the two Fish make it 3
    to 3, and the sentence still created exactly two of them."""
    scenario = _beza(alice_life=17, bob_life=20, bob_creatures=3)
    _cast_beza_and_resolve_trigger(scenario)

    assert scenario.player("alice").life == 21
    assert _names(scenario, "alice").count("Fish") == 2


def test_beza_the_opponent_comparison_is_not_about_yourself():
    """ "An opponent" (CR 102.3) is never the ability's own controller: Alice
    has more cards in hand than Bob here, which is not a reason to draw."""
    scenario = _beza(alice_hand=["Plains", "Plains"])
    _cast_beza_and_resolve_trigger(scenario)

    assert len(scenario.player("alice").hand) == 2


# -- Sunset Revelry (leading "If <comparison>, <effect>." on a sorcery) ------


def _revelry(
    *,
    alice_life: int = 20,
    bob_life: int = 20,
    bob_creatures: int = 0,
    bob_hand: list[str] | None = None,
) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            life=alice_life,
            hand=["Sunset Revelry"],
            battlefield=["Plains", "Plains"],
            library=["Plains"] * 3,
        )
        .player(
            "bob",
            life=bob_life,
            hand=list(bob_hand or []),
            battlefield=["Grizzly Bears"] * bob_creatures,
            library=["Island"] * 3,
        )
        .build()
    )


def _cast_revelry(scenario: Scenario) -> None:
    scenario.start_at(Step.PRECOMBAT_MAIN)
    plains = scenario.untapped_sources("Plains", "Plains", username="alice")
    scenario.cast_and_resolve("Sunset Revelry", *plains, username="alice")


def test_revelry_every_branch_when_every_comparison_holds():
    scenario = _revelry(alice_life=10, bob_life=12, bob_creatures=1, bob_hand=["Island"])
    _cast_revelry(scenario)

    alice = scenario.player("alice")
    assert alice.life == 14
    assert _names(scenario, "alice").count("Human") == 2
    assert len(alice.hand) == 1


def test_revelry_nothing_when_nothing_holds():
    scenario = _revelry()
    _cast_revelry(scenario)

    alice = scenario.player("alice")
    assert alice.life == 20
    assert "Human" not in _names(scenario, "alice")
    assert len(alice.hand) == 0
    assert scenario.find("Sunset Revelry", Zone.GRAVEYARD, "alice") is not None


def test_revelry_only_the_life_branch():
    scenario = _revelry(alice_life=5, bob_life=6)
    _cast_revelry(scenario)

    assert scenario.player("alice").life == 9
    assert "Human" not in _names(scenario, "alice")


def test_revelry_only_the_creature_branch():
    scenario = _revelry(bob_creatures=1)
    _cast_revelry(scenario)

    assert _names(scenario, "alice").count("Human") == 2
    assert scenario.player("alice").life == 20


def test_revelry_only_the_hand_branch():
    scenario = _revelry(bob_hand=["Island", "Island"])
    _cast_revelry(scenario)

    assert len(scenario.player("alice").hand) == 1
    assert "Human" not in _names(scenario, "alice")


# -- Ticket Tortoise (intervening if, CR 603.4) -------------------------------


def _tortoise(*, bob_lands: int) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=["Ticket Tortoise"],
            battlefield=["Plains", "Plains"],
            library=["Plains"] * 3,
        )
        .player("bob", battlefield=["Island"] * bob_lands, library=["Island"] * 3)
        .build()
    )


def _cast_tortoise(scenario: Scenario) -> None:
    scenario.start_at(Step.PRECOMBAT_MAIN)
    plains = scenario.untapped_sources("Plains", "Plains", username="alice")
    scenario.cast_and_resolve("Ticket Tortoise", *plains, username="alice")


def test_tortoise_triggers_and_makes_a_treasure_when_an_opponent_has_more_lands():
    scenario = _tortoise(bob_lands=3)
    _cast_tortoise(scenario)

    assert scenario.stack_names() == ["Ticket Tortoise's triggered ability"]
    scenario.resolve_top()
    assert _names(scenario, "alice").count("Treasure") == 1
    assert scenario.game.intervening_if_notices == []


def test_tortoise_does_not_trigger_on_a_tie():
    scenario = _tortoise(bob_lands=2)
    _cast_tortoise(scenario)

    assert scenario.stack_names() == []
    assert scenario.pending_triggers == []
    assert scenario.game.intervening_if_notices == []


def test_tortoise_rechecks_on_resolution():
    """CR 603.4: "it checks the stated condition again as it resolves" - Alice
    plays a land in response, drawing level with Bob, and the trigger is
    removed from the stack doing nothing."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Ticket Tortoise", "Plains"],
            battlefield=["Plains", "Plains"],
            library=["Plains"] * 3,
        )
        .player("bob", battlefield=["Island"] * 3, library=["Island"] * 3)
        .build()
    )
    _cast_tortoise(scenario)
    assert scenario.stack_names() == ["Ticket Tortoise's triggered ability"]
    # A land drop needs an empty stack, so the extra land comes onto the
    # battlefield the Tooth and Nail way instead - the board is what matters.
    scenario.put_onto_battlefield("Plains", "alice")
    scenario.resolve_top()

    assert "Treasure" not in _names(scenario, "alice")
