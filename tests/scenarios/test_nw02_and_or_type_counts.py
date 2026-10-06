"""Scenario: a count over an "`<A>` and/or `<B>`" list of types - "the number
of creatures and/or Spacecraft you control" - as a damage amount.

Focus Fire: "Focus Fire deals X damage to target attacking or blocking
creature, where X is 2 plus the number of creatures and/or Spacecraft you
control." The count is of the permanents that match *any* item of the list, so
a permanent that is both (a Spacecraft stationed past its creature threshold)
counts once, and one that is neither does not count. Spacecraft is an artifact
subtype (CR 205.3g), so the list mixes a card type with a subtype.

Collision Course ("... deals X damage to target creature, where X is the number
of permanents you control that are creatures and/or Vehicles.") is the off-set
proof: the same union read through the "permanents you control that are
`<list>`" phrasing, inside a modal spell's mode. A crewed Vehicle is a creature
and a Vehicle at once and counts once.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.keywords import crew_activation
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter

from .harness import Scenario


def _focus_fire(alice_bf):
    """Alice attacks with her own Colossal Dreadmaw (6/6, survives the damage)
    and casts Focus Fire at it; returns the Dreadmaw."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Focus Fire"],
            battlefield=["Plains", "Plains", "Colossal Dreadmaw", *alice_bf],
        )
        .player("bob", battlefield=["Grizzly Bears", "Memnite"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    dreadmaw = scenario.creature("Colossal Dreadmaw", "alice")
    scenario.attack_with(dreadmaw)
    scenario.cast_and_resolve("Focus Fire", auto=True, targets=[dreadmaw])
    return dreadmaw


def test_focus_fire_with_only_a_creature_is_two_plus_one():
    assert _focus_fire([]).damage == 3


def test_every_creature_you_control_counts():
    assert _focus_fire(["Memnite", "Grizzly Bears"]).damage == 5


def test_a_noncreature_spacecraft_counts():
    assert _focus_fire(["Wurmwall Sweeper"]).damage == 4


def test_a_permanent_that_is_both_counts_once():
    """Lumen-Class Frigate at 12 charge counters is an artifact creature
    Spacecraft: one permanent, one count (and its station line gives the
    Dreadmaw +1/+1, which does not move the damage)."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Focus Fire"],
            battlefield=["Plains", "Plains", "Colossal Dreadmaw", "Lumen-Class Frigate"],
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    frigate = scenario.find("Lumen-Class Frigate", Zone.BATTLEFIELD)
    scenario.game.add_counters(frigate, Counter.CHARGE, 12)
    assert scenario.game.characteristics_of(frigate).is_creature
    dreadmaw = scenario.creature("Colossal Dreadmaw", "alice")
    scenario.attack_with(dreadmaw)
    scenario.cast_and_resolve("Focus Fire", auto=True, targets=[dreadmaw])
    assert dreadmaw.damage == 4  # 2 + (Dreadmaw, Frigate)


def test_lands_and_other_artifacts_do_not_count():
    assert _focus_fire(["Plains", "Sol Ring"]).damage == 3


def test_collision_course_counts_creatures_and_vehicles_you_control():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Collision Course"],
            battlefield=["Plains", "Plains", "Memnite", "Smuggler's Copter"],
        )
        .player("bob", battlefield=["Colossal Dreadmaw"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    target = scenario.creature("Colossal Dreadmaw", "bob")
    casting = scenario.cast("Collision Course")
    casting.choose_modes([1])
    casting.choose_targets([target])
    payment = casting.begin_paying()
    scenario.auto_pay(payment, username="alice")
    scenario.put_on_stack(casting)
    scenario.resolve_top()
    assert target.damage == 2  # Memnite + the uncrewed Vehicle


def test_collision_course_counts_a_crewed_vehicle_once():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Collision Course"],
            battlefield=["Plains", "Plains", "Memnite", "Smuggler's Copter"],
        )
        .player("bob", battlefield=["Colossal Dreadmaw"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    copter = scenario.find("Smuggler's Copter", Zone.BATTLEFIELD)
    memnite = scenario.creature("Memnite", "alice")
    crew = crew_activation(scenario.game, copter, [memnite], "alice")
    crew.begin_paying()
    crew.payment.pay()
    crew.activate()
    crew.resolve()
    assert scenario.game.characteristics_of(copter).is_creature
    target = scenario.creature("Colossal Dreadmaw", "bob")
    casting = scenario.cast("Collision Course")
    casting.choose_modes([1])
    casting.choose_targets([target])
    payment = casting.begin_paying()
    scenario.auto_pay(payment, username="alice")
    scenario.put_on_stack(casting)
    scenario.resolve_top()
    assert target.damage == 2  # Memnite, and the crewed Copter once
