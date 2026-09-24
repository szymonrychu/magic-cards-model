"""Scenario: a cast trigger putting +1/+1 counters equal to the cast spell's
own mana value (CR 400.7's "that spell" anaphora, CR 107.3f's X-by-definition,
CR 122.1's counters).

Dancing from Dark to Dawn: "Whenever you cast a creature spell, put X +1/+1
counters on target creature you control, where X is that spell's mana
value."

Verified this session with `mise run rules:find`:

- **CR 601.2b** - targets for a triggered ability are chosen as it is put on
  the stack, before the spell it watches has necessarily resolved (here it
  is still on the stack, above this trigger).
- **CR 202.3** - mana value; CR 202.3e's own X-on-the-stack special case does
  not apply here since none of these creature spells carry an {X} cost.

No off-pool second printing of this exact wording was found by
`card_search`; the composition is HOB-only (dated MEMORY.md line). The
underlying anaphora this reader threads through - `ability.event.subject_id`
naming "that spell" - is the identical channel `_parse_counter_that_spell_
clause` and `_parse_counter_then_create_tokens_by_mana_value_pair` already
use for Vexing Bauble/Chalice of the Void and Access Denied, both pre-existing
and covered by their own tests.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models.card_state import Counter

from .harness import Scenario


def test_counters_equal_the_cast_creature_spells_own_mana_value():
    """Casting a 3-mana-value Grizzly Bears puts 3 +1/+1 counters on the
    target creature - here, Dancing from Dark to Dawn's own controller has
    another creature already on the battlefield to target."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Grizzly Bears"],
            battlefield=["Dancing from Dark to Dawn", "Elvish Mystic"] + ["Forest"] * 3,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    target = scenario.creature("Elvish Mystic", "alice")

    scenario.choose_trigger_targets("Dancing from Dark to Dawn", [target])
    scenario.cast_and_resolve("Grizzly Bears", *scenario.untapped_sources(*["Forest"] * 3))
    scenario.pass_until_resolved()

    assert target.counters[Counter.PLUS_ONE] == 2  # Grizzly Bears is {1}{G}, mana value 2


def test_a_noncreature_spell_does_not_trigger_it():
    """CR 601.2b/700.2: "you cast a creature spell" only - an instant does
    not fire the ability at all."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Bolt"],
            battlefield=["Dancing from Dark to Dawn", "Elvish Mystic"] + ["Mountain"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    target = scenario.creature("Elvish Mystic", "alice")

    scenario.cast_and_resolve(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=["bob"]
    )
    scenario.pass_until_resolved()

    assert target.counters[Counter.PLUS_ONE] == 0
