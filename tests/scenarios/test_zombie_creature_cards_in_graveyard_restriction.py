"""Scenario: "Activate only during your turn and only if there are at least
three Zombie creature cards in your graveyard" (CR 602.1b, CR 602.5b) - Tomb
Tyrant's own compound activation restriction. The effect itself ("Return a
Zombie creature card at random from your graveyard to the battlefield") is
out of scope for this file; only the restriction is under test, checked
directly through `Game.why_cannot_activate` independently of whether the
effect resolves.

Verified with `mise run rules:find` in this session:

- **CR 602.1b**: "Some text after the colon of an activated ability states
  instructions that must be followed while activating that ability."
  `Game.read_activation_instructions` already splits "during your turn"
  (a window, CR 602.1b's own timing restriction) from "there are at least
  three Zombie creature cards in your graveyard" (an "only if" condition) at
  the "and only" join - no change needed there.
- **CR 602.5b**: the condition, asked of `Game.condition_holds`.

`models.game._card_quality` (a graveyard card's quality, shared by
`machines/conditions/player.py`'s "there are `<count>` `<quality>` cards in
your graveyard" reader) is widened here from a single word to any number of
words ANDed - "Zombie creature" as "Zombie" (a subtype) *and* "creature" (a
type) - the same qualifiers-then-noun reading `_permanent_quality` already
gives a permanent's own computed characteristics.

Oracle text pulled with `scripts/add_card.py`:

- **Tomb Tyrant** (the reported card; its static Zombie anthem and the
  activated ability's own effect are out of scope here).
- No Modern/Pioneer/Standard-legal, or even off-format, printing of
  "`<subtype>` creature cards in your graveyard" exists besides Tomb Tyrant
  itself (a Scryfall search across fifteen common creature subtypes for
  exactly that two-word phrase turns up only this one card), so the
  multi-word widening is proven generic within this file instead: the same
  `_card_quality` reader answers "Human creature cards" and "artifact
  creature cards" as readily as "Zombie creature cards"
  (`test_the_quality_reads_any_type_and_subtype_pair` below), off real
  Human, Zombie and artifact-creature printings already in the pool.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone

from .harness import Scenario


def _fill_graveyard(scenario, *names: str, username: str = "alice") -> None:
    for name in names:
        card = scenario.find(name, Zone.HAND, username)
        scenario.game.discard_cards(username, [card])


def test_cannot_activate_with_fewer_than_three_zombies_in_graveyard():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Tomb Tyrant", "Grizzly Bears"],
            hand=["Carrion Feeder", "Diregraf Colossus"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _fill_graveyard(scenario, "Carrion Feeder", "Diregraf Colossus")
    tyrant = scenario.creature("Tomb Tyrant", "alice")

    assert scenario.why_cannot_activate(tyrant, index=0) is not None


def test_activates_with_three_zombies_in_graveyard_on_your_turn():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Tomb Tyrant", "Grizzly Bears"],
            hand=["Carrion Feeder", "Diregraf Colossus", "Arisen Gorgon"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _fill_graveyard(scenario, "Carrion Feeder", "Diregraf Colossus", "Arisen Gorgon")
    tyrant = scenario.creature("Tomb Tyrant", "alice")

    assert scenario.why_cannot_activate(tyrant, index=0) is None


def test_cannot_activate_during_an_opponents_turn():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Tomb Tyrant", "Grizzly Bears"],
            hand=["Carrion Feeder", "Diregraf Colossus", "Arisen Gorgon"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _fill_graveyard(scenario, "Carrion Feeder", "Diregraf Colossus", "Arisen Gorgon")
    tyrant = scenario.creature("Tomb Tyrant", "alice")
    assert scenario.why_cannot_activate(tyrant, index=0) is None

    while scenario.game.turn.active_player != "bob":
        scenario.advance()

    assert scenario.why_cannot_activate(tyrant, index=0) is not None


def test_a_non_zombie_creature_card_does_not_count():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Tomb Tyrant", "Grizzly Bears"],
            hand=["Carrion Feeder", "Diregraf Colossus", "Grizzly Bears"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _fill_graveyard(scenario, "Carrion Feeder", "Diregraf Colossus", "Grizzly Bears")
    tyrant = scenario.creature("Tomb Tyrant", "alice")

    assert scenario.why_cannot_activate(tyrant, index=0) is not None


def test_the_quality_reads_any_type_and_subtype_pair():
    """The widened `_card_quality` off-Tomb-Tyrant: "Human creature" and
    "artifact creature" read the same way "Zombie creature" does, over a
    real graveyard of real printings."""
    scenario = (
        Scenario()
        .player(
            "alice",
            graveyard=["Grizzly Bears", "Carrion Feeder", "Ornithopter"],
        )
        .build()
    )

    assert (
        scenario.game.condition_holds(
            "alice", "there are at least two Human creature cards in your graveyard"
        )
        is False
    )
    assert scenario.game.condition_holds(
        "alice", "there are at least one Zombie creature cards in your graveyard"
    )
    assert scenario.game.condition_holds(
        "alice", "there are at least one artifact creature cards in your graveyard"
    )
