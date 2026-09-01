"""CR 106.6's *other* two clauses: what a mana ability does to the thing its
mana is later spent on.

CR 106.6, looked up with `knowledge_search(type="rules")` this session: "Some
spells or abilities that produce mana restrict how that mana can be spent,
**have an additional effect that affects the spell or ability that mana is
spent on**, or **create a delayed triggered ability**."

The first clause - the restriction - is modelled and enforced; see
`tests/scenarios/test_mana_spend_restrictions.py`. This file is about the
second, and the one printing in the pool that carries it (oracle text confirmed
with `resolve_cards` this session):

    Arena of Glory
    {R}, {T}, Exert this land: Add {R}{R}. If that mana is spent on a creature
    spell, it gains haste until end of turn.

Two rules keep that sentence out of the machinery that already exists:

- It is **not CR 405.6c**'s "if a mana ability both produces mana and has
  another effect, the mana is produced and the other effect happens
  immediately". Nothing happens immediately here - the effect is conditional on
  a spend that has not happened when the mana ability resolves. That is why the
  parser does not report it as a `rider`.
- It is **not** an unreadable sentence either. Treating it as one would make
  `Game.why_cannot_activate` refuse the whole ability, and the land would stop
  making mana at all - a much louder wrong answer than the one it replaces.

Measured before this file existed: `parse_mana_abilities(card("Arena of
Glory"))[1]` came back with `rider=None` **and** `unparsed_rider=None`. The
sentence was skipped and forgotten, so nothing downstream could tell the
ability apart from a plain "{R}, {T}, Exert: Add {R}{R}." It is now recorded on
`ManaAbility.spend_effect`. Nothing applies it yet, which is the `xfail` at the
bottom - but the gap is queryable instead of invisible.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.abilities import parse_mana_abilities
from magic_cards_model.machines.combat import Keyword, has_keyword
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Color
from tests.cards import card
from tests.scenarios.harness import Scenario


def test_the_arenas_exert_ability_records_its_spend_effect():
    """CR 106.6's second clause, kept as the printed sentence.

    Read off the ability's own trailing text, not off a per-card table: the
    shape is "If that mana is spent on ...", which is how WOTC templates every
    card in this family.
    """
    plain, exerted = parse_mana_abilities(card("Arena of Glory"))

    assert plain.spend_effect is None
    assert exerted.spend_effect == (
        "If that mana is spent on a creature spell, it gains haste until end of turn."
    )
    assert exerted.options == [[Color.RED, Color.RED]]


def test_a_spend_effect_is_not_a_cr_405_6c_rider_and_does_not_block_activation():
    """The distinction that keeps the land working.

    CR 405.6c's rider happens *immediately*, alongside the mana; this one is
    conditional on a later spend. Reporting it as `unparsed_rider` would make
    `Game.why_cannot_activate` refuse the ability under the project's
    fail-closed rule, so the land would make no mana at all rather than mana
    with one clause unapplied.
    """
    _plain, exerted = parse_mana_abilities(card("Arena of Glory"))

    assert exerted.rider is None
    assert exerted.unparsed_rider is None

    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Arena of Glory", "Mountain"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    arena = scenario.find("Arena of Glory", Zone.BATTLEFIELD)

    assert scenario.game.why_cannot_activate(arena, 1) is None


@pytest.mark.xfail(
    strict=True,
    reason="`ManaAbility.spend_effect` is parsed and consumed by nobody. CR 106.6's "
    "spend *restriction* has a whole pipeline; its sibling clause - 'have an "
    "additional effect that affects the spell or ability that mana is spent on' - "
    "has none, and the four missing pieces are each the exact mirror of a "
    "restriction piece that is already there. Measured on this board: after "
    "`activate(arena, index=1)` the pool is `floating={RED: 2}` with "
    "`restricted=[]`, and the Hound's CastRecord is `mana_spent={RED: 2}` - a "
    "colour count with nothing to say which mana it was. What is needed, in "
    "order:\n"
    "1. models/mana.py: a `ManaSpendEffect` beside `ManaRestriction`, a "
    "`spend_effect` slot in `ManaPool.add`/`add_all` and in `_Bucket` (today "
    "`(color, snow, restriction_slot)`), and a `spend_effects_spent` list on "
    "`ManaPayment` filled by `_settle` exactly the way `restricted_spent` is. "
    "Without the bucket dimension there is no way to say which of the two red "
    "mana paid.\n"
    "2. models/game.py, in `activate_ability`'s mana branch beside "
    "`restriction = spend_restriction(ability.effect, permanent)`: pass "
    "`ability.mana.spend_effect` into the same `mana_pool.add` call, so the "
    "Arena's `{R}{R}` is tagged as it is produced (CR 605.3b - the tag goes on "
    "the mana, not on the land). This is where the mana in *this* test is made; "
    "`machines/cost.CostPayment.tap_for_mana` is the other production site and "
    "needs the same one-line mirror of its `restriction_for_production` call, "
    "but nothing here traverses it.\n"
    "3. machines/casting.py at CR 601.2h: once step 1 exists, "
    "`Casting._move_to_the_stack` reads "
    "`self.payment.mana_payment.spend_effects_spent` and records it on the "
    "spell, and models/game.py's `note_cast`/`CastRecord` carry it the way "
    "`mana_spent` already does.\n"
    "4. machines/layers.py: 'it gains haste until end of turn' as a "
    "`ContinuousEffect` on the permanent the creature spell becomes - CR 400.7b "
    "is why the effect survives the stack-to-battlefield move at all.\n"
    "None of 1, 2 or 4 is in a file this task owns, and 3 cannot be written "
    "against a `ManaPayment` field that does not exist yet.",
)
def test_a_creature_cast_with_the_arenas_mana_gains_haste():
    """CR 106.6's second clause, doing what it says.

    The Arena's own ability costs {R} on top of the tap and the exert, so the
    Mountain pays that; the {R}{R} it adds is what casts the Hound, and that is
    the mana the sentence is about.
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Ashmouth Hound"], battlefield=["Arena of Glory", "Mountain"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    arena = scenario.find("Arena of Glory", Zone.BATTLEFIELD)
    mountain = scenario.find("Mountain", Zone.BATTLEFIELD)

    scenario.activate(mountain)
    scenario.activate(arena, index=1)
    hound = scenario.cast_and_resolve("Ashmouth Hound")

    assert hound.zone is Zone.BATTLEFIELD
    assert has_keyword(hound, Keyword.HASTE, scenario.game)
