"""Entering-counter statics read off how the spell was cast: "escapes with"
and "for each time it was kicked".

CR 702.138c: "An ability that reads "[This permanent] escapes with [one or
more of a kind of counter]" means "If this permanent escaped, it enters with
[those counters]"" - a CR 614.1c "enters with" replacement whose condition is
CR 702.138b's "escaped" (the spell that became it was cast with escape).

CR 702.33d: "If a spell has two kicker costs or has multikicker, it may be
kicked multiple times." - "This creature enters with a +1/+1 counter on it for
each time it was kicked." counts the kicks recorded on the spell's cast record
(`CastRecord.kicked`), read as the permanent enters (CR 122.6: counters given
as it enters), never live afterwards. A permanent that was never cast has no
record and enters with none.

Printings: Chainweb Aracnir (three counters), Woe Strider (two) and
Underworld Rage-Hound (one) for "escapes with"; Flametongue Yearling, Gnarlid
Pack, Apex Hawks (+1/+1 per kick) and Everflowing Chalice (a charge counter
per kick) for the kicked count.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario

# -- escapes with -------------------------------------------------------------


def _fuel(n: int) -> list[str]:
    return ["Mishra's Bauble"] * n


def _escape(scenario, name: str, fuel_count: int, *lands: str):
    fuel = [c for c in scenario.player("alice").graveyard if c.name != name][:fuel_count]
    casting = scenario.cast(name, from_zone=Zone.GRAVEYARD)
    casting.use_keyword("Escape", choosing=fuel)
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources(*lands))
    spell = scenario.put_on_stack(casting)
    scenario.resolve_top()
    return spell


def test_chainweb_aracnir_escapes_with_three_counters():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            graveyard=["Chainweb Aracnir", *_fuel(4)],
            battlefield=["Forest"] * 5,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    spider = _escape(scenario, "Chainweb Aracnir", 4, *["Forest"] * 5)

    assert spider.zone is Zone.BATTLEFIELD
    assert spider.counter_count(Counter.PLUS_ONE) == 3
    assert (spider.power, spider.toughness) == (4, 5)  # a 1/2 with three counters


def test_chainweb_aracnir_cast_from_hand_enters_with_none():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Chainweb Aracnir"], battlefield=["Forest"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    spider = scenario.cast_and_resolve("Chainweb Aracnir", auto=True, username="alice")

    assert spider.zone is Zone.BATTLEFIELD
    assert spider.counter_count(Counter.PLUS_ONE) == 0


def test_woe_strider_escapes_with_two_counters():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", graveyard=["Woe Strider", *_fuel(4)], battlefield=["Swamp"] * 5)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    strider = _escape(scenario, "Woe Strider", 4, *["Swamp"] * 5)

    assert strider.counter_count(Counter.PLUS_ONE) == 2
    assert (strider.power, strider.toughness) == (5, 4)


def test_underworld_rage_hound_escapes_with_one_counter():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice", graveyard=["Underworld Rage-Hound", *_fuel(3)], battlefield=["Mountain"] * 4
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    hound = _escape(scenario, "Underworld Rage-Hound", 3, *["Mountain"] * 4)

    assert hound.counter_count(Counter.PLUS_ONE) == 1


def test_put_onto_the_battlefield_from_the_graveyard_is_not_escaping():
    """CR 702.138b: only a spell cast with escape escaped."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", graveyard=["Woe Strider"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    strider = scenario.find("Woe Strider", Zone.GRAVEYARD, "alice")
    scenario.player("alice").graveyard.remove(strider)

    scenario.game.put_onto_battlefield(strider, "alice")

    assert strider.counter_count(Counter.PLUS_ONE) == 0


def test_an_escaped_creature_that_is_blinked_comes_back_without_them():
    """CR 400.7: the returned object is new and was not cast at all."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", graveyard=["Woe Strider", *_fuel(4)], battlefield=["Swamp"] * 5)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    strider = _escape(scenario, "Woe Strider", 4, *["Swamp"] * 5)
    assert strider.counter_count(Counter.PLUS_ONE) == 2

    scenario.game.exile_permanent(strider)
    scenario.game.exile.remove(strider)
    scenario.game.put_onto_battlefield(strider, "alice")

    assert strider.counter_count(Counter.PLUS_ONE) == 0


# -- for each time it was kicked ---------------------------------------------


def _cast_kicked(scenario, name: str, kicks: int):
    card_state = scenario.find(name, Zone.HAND, "alice")
    lands = [s for s in scenario.game.battlefield if s.card.is_land and s.untapped]
    spell = scenario.game.cast(card_state, "alice", kicker=kicks, mana_sources=lands)
    assert scenario.game.cast_record(spell).kicked == kicks
    scenario.resolve_top()
    return spell


def _kick_board(name: str, lands: list[str]) -> Scenario:
    return Scenario().manual_turn_based_actions().player("alice", hand=[name], battlefield=lands)


def test_gnarlid_pack_kicked_twice_enters_with_two_counters():
    scenario = _kick_board("Gnarlid Pack", ["Forest"] * 6).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    pack = _cast_kicked(scenario, "Gnarlid Pack", 2)

    assert pack.zone is Zone.BATTLEFIELD
    assert pack.counter_count(Counter.PLUS_ONE) == 2
    assert (pack.power, pack.toughness) == (4, 4)


def test_gnarlid_pack_not_kicked_enters_with_none():
    scenario = _kick_board("Gnarlid Pack", ["Forest"] * 2).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    pack = _cast_kicked(scenario, "Gnarlid Pack", 0)

    assert pack.zone is Zone.BATTLEFIELD
    assert pack.counter_count(Counter.PLUS_ONE) == 0
    assert (pack.power, pack.toughness) == (2, 2)


def test_apex_hawks_kicked_once_enters_with_one_counter():
    scenario = _kick_board("Apex Hawks", ["Plains"] * 5).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    hawks = _cast_kicked(scenario, "Apex Hawks", 1)

    assert hawks.counter_count(Counter.PLUS_ONE) == 1


def test_flametongue_yearling_kicked_twice_enters_as_a_four_three():
    scenario = _kick_board("Flametongue Yearling", ["Mountain"] * 6).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    yearling = _cast_kicked(scenario, "Flametongue Yearling", 2)

    assert yearling.counter_count(Counter.PLUS_ONE) == 2
    assert (yearling.power, yearling.toughness) == (4, 3)  # a 2/1 with two counters


def test_everflowing_chalice_kicked_three_times_has_three_charge_counters():
    scenario = _kick_board("Everflowing Chalice", ["Island"] * 6).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    chalice = _cast_kicked(scenario, "Everflowing Chalice", 3)

    assert chalice.counter_count("charge") == 3


def test_a_permanent_that_was_never_cast_was_never_kicked():
    """No cast record: zero kicks, so no counters (CR 702.33d)."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", graveyard=["Gnarlid Pack"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    pack = scenario.find("Gnarlid Pack", Zone.GRAVEYARD, "alice")
    scenario.player("alice").graveyard.remove(pack)

    scenario.game.put_onto_battlefield(pack, "alice")

    assert pack.zone is Zone.BATTLEFIELD
    assert pack.counter_count(Counter.PLUS_ONE) == 0
