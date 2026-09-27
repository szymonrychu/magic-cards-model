"""Scenario: a single-target pump activated ability whose "instead" upgrade
condition asks about the mana that paid the *activation itself* (CR 601.2h,
imported for activation by CR 602.2b) - `_parse_layer_counter_instead_
upgrade`'s existing "if `<condition>`, put N counters on it instead" shape
(`test_layer_effect_instead_counter_upgrade.py`), with a condition family
this engine could not read at all before: `machines/conditions/
activation.py`, off `AbilityOnStack.mana_spent`/`treasure_mana_spent`
(schema 96).

Paragon of Modernity: "{3}: This creature gets +1/+1 until end of turn. If
exactly three colors of mana were spent to activate this ability, put a
+1/+1 counter on it instead."

Jetmir's Fixer: "{R}{G}: This creature gets +1/+1 until end of turn. If mana
from a Treasure was spent to activate this ability, put a +1/+1 counter on
this creature instead." Together the two cards prove the shared machinery
(the resolving `AbilityOnStack` itself, threaded through `Game.condition_
holds`'s own `ability=` parameter) against two genuinely different
conditions - a distinct-colors count and a mana source - neither hand-fitted
to the other's wording.

Rules verified with `mise run rules:find` (on-disk CR effective 2026-09-25):

- **CR 602.2b** - "The remainder of the process for activating an ability is
  identical to the process for casting a spell ... An activated ability's
  analog to a spell's mana cost ... is its activation cost."
- **CR 601.2h** - the total cost is paid; that is "the mana spent".
- **CR 105.1** - the five colors of mana; **CR 105.2c** - colorless is not
  one of them.
- **CR 106.3** - the source of mana is the source of the ability that
  produced it - a Treasure's own sacrifice ability.
- **CR 614.1a** - "instead" replaces the whole preceding sentence's effect.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Color
from magic_cards_model.models.card_state import Counter
from magic_cards_model.models.token import create_predefined_tokens
from tests.scenarios.harness import Scenario


def computed(scenario: Scenario):
    return scenario.game.continuous_effects.board(scenario.game.battlefield)


def test_paragon_of_modernity_pumps_with_two_colors():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Paragon of Modernity", "Mountain", "Mountain", "Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    paragon = scenario.creature("Paragon of Modernity", "alice")
    scenario.activate(paragon, *scenario.untapped_sources("Mountain", "Mountain", "Forest"))
    scenario.pass_until_resolved()

    assert paragon.counter_count(Counter.PLUS_ONE) == 0
    assert computed(scenario).of(paragon).power_toughness == (3, 3), "a 2/2 plus a temporary +1/+1"


def test_paragon_of_modernity_upgrades_to_a_counter_with_exactly_three_colors():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Paragon of Modernity", "Mountain", "Forest", "Plains"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    paragon = scenario.creature("Paragon of Modernity", "alice")
    scenario.activate(paragon, *scenario.untapped_sources("Mountain", "Forest", "Plains"))
    scenario.pass_until_resolved()

    assert paragon.counter_count(Counter.PLUS_ONE) == 1, "the counter, not the temporary pump"
    assert computed(scenario).of(paragon).power_toughness == (3, 3), "the same +1/+1, now lasting"


def test_jetmirs_fixer_pumps_when_no_treasure_mana_is_spent():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Jetmir's Fixer", "Mountain", "Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    fixer = scenario.creature("Jetmir's Fixer", "alice")
    scenario.activate(fixer, *scenario.untapped_sources("Mountain", "Forest"))
    scenario.pass_until_resolved()

    assert fixer.counter_count(Counter.PLUS_ONE) == 0
    assert computed(scenario).of(fixer).power_toughness == (3, 3), "a 2/2 plus a temporary +1/+1"


def test_jetmirs_fixer_upgrades_to_a_counter_when_treasure_mana_is_spent():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Jetmir's Fixer", "Forest"],
        )
        .player("bob")
        .build()
    )
    # The Treasure pays the {R} half of {R}{G}; the Forest still pays {G}.
    scenario.start_at(Step.PRECOMBAT_MAIN)
    fixer = scenario.creature("Jetmir's Fixer", "alice")
    (treasure,) = create_predefined_tokens(scenario.game, "Treasure", "alice")
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()
    scenario.game.activate_ability(treasure, 0, "alice", color=Color.RED)

    scenario.activate(fixer, *scenario.untapped_sources("Forest"))
    scenario.pass_until_resolved()

    assert fixer.counter_count(Counter.PLUS_ONE) == 1, "the counter, not the temporary pump"
    assert computed(scenario).of(fixer).power_toughness == (3, 3), "the same +1/+1, now lasting"
