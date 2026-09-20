"""Scenario: announcing an `{X}` spell must not count an ability's own
target as the spell's.

Reported live: "Walking Ballista got broken. On cast it asks for target, but
when I pick one I get error, that it can't take more than 0 targets - it
renders it uncastable." Walking Ballista is `{X}{X}` with no target on cast;
its only "target" word is on its activated ability, "Remove a +1/+1 counter
from this creature: It deals 1 damage to any target."

`Game.announcement_profile` (`models/game.py`) has five branches that answer
"what does this cast target" (CR 601.2c). Four of them - the ability-index
branch, the modal branch, the face-being-cast branch, and the plain
no-x-value fallback (`targeting_profile`) - all drop an ability's own lines
before reading a spell's targets, because CR 113.1c makes a triggered or
activated ability "an object" of its own, choosing its own targets only once
it is on the stack, never when the permanent that carries it is cast. The
fifth branch - reached only when an `{X}` value has actually been announced -
read the printing's oracle text *whole* (`profile_for_text`, built to read
one ability's own words in isolation) instead of through the same
ability-line-dropping reader as the other four
(`spell_profile_for_text`/`_spell_text`), so it alone counted the activated
ability's "any target" as the *spell's* own requirement. That is why the bug
reproduces only once a player has typed an X: `legal_actions` never sends an
`x_value` at all, so the correctly-read no-x-value branch is what a seat sees
building the cast row (no target slot at all, matching this file's own
"no x value" control below) - it is only the *second* read, animated once X is
announced, that disagreed and demanded one.

Rules, each verified in this session with `mise run rules:find` against
`.rules/MagicCompRules.txt` (effective September 25, 2026; `knowledge_search`
was not reachable in this session, so the on-disk primary source was used per
`CLAUDE.md`, "When `knowledge_search` is not enough"):

- **CR 113.1c** - "An ability can be an activated or triggered ability on the
  stack. This kind of ability is an object."
- **CR 601.2c** - the announcement step in which a spell's targets are chosen;
  "a spell may require some targets only if an alternative or additional
  cost ... or a particular mode was chosen for it; otherwise, the spell is
  cast as though it did not require those targets."

Chamber Sentry and Ajani's Anguish prove the fix is general, not a Walking
Ballista special case: Chamber Sentry is a different printing with the same
activated-ability shape (`{X}, {T}, Remove X +1/+1 counters ...: It deals X
damage to any target.`), and Ajani's Anguish puts the same "any target" on a
*triggered* ability instead ("When this enchantment enters, it deals X damage
to any target.") on an Enchantment rather than a Creature - so this closes the
mechanic, "a card's ability owns its own target, not the {X} spell that casts
it," rather than one card's activated-ability clause.

Syncopate is the control in the other direction: an `{X}` spell whose *own*
printed line - not an ability's - says "target", so the fix must not read as
"an `{X}` spell never targets."
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _profile(name: str, x_value: int | None):
    scenario = (
        Scenario().player("alice", hand=[name], battlefield=["Island"] * 8).player("bob").build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    state = scenario.find(name, Zone.HAND, "alice")
    return scenario.game.announcement_profile(state, x_value=x_value)


# -- the reported card -------------------------------------------------------


def test_walking_ballista_announces_no_targets_when_cast_with_an_x_value():
    """The reported bug, reproduced directly: cast with X=1 (as the player
    who hit the error did), the spell's own announcement must ask for no
    target at all - the "any target" phrase belongs to the activated ability,
    not to casting the creature."""
    profile = _profile("Walking Ballista", x_value=1)

    assert profile.requirements == ()


def test_walking_ballista_announces_no_targets_with_no_x_value_control():
    """Control: the no-x-value branch (`targeting_profile`) already read this
    correctly before the fix - it must stay correct after it, since this is
    the shape most of `legal_actions`' own cast rows go through."""
    profile = _profile("Walking Ballista", x_value=None)

    assert profile.requirements == ()


# -- generality: a different printing, an activated ability -----------------


def test_chamber_sentry_announces_no_targets_when_cast_with_an_x_value():
    """Chamber Sentry is not Walking Ballista and is not in any deck pool
    this repo's tests draw from: a different set, a different activated-cost
    shape (`{X}, {T}, Remove X +1/+1 counters ...`), same "any target" on the
    ability rather than the spell."""
    profile = _profile("Chamber Sentry", x_value=2)

    assert profile.requirements == ()


def test_chamber_sentry_announces_no_targets_with_no_x_value_control():
    profile = _profile("Chamber Sentry", x_value=None)

    assert profile.requirements == ()


# -- generality: a triggered ability, on an enchantment ----------------------


def test_ajanis_anguish_announces_no_targets_when_cast_with_an_x_value():
    """Ajani's Anguish puts its "any target" on a *triggered* ability ("When
    this enchantment enters, it deals X damage to any target.") rather than
    an activated one, and the permanent is an Enchantment, not a Creature -
    proving the fix reads CR 113.1c's "an ability is its own object" rule
    generally, not "activated abilities on artifact creatures"."""
    profile = _profile("Ajani's Anguish", x_value=3)

    assert profile.requirements == ()


def test_ajanis_anguish_announces_no_targets_with_no_x_value_control():
    profile = _profile("Ajani's Anguish", x_value=None)

    assert profile.requirements == ()


# -- the fix must not read as "an X spell never targets" --------------------


def test_an_x_spell_that_genuinely_targets_still_announces_its_target():
    """Syncopate ({X}{U}, "Counter target spell unless its controller pays
    {X}.") prints its own "target" on the spell's own line, not an ability's -
    the announcement must still ask for it once X is chosen."""
    profile = _profile("Syncopate", x_value=2)

    assert len(profile.requirements) == 1
    (requirement,) = profile.requirements
    assert requirement.phrase == "target spell"
    assert requirement.minimum == 1
