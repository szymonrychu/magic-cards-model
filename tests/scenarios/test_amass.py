"""Scenario: amass (CR 701.47), the keyword action Orcish Bowmasters ends on.

Read out of the Comprehensive Rules on disk this session with `mise run
rules:find 701.47`:

- **CR 701.47a** - "To amass [subtype] N means 'If you don't control an Army
  creature, create a 0/0 black [subtype] Army creature token. Choose an Army
  creature you control. Put N +1/+1 counters on that creature. If it isn't a
  [subtype], it becomes a [subtype] in addition to its other types.'"
- **CR 701.47b** - "A player 'amassed' after the process described in rule
  701.47a is complete, even if some or all of those actions were impossible."
- **CR 701.47c** - "The phrases 'the Army you amassed' and 'the amassed Army'
  refer to the creature you chose, whether or not it received counters."
- **CR 608.2d** - "If an effect of a spell or ability offers any choices other
  than choices already made as part of casting the spell ... the player
  announces these while applying the effect" - "Choose an Army creature you
  control" is exactly such a choice, and it is only *asked* when there is more
  than one to choose between.
- **CR 613.4c** - +1/+1 counters apply in sublayer 7c, on top of the token's
  own 0/0, so one counter on a fresh Army is unconditionally a 1/1.
- **CR 205.1b** - "in addition to its other types" is an addition, never a
  replacement, so an existing Army keeps whatever it already was.

Orcish Bowmasters is the vehicle - "When this creature enters and whenever an
opponent draws a card except the first one they draw in each of their draw
steps, this creature deals 1 damage to any target. Then amass Orcs 1." - and
it was silent on **both** counts before this: the sentence-initial "Then" made
the second clause unreadable, which correctly refused the damage too (CR
608.2c), and nothing anywhere in the engine knew what amass meant.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.keywords import executes
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter

from .harness import Scenario


def test_amass_is_reported_as_executed_by_the_pool_sweeper():
    """A CR 701 keyword action embedded in another ability's effect text, the
    same shape earthbend and airbend already are: the clause parser lives in
    `machines/effects.py`, but `scripts/sweep_pool.py` reads
    `machines/keywords.executes` and cannot tell "known and ignored" from
    "unknown" without being told."""
    assert executes("Amass") is True
    assert executes("amass") is True


def test_orcish_bowmasters_deals_damage_and_amasses():
    """The whole trigger, both clauses. With no Army on the battlefield, CR
    701.47a creates a 0/0 black Orc Army token and puts the one counter on
    it - a 1/1 (CR 613.4c) - and the damage half fires too.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Orcish Bowmasters"], battlefield=["Swamp", "Swamp"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.choose_trigger_targets("Orcish Bowmasters", [bears])

    sources = scenario.untapped_sources("Swamp", "Swamp")
    scenario.cast_and_resolve("Orcish Bowmasters", *sources)
    scenario.pass_until_resolved()

    assert bears.damage == 1
    army = scenario.creature("Orc Army Token", "alice")
    assert army.counters[Counter.PLUS_ONE] == 1
    assert scenario.game.power_of(army) == 1
    assert scenario.game.toughness_of(army) == 1


def test_the_amassed_army_is_a_black_orc_army_creature_token():
    """CR 701.47a states every characteristic of the token it creates, and CR
    111.3 says a token has none it was not given."""
    scenario = (
        Scenario()
        .player("alice", hand=["Orcish Bowmasters"], battlefield=["Swamp", "Swamp"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.choose_trigger_targets("Orcish Bowmasters", [bears])

    sources = scenario.untapped_sources("Swamp", "Swamp")
    scenario.cast_and_resolve("Orcish Bowmasters", *sources)
    scenario.pass_until_resolved()

    army = scenario.creature("Orc Army Token", "alice")
    characteristics = scenario.game.characteristics_of(army)
    assert characteristics.is_creature
    assert "Orc" in characteristics.subtypes
    assert "Army" in characteristics.subtypes
    assert [color.value for color in characteristics.colors] == ["B"]


def test_a_second_amass_grows_the_same_army_rather_than_making_another():
    """ "If you don't control an Army creature, create ..." - the condition is
    the whole point of the keyword: the second amass finds the Army already
    there, makes no token, and puts its counter on that one instead.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Orcish Bowmasters", "Orcish Bowmasters"],
            battlefield=["Swamp"] * 4,
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")

    scenario.choose_trigger_targets("Orcish Bowmasters", [bears])
    first_pair = scenario.untapped_sources("Swamp", "Swamp")
    scenario.cast_and_resolve("Orcish Bowmasters", *first_pair)
    scenario.pass_until_resolved()

    scenario.choose_trigger_targets("Orcish Bowmasters", [bears])
    second_pair = scenario.untapped_sources("Swamp", "Swamp")
    scenario.cast_and_resolve("Orcish Bowmasters", *second_pair)
    scenario.pass_until_resolved()

    armies = [
        state
        for state in scenario.game.permanents_controlled_by("alice")
        if state.name == "Orc Army Token"
    ]
    assert len(armies) == 1
    assert armies[0].counters[Counter.PLUS_ONE] == 2
    assert bears.zone is Zone.GRAVEYARD  # two 1-damage pings killed a 2/2


def test_an_opponents_army_is_not_yours_to_amass():
    """ "an Army creature **you control**" - Alice's Army is invisible to
    Bob's amass, so Bob gets a token of his own rather than growing hers.
    Orcish Bowmasters has flash, so both casts fit in Alice's main phase.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Orcish Bowmasters"], battlefield=["Swamp", "Swamp"])
        .player("bob", hand=["Orcish Bowmasters"], battlefield=["Swamp", "Swamp"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice_bears = scenario.player("alice")
    scenario.choose_trigger_targets("Orcish Bowmasters", ["bob"])
    scenario.cast_and_resolve("Orcish Bowmasters", *scenario.untapped_sources("Swamp", "Swamp"))
    scenario.pass_until_resolved()

    scenario.pass_priority()  # bob now holds priority, and Bowmasters has flash
    scenario.choose_trigger_targets("Orcish Bowmasters", ["alice"])
    scenario.cast_and_resolve(
        "Orcish Bowmasters",
        *scenario.untapped_sources("Swamp", "Swamp", username="bob"),
        username="bob",
    )
    scenario.pass_until_resolved()

    alice_army = scenario.creature("Orc Army Token", "alice")
    bob_army = scenario.creature("Orc Army Token", "bob")
    assert alice_army is not bob_army
    assert alice_army.counters[Counter.PLUS_ONE] == 1
    assert bob_army.counters[Counter.PLUS_ONE] == 1
    assert alice_bears.life == 19
    assert scenario.player("bob").life == 19


def test_commence_the_endgame_reads_amass_x_where_x_is_defined_by_the_card():
    """Commence the Endgame (off-pool, added with `scripts/add_card.py`,
    verified against its own printed text): "This spell can't be countered.
    Draw two cards, then amass Zombies X, where X is the number of cards in
    your hand."

    X is CR 107.3f's own defined X - `_fixed_or_where_x_amount` reads it
    through `machines/effects.amount_expression`, the same way Rockalanche's
    own earthbend X is - and CR 608.2c's "in the order written" is why it has
    to be counted *after* the draw: the two cards just drawn are already in
    hand by the time this clause runs, so X is not merely "the number of
    cards you started with."
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Commence the Endgame", "Forest", "Island"],
            battlefield=["Island"] * 6,
            library=["Mountain", "Swamp"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources(*["Island"] * 6)

    scenario.cast_and_resolve("Commence the Endgame", *sources)

    # Casting removed the spell (3 -> 2), the draw added two (2 -> 4).
    assert len(scenario.player("alice").hand) == 4
    army = scenario.creature("Zombie Army Token", "alice")
    assert army.counters[Counter.PLUS_ONE] == 4
    assert scenario.game.power_of(army) == 4
    assert scenario.game.toughness_of(army) == 4
