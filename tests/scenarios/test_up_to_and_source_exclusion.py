"""Scenario: "up to one **other** target ..." (CR 115.6) and self-exclusion.

Two related defects, both observed running `profile_for_text` before this file
existed:

- `_read_count` reads the last three words before "target" to find "up to N".
  "exile up to one other " ends in `["to", "one", "other"]` - "other" breaks
  the window, so it fell through to the plain-count branch and read "other" as
  if it were the count word, landing on the default `(1, 1, False)`: mandatory
  exactly one. Phelia, Exuberant Shepherd and Solitude both print "exile up to
  one other target ...", and both came out mandatory instead of optional.
- "other"/"another" were simply dropped (`_IGNORED_ADJECTIVES`), so nothing
  stopped Phelia from being a legal target of her own "attacks" trigger, or
  Solitude from being a legal target of her own "enters" trigger.

The fix: `_read_count` filters "other"/"another" out before reading the count
(`_SOURCE_EXCLUDING`), and a separate `_excludes_source` reads the word for
what it means - `TargetRequirement.excludes_source` - checked against the
ability's source id, threaded through from `AbilityOnStack.source_id`.

No CR number is cited for "another"/"other" itself - `knowledge_search` found
none this session (see `machines/targeting.py`). CR 115.6 ("a spell or ability
that requires targets may allow zero targets to be chosen") is what makes "up
to one" genuinely optional, and is checked directly below.
"""

import pytest

from magic_cards_model.machines.targeting import profile_for_text
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import TargetRef
from tests.scenarios.harness import Scenario

# -- profile_for_text, directly -------------------------------------------


@pytest.mark.parametrize(
    "name,text",
    [
        (
            "Phelia, Exuberant Shepherd",
            "Whenever Phelia attacks, exile up to one other target nonland permanent. "
            "At the beginning of the next end step, return that card to the battlefield "
            "under its owner's control. If it entered under your control, put a +1/+1 "
            "counter on Phelia.",
        ),
        (
            "Solitude",
            "When this creature enters, exile up to one other target creature. "
            "That creature's controller gains life equal to its power.",
        ),
    ],
)
def test_up_to_one_other_reads_as_optional_and_self_excluding(name, text):
    profile = profile_for_text(text)
    assert profile.understood, name
    (requirement,) = profile.requirements
    assert requirement.minimum == 0, f"{name}: 'up to one' must allow declining (CR 115.6)"
    assert requirement.count == 1
    assert not requirement.unbounded
    assert requirement.excludes_source, f"{name}: 'other' must exclude the source"


# -- Phelia in play: zero targets is legal, and she cannot target herself --


def _phelia_board() -> Scenario:
    return (
        Scenario()
        .player("alice", battlefield=["Phelia, Exuberant Shepherd"])
        .player("bob", battlefield=["Grizzly Bears"])
    )


def test_phelia_declining_to_exile_anything_is_legal():
    """Nobody scripts an answer; the default is zero targets, not a forced one."""
    scenario = _phelia_board().build()
    phelia = scenario.creature("Phelia, Exuberant Shepherd", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    phelia.summoning_sick = False

    scenario.attack_with(phelia)
    scenario.game.put_triggers_on_stack()

    (ability,) = scenario.game.abilities_on_stack
    assert ability.targets == [], "declining is legal (CR 115.6) - not a forced pick"

    while not scenario.game.stack_is_empty:
        scenario.resolve_top()
    assert bears.zone is Zone.BATTLEFIELD
    assert phelia.zone is Zone.BATTLEFIELD


def test_phelia_cannot_target_herself():
    """The candidate list offered for the decision never includes Phelia."""
    scenario = _phelia_board().build()
    phelia = scenario.creature("Phelia, Exuberant Shepherd", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    phelia.summoning_sick = False

    with pytest.raises(ValueError, match="which this is on"):
        scenario.choose_trigger_targets("Phelia, Exuberant Shepherd", [phelia])

    # A legal target is still accepted - the refusal is about Phelia specifically.
    # (Phelia's exile-then-return effect has no `machines/effects.py` entry, so
    # this checks the ability was announced with the chosen target, not that it
    # resolved - that registry gap is out of scope for this file.)
    scenario.choose_trigger_targets("Phelia, Exuberant Shepherd", [bears])
    scenario.attack_with(phelia)
    scenario.game.put_triggers_on_stack()
    (ability,) = scenario.game.abilities_on_stack
    assert TargetRef.to_card(bears) in ability.targets, "the legal target was accepted"


# -- Solitude: the same shape on a different card --------------------------


def test_solitude_up_to_one_other_allows_declining_and_excludes_itself():
    scenario = (
        Scenario()
        .player("alice", hand=["Solitude"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    solitude = scenario.put_onto_battlefield("Solitude")
    bears = scenario.creature("Grizzly Bears", "bob")

    with pytest.raises(ValueError, match="which this is on"):
        scenario.choose_trigger_targets("Solitude", [solitude])

    scenario.game.put_triggers_on_stack()
    (ability,) = scenario.game.abilities_on_stack
    assert ability.targets == [], "no answer staged - declining is the default"

    while not scenario.game.stack_is_empty:
        scenario.resolve_top()
    assert bears.zone is Zone.BATTLEFIELD
    assert solitude.zone is Zone.BATTLEFIELD
