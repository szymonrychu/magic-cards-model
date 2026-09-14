"""Scenario: a count a card spells out past ten is still a count.

Every oracle-text parser used to carry its own table of number words, and most
stopped at "ten". A card printing "thirteen" or "twelve" was read as if the
clause were not there at all - silent in `scripts/sweep_pool.py --effects`,
doing nothing in a game. `magic_cards_model.numbers` is now the one reader
every parser delegates to, so these read without any card-specific code.

The cards (texts from their Scryfall printings, added with
`scripts/add_card.py`; none is in a tournament deck in the pool):

- **Army of the Damned** - "Create thirteen tapped 2/2 black Zombie creature
  tokens." A spell's token clause.
- **Archive Trap** - "Target opponent mills thirteen cards." A spell's targeted
  mill, read by a different parser from Army of the Damned's token clause.
- **Shimatsu the Bloodcloaked** - "Shimatsu enters with that many +1/+1
  counters on it." and **Devouring Hellion** - "it enters with twice that many
  +1/+1 counters on it." The replacement reader split "that many" into an
  unknown count word "that" (and "twice" on the Hellion) and treated the word
  as the spell's X (CR 107.3m), so the count was taken from an announcement
  neither card has. Neither count is readable yet, so the sentence is now
  reported `UNPARSED` instead of being given the wrong amount.

Every CR number here was looked up with `mise run rules:find` in the session
that wrote this file:

- **CR 107.1** - "The only numbers the Magic game uses are integers."
- **CR 107.3m** - "If an object's enters-the-battlefield triggered ability or
  replacement effect refers to X, and the spell that became that object as it
  resolved had a value of X chosen for any of its costs, the value of X for
  that ability is the same as the value of X for that spell".
- **CR 701.7a** - "To create one or more tokens with certain characteristics,
  put the specified number of tokens with the specified characteristics onto
  the battlefield."
- **CR 701.17a** - "For a player to mill a number of cards, that player puts
  that many cards from the top of their library into their graveyard."
- **CR 614.1c** - "Effects that read '[This permanent] enters with . . .' ...
  are replacement effects."
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.replacement import (
    ReplacementKind,
    parse_replacement_effects,
    unparsed_effects,
)
from magic_cards_model.models import Zone
from tests.cards import card
from tests.scenarios.harness import Scenario

ARMY = "Army of the Damned"
ARCHIVE_TRAP = "Archive Trap"
SHIMATSU = "Shimatsu the Bloodcloaked"
HELLION = "Devouring Hellion"


def test_army_of_the_damned_creates_thirteen_tapped_zombies():
    """CR 701.7a: the specified number is thirteen, read off the card."""
    scenario = (
        Scenario().player("alice", hand=[ARMY], battlefield=["Swamp"] * 8).player("bob").build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    army = scenario.cast_and_resolve(ARMY, auto=True)

    zombies = [
        state
        for state in scenario.game.battlefield
        if state.token and state.controller == "alice" and "Zombie" in state.subtypes
    ]
    assert len(zombies) == 13
    assert all(state.tapped for state in zombies)
    assert {(state.power, state.toughness) for state in zombies} == {(2, 2)}
    assert army.zone is Zone.GRAVEYARD


def test_archive_trap_mills_thirteen():
    """CR 701.17a: thirteen cards move from the top of bob's library to his
    graveyard, and the fourteenth stays."""
    scenario = (
        Scenario()
        .player("alice", hand=[ARCHIVE_TRAP], battlefield=["Island"] * 5)
        .player("bob", library=["Forest"] * 14)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.cast_and_resolve(ARCHIVE_TRAP, targets=["bob"], auto=True)

    assert len(scenario.player("bob").graveyard) == 13
    assert len(scenario.player("bob").library) == 1


def _enters_with_lines(name: str) -> list[str]:
    return [
        effect.text
        for effect in parse_replacement_effects(card(name))
        if effect.kind is ReplacementKind.ENTERS_WITH
    ]


def test_shimatsus_that_many_counters_is_unparsed_not_read_as_x():
    """ "that many" is the number of permanents sacrificed as Shimatsu enters,
    not an X (CR 107.3m refers only to an X). Until that count is carried from
    the sacrifice, the sentence is reported unparsed rather than recorded as an
    enters-with effect of an unknown kind of counter taking the cast's X."""
    unparsed = [effect.text for effect in unparsed_effects(card(SHIMATSU))]

    assert any("that many +1/+1 counters" in text for text in unparsed)
    assert not any("that many" in text for text in _enters_with_lines(SHIMATSU))


def test_devouring_hellions_twice_that_many_counters_is_unparsed_not_read_as_x():
    unparsed = [effect.text for effect in unparsed_effects(card(HELLION))]

    assert any("twice that many +1/+1 counters" in text for text in unparsed)
    assert not any("that many" in text for text in _enters_with_lines(HELLION))
