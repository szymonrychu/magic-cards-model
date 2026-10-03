"""Scenario: a mass pump followed by "If `<condition>`, those creatures get
`<A>`/`<B>` until end of turn instead." (CR 614.1a's "instead" replaces the
whole preceding sentence's effect, never adds to it - the mass-pump twin of
`test_layer_effect_instead_counter_upgrade.py`'s single-target "put N
counters on it instead").

Pride of Conquerors (reported): "Ascend (If you control ten or more
permanents, you get the city's blessing for the rest of the game.) Creatures
you control get +1/+1 until end of turn. If you have the city's blessing,
those creatures get +2/+2 until end of turn instead." `_parse_mass_pump_
clause` used to read only the leading "Creatures you control get +1/+1 until
end of turn." and drop the whole city's-blessing sentence as an unparsed
remainder - the pump always ran at its base size even with the blessing.

Dauntless Unity is the off-pool generality proof: the identical shape with a
different condition (CR 702.33d's kicker, not CR 702.131c's city's blessing),
a different upgraded amount (+2/+1, not +2/+2), and a spell rather than an
ability's own resolution - `_parse_mass_pump_instead_upgrade` and `Game.
condition_holds` both already answer this condition for every other card
that prints it; only the mass-pump composition was missing.

Rules verified with `mise run rules:find` (on-disk CR effective 2026-09-25):

- **CR 614.1a** - "instead" effects are replacement effects; CR 608.2c's own
  worked example (Comprehensive Rules, quoted in `test_layer_effect_instead_
  counter_upgrade.py`) is the identical "later text modifies earlier text"
  reading applied here to a bigger pump rather than a counter.
- **CR 702.131a/c** - ascend on an instant or sorcery spell (Pride of
  Conquerors is an instant, never CR 702.131b's permanent-static form), and
  the city's blessing designation.
- **CR 611.2/611.2a** - the pump itself, a continuous effect lasting until
  end of turn.
- **CR 702.33d** - a spell whose kicker cost was declared "has been kicked".
"""

from magic_cards_model.machines import Step
from tests.scenarios.harness import Scenario


def computed(scenario: Scenario):
    return scenario.game.continuous_effects.board(scenario.game.battlefield)


def test_pride_of_conquerors_pumps_by_one_without_the_citys_blessing():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Pride of Conquerors"],
            battlefield=["Grizzly Bears", "Plains", "Mountain"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    assert not scenario.player("alice").has_citys_blessing

    scenario.cast_and_resolve(
        "Pride of Conquerors", *scenario.untapped_sources("Plains", "Mountain")
    )

    assert computed(scenario).of(bears).power_toughness == (3, 3), "a 2/2 plus a temporary +1/+1"


def test_pride_of_conquerors_pumps_by_two_with_the_citys_blessing():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Pride of Conquerors"],
            battlefield=["Grizzly Bears", "Plains"] + ["Forest"] * 8,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    assert len(scenario.game.permanents_controlled_by("alice")) == 10

    scenario.cast_and_resolve("Pride of Conquerors", *scenario.untapped_sources("Plains", "Forest"))

    assert scenario.player("alice").has_citys_blessing, "ascend grants it as the spell resolves"
    assert computed(scenario).of(bears).power_toughness == (4, 4), (
        "a 2/2 plus the upgraded +2/+2, not the base +1/+1"
    )


def test_dauntless_unity_pumps_by_one_when_not_kicked_off_pool():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Dauntless Unity"],
            battlefield=["Grizzly Bears", "Plains", "Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    casting = scenario.cast("Dauntless Unity", "alice")
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Plains", "Forest"))
    scenario.put_on_stack(casting)
    scenario.pass_until_resolved()

    assert computed(scenario).of(bears).power_toughness == (3, 3), "a 2/2 plus a temporary +1/+1"


def test_dauntless_unity_pumps_by_two_one_when_kicked_off_pool():
    """Off-pool generality proof: a different amount (+2/+1) and a different
    condition (kicker) than Pride of Conquerors' own +2/+2 and city's
    blessing, proving the reader is not fitted to the one reported card."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Dauntless Unity"],
            battlefield=["Grizzly Bears", "Plains", "Plains", "Forest", "Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    casting = scenario.cast("Dauntless Unity", "alice")
    casting.pay_kicker(1)
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Plains", "Plains", "Forest", "Forest"))
    scenario.put_on_stack(casting)
    scenario.pass_until_resolved()

    assert computed(scenario).of(bears).power_toughness == (4, 3), (
        "a 2/2 plus the upgraded +2/+1, not the base +1/+1"
    )
