"""CR 405.6c: a mana ability's own "another effect", paid alongside the mana.

Bug report: Talisman of Resilience's `{T}: Add {B} or {G}. This artifact deals
1 damage to you.` produced the mana in play, but the controller's life stayed
at 20 - the second sentence never happened.

Rules looked up this session:

- **CR 605.1a** - an activated ability is a mana ability if it meets four
  criteria (no target, could add mana, not a loyalty ability, moves no library
  card); nothing in the criteria disqualifies a second sentence.
- **CR 605.3b** - "An activated mana ability doesn't go on the stack, so it
  can't be targeted, countered, or otherwise responded to. Rather, it resolves
  immediately after it is activated. (See rule 405.6c.)"
- **CR 405.6c** - "Mana abilities resolve immediately. If a mana ability both
  produces mana and has another effect, the mana is produced and the other
  effect happens immediately."

So the whole paragraph is one ability (CR 113.3b/602.1), it stays a mana
ability, and its "other effect" is not a separate triggered ability, not put on
the stack, and not optional - it happens in the same instant as the mana.

The fix is general, not a Talisman special case: `machines/abilities.py`'s
`_parse_mana_rider` reads the trailing sentence off *any* `{T}: Add ...`
ability's own printed text, and `Game.activate_ability`'s mana fast path
applies it. Karplusan Forest (`{T}: Add {R} or {G}. This land deals 1 damage to
you.`) is the second, independently-printed card in the fixture pool that
exercises the exact same parser with no card-name-keyed code at all.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Color, Zone
from tests.scenarios.harness import Scenario


def test_talismans_colored_mana_ability_also_deals_1_damage():
    """The reported bug, reproduced: the mana lands in the pool and the
    controller loses exactly 1 life, in the same activation (CR 405.6c)."""
    scenario = Scenario().player("alice", battlefield=["Talisman of Resilience"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    talisman = scenario.find("Talisman of Resilience", Zone.BATTLEFIELD)

    assert scenario.player("alice").life == 20

    scenario.activate(talisman, index=1, color=Color.BLACK)

    assert scenario.player("alice").mana_pool.floating == {Color.BLACK: 1}
    assert scenario.player("alice").life == 19, "the rider must fire, not be dropped"


def test_talismans_colored_ability_offers_its_other_color_too():
    """The same ability, the other half of its "or" - and the same 1 damage,
    since the rider is on the ability, not on the colour chosen."""
    scenario = Scenario().player("alice", battlefield=["Talisman of Resilience"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    talisman = scenario.find("Talisman of Resilience", Zone.BATTLEFIELD)

    scenario.activate(talisman, index=1, color=Color.GREEN)

    assert scenario.player("alice").mana_pool.floating == {Color.GREEN: 1}
    assert scenario.player("alice").life == 19


def test_talismans_colorless_ability_has_no_rider():
    """Talisman's *other* printed ability, `{T}: Add {C}.`, is a separate
    paragraph (CR 602.1) with no second sentence - CR 405.6c has nothing to
    apply, and life must stay at 20."""
    scenario = Scenario().player("alice", battlefield=["Talisman of Resilience"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    talisman = scenario.find("Talisman of Resilience", Zone.BATTLEFIELD)

    scenario.activate(talisman, index=0)

    assert scenario.player("alice").mana_pool.floating == {Color.COLORLESS: 1}
    assert scenario.player("alice").life == 20


def test_karplusan_forest_shares_the_same_parser_not_a_card_name_fix():
    """A second, independently-printed card with the identical CR 405.6c
    shape ("This land deals 1 damage to you.") - proof the fix reads the
    template generically rather than special-casing Talisman by name."""
    scenario = Scenario().player("alice", battlefield=["Karplusan Forest"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    karplusan = scenario.find("Karplusan Forest", Zone.BATTLEFIELD)

    scenario.activate(karplusan, index=1, color=Color.RED)

    assert scenario.player("alice").mana_pool.floating == {Color.RED: 1}
    assert scenario.player("alice").life == 19


def test_karplusan_forests_colorless_ability_has_no_rider():
    """Karplusan Forest's `{T}: Add {C}.` half, same as Talisman's - no
    second sentence, no life loss."""
    scenario = Scenario().player("alice", battlefield=["Karplusan Forest"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    karplusan = scenario.find("Karplusan Forest", Zone.BATTLEFIELD)

    scenario.activate(karplusan, index=0)

    assert scenario.player("alice").mana_pool.floating == {Color.COLORLESS: 1}
    assert scenario.player("alice").life == 20


def test_the_rider_is_not_prevented_by_a_general_damage_shield():
    """CR 405.6c's "other effect" is still damage (CR 120): a prevention
    shield created against the artifact's own damage stops it, the same way
    it would stop combat damage from that source - proof the fix routes
    through `Game.deal_damage` rather than a bare life-total edit that skips
    CR 615 entirely."""
    from magic_cards_model.models.game import PreventionShield, ShieldKind

    scenario = Scenario().player("alice", battlefield=["Talisman of Resilience"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    talisman = scenario.find("Talisman of Resilience", Zone.BATTLEFIELD)

    scenario.game.create_prevention_shield(
        PreventionShield(
            kind=ShieldKind.ALL,
            label="prevent all damage that would be dealt to alice this turn",
            controller="alice",
            player="alice",
        )
    )

    scenario.activate(talisman, index=1, color=Color.BLACK)

    assert scenario.player("alice").mana_pool.floating == {Color.BLACK: 1}
    assert scenario.player("alice").life == 20, "the shield should have absorbed the rider's damage"
