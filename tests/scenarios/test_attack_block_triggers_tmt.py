"""Scenario: attack/block triggers from Teenage Mutant Ninja Turtles (round
271-tmt).

- **Bebop & Rocksteady**: "Whenever Bebop & Rocksteady attack or block,
  sacrifice a permanent unless you discard a card." CR 118.12a: "Some spells,
  activated abilities, and triggered abilities read, '[Do something] unless
  [a player does something else].' This means the same thing as '[A player
  may do something else]. If [that player doesn't], [do something].'" Two
  widened pieces: `machines/triggers._expand_attacks_or_blocks` only ever read
  "this `<kind>` attacks or blocks" (singular verb, "this creature"/"this
  Vehicle" self-reference) - a legendary's own comma-joined name ("Bebop &
  Rocksteady") self-references with the *plural* verb form ("attack or
  block", no trailing "s"), which the compound splitter never recognised, so
  only the "attacks" half ever fired and "or block" was silently dropped.
  Proved general on Molten-Tail Masticore's differently-shaped "sacrifice this
  creature unless you discard a card" (an upkeep trigger, self-sacrifice
  rather than "a permanent") - Modern legal, not a listed card, not in any
  deck list, verified with `resolve_cards`/Scryfall this session, 2026-09-27.
- **Wingnut, Bat on the Belfry**: Alliance - "Wingnut gains your choice of
  flying, menace, or haste until end of turn." (a self-referential choice,
  the un-anaphoric twin of `effects._RIDER_KEYWORD_CHOICE_RE`'s targeted
  "`<it>` gains your choice of ... until end of turn.") and "Whenever Wingnut
  attacks, each other attacking creature gets +1/+0 until end of turn." -
  CR 702.91a's Battle cry effect, written out as plain, unkeyworded text
  rather than reached through the keyword itself.
- **Ravenous Robots**: "{R}, {T}: Creature tokens you control gain haste
  until end of turn." - a mass keyword grant filtered to tokens.

Every CR number was looked up with `mise run rules:find <n>` this session.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone

from .harness import Scenario

# --------------------------------------------------------------------------
# Bebop & Rocksteady - "attack or block, sacrifice a permanent unless you
# discard a card" (CR 118.12a)
# --------------------------------------------------------------------------


def test_bebop_and_rocksteady_attack_trigger_discards_to_avoid_sacrifice():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Bolt"],
            battlefield=["Bebop & Rocksteady", "Mountain"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    bebop = scenario.creature("Bebop & Rocksteady")
    scenario.will_discard(scenario.find("Lightning Bolt", Zone.HAND, "alice"))
    scenario.attack_with(bebop)
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()

    assert scenario.find("Lightning Bolt", Zone.GRAVEYARD, "alice") is not None
    assert bebop.zone is Zone.BATTLEFIELD, "Mountain was never asked to be sacrificed"
    assert scenario.find("Mountain", Zone.BATTLEFIELD, "alice") is not None


def test_bebop_and_rocksteady_attack_trigger_sacrifices_when_declining_to_discard():
    scenario = (
        Scenario()
        .player("alice", hand=["Lightning Bolt"], battlefield=["Bebop & Rocksteady", "Mountain"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    bebop = scenario.creature("Bebop & Rocksteady")
    mountain = scenario.creature("Mountain")
    scenario.will_take_the_may(False)  # declines the discard
    scenario.attack_with(bebop)
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()

    assert scenario.find("Lightning Bolt", Zone.HAND, "alice") is not None
    assert mountain.zone is Zone.GRAVEYARD


def test_bebop_and_rocksteady_block_trigger_also_fires():
    """The "or block" half of the compound self-reference, previously
    silently dropped for a comma-joined legendary name."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Hill Giant"])
        .player("bob", hand=["Lightning Bolt"], battlefield=["Bebop & Rocksteady", "Mountain"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    giant = scenario.creature("Hill Giant")
    bebop = scenario.creature("Bebop & Rocksteady", "bob")
    scenario.will_discard(scenario.find("Lightning Bolt", Zone.HAND, "bob"))
    scenario.attack_with(giant, defending="bob")
    scenario.block(giant, bebop)
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()

    assert scenario.find("Lightning Bolt", Zone.GRAVEYARD, "bob") is not None


def test_molten_tail_masticore_proves_the_same_unless_discard_template():
    """A second, differently-shaped printing of "sacrifice `<X>` unless you
    discard a card" - self-sacrifice rather than "a permanent", an upkeep
    trigger rather than an attack/block one."""
    scenario = (
        Scenario()
        .player("alice", hand=["Lightning Bolt"], battlefield=["Molten-Tail Masticore"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.UNTAP)
    masticore = scenario.creature("Molten-Tail Masticore")
    scenario.will_take_the_may(False)
    scenario.advance()  # untap -> upkeep, raising "at the beginning of your upkeep"
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()

    assert masticore.zone is Zone.GRAVEYARD


def test_molten_tail_masticore_survives_when_the_player_discards():
    scenario = (
        Scenario()
        .player("alice", hand=["Lightning Bolt"], battlefield=["Molten-Tail Masticore"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.UNTAP)
    masticore = scenario.creature("Molten-Tail Masticore")
    scenario.will_discard(scenario.find("Lightning Bolt", Zone.HAND, "alice"))
    scenario.advance()  # untap -> upkeep
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()

    assert masticore.zone is Zone.BATTLEFIELD
    assert scenario.find("Lightning Bolt", Zone.GRAVEYARD, "alice") is not None


# --------------------------------------------------------------------------
# Wingnut, Bat on the Belfry - Alliance choice, and battle-cry-shaped pump
# --------------------------------------------------------------------------


def test_wingnut_alliance_gains_the_chosen_keyword_until_end_of_turn():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Llanowar Elves"],
            battlefield=["Wingnut, Bat on the Belfry", "Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    wingnut = scenario.creature("Wingnut, Bat on the Belfry")
    (forest,) = scenario.untapped_sources("Forest")
    scenario.will_choose("Flying", source="Wingnut, Bat on the Belfry")
    scenario.cast_and_resolve("Llanowar Elves", forest)
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()

    board = scenario.game.computed_board()
    assert board.of(wingnut).has_ability("Flying")


def test_wingnut_attack_pumps_each_other_attacking_creature():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Wingnut, Bat on the Belfry", "Grizzly Bears", "Hill Giant"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    wingnut = scenario.creature("Wingnut, Bat on the Belfry")
    bears = scenario.creature("Grizzly Bears")
    giant = scenario.creature("Hill Giant")
    scenario.attack_with(wingnut, bears, giant)
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()

    board = scenario.game.computed_board()
    assert board.of(bears).power_toughness == (3, 2)
    assert board.of(giant).power_toughness == (4, 3)
    assert board.of(wingnut).power_toughness == (1, 2), "never itself - CR 702.91a's 'other'"


# --------------------------------------------------------------------------
# Ravenous Robots - "{R}, {T}: Creature tokens you control gain haste until
# end of turn."
# --------------------------------------------------------------------------


def test_ravenous_robots_grants_haste_to_a_fresh_token_but_not_a_fresh_nontoken():
    """Ravenous Robots' own first ability makes the token to test against -
    "Whenever you cast an artifact spell, create a 1/1 colorless Robot
    artifact creature token" - so both the token and Ornithopter itself enter
    the same turn, summoning sick (CR 302.6); only the haste grant's own
    "creature tokens" filter should let the token attack anyway."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Ornithopter"],
            battlefield=["Ravenous Robots", "Mountain"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    robots = scenario.creature("Ravenous Robots")
    (mountain,) = scenario.untapped_sources("Mountain")
    scenario.cast_onto_stack("Ornithopter")
    scenario.game.put_triggers_on_stack()
    while scenario.stack_names():
        scenario.resolve_top()
    ornithopter = scenario.creature("Ornithopter")
    (robot_token,) = [
        state
        for state in scenario.all_card_states()
        if state.name == "Robot Token" and state.zone is Zone.BATTLEFIELD
    ]
    assert robot_token.summoning_sick
    assert ornithopter.summoning_sick

    scenario.advance()  # precombat main -> declare attackers
    assert scenario.can_attack(robot_token) is False, "no haste yet"
    assert scenario.can_attack(ornithopter) is False

    scenario.activate(robots, mountain)
    scenario.resolve_top()

    assert scenario.can_attack(robot_token) is True, "creature tokens you control gain haste"
    assert scenario.can_attack(ornithopter) is False, "Ornithopter is not a token"
