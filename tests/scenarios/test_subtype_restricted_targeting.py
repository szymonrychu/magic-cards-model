"""A bare CR 205.3m creature-type used as the target noun itself - "target
Vampire, Werewolf, or Zombie" (Slayer of the Wicked, two-or-more items) and
"another target Soldier you control" (Aeronaut Cavalry, exactly one) - rather
than "target creature" narrowed by a "with"/"you control" clause.
`_read_subtype_list`/`_is_bare_subtype_word`/`TargetRequirement.
required_subtypes` in `machines/targeting.py`.

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
- **CR 122.1a** - a +1/+1 counter's effect on power and toughness - Aeronaut
  Cavalry's own trigger.

Aeronaut Cavalry's singular case was originally left unread on purpose - see
this module's own history in `docs/engine-coverage.md` - because a lone
capitalized word cannot be told apart from a real English noun with the same
confidence a multi-item Oxford list gives. It is read now: `_is_bare_subtype_
word` is the shared predicate both the plural-list reader above and the
singular noun-position reader below apply, so a genuine subtype ("Soldier")
and an ordinary noun the parser already knows some other way never collide.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.targeting import profile_for_text
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario

SLAYER_TEXT = "When this creature enters, you may destroy target Vampire, Werewolf, or Zombie."
AERONAUT_TEXT = (
    "When this creature enters, put a +1/+1 counter on another target Soldier you control."
)


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


def test_a_bare_singular_subtype_is_read():
    profile = profile_for_text(AERONAUT_TEXT)
    assert profile.understood
    (requirement,) = profile.requirements
    assert requirement.required_subtypes == frozenset({"soldier"})
    assert requirement.excludes_source, '"another" must exclude Aeronaut Cavalry itself'


def test_aeronaut_cavalry_puts_a_counter_on_another_soldier():
    """Fencing Ace is a Human Soldier - the named subtype - so Aeronaut
    Cavalry's ETB trigger can target it and does put the counter on."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Aeronaut Cavalry"],
            battlefield=["Plains"] * 5 + ["Fencing Ace"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    soldier = scenario.creature("Fencing Ace", "alice")
    sources = scenario.untapped_sources(*["Plains"] * 5)
    scenario.choose_trigger_targets("Aeronaut Cavalry", [soldier])

    scenario.cast_and_resolve("Aeronaut Cavalry", *sources)
    scenario.pass_until_resolved()

    assert soldier.counters[Counter.PLUS_ONE] == 1


def test_aeronaut_cavalry_cannot_target_itself():
    """CR 205.3m's own subtype word plus "another": Aeronaut Cavalry is
    itself a Human Soldier, but the printed "another" (`excludes_source`)
    refuses it as its own trigger's target even though it satisfies the bare
    subtype restriction on its own."""
    scenario = (
        Scenario()
        .player("alice", hand=["Aeronaut Cavalry"], battlefield=["Plains"] * 5)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (requirement,) = profile_for_text(AERONAUT_TEXT).requirements
    sources = scenario.untapped_sources(*["Plains"] * 5)

    cavalry = scenario.cast_and_resolve("Aeronaut Cavalry", *sources)
    scenario.pass_until_resolved()

    reason = requirement.rejects(cavalry, "alice", source_id=cavalry.id)
    assert reason is not None


def test_an_opponents_soldier_is_not_a_legal_target():
    """ "you control" narrows the bare subtype the same way it narrows an
    ordinary "target creature you control" - a Soldier alice does not
    control is not a legal target for her own trigger."""
    scenario = (
        Scenario()
        .player("alice", hand=["Aeronaut Cavalry"], battlefield=["Plains"] * 5)
        .player("bob", battlefield=["Fencing Ace"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    their_soldier = scenario.creature("Fencing Ace", "bob")
    (requirement,) = profile_for_text(AERONAUT_TEXT).requirements

    reason = requirement.rejects(their_soldier, "alice")
    assert reason is not None


FACTORY_TEXT = "Target Assembly-Worker creature gets +1/+1 until end of turn."


def test_a_hyphenated_creature_type_is_read_as_one_subtype_word():
    """Mishra's Factory's "Target Assembly-Worker creature" (CR 205.3m).

    A creature type may be hyphenated, and `_SUBTYPE_WORD_RE` used to stop at
    the hyphen - so this phrase came back unreadable and the whole ability was
    `understood=False`, the pool's last unchecked targeting phrase. Both halves
    are capitalized, which is still what tells a creature type apart from an
    ordinary hyphenated English word.
    """
    scenario = Scenario().player("alice", battlefield=["Mishra's Factory", "Grizzly Bears"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    profile = profile_for_text(FACTORY_TEXT)
    assert profile.understood
    (requirement,) = profile.requirements
    assert "assembly-worker" in requirement.required_subtypes

    bears = scenario.creature("Grizzly Bears", "alice")
    assert requirement.rejects(bears, "alice") is not None, "a Bear is not an Assembly-Worker"
