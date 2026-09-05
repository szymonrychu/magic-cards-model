"""Scenario: "Flashback" (the spell, not the keyword) - "Target instant or
sorcery card in your graveyard gains flashback until end of turn. The
flashback cost is equal to its mana cost."

CR 702.34a's flashback is two static abilities this engine has nowhere to
*grant*: `machines/casting.keyword_cast_options` only ever reads a keyword
printed on the `Card` itself, and `Card` is deliberately immutable, so
nothing here can stamp a runtime-granted keyword onto one. Reused instead:
CR 601.3's ordinary "you may cast [that card] this turn" permission
(`machines/casting.PlayPermission`/`Game.grant_play_permission`), aimed at
the graveyard rather than exile, paying the card's own mana cost - which is
exactly what "the flashback cost is equal to its mana cost" describes.

CR 702.34a's own second half - "then exile it instead of putting it anywhere
else any time it would leave the stack" - now fires for this
`PlayPermission`-driven cast too: `PlayPermission.flashback` marks the grant
as CR 702.34a's own (set by `_parse_grant_flashback_clause` in
`machines/effects.py`), and `Casting.cast()` reads it to write
`CastRecord.keyword = "Flashback"` even though no keyword line was announced
- the only thing `machines/replacement.py`'s exile-on-leaving-the-stack check
(`_stack_replacements`) actually looks at.
`test_the_recast_spell_is_exiled_not_returned_to_the_graveyard` below proves
it, rather than merely claiming it.

Every CR number below was looked up with `knowledge_search(q="...",
type="rules")` in the session that wrote this file:

- **CR 702.34a** - flashback's two static abilities.
- **CR 601.3** - "A player can begin to cast a spell only if a rule or
  effect allows that player to cast it."
- **CR 400.7** - the permission is stamped with the object's zone-change
  identity and dies if the card moves again before it is used.
- **CR 118.9c** - an alternative cost replaces what is paid, not the
  card's own printed mana cost.
- **CR 611.3d** - a static ability's continuous effect may "grant an ability
  to a permanent spell or card that allows it to be cast", which is what lets
  a *granted* flashback carry both of CR 702.34a's static abilities, not just
  the first.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.casting import PlayAction
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_flashback_grants_a_permission_to_cast_the_graveyard_card():
    """Lightning Bolt sits in alice's graveyard; Flashback targets it and
    hands out a CR 601.3 permission to cast it, this turn, for its own
    mana cost."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Flashback"],
            graveyard=["Lightning Bolt"],
            battlefield=["Mountain"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bolt = scenario.find("Lightning Bolt", Zone.GRAVEYARD, "alice")
    sources = scenario.untapped_sources("Mountain")

    scenario.cast_and_resolve("Flashback", *sources, targets=[bolt])

    permission = scenario.game.play_permission_for(bolt, "alice")
    assert permission is not None
    assert permission.action is PlayAction.CAST
    assert permission.pays_mana_cost is True
    assert permission.zone is Zone.GRAVEYARD


def test_the_recast_spell_can_actually_be_cast_from_the_graveyard():
    """The permission is not just recorded - it works: alice pays Lightning
    Bolt's own {R} and it leaves the graveyard for the stack."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Flashback"],
            graveyard=["Lightning Bolt"],
            battlefield=["Mountain", "Mountain"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bolt = scenario.find("Lightning Bolt", Zone.GRAVEYARD, "alice")
    flashback_source = scenario.untapped_sources("Mountain")

    scenario.cast_and_resolve("Flashback", *flashback_source, targets=[bolt])

    casting = scenario.cast("Lightning Bolt", from_zone=Zone.GRAVEYARD)
    casting.use_permission()
    casting.choose_targets(["bob"])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Mountain"))
    scenario.put_on_stack(casting)

    assert bolt.zone is Zone.STACK


def test_the_recast_spell_is_exiled_not_returned_to_the_graveyard():
    """CR 702.34a's second static ability - "exile this card instead of
    putting it anywhere else any time it would leave the stack" - applies to
    a *granted* flashback exactly as it does to a printed one (CR 611.3d):
    once the flashback cost (here, Lightning Bolt's own mana cost, per
    Flashback's "the flashback cost is equal to its mana cost") was paid, the
    resolved spell is exiled rather than going to its owner's graveyard.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Flashback"],
            graveyard=["Lightning Bolt"],
            battlefield=["Mountain", "Mountain"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bolt = scenario.find("Lightning Bolt", Zone.GRAVEYARD, "alice")
    flashback_source = scenario.untapped_sources("Mountain")

    scenario.cast_and_resolve("Flashback", *flashback_source, targets=[bolt])

    casting = scenario.cast("Lightning Bolt", from_zone=Zone.GRAVEYARD)
    casting.use_permission()
    casting.choose_targets(["bob"])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Mountain"))
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert bolt.zone is Zone.EXILE
