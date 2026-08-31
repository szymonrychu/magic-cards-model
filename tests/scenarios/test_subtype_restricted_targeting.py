"""A bare CR 205.3m creature-type list used as the target noun itself -
"target Vampire, Werewolf, or Zombie" (Slayer of the Wicked) - rather than
"target creature" narrowed by a "with"/"you control" clause.
`_read_subtype_list`/`TargetRequirement.required_subtypes` in
`machines/targeting.py`.

Every CR number below was looked up with `knowledge_search(q="...",
type="rules")` in the session that wrote this file:

- **CR 205.3m** - "Creatures ... share their lists of subtypes; these
  subtypes are called creature types" - Vampire, Werewolf, and Zombie are
  each one, and Oracle templating elides the word "creature" that would
  otherwise follow the list.
- **CR 115.1** - what a target is, and CR 115.2's "only permanents are legal
  targets ... unless ... it targets an object that can't exist on the
  battlefield" (not relevant here - every named type is a creature type, so
  the target is always a permanent).
- **CR 608.2d** - "The player can't choose an option that's illegal or
  impossible" - Slayer of the Wicked's own "you may" over the destroy.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.targeting import profile_for_text
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

SLAYER_TEXT = "When this creature enters, you may destroy target Vampire, Werewolf, or Zombie."


def test_a_named_subtype_is_a_legal_target():
    """Gray Merchant of Asphodel is a Zombie - one of the three named types - so Slayer of
    the Wicked's "you may" destroy is legal and, taken, actually destroys
    it."""
    scenario = (
        Scenario()
        .player("alice", hand=["Slayer of the Wicked"], battlefield=["Plains"] * 4)
        .player("bob", battlefield=["Gray Merchant of Asphodel"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    zombie = scenario.creature("Gray Merchant of Asphodel", "bob")
    sources = scenario.untapped_sources("Plains", "Plains", "Plains", "Plains")
    scenario.choose_trigger_targets("Slayer of the Wicked", [zombie])
    scenario.will_take_the_may(True, source="Slayer of the Wicked")

    scenario.cast_and_resolve("Slayer of the Wicked", *sources)
    scenario.pass_until_resolved()

    assert zombie.zone is Zone.GRAVEYARD


def test_all_three_named_types_are_read():
    profile = profile_for_text(SLAYER_TEXT)
    assert profile.understood
    (requirement,) = profile.requirements
    assert requirement.required_subtypes == frozenset({"vampire", "werewolf", "zombie"})


def test_a_creature_outside_the_named_types_cannot_be_targeted():
    """Grizzly Bears is a plain Bear - none of Vampire, Werewolf, or Zombie -
    so `TargetRequirement.rejects` refuses it as a target at all, the same
    check `Game.legal_target`/`why_cannot_target_with_trigger` make during a
    real game."""
    scenario = (
        Scenario()
        .player("alice", hand=["Slayer of the Wicked"], battlefield=["Plains"] * 4)
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    (requirement,) = profile_for_text(SLAYER_TEXT).requirements

    reason = requirement.rejects(bears, "alice")
    assert reason is not None
    assert "vampire" in reason or "werewolf" in reason or "zombie" in reason


def test_declining_the_may_leaves_the_target_alone():
    """CR 608.2d: the destroy is optional even against a legal target."""
    scenario = (
        Scenario()
        .player("alice", hand=["Slayer of the Wicked"], battlefield=["Plains"] * 4)
        .player("bob", battlefield=["Gray Merchant of Asphodel"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    zombie = scenario.creature("Gray Merchant of Asphodel", "bob")
    sources = scenario.untapped_sources("Plains", "Plains", "Plains", "Plains")
    scenario.choose_trigger_targets("Slayer of the Wicked", [zombie])
    scenario.will_take_the_may(False, source="Slayer of the Wicked")

    scenario.cast_and_resolve("Slayer of the Wicked", *sources)
    scenario.pass_until_resolved()

    assert zombie.zone is Zone.BATTLEFIELD
