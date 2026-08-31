"""Scenario: a life total raised above the starting 20, and damage taken off it.

CR 119.1 sets the starting life total at 20 and nothing caps it there: CR 119.3
adjusts the total by whatever an effect gains or loses, so a player who gains
four life is at 24 and stays at 24. Damage then subtracts from *that* total -
CR 119.2 and CR 120.3a make damage dealt to a player by a source without infect
a loss of that much life - so one point of damage to a player at 24 leaves 23,
never 19.

That is the arithmetic a live game called into question: prison-tron pinged a
boros-energy player who had gained life off Guide of Souls several times, and
the reported life afterwards read as though the total had been reset to 20 and
then reduced by 1. This file plays the whole reported sequence with the real
cards - the Guide triggers on an earlier turn, an All Is Dust wipe (CR 701.21a)
that removes every source of the gain, Karn fetching Walking Ballista from
outside the game (CR 400.11a, 108.3b), the Ballista cast for X (CR 107.3a) and
its counter-removal ability activated at the face (CR 602.2) - and asserts the
life total the whole way through. The engine gets it right at every step; the
file stays as the regression that would catch a reset.

The corner cases around it: the gain and the damage in the same turn against
the gain a turn earlier, a player at exactly 20, and a player already below it.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone

from .harness import Scenario

# Guide of Souls: "Whenever another creature you control enters, you gain 1 life
# and get {E}" - three Savannah Lions is three life (CR 603.3 puts each trigger
# on the stack, CR 119.3 adjusts the total).
LIONS = 3


def boros_and_a_ballista(boros_life: int = 20) -> Scenario:
    """`tron` takes the first turn with a Ballista to point at a face; `boros`
    has Guide of Souls and the Lions to trigger it."""
    return (
        Scenario()
        .player(
            "tron",
            library=["Wastes"] * 10,
            battlefield=["Wastes"] * 4,
            hand=["Walking Ballista"],
        )
        .player(
            "boros",
            life=boros_life,
            library=["Plains"] * 10,
            battlefield=["Guide of Souls"] + ["Plains"] * LIONS,
            hand=["Savannah Lions"] * LIONS,
        )
    )


def life(scenario) -> dict[str, int]:
    return {player.username: player.life for player in scenario.game.players}


def drain(scenario) -> None:
    """Resolve everything waiting on the stack, triggers included (CR 603.3)."""
    while scenario.stack_names():
        scenario.resolve_top()


def to_main(scenario, username: str) -> None:
    """Walk the turn machine to that player's precombat main phase."""
    for _ in range(40):
        drain(scenario)
        scenario.advance()
        drain(scenario)
        if (
            scenario.game.active_player.username == username
            and scenario.step is Step.PRECOMBAT_MAIN
        ):
            return
    raise AssertionError(f"never reached a main phase for {username}")


def gain_with_lions(scenario, count: int = LIONS) -> None:
    """Cast `count` Savannah Lions, letting every Guide trigger resolve."""
    for _ in range(count):
        scenario.cast_and_resolve(
            "Savannah Lions", *scenario.untapped_sources("Plains", username="boros")
        )
        drain(scenario)


def ballista_on_the_battlefield(scenario, counters: int = 2):
    """A Walking Ballista under `tron` with `counters` +1/+1 counters on it.

    Staged rather than cast, so the tests that are about the life total do not
    also depend on X (CR 107.3a) - the sequence test below casts one for real.
    """
    ballista = scenario.put_onto_battlefield("Walking Ballista", "tron")
    ballista.add_counters("+1/+1", counters)
    return ballista


def ping(scenario, ballista, target: str = "boros") -> None:
    """Activate "Remove a +1/+1 counter from this creature: It deals 1 damage to
    any target" at a player (CR 602.2), and resolve it."""
    if scenario.priority_holder != "tron":
        scenario.pass_priority(scenario.priority_holder)
    scenario.activate(ballista, username="tron", index=1, targets=[target])
    drain(scenario)


def test_three_guide_triggers_put_the_life_total_above_twenty():
    """CR 119.1's starting 20 is not a ceiling: CR 119.3 just adjusts (20 -> 23)."""
    scenario = boros_and_a_ballista().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    to_main(scenario, "boros")

    gain_with_lions(scenario)

    assert life(scenario)["boros"] == 20 + LIONS


def test_a_ping_takes_one_off_a_life_total_above_twenty():
    """The reported bug: 23 - 1 is 22, not 19 (CR 119.2, 120.3a).

    Gain and damage in the same turn, which is the tightest form of it.
    """
    scenario = boros_and_a_ballista().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    to_main(scenario, "boros")
    gain_with_lions(scenario)
    assert life(scenario)["boros"] == 23

    ping(scenario, ballista_on_the_battlefield(scenario))

    assert life(scenario)["boros"] == 22


def test_a_life_total_above_twenty_survives_the_turn_passing():
    """The gain was on an earlier turn than the damage, as in the live game.

    Nothing about a new turn resets a life total - CR 119.3 changed it and only
    another gain or loss changes it back.
    """
    scenario = boros_and_a_ballista().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    to_main(scenario, "boros")
    gain_with_lions(scenario)
    assert life(scenario)["boros"] == 23

    to_main(scenario, "tron")
    assert life(scenario)["boros"] == 23, "a turn boundary is not a life reset"

    ping(scenario, ballista_on_the_battlefield(scenario))

    assert life(scenario)["boros"] == 22


def test_a_ping_at_exactly_twenty_leaves_nineteen():
    """The same activation with no life gained at all - the total the bug's
    symptom looked like (CR 119.1, 119.2)."""
    scenario = boros_and_a_ballista().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    assert life(scenario)["boros"] == 20

    ping(scenario, ballista_on_the_battlefield(scenario))

    assert life(scenario)["boros"] == 19


def test_a_ping_below_twenty_takes_one_more():
    """Below the starting total the arithmetic is the same (CR 119.3)."""
    scenario = boros_and_a_ballista(boros_life=7).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    ping(scenario, ballista_on_the_battlefield(scenario))

    assert life(scenario)["boros"] == 6


def test_two_pings_from_one_ballista_take_two():
    """Each activation removes a counter of its own (CR 602.2's cost) and each
    deals its own 1 damage: 23 -> 21."""
    scenario = boros_and_a_ballista().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    to_main(scenario, "boros")
    gain_with_lions(scenario)

    ballista = ballista_on_the_battlefield(scenario)
    ping(scenario, ballista)
    ping(scenario, ballista)

    assert life(scenario)["boros"] == 21
    assert ballista.counters["+1/+1"] == 0


def test_the_whole_reported_sequence_keeps_the_gained_life():
    """The live game end to end, with the real cards it was played with.

    Boros gains life off Guide of Souls (Ajani, Nacatl Pariah and its Cat token
    are two entering creatures, Ocelot Pride a third, and Ocelot Pride's own end
    step trigger makes a fourth), tron wipes the colored board with All Is Dust
    (CR 701.21a), fetches Walking Ballista from outside the game with Karn's
    -2 (CR 400.11a: the sideboard is outside the game; CR 108.3b lets an effect
    bring a card you own in), casts it for X=1 (CR 107.3a) and pings the face.

    The life gained on turn 2 is still there on turn 3 - the wipe took the Guide
    away, not the life - so the ping reads 24 -> 23.
    """
    scenario = (
        Scenario()
        .player(
            "tron",
            library=["Wastes"] * 20,
            battlefield=["Wastes"] * 9,
            hand=["All Is Dust", "Karn, the Great Creator"],
            sideboard=["Walking Ballista"],
        )
        .player(
            "boros",
            library=["Plains"] * 20,
            battlefield=["Guide of Souls"] + ["Plains"] * 4,
            hand=["Ajani, Nacatl Pariah", "Ocelot Pride"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    to_main(scenario, "boros")
    scenario.cast_and_resolve(
        "Ajani, Nacatl Pariah", *scenario.untapped_sources("Plains", "Plains", username="boros")
    )
    drain(scenario)
    scenario.cast_and_resolve(
        "Ocelot Pride", *scenario.untapped_sources("Plains", username="boros")
    )
    drain(scenario)
    assert life(scenario)["boros"] == 23, "Ajani, its Cat token and Ocelot Pride"

    to_main(scenario, "tron")
    assert life(scenario)["boros"] == 24, "Ocelot Pride's end step Cat is a fourth trigger"

    scenario.cast_and_resolve("All Is Dust", *scenario.untapped_sources(*(["Wastes"] * 7)))
    drain(scenario)
    assert "Guide of Souls" not in scenario.battlefield_names()
    assert life(scenario)["boros"] == 24, "the wipe takes permanents, not life"

    to_main(scenario, "tron")
    karn = scenario.cast_and_resolve(
        "Karn, the Great Creator", *scenario.untapped_sources(*(["Wastes"] * 4))
    )
    drain(scenario)
    scenario.activate(karn, index=1, username="tron")  # -2: from outside the game
    drain(scenario)
    assert scenario.find("Walking Ballista", Zone.HAND, "tron")

    casting = scenario.cast("Walking Ballista", "tron")
    casting.determine_cost(x_value=1)
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources(*(["Wastes"] * 2)))
    scenario.put_on_stack(casting)
    ballista = scenario.resolve_top()
    drain(scenario)
    assert ballista.counters["+1/+1"] == 1, "enters with X counters"

    ping(scenario, ballista)

    assert life(scenario)["boros"] == 23
