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
    reason="`ManaAbility.spend_effect` is recorded and nothing applies it: no path "
    "from the mana in the pool to the spell it later pays for carries CR 106.6's "
    "'additional effect that affects the spell or ability that mana is spent on', so "
    "the Ashmouth Hound cast off the Arena's {R}{R} enters without haste.",
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
