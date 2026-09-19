"""FRA stream S8: "Surveil `<n>`. If you put a `<quality>` card into your
graveyard this way, put that card into your hand." (CR 701.25a, CR 608.2c).

Every CR number below was looked up with `mise run rules:find` in the
session that wrote this file.

- **CR 701.25a** - surveil: look at the top N, then any number into the
  graveyard and the rest back on top.
- **CR 608.2c** - "this way" is anaphora onto exactly what the surveil just
  put into the graveyard - a fresh graveyard scan could not tell that card
  apart from one already sitting there.
- **CR 202.3** - mana value, for Enlightened Confidant's own dynamic
  ceiling.

Chandra, Chill of Compliance's own `+1` is the reported card - a plain,
static quality ("noncreature, nonland"). Enlightened Confidant (real,
non-FRA, non-pool, a Modern staple) is the off-set proof: the identical
surveil-then-conditional-hand shape with a genuinely different, *dynamic*
quality bound (a mana value ceiling read off `Game.life_gained_amount_
this_turn`, a new per-turn-history field this session added since nothing
before it recorded the actual life-gained amount, only whether any was
gained at all).
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_chandra_surveils_and_takes_a_noncreature_nonland_card():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Chandra, Chill of Compliance"],
            library=["Lightning Bolt", "Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    chandra = scenario.creature("Chandra, Chill of Compliance", "alice")
    alice = scenario.player("alice")
    bolt = alice.library[0]
    assert bolt.name == "Lightning Bolt"

    scenario.surveil_to_graveyard(bolt, username="alice")
    scenario.activate(chandra, index=0)
    scenario.pass_until_resolved()

    assert bolt.zone is Zone.HAND, "an instant is noncreature and nonland"


def test_chandra_leaves_a_land_in_the_graveyard_not_the_hand():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Chandra, Chill of Compliance"],
            library=["Forest", "Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    chandra = scenario.creature("Chandra, Chill of Compliance", "alice")
    alice = scenario.player("alice")
    forest = alice.library[0]
    assert forest.name == "Forest"

    scenario.surveil_to_graveyard(forest, username="alice")
    scenario.activate(chandra, index=0)
    scenario.pass_until_resolved()

    assert forest.zone is Zone.GRAVEYARD, "a land fails the nonland half"


def test_enlightened_confidant_reads_a_dynamic_mana_value_ceiling():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Enlightened Confidant"],
            library=["Lightning Bolt", "Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    bolt = alice.library[0]
    assert bolt.name == "Lightning Bolt" and bolt.mana_value == 1

    alice.gain_life(1)
    while scenario.step is not Step.END_STEP:
        scenario.advance()
    scenario.surveil_to_graveyard(bolt, username="alice")
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert bolt.zone is Zone.HAND, "1 life gained covers a mana value 1 card"


def test_enlightened_confidant_leaves_a_too_expensive_card_in_the_graveyard():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Enlightened Confidant"],
            library=["Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    bears = alice.library[0]
    assert bears.name == "Grizzly Bears" and bears.mana_value == 2

    alice.gain_life(1)
    while scenario.step is not Step.END_STEP:
        scenario.advance()
    scenario.surveil_to_graveyard(bears, username="alice")
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert bears.zone is Zone.GRAVEYARD, "mana value 2 exceeds the 1 life gained"
