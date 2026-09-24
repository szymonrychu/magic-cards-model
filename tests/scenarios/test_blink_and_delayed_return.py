"""Scenario: exile permanents and return them to the battlefield under their
owner's control - at once ("then return them"), or "at the beginning of the
next end step" through a delayed triggered ability (CR 603.7a), including
the Saga chapter form, the "If you do" form, and the kicked "choose any
number of targets ... return each ... at the beginning of the next upkeep"
bounce.

A returned card is a new object (CR 400.7): its counters are gone, and it is
summoning sick again (CR 302.6). It returns under its owner's control (CR
610.3c's default, and "under their owner's control" says so). An immediate
"then return them" puts every exiled card back in one event (CR 603.6a), so
each newcomer's enters ability sees the others. A delayed return that finds
its card no longer in exile, or back as a new object, does nothing (CR
603.7c); a token exiled this way ceases to exist before it could return
(CR 111.7). "Up to one" and "any number" may choose zero (CR 115.6, CR
107.1c); "If you do" returns only what was actually exiled. A kicked spell
may need different targets (CR 601.2c: "A spell may require some targets
only if an alternative or additional cost (such as a kicker cost) ... is
paid"; CR 702.33d: that spell has been "kicked").

Printings: Lake-town Mariners // Gone Fishing (two targets, "and/or", "then
return them"), Roll-Roll-Roll-Roll (Saga chapter, "up to one", "If you do",
next end step), Elrond, Moon-Reader's activation ("up to two other",
"Return those cards"), The Eagles Are Coming! (kicked "any number", next
upkeep); off-set Displace ("up to two ... then return those cards"), Eerie
Interlude ("any number ... Return those cards"), Sentinel of the Pearl
Trident ("you may exile ... If you do, return that card").

CR numbers verified with `mise run rules:find`: 603.7a, 400.7, 302.6,
610.3c, 603.6a, 603.7c, 111.7, 115.6, 107.1c, 601.2c, 702.33d, 714.2b.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from magic_cards_model.support import card_support
from tests.cards import card

from .harness import Scenario

MARINERS = "Lake-town Mariners // Gone Fishing"
ROLL = "Roll-Roll-Roll-Roll"
ELROND = "Elrond, Moon-Reader"
EAGLES = "The Eagles Are Coming!"


def test_listed_and_proof_printings_are_handled():
    for name in (
        ROLL,
        ELROND,
        EAGLES,
        "Displace",
        "Eerie Interlude",
        "Sentinel of the Pearl Trident",
    ):
        bad = [c for c in card_support(card(name)).clauses if c.outcome not in ("handled",)]
        assert not bad, (name, bad)


def _settle(scenario):
    scenario.game.put_triggers_on_stack()
    while scenario.stack_names():
        scenario.pass_until_resolved()
        scenario.game.put_triggers_on_stack()


def _to_end_step(scenario):
    while scenario.step is not Step.END_STEP:
        _settle(scenario)
        scenario.advance()
    _settle(scenario)


# -- immediate: "then return them" -------------------------------------------


def test_gone_fishing_blinks_a_creature_and_a_land_together_as_new_objects():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[MARINERS],
            battlefield=["Island"] * 4 + ["Grizzly Bears"],
            library=["Island"] * 3,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears")
    scenario.game.add_counters(bears, Counter.PLUS_ONE, 1)
    lands = scenario.untapped_sources(*["Island"] * 4)
    casting = scenario.cast("Lake-town Mariners")
    casting.cast_as_adventure()
    casting.choose_targets([bears, lands[0]])
    scenario.pay_with(casting.begin_paying(), *lands)
    scenario.put_on_stack(casting)
    scenario.resolve_top()
    bears_now = scenario.creature("Grizzly Bears")
    assert bears_now.counter_count(Counter.PLUS_ONE) == 0
    assert bears_now.controller == "alice"
    returned_island = next(c for c in scenario.game.battlefield if c.id == lands[0].id)
    assert not returned_island.tapped  # CR 400.7: a new, untapped object
    assert scenario.game.exile == [c for c in scenario.game.exile if c.name == "Lake-town Mariners"]


def test_displace_blinks_up_to_two_creatures():
    scenario = (
        Scenario()
        .player(
            "alice", hand=["Displace"], battlefield=["Island"] * 3 + ["Grizzly Bears", "Hill Giant"]
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears")
    giant = scenario.creature("Hill Giant")
    bears.tapped = True
    giant.tapped = True
    scenario.cast_and_resolve("Displace", auto=True, targets=[bears, giant])
    assert not scenario.creature("Grizzly Bears").tapped
    assert not scenario.creature("Hill Giant").tapped


# -- delayed: "at the beginning of the next end step" ------------------------


def test_roll_chapter_one_exiles_and_returns_at_the_next_end_step():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[ROLL],
            battlefield=["Island"] * 3 + ["Grizzly Bears"],
            library=["Island"] * 5,
        )
        .player("bob", library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears")
    scenario.choose_trigger_targets(ROLL, [bears])
    scenario.cast_and_resolve(ROLL, auto=True)
    _settle(scenario)
    assert bears.zone is Zone.EXILE
    _to_end_step(scenario)
    returned = scenario.creature("Grizzly Bears")
    assert returned.controller == "alice"


def test_roll_choosing_no_target_exiles_and_returns_nothing():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[ROLL],
            battlefield=["Island"] * 3 + ["Grizzly Bears"],
            library=["Island"] * 5,
        )
        .player("bob", library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.choose_trigger_targets(ROLL, [])
    scenario.cast_and_resolve(ROLL, auto=True)
    _settle(scenario)
    assert scenario.creature("Grizzly Bears").zone is Zone.BATTLEFIELD
    assert scenario.game.delayed_triggers.triggers == []


def test_elrond_blinks_up_to_two_other_permanents_at_the_end_step():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[ELROND, "Grizzly Bears", "Mind Stone"] + ["Island"] * 7,
            library=["Island"] * 5,
        )
        .player("bob", library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    elrond = scenario.creature(ELROND)
    bears = scenario.creature("Grizzly Bears")
    stone = scenario.find("Mind Stone", Zone.BATTLEFIELD, "alice")
    scenario.activate(
        elrond, *scenario.untapped_sources(*["Island"] * 7), index=0, targets=[bears, stone]
    )
    _settle(scenario)
    assert bears.zone is Zone.EXILE and stone.zone is Zone.EXILE
    assert elrond.zone is Zone.BATTLEFIELD
    _to_end_step(scenario)
    assert scenario.creature("Grizzly Bears").zone is Zone.BATTLEFIELD
    assert scenario.find("Mind Stone", Zone.BATTLEFIELD, "alice")


def test_elrond_cannot_target_itself():
    scenario = (
        Scenario().player("alice", battlefield=[ELROND] + ["Island"] * 7).player("bob").build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    elrond = scenario.creature(ELROND)
    try:
        scenario.activate(
            elrond, *scenario.untapped_sources(*["Island"] * 7), index=0, targets=[elrond]
        )
    except ValueError:
        return
    raise AssertionError("Elrond targeted itself despite 'other'")


def test_eerie_interlude_returns_every_exiled_creature_together():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Eerie Interlude"],
            battlefield=["Plains"] * 3 + ["Grizzly Bears", "Hill Giant"],
            library=["Plains"] * 5,
        )
        .player("bob", library=["Plains"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears")
    giant = scenario.creature("Hill Giant")
    scenario.cast_and_resolve("Eerie Interlude", auto=True, targets=[bears, giant])
    assert bears.zone is Zone.EXILE and giant.zone is Zone.EXILE
    _to_end_step(scenario)
    assert scenario.creature("Grizzly Bears") and scenario.creature("Hill Giant")


def test_a_card_that_left_exile_before_the_end_step_is_not_returned():
    """CR 603.7c: the delayed ability no longer finds its object in exile."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Eerie Interlude"],
            battlefield=["Plains"] * 3 + ["Grizzly Bears"],
            library=["Plains"] * 5,
        )
        .player("bob", library=["Plains"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears")
    scenario.cast_and_resolve("Eerie Interlude", auto=True, targets=[bears])
    exiled = scenario.find("Grizzly Bears", Zone.EXILE)
    scenario.game.put_into_graveyard(exiled)
    _to_end_step(scenario)
    assert not [c for c in scenario.game.battlefield if c.name == "Grizzly Bears"]


def test_sentinel_declining_the_may_exiles_and_returns_nothing():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Sentinel of the Pearl Trident"],
            battlefield=["Island"] * 5 + ["Mind Stone"],
            library=["Island"] * 5,
        )
        .player("bob", library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    stone = scenario.find("Mind Stone", Zone.BATTLEFIELD, "alice")
    scenario.choose_trigger_targets("Sentinel of the Pearl Trident", [stone])
    scenario.will_take_the_may(False)
    scenario.cast_and_resolve(
        "Sentinel of the Pearl Trident", *scenario.untapped_sources(*["Island"] * 5)
    )
    _settle(scenario)
    assert stone.zone is Zone.BATTLEFIELD
    assert scenario.game.delayed_triggers.triggers == []


def test_sentinel_taking_the_may_blinks_until_the_end_step():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Sentinel of the Pearl Trident"],
            battlefield=["Island"] * 5 + ["Mind Stone"],
            library=["Island"] * 5,
        )
        .player("bob", library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    stone = scenario.find("Mind Stone", Zone.BATTLEFIELD, "alice")
    scenario.choose_trigger_targets("Sentinel of the Pearl Trident", [stone])
    scenario.will_take_the_may(True)
    scenario.cast_and_resolve(
        "Sentinel of the Pearl Trident", *scenario.untapped_sources(*["Island"] * 5)
    )
    _settle(scenario)
    assert stone.zone is Zone.EXILE
    _to_end_step(scenario)
    assert scenario.find("Mind Stone", Zone.BATTLEFIELD, "alice")


# -- The Eagles Are Coming!: kicked, any number, next upkeep -----------------


def _eagles_board():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[EAGLES],
            battlefield=["Plains"] * 6 + ["Grizzly Bears", "Hill Giant"],
            library=["Plains"] * 5,
        )
        .player("bob", battlefield=["Grizzly Bears"], library=["Plains"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _birds(scenario):
    return [c for c in scenario.game.battlefield if c.name.startswith("Bird Soldier")]


def _to_next_upkeep(scenario):
    active = scenario.turn.active_player
    while not (scenario.turn.active_player != active and scenario.step is Step.UPKEEP):
        _settle(scenario)
        scenario.advance()
    _settle(scenario)


def test_eagles_unkicked_returns_one_creature_and_makes_one_bird_next_upkeep():
    scenario = _eagles_board()
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.cast_and_resolve(
        EAGLES, *scenario.untapped_sources("Plains", "Plains"), targets=[bears]
    )
    assert [c.name for c in scenario.player("alice").hand] == ["Grizzly Bears"]
    assert _birds(scenario) == []
    _to_next_upkeep(scenario)
    (bird,) = _birds(scenario)
    chars = scenario.game.characteristics_of(bird)
    assert (chars.power, chars.toughness) == (4, 4)
    assert bird.controller == "alice"


def test_eagles_unkicked_may_not_choose_two_targets():
    scenario = _eagles_board()
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "alice")
    try:
        scenario.cast(EAGLES, targets=[bears, giant])
    except ValueError:
        return
    raise AssertionError("an unkicked Eagles took two targets")


def test_eagles_kicked_returns_any_number_and_makes_a_bird_for_each():
    scenario = _eagles_board()
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "alice")
    casting = scenario.cast(EAGLES)
    casting.pay_kicker()
    casting.choose_targets([bears, giant])
    scenario.pay_with(casting.begin_paying(), *scenario.untapped_sources(*["Plains"] * 6))
    scenario.put_on_stack(casting)
    scenario.resolve_top()
    assert sorted(c.name for c in scenario.player("alice").hand) == ["Grizzly Bears", "Hill Giant"]
    _to_next_upkeep(scenario)
    assert len(_birds(scenario)) == 2


def test_eagles_may_not_target_a_creature_you_do_not_own():
    scenario = _eagles_board()
    theirs = scenario.creature("Grizzly Bears", "bob")
    try:
        scenario.cast(EAGLES, targets=[theirs])
    except ValueError:
        return
    raise AssertionError("Eagles targeted a creature its caster does not own")


def test_eagles_counts_only_creatures_actually_returned():
    """A target gone by resolution (CR 608.2b) is not returned, so it makes no Bird."""
    scenario = _eagles_board()
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "alice")
    casting = scenario.cast(EAGLES)
    casting.pay_kicker()
    casting.choose_targets([bears, giant])
    scenario.pay_with(casting.begin_paying(), *scenario.untapped_sources(*["Plains"] * 6))
    scenario.put_on_stack(casting)
    scenario.game.destroy(giant)
    scenario.resolve_top()
    _to_next_upkeep(scenario)
    assert len(_birds(scenario)) == 1
