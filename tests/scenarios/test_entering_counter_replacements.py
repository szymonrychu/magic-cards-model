"""Scenario: replacement effects on the counters a permanent enters with -
a planeswalker's loyalty, a battle's defense, a Saga's lore counter and an
ordinary "enters with N +1/+1 counters" creature, one family at a time.

The intrinsic entering counters are replacement effects of their own
(CR 614.1c), and placing them is the "counters being put on" event inside
the entering event (CR 616.1g) that CR 122.6 says counter replacements see.
So every family below has to reach all four permanent kinds alike, gated
only by what its own text names:

- **Doubling Season** - "twice that many of those counters" on a permanent
  you control: every kind.
- **Vorinclex, Monstrous Raider** - you put twice as many; an opponent puts
  half as many, rounded down. The opponent's own planeswalker is the corner:
  CR 122.6a makes its controller the one who puts its entering loyalty.
- **"that many plus one"** - Doc Samson, Super Psychiatrist (any kind, a
  permanent you control), Hardened Scales (+1/+1 only) and Winding
  Constrictor (an artifact or creature only).
- **Solemnity** - "Counters can't be put on artifacts, creatures,
  enchantments, or lands." A planeswalker and a battle are neither, so they
  still get theirs; a creature and a Saga get none. "Players can't get
  counters." stops a player's poison and energy.
- **Compleated** - its "that many minus two for each" is part of the
  entering event, so Doubling Season doubles what is left.

Every CR number here was looked up with `mise run rules:find` in the
session that wrote this file:

- **CR 306.5b** - a planeswalker's intrinsic "This permanent enters with a
  number of loyalty counters on it equal to its printed loyalty number",
  a replacement effect (CR 614.1c).
- **CR 310.4b** - a battle's same intrinsic ability for defense counters.
- **CR 714.3a** - a Saga's intrinsic "This Saga enters with a lore counter
  on it."
- **CR 614.1c** - "[This permanent] enters with ..." is a replacement
  effect.
- **CR 616.1g** - a replacement may apply to an event contained within the
  first event.
- **CR 122.6** / **CR 122.6a** - counters an object is given as it enters
  are counters put on it; with no player specified, its controller puts
  them.
- **CR 614.17a** - "can't" effects must exist before the event.
- **CR 702.150a** - compleated's "that many loyalty counters minus two for
  each of those mana symbols".
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario

WALKER = "Liliana of the Veil"
"""Printed loyalty 3."""
BATTLE = "Invasion of Zendikar"
"""Battle - Siege, printed defense 3."""
HYDRA = "Kalonian Hydra"
"""0/0, "This creature enters with four +1/+1 counters on it."."""
SAGA = "History of Benalia"
"""Chapter I and II each create a 2/2 vigilant Knight."""

DOUBLING = "Doubling Season"
VORINCLEX = "Vorinclex, Monstrous Raider"
SAMSON = "Doc Samson, Super Psychiatrist"
SCALES = "Hardened Scales"
CONSTRICTOR = "Winding Constrictor"
SOLEMNITY = "Solemnity"


def _enter(name: str, *, owner: str = "alice", **boards: list[str]):
    """`owner` puts `name` straight onto the battlefield (CR 110.2a) with
    `boards[player]` already in play; returns (scenario, permanent)."""
    scenario = (
        Scenario()
        .player(
            "alice", hand=[name] if owner == "alice" else [], battlefield=boards.get("alice", [])
        )
        .player("bob", hand=[name] if owner == "bob" else [], battlefield=boards.get("bob", []))
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    permanent = scenario.put_onto_battlefield(name, owner)
    return scenario, permanent


# -- the baseline: nothing replaces anything --------------------------------


def test_the_intrinsic_counters_with_no_replacement_in_play():
    assert _enter(WALKER)[1].counter_count(Counter.LOYALTY) == 3
    assert _enter(BATTLE)[1].counter_count(Counter.DEFENSE) == 3
    assert _enter(HYDRA)[1].counter_count(Counter.PLUS_ONE) == 4
    assert _enter(SAGA)[1].counter_count(Counter.LORE) == 1


# -- Doubling Season --------------------------------------------------------


def test_doubling_season_doubles_a_planeswalkers_entering_loyalty():
    _, walker = _enter(WALKER, alice=[DOUBLING])
    assert walker.counter_count(Counter.LOYALTY) == 6


def test_doubling_season_doubles_a_battles_entering_defense():
    _, battle = _enter(BATTLE, alice=[DOUBLING])
    assert battle.counter_count(Counter.DEFENSE) == 6


def test_doubling_season_doubles_a_creatures_entering_counters():
    _, hydra = _enter(HYDRA, alice=[DOUBLING])
    assert hydra.counter_count(Counter.PLUS_ONE) == 8


def test_doubling_season_gives_a_saga_two_lore_counters_and_both_chapters_trigger():
    """Two lore counters at once cross chapter I's and chapter II's
    thresholds together (CR 714.2b/CR 107.15a read "one or more lore counters
    ... put onto this Saga"), and the Season doubles each Knight too."""
    scenario, saga = _enter(SAGA, alice=[DOUBLING])
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()

    assert saga.counter_count(Counter.LORE) == 2
    knights = [p for p in scenario.game.battlefield if p.name == "Knight Token"]
    assert len(knights) == 4, "two chapters, each Knight doubled by the same Season"


def test_an_opponents_doubling_season_doubles_none_of_your_entering_counters():
    """ "on a permanent you control" - bob's walker and battle are his."""
    _, walker = _enter(WALKER, owner="bob", alice=[DOUBLING])
    _, battle = _enter(BATTLE, owner="bob", alice=[DOUBLING])
    assert walker.counter_count(Counter.LOYALTY) == 3
    assert battle.counter_count(Counter.DEFENSE) == 3


def test_two_doubling_seasons_quadruple_a_planeswalkers_loyalty():
    """CR 614.5: each applies once to the one entering-counters event."""
    _, walker = _enter(WALKER, alice=[DOUBLING, DOUBLING])
    assert walker.counter_count(Counter.LOYALTY) == 12


def test_the_doubled_counters_are_one_counters_put_event_the_walker_can_use():
    """The doubled loyalty is real loyalty: a 6-loyalty Liliana survives
    losing 3 in a way a 3-loyalty one would not (CR 704.5i)."""
    scenario, walker = _enter(WALKER, alice=[DOUBLING])
    walker.remove_counters(Counter.LOYALTY, 3)
    scenario.game.check_state_based_actions()
    assert walker.zone is Zone.BATTLEFIELD


# -- Vorinclex, Monstrous Raider --------------------------------------------


def test_vorinclex_doubles_your_planeswalkers_loyalty():
    _, walker = _enter(WALKER, alice=[VORINCLEX])
    assert walker.counter_count(Counter.LOYALTY) == 6


def test_vorinclex_doubles_your_battles_defense():
    _, battle = _enter(BATTLE, alice=[VORINCLEX])
    assert battle.counter_count(Counter.DEFENSE) == 6


def test_vorinclex_doubles_your_creatures_entering_counters():
    _, hydra = _enter(HYDRA, alice=[VORINCLEX])
    assert hydra.counter_count(Counter.PLUS_ONE) == 8


def test_vorinclex_halves_an_opponents_planeswalker_rounded_down():
    """CR 122.6a: bob controls his Liliana, so bob puts its three loyalty
    counters - "an opponent would put", half of three rounded down is one."""
    _, walker = _enter(WALKER, owner="bob", alice=[VORINCLEX])
    assert walker.counter_count(Counter.LOYALTY) == 1


def test_vorinclex_halves_an_opponents_battle_and_creature():
    _, battle = _enter(BATTLE, owner="bob", alice=[VORINCLEX])
    _, hydra = _enter(HYDRA, owner="bob", alice=[VORINCLEX])
    assert battle.counter_count(Counter.DEFENSE) == 1
    assert hydra.counter_count(Counter.PLUS_ONE) == 2


def test_vorinclex_halving_one_counter_leaves_none():
    """Half of one, rounded down, is zero: an opponent's Saga enters with no
    lore counter at all, so its chapter I never triggers."""
    scenario, saga = _enter(SAGA, owner="bob", alice=[VORINCLEX])
    scenario.game.put_triggers_on_stack()
    assert saga.counter_count(Counter.LORE) == 0
    assert not scenario.game.stack


def test_vorinclex_doubles_a_players_counters_you_give_yourself():
    """ "on a permanent or player" - the player half, through the same door
    poison and energy use (`Game.add_player_counters`)."""
    scenario, _ = _enter(WALKER, alice=[VORINCLEX])
    scenario.game.add_player_counters("alice", Counter.ENERGY, 2)
    assert scenario.game.player("alice").counter_count(Counter.ENERGY) == 4


# -- "that many plus one" ---------------------------------------------------


def test_doc_samson_adds_one_loyalty_and_one_defense():
    _, walker = _enter(WALKER, alice=[SAMSON])
    _, battle = _enter(BATTLE, alice=[SAMSON])
    _, hydra = _enter(HYDRA, alice=[SAMSON])
    assert walker.counter_count(Counter.LOYALTY) == 4
    assert battle.counter_count(Counter.DEFENSE) == 4
    assert hydra.counter_count(Counter.PLUS_ONE) == 5


def test_hardened_scales_adds_only_to_plus_one_counters():
    """ "+1/+1 counters would be put on a creature you control" - loyalty
    and defense are neither the kind nor on a creature."""
    _, walker = _enter(WALKER, alice=[SCALES])
    _, battle = _enter(BATTLE, alice=[SCALES])
    _, hydra = _enter(HYDRA, alice=[SCALES])
    assert walker.counter_count(Counter.LOYALTY) == 3
    assert battle.counter_count(Counter.DEFENSE) == 3
    assert hydra.counter_count(Counter.PLUS_ONE) == 5


def test_winding_constrictor_reaches_only_artifacts_and_creatures():
    _, walker = _enter(WALKER, alice=[CONSTRICTOR])
    _, battle = _enter(BATTLE, alice=[CONSTRICTOR])
    _, hydra = _enter(HYDRA, alice=[CONSTRICTOR])
    assert walker.counter_count(Counter.LOYALTY) == 3
    assert battle.counter_count(Counter.DEFENSE) == 3
    assert hydra.counter_count(Counter.PLUS_ONE) == 5


def test_plus_one_then_doubling_in_the_order_the_controller_picks():
    """CR 616.1: alice orders them. Doubling Season first then Doc Samson is
    3 -> 6 -> 7; the reverse is 3 -> 4 -> 8. The harness's default order is
    whichever the controller is asked about first, so assert it is one of
    the two legal results and never the unmodified or singly-modified one."""
    _, walker = _enter(WALKER, alice=[SAMSON, DOUBLING])
    assert walker.counter_count(Counter.LOYALTY) in (7, 8)


# -- Solemnity ----------------------------------------------------------------


def test_solemnity_leaves_a_planeswalkers_loyalty_alone():
    """Planeswalker is not among "artifacts, creatures, enchantments, or
    lands", so CR 306.5b's counters are still put on."""
    _, walker = _enter(WALKER, bob=[SOLEMNITY])
    assert walker.counter_count(Counter.LOYALTY) == 3


def test_solemnity_leaves_a_battles_defense_alone():
    _, battle = _enter(BATTLE, bob=[SOLEMNITY])
    assert battle.counter_count(Counter.DEFENSE) == 3


def test_solemnity_stops_a_creatures_entering_counters_and_it_dies():
    """CR 614.17a: Solemnity was already there, so the Hydra enters with no
    counters, a 0/0, and CR 704.5f puts it into the graveyard."""
    scenario, hydra = _enter(HYDRA, bob=[SOLEMNITY])
    assert hydra.counter_count(Counter.PLUS_ONE) == 0
    scenario.game.check_state_based_actions()
    assert hydra.zone is Zone.GRAVEYARD


def test_solemnity_beats_doubling_season():
    """No counters are put at all, so there is nothing to double."""
    _, hydra = _enter(HYDRA, alice=[DOUBLING], bob=[SOLEMNITY])
    assert hydra.counter_count(Counter.PLUS_ONE) == 0


def test_solemnity_stops_a_sagas_lore_counter_and_its_chapter_one():
    scenario, saga = _enter(SAGA, bob=[SOLEMNITY])
    scenario.game.put_triggers_on_stack()
    assert saga.counter_count(Counter.LORE) == 0
    assert not scenario.game.stack


def test_solemnity_stops_counters_on_a_permanent_already_there():
    scenario, walker = _enter(WALKER, alice=[HYDRA], bob=[SOLEMNITY])
    hydra = scenario.creature(HYDRA, "alice")
    before = hydra.counter_count(Counter.PLUS_ONE)
    scenario.game.add_counters(hydra, Counter.PLUS_ONE, 2)
    scenario.game.add_counters(walker, Counter.LOYALTY, 1)
    assert hydra.counter_count(Counter.PLUS_ONE) == before
    assert walker.counter_count(Counter.LOYALTY) == 4


def test_solemnity_stops_players_getting_counters():
    """ "Players can't get counters." - poison and energy alike, for both
    players (the line is symmetric)."""
    scenario, _ = _enter(WALKER, bob=[SOLEMNITY])
    scenario.game.add_player_counters("alice", Counter.POISON, 3)
    scenario.game.add_player_counters("bob", Counter.ENERGY, 2)
    assert scenario.game.player("alice").counter_count(Counter.POISON) == 0
    assert scenario.game.player("bob").counter_count(Counter.ENERGY) == 0


def test_solemnity_gone_counters_flow_again():
    """CR 604.2 / 611.3a: the prohibition lasts only while Solemnity is on
    the battlefield."""
    scenario, _ = _enter(WALKER, bob=[SOLEMNITY])
    solemnity = next(p for p in scenario.game.battlefield if p.name == SOLEMNITY)
    scenario.game.put_into_graveyard(solemnity)
    scenario.game.add_player_counters("alice", Counter.POISON, 3)
    assert scenario.game.player("alice").counter_count(Counter.POISON) == 3


# -- compleated, then doubled -------------------------------------------------


def test_compleated_reduction_happens_before_doubling_season_doubles():
    """CR 702.150a modifies the entering event itself ("enters with that many
    loyalty counters minus two for each"); CR 616.1g's contained counters
    event is what Doubling Season doubles. Nissa, Ascended Animist (7) with
    both Phyrexian symbols paid with life enters with 7 - 4 = 3, doubled to 6
    - not 7 doubled to 14 then reduced to 10."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Nissa, Ascended Animist"],
            battlefield=[DOUBLING, "Forest", "Forest", "Forest", "Forest", "Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    lands = scenario.untapped_sources(*["Forest"] * 5)
    nissa = scenario.cast_and_resolve("Nissa, Ascended Animist", *lands)
    assert nissa.counter_count(Counter.LOYALTY) == 6


# -- the same "permanent or player" line on a second printing --------------


def test_innkeepers_talent_level_three_doubles_a_planeswalkers_loyalty():
    """Innkeeper's Talent's level 3 prints Vorinclex's first line word for
    word; below level 3 the Class does not have it (CR 716.2a)."""
    scenario = (
        Scenario()
        .player("alice", hand=[WALKER, BATTLE], battlefield=["Innkeeper's Talent"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    talent = scenario.find("Innkeeper's Talent", Zone.BATTLEFIELD, "alice")

    battle = scenario.put_onto_battlefield(BATTLE, "alice")
    talent.class_level = 3
    walker = scenario.put_onto_battlefield(WALKER, "alice")

    assert battle.counter_count(Counter.DEFENSE) == 3
    assert walker.counter_count(Counter.LOYALTY) == 6
