"""Auras and what they are attached to: CR 303.4 and the state-based action CR 704.5m.

Every rule number here was looked up with `knowledge_search(type="rules")` and
then read **in full** out of the 2026-08-19 Comprehensive Rules (sha256
`4381ad1b…423f`, the release `cr_versions` names as current), because the search
excerpts truncate at roughly 150 characters and CR 303.4 keeps its list of ways
an Aura becomes illegal in the tail.

The letter is the trap. The Aura state-based action is **CR 704.5m**, and its
neighbours are not it: CR 704.5n is the Equipment one, CR 704.5p is every other
attached permanent, and CR 704.5z is the Role one. All four were read off the
full text rather than guessed.

CR 704.5m and CR 704.5n are opposites, and this file is largely about that: an
Aura on an illegal object *dies*, an Equipment on one merely *falls off*.

Roles are Auras too (CR 303.7) and have a file of their own,
`test_role_tokens.py`, because being a token brings CR 704.5d with it.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def board() -> Scenario:
    """A bear to enchant, a Mountain that is not one, and the Aura."""
    return (
        Scenario()
        .player("alice", battlefield=["Hyena Umbra", "Grizzly Bears", "Mountain"])
        .player("bob", battlefield=["Grizzly Bears"])
    )


def _enchant(scenario, host):
    """Attach the Umbra to `host` by hand (CR 701.3a).

    Hyena Umbra is an Aura *spell* and CR 303.4a would have it target as it is
    cast, but `machines/effects.py` has no entry that attaches a resolving Aura,
    so casting it would put an unattached enchantment onto the battlefield and
    test the gap rather than the rule. Attaching a permanent already on the
    battlefield is CR 701.3a - "take it from where it currently is and put it
    onto that object" - and is staging, not a mock: the Aura is a real Scryfall
    printing and the attachment is the real model field.
    """
    umbra = scenario.find("Hyena Umbra", Zone.BATTLEFIELD, username="alice")
    umbra.attach_to(host)
    return umbra


# --------------------------------------------------------------------------
# The happy path: a legal attachment survives the check
# --------------------------------------------------------------------------


def test_an_aura_on_a_legal_creature_survives_the_check():
    """CR 704.5m only acts on an Aura that is attached to something illegal or to
    nothing at all: "If an Aura is attached to an illegal object or player, or is
    not attached to an object or player, that Aura is put into its owner's
    graveyard."

    Hyena Umbra reads "Enchant creature", and CR 702.5a is what makes that a
    restriction rather than flavour: "Enchant is a static ability, written
    'Enchant [object or player].' The enchant ability restricts what an Aura spell
    can target and what an Aura can enchant." A bear satisfies it, so nothing
    happens.
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    umbra = _enchant(scenario, bears)

    assert scenario.state_based_actions() == []
    assert umbra.zone is Zone.BATTLEFIELD
    assert umbra.attached_to == bears.id


def test_an_aura_may_enchant_a_creature_its_controller_does_not_control():
    """CR 303.4e: "An Aura's controller is separate from the enchanted object's
    controller or the enchanted player; the two need not be the same."

    Nothing about controlling the host is part of CR 704.5m's legality test, so
    alice's Umbra on bob's bear is a perfectly legal attachment.
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    theirs = scenario.creature("Grizzly Bears", "bob")
    umbra = _enchant(scenario, theirs)

    assert scenario.state_based_actions() == []
    assert umbra.controller == "alice"
    assert umbra.attached_to == theirs.id


# --------------------------------------------------------------------------
# The three ways CR 704.5m fires
# --------------------------------------------------------------------------


def test_an_aura_attached_to_nothing_is_put_into_its_owners_graveyard():
    """The second half of CR 704.5m: "...or is not attached to an object or
    player".

    An Aura that reaches the battlefield without a host has nothing to enchant
    and does not linger. CR 303.4g normally stops it getting there in the first
    place - "if an Aura is entering the battlefield and there is no legal object
    or player for it to enchant, the Aura remains in its current zone, unless
    that zone is the stack" - which this engine does not model, so the
    state-based action is the backstop that catches it.
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    umbra = scenario.find("Hyena Umbra", Zone.BATTLEFIELD, username="alice")
    assert not umbra.is_attached

    scenario.state_based_actions()

    assert umbra.zone is Zone.GRAVEYARD
    assert umbra in scenario.player("alice").graveyard
    assert "Hyena Umbra" not in scenario.battlefield_names()


def test_an_aura_whose_creature_died_is_put_into_its_owners_graveyard():
    """CR 303.4c names this case in as many words: an Aura goes to its owner's
    graveyard when "the object it was attached to no longer exists".

    CR 400.7 is why a creature that went to a graveyard "no longer exists" as far
    as the Aura is concerned - the card in the graveyard is a new object - and it
    is the everyday case: kill the creature, the Aura falls off and dies with it.
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    umbra = _enchant(scenario, bears)

    scenario.game.destroy(bears)
    scenario.state_based_actions()

    assert umbra.zone is Zone.GRAVEYARD
    assert "Hyena Umbra" not in scenario.battlefield_names()


def test_an_aura_on_an_object_its_enchant_ability_forbids_is_binned():
    """The first half of CR 704.5m: "attached to an illegal object".

    CR 303.4c defines illegal as "enchanting an illegal object or player **as
    defined by its enchant ability** and other applicable effects", and Hyena
    Umbra's enchant ability says creature. A Mountain is a land (CR 300.1), so
    the attachment is illegal and the Aura goes.

    CR 303.4j is the related rule that would normally prevent this happening -
    "if an effect attempts to attach an Aura on the battlefield to an object or
    player it can't legally enchant, the Aura doesn't move" - so this board is
    reaching a state the rules would not produce, in order to prove the
    state-based action cleans it up if anything ever does.
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mountain = scenario.find("Mountain", Zone.BATTLEFIELD, username="alice")
    umbra = _enchant(scenario, mountain)

    scenario.state_based_actions()

    assert umbra.zone is Zone.GRAVEYARD
    assert mountain.zone is Zone.BATTLEFIELD, "the land is untouched"


# --------------------------------------------------------------------------
# CR 704.5m against CR 704.5n: the Aura dies, the Equipment falls off
# --------------------------------------------------------------------------


def test_an_equipment_falls_off_where_an_aura_would_have_died():
    """CR 704.5n: "If an Equipment or Fortification is attached to an illegal
    permanent or to a player, it becomes unattached from that permanent or
    player. **It remains on the battlefield.**"

    That last sentence is the whole difference, and it is the part a
    `knowledge_search` excerpt is apt to cut. Same board, same dead creature: the
    Aura is in a graveyard and the Equipment is still there, unattached.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Hyena Umbra", "Cori-Steel Cutter", "Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    umbra = scenario.find("Hyena Umbra", Zone.BATTLEFIELD, username="alice")
    cutter = scenario.find("Cori-Steel Cutter", Zone.BATTLEFIELD, username="alice")
    umbra.attach_to(bears)
    cutter.attach_to(bears)

    scenario.game.destroy(bears)
    scenario.state_based_actions()

    assert umbra.zone is Zone.GRAVEYARD, "CR 704.5m"
    assert cutter.zone is Zone.BATTLEFIELD, "CR 704.5n keeps it on the battlefield"
    assert not cutter.is_attached


# --------------------------------------------------------------------------
# What is not judged
# --------------------------------------------------------------------------


@pytest.mark.xfail(
    strict=True,
    reason="CR 704.5m also covers an Aura attached to a *player*, and "
    "CardState.attached_to is a UUID naming a card - models/card_state.py has no way to "
    "record a player as the enchanted object, so 'enchant player' Auras cannot be attached "
    "at all and the illegal-player half of CR 704.5m has nothing to act on. The hook is on "
    "models/card_state.py, which this change does not own: attached_to needs to accept a "
    "TargetRef rather than a card id.",
)
def test_an_aura_on_a_player_who_left_the_game_is_binned():
    """CR 303.4c's third clause: an Aura goes to its owner's graveyard when "the
    player it was attached to has left the game".

    CR 800.4a is what removes the player (looked up: it is 800.4a, not 800.4).
    An "enchant player" Aura on a conceded player is the only way CR 704.5m's
    "or player" branch is reachable, and `CardState.attached_to` cannot express
    it.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Hyena Umbra"])
        .player("bob")
        .player("carol")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    umbra = scenario.find("Hyena Umbra", Zone.BATTLEFIELD, username="alice")
    umbra.attach_to(scenario.player("carol"))  # CardState.attach_to takes a CardState

    scenario.game.concede("carol")
    scenario.state_based_actions()

    assert umbra.zone is Zone.GRAVEYARD
