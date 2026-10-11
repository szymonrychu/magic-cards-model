"""Scenario: Ob Nixilis, the Adversary - "Casualty X. The copy isn't legendary
and has starting loyalty X." and "+1: Each opponent loses 2 life unless they
discard a card. If you control a Demon or Devil, you gain 2 life."

CR 702.153a: casualty N lets the caster sacrifice a creature with power N or
greater as an additional cost, and copies the spell when it was paid. For
"Casualty X" the value of X is announced as the spell is cast (CR 107.3a) and
is what the copy's starting loyalty (CR 306.5b) is. CR 707.10f: the copy of a
permanent spell becomes a token as it resolves; it is not legendary, so CR
704.5j's legend rule leaves both Ob Nixilis permanents on the battlefield.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Supertype
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import PlayedScenario, Scenario

OB = "Ob Nixilis, the Adversary"


def board(*creatures: str) -> PlayedScenario:
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[OB],
            battlefield=["Swamp", "Swamp", "Mountain"] + list(creatures),
            library=["Island"] * 4,
        )
        .player("bob", hand=["Island", "Island"], library=["Island"] * 4)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def resolve_everything(scenario: PlayedScenario) -> None:
    while scenario.game.stack:
        scenario.resolve_top()


def cast_ob(scenario: PlayedScenario, x: int | None = None, sacrifice=None):
    casting = scenario.cast(OB)
    if x is not None:
        casting.announce_casualty_x(x)
    if sacrifice is not None:
        casting.pay_casualty(sacrifice)
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Swamp", "Swamp", "Mountain"))
    return scenario.put_on_stack(casting)


def obs(scenario: PlayedScenario) -> list:
    return [p for p in scenario.game.battlefield if p.name == OB]


def test_paying_casualty_x_makes_a_nonlegendary_copy_with_x_loyalty():
    scenario = board("Serra Angel")
    angel = scenario.creature("Serra Angel", "alice")

    cast_ob(scenario, x=3, sacrifice=angel)
    resolve_everything(scenario)

    assert angel.zone is Zone.GRAVEYARD
    original, copy = sorted(obs(scenario), key=lambda p: p.token)
    assert not original.token and copy.token
    assert original.counter_count(Counter.LOYALTY) == 3
    assert copy.counter_count(Counter.LOYALTY) == 3
    assert Supertype.LEGENDARY in scenario.game.characteristics_of(original).supertypes
    assert Supertype.LEGENDARY not in scenario.game.characteristics_of(copy).supertypes


def test_the_copy_has_the_announced_x_as_its_starting_loyalty():
    scenario = board("Serra Angel")
    angel = scenario.creature("Serra Angel", "alice")

    cast_ob(scenario, x=1, sacrifice=angel)
    resolve_everything(scenario)

    copy = next(p for p in obs(scenario) if p.token)
    assert copy.counter_count(Counter.LOYALTY) == 1
    original = next(p for p in obs(scenario) if not p.token)
    assert original.counter_count(Counter.LOYALTY) == 3


def test_the_sacrificed_creature_needs_power_x_or_greater():
    scenario = board("Grizzly Bears")
    bears = scenario.creature("Grizzly Bears", "alice")

    casting = scenario.cast(OB)
    casting.announce_casualty_x(3)
    with pytest.raises(ValueError, match="power"):
        casting.pay_casualty(bears)
    assert bears.zone is Zone.BATTLEFIELD


def test_without_paying_casualty_there_is_no_copy():
    scenario = board("Serra Angel")

    cast_ob(scenario)
    resolve_everything(scenario)

    (only,) = obs(scenario)
    assert not only.token


def test_game_cast_takes_the_announced_x_and_creature():
    scenario = board("Serra Angel")
    angel = scenario.creature("Serra Angel", "alice")

    scenario.game.cast(
        scenario.find(OB, Zone.HAND, "alice"),
        "alice",
        casualty=[angel],
        casualty_x=2,
        mana_sources=scenario.untapped_sources("Swamp", "Swamp", "Mountain"),
    )
    resolve_everything(scenario)

    assert angel.zone is Zone.GRAVEYARD
    copy = next(p for p in obs(scenario) if p.token)
    assert copy.counter_count(Counter.LOYALTY) == 2


def test_a_cast_during_resolution_asks_for_x_and_the_creature():
    scenario = board("Serra Angel")
    angel = scenario.creature("Serra Angel", "alice")
    scenario.will_take_the_may(True)
    scenario.will_choose_an_amount(2)
    scenario.will_choose_cards(angel)

    scenario.game.cast_during_resolution(
        scenario.find(OB, Zone.HAND, "alice"),
        "alice",
        source_name="test",
        rule="CR 608.2g",
    )
    scenario.game.put_triggers_on_stack()
    resolve_everything(scenario)

    assert angel.zone is Zone.GRAVEYARD
    copy = next(p for p in obs(scenario) if p.token)
    assert copy.counter_count(Counter.LOYALTY) == 2


def test_declining_the_casualty_asks_nothing_further_and_makes_no_copy():
    scenario = board("Serra Angel")
    scenario.will_take_the_may(False)

    scenario.game.cast_during_resolution(
        scenario.find(OB, Zone.HAND, "alice"),
        "alice",
        source_name="test",
        rule="CR 608.2g",
    )
    resolve_everything(scenario)

    (only,) = obs(scenario)
    assert not only.token


def test_plus_one_makes_each_opponent_lose_2_life_unless_they_discard():
    scenario = board()
    scenario.game.put_onto_battlefield(
        scenario.find(OB, Zone.HAND, "alice"), "alice"
    )
    ob = obs(scenario)[0]
    life = scenario.player("bob").life
    scenario.will_take_the_may(False)

    scenario.activate(ob, index=0, username="alice")
    scenario.resolve_top()

    assert scenario.player("bob").life == life - 2
    assert scenario.player("alice").life == 20


def test_plus_one_with_a_discard_costs_no_life():
    scenario = board()
    scenario.game.put_onto_battlefield(scenario.find(OB, Zone.HAND, "alice"), "alice")
    ob = obs(scenario)[0]
    life = scenario.player("bob").life
    scenario.will_take_the_may(True)
    scenario.will_discard(scenario.find("Island", Zone.HAND, "bob"), username="bob")

    scenario.activate(ob, index=0, username="alice")
    scenario.resolve_top()

    assert scenario.player("bob").life == life
    assert len(scenario.player("bob").hand) == 1


def _plus_one_with(scenario):
    scenario.game.put_onto_battlefield(scenario.find(OB, Zone.HAND, "alice"), "alice")
    ob = obs(scenario)[0]
    scenario.will_take_the_may(False)
    scenario.activate(ob, index=0, username="alice")
    scenario.resolve_top()


def test_a_devil_makes_it_gain_two_life():
    scenario = board("Perforating Artist")
    _plus_one_with(scenario)

    assert scenario.player("alice").life == 22


def test_a_demon_makes_it_gain_two_life():
    scenario = board("Demonic Taskmaster")
    _plus_one_with(scenario)

    assert scenario.player("alice").life == 22


def test_without_a_demon_or_devil_it_gains_nothing():
    scenario = board("Grizzly Bears")
    _plus_one_with(scenario)

    assert scenario.player("alice").life == 20


def test_each_opponent_discards_their_hand_only_for_opponents():
    """The "each opponent" head of the each-player step reader, on a second
    printing: Myojin of Night's Reach's "Remove a divinity counter ...: Each
    opponent discards their hand." empties bob's hand and leaves alice's."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Island", "Island"],
            battlefield=["Myojin of Night's Reach"],
            library=["Island"] * 3,
        )
        .player("bob", hand=["Island", "Island", "Island"], library=["Island"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    myojin = scenario.creature("Myojin of Night's Reach", "alice")
    myojin.add_counters("divinity", 1)

    abilities = scenario.game.activated_abilities(myojin)
    index = next(i for i, a in enumerate(abilities) if "Each opponent discards" in a.raw)
    scenario.activate(myojin, index=index, username="alice")
    scenario.resolve_top()

    assert len(scenario.player("bob").hand) == 0
    assert len(scenario.player("alice").hand) == 2
