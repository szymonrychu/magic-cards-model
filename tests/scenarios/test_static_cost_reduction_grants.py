"""Board-wide static cost *decreases* a permanent grants to its controller's
own spells (CR 601.2f) - the Medallion cycle's own template, "`<Color>`
spells you cast cost `{N}` less to cast." Ruby Medallion's printing (verified
with `resolve_cards` in this session, against
`tests/fixtures/cards/ruby_medallion.json`): "Red spells you cast cost {1}
less to cast."

`test_costs.py` already covers this project's board-wide *increase* half
(Sphere of Resistance, Trinisphere's floor, Damping Sphere) through
`Game.static_cost_modifiers_for`; this file is the decrease half of the same
primitive, gated the increases never needed - "you cast" makes the grant
controller-scoped rather than universal.

Every rule cited here was looked up with `knowledge_search(type="rules")` in
the session that wrote this file:

- **CR 601.2f** - "Some effects may increase or reduce the cost to pay ...
  Once the total cost is determined, any effects that directly affect the
  total cost are applied."
- **CR 205.2b** - "Some objects have more than one card type ... Such objects
  satisfy the criteria for any effect that applies to any of their card
  types" - read here backwards, for *color*: a spell need only carry the one
  named color among however many it has.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import ManaCost, Zone

from .harness import Scenario


def test_ruby_medallion_discounts_a_red_spell_by_one_generic_mana():
    scenario = (
        Scenario()
        .player("alice", hand=["Lightning Bolt"], battlefield=["Mountain", "Ruby Medallion"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Lightning Bolt")

    assert casting.total_cost.mana == ManaCost.parse("{R}")


def test_a_single_mountain_now_pays_for_the_discounted_bolt():
    """The DDR#978-shaped repro, run the other way: the fix has to be
    observable in an actual payment, not only in the priced number."""
    scenario = (
        Scenario()
        .player("alice", hand=["Lightning Bolt"], battlefield=["Mountain", "Ruby Medallion"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    (mountain,) = scenario.untapped_sources("Mountain")

    bolt = scenario.cast_and_resolve("Lightning Bolt", mountain, targets=[bears])

    assert bolt.zone is Zone.GRAVEYARD
    assert scenario.game.permanents_controlled_by("bob") == []


def test_ruby_medallion_does_not_discount_a_blue_spell():
    """ "Red spells" names one color; CR 205.2b's multi-type matching runs the
    same way for color, but Counterspell simply is not red at all."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Counterspell"],
            battlefield=["Island", "Island", "Ruby Medallion"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Counterspell")

    assert casting.total_cost.mana == ManaCost.parse("{U}{U}")


def test_ruby_medallion_does_not_discount_an_opponents_red_spell():
    """ "Spells you cast" is controller-scoped - alice's Medallion does not
    touch bob's own Lightning Bolt."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Ruby Medallion"])
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Lightning Bolt", username="bob")

    assert casting.total_cost.mana == ManaCost.parse("{R}")


def test_two_ruby_medallions_stack_their_discount():
    """CR 601.2f: every applicable effect is applied - nothing here caps a
    board to one copy of an ability. Blood Moon ({2}{R}) rather than
    Lightning Bolt ({R}): CR 118.7a lets a reduction touch only the generic
    component, and two generic pips is what actually shows two Medallions
    doing more than one."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Blood Moon"],
            battlefield=["Mountain", "Mountain", "Ruby Medallion", "Ruby Medallion"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Blood Moon")

    assert casting.total_cost.mana == ManaCost.parse("{R}")


def test_the_discount_does_not_go_below_zero_generic_mana():
    """`apply_modifications` (the same one `test_sphere_of_resistance...`
    exercises for an increase) floors generic mana at {0} rather than paying
    a player to cast their own spell - three Medallions' {3} against Blood
    Moon's own two generic pips."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Blood Moon"],
            battlefield=[
                "Mountain",
                "Mountain",
                "Ruby Medallion",
                "Ruby Medallion",
                "Ruby Medallion",
            ],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Blood Moon")

    assert casting.total_cost.mana == ManaCost.parse("{R}")


def test_sphere_of_resistances_increase_applies_before_the_medallions_decrease():
    """`apply_modifications`'s own documented ordering (`test_costs.py`'s own
    `test_increase_applies_before_a_generic_reduction_can_touch_it`):
    increases first, decreases after - a taxed {1}{R} discounted by {1}
    lands back on the printed {R}, not on some lower number an increase
    should have touched first."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Bolt"],
            battlefield=["Mountain", "Ruby Medallion", "Sphere of Resistance"],
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Lightning Bolt")

    assert casting.total_cost.mana == ManaCost.parse("{R}")
