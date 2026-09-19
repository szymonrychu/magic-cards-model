"""Stingcaster Mage: "Haste. When this creature enters, target instant or
sorcery card in your graveyard gains flashback until end of turn. The
flashback cost is equal to its mana cost."

Word for word the same sentence `test_flashback_grant.py`'s own "Flashback"
spell prints - `_GRANT_FLASHBACK_RE`/`_parse_grant_flashback_clause` already
read it - but here it is a creature's ETB *trigger* consequence, not a
spell's whole and only instruction. `trigger_effect_for` with no
`TRIGGER_EFFECTS` row falls back to `_ability_effect_or_notice`, a different
function from the `_spell_effect_or_notice` the spell path uses, and the
flashback-grant check was previously wired into the spell path only - a
creature printing this exact sentence had no path to it at all. Proven here
on a genuinely different card shape (a permanent's triggered ability) rather
than by re-reading the "Flashback" instant.

CR numbers below were looked up with `knowledge_search(q="...", type="rules")`
in the session that wrote this file (already verified once for
`test_flashback_grant.py`, re-confirmed for reuse here):

- **CR 702.34a** - flashback's two static abilities.
- **CR 601.3** - "A player can begin to cast a spell only if a rule or effect
  allows that player to cast it."
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.casting import PlayAction
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_the_etb_trigger_grants_flashback_to_the_targeted_graveyard_card():
    """The permission is recorded exactly as the spell's own grant is:
    CR 601.3, aimed at the graveyard, paying the card's own mana cost."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Stingcaster Mage"],
            graveyard=["Lightning Bolt"],
            battlefield=["Mountain", "Mountain"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bolt = scenario.find("Lightning Bolt", Zone.GRAVEYARD, "alice")
    sources = scenario.untapped_sources("Mountain", "Mountain")

    scenario.choose_trigger_targets("Stingcaster Mage", [bolt])
    scenario.cast_and_resolve("Stingcaster Mage", *sources)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    permission = scenario.game.play_permission_for(bolt, "alice")
    assert permission is not None
    assert permission.action is PlayAction.CAST
    assert permission.pays_mana_cost is True
    assert permission.zone is Zone.GRAVEYARD


def test_the_granted_flashback_can_actually_be_cast_and_is_exiled_after():
    """CR 702.34a's second static ability rides along with a trigger-granted
    flashback exactly as it does with a spell-granted one: once paid, the
    resolved spell is exiled rather than returned to the graveyard."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Stingcaster Mage"],
            graveyard=["Lightning Bolt"],
            battlefield=["Mountain", "Mountain", "Mountain"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bolt = scenario.find("Lightning Bolt", Zone.GRAVEYARD, "alice")
    sources = scenario.untapped_sources("Mountain", "Mountain")

    scenario.choose_trigger_targets("Stingcaster Mage", [bolt])
    scenario.cast_and_resolve("Stingcaster Mage", *sources)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    casting = scenario.cast("Lightning Bolt", from_zone=Zone.GRAVEYARD)
    casting.use_permission()
    casting.choose_targets(["bob"])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Mountain"))
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert bolt.zone is Zone.EXILE
    assert scenario.player("bob").life == 17
