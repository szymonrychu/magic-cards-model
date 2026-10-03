"""Scenario: a cast trigger returns every graveyard card sharing its own
printed name to the battlefield - Demigod of Revenge's own "return all cards
named Demigod of Revenge from your graveyard to the battlefield."

Demigod of Revenge: "When you cast this spell, return all cards named
Demigod of Revenge from your graveyard to the battlefield." (Modern).

Every CR number below was looked up with `mise run rules:find` in the
session that wrote this file.

- **CR 201.2a** - "Two or more objects have the same name if they have at
  least one name in common" - the rule "cards named `<Name>`" reads, whether
  or not `<Name>` happens to be the printed card's own.
- **CR 400.1/404.1** - the graveyard is one of a player's own zones, one per
  player; "your graveyard" is the resolving object's controller's own.
- **CR 110.2a** - a permanent an effect puts onto the battlefield from
  somewhere else enters under its own controller's control when nobody else
  is named.
- **CR 608.2f** - the whole group returns as one action, snapshotted before
  any of them arrives.

Added to `_parse_card_group_qualifier` (`machines/effects.py`) as a plain
"cards? named `<Name>`" branch: the name is read straight off whatever the
clause itself prints, not fitted to this one card, so it reuses the already-
existing `_MASS_RETURN_FROM_GRAVEYARD_TO_BATTLEFIELD_RE`/`_parse_mass_
return_from_graveyard_to_battlefield_clause` reader (Raise the Past's own
mechanic) rather than adding a new one.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone

from .harness import Scenario


def _board(*, alice_graveyard: list[str], bob_graveyard: list[str] | None = None) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=["Demigod of Revenge"],
            graveyard=alice_graveyard,
            battlefield=["Mountain"] * 5,
        )
        .player("bob", graveyard=bob_graveyard or [])
        .build()
    )


def test_returns_the_single_copy_from_its_controllers_graveyard():
    scenario = _board(alice_graveyard=["Demigod of Revenge"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    demigod = scenario.find("Demigod of Revenge", Zone.GRAVEYARD, "alice")
    sources = scenario.untapped_sources(*["Mountain"] * 5)

    scenario.cast_onto_stack("Demigod of Revenge", *sources)
    scenario.pass_until_resolved()  # the cast trigger

    assert demigod.zone is Zone.BATTLEFIELD
    assert demigod.controller == "alice"


def test_a_differently_named_card_in_the_graveyard_is_left_alone():
    scenario = _board(alice_graveyard=["Grizzly Bears"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")
    sources = scenario.untapped_sources(*["Mountain"] * 5)

    scenario.cast_onto_stack("Demigod of Revenge", *sources)
    scenario.pass_until_resolved()

    assert bears.zone is Zone.GRAVEYARD


def test_a_same_named_card_in_an_opponents_graveyard_is_not_returned():
    """CR 404.1: the graveyard is per player, and this reads only the
    resolving spell's own controller's graveyard."""
    scenario = _board(alice_graveyard=[], bob_graveyard=["Demigod of Revenge"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bobs_copy = scenario.find("Demigod of Revenge", Zone.GRAVEYARD, "bob")
    sources = scenario.untapped_sources(*["Mountain"] * 5)

    scenario.cast_onto_stack("Demigod of Revenge", *sources)
    scenario.pass_until_resolved()

    assert bobs_copy.zone is Zone.GRAVEYARD
    assert bobs_copy.owner == "bob"


def test_no_copies_in_the_graveyard_returns_nothing_and_the_spell_still_resolves():
    scenario = _board(alice_graveyard=[])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources(*["Mountain"] * 5)

    scenario.cast_onto_stack("Demigod of Revenge", *sources)
    scenario.pass_until_resolved()  # the cast trigger, nothing to return
    scenario.pass_until_resolved()  # Demigod of Revenge itself

    assert scenario.player("alice").graveyard == []
    names = scenario.battlefield_names()
    assert names.count("Demigod of Revenge") == 1
