"""Ajani Resolute's own "Whenever you gain life, put a loyalty counter on
Ajani." - CR 201.5c's bare two-word short name (no comma, no "the"/"of"
epithet at all) naming itself, feeding a self-referential loyalty-counter
trigger body.

`self_normalized_effect_text` (`machines/abilities.py`) already rewrites the
bare short form to CR 700.7's "this permanent"
(`test_self_reference_names.py::test_a_bare_two_word_legend_shortens_to_its_
first_word` proves that unit in isolation), and the resulting "put a loyalty
counter on this permanent." is an ordinary self-referential counter clause
`trigger_effect_for` already reads. What was missing before this file is a
real, played-through-the-engine proof that the whole chain - short name ->
normalized text -> trigger fires on a genuine life gain -> the loyalty
counter actually lands - works end to end, not merely that the text
rewrites correctly in isolation.

Verified this session with `mise run rules:find` (on-disk CR effective
2026-09-25):

- **CR 201.5c** - a card's own shortened name, used on itself, means the
  card (quoted above).
- **CR 306.5b** - a planeswalker enters with loyalty counters equal to its
  printed loyalty (Ajani Resolute prints 2, so `0: You gain 1 life.` is
  payable at once).
- **CR 122.1/122.5** - counters generally; a loyalty counter is CR 306.5's
  own kind.
- **CR 119.3** - life gain generally, which the trigger condition reads
  regardless of source - a coin flip's own life gain and lifelink's both
  qualify, not only the planeswalker's own `0` ability.
"""

from magic_cards_model.machines import Step
from tests.scenarios.harness import Scenario


def test_ajani_resolutes_zero_ability_gains_life_and_puts_a_loyalty_counter():
    scenario = Scenario().player("alice", battlefield=["Ajani Resolute"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ajani = scenario.creature("Ajani Resolute", "alice")
    assert ajani.loyalty == 2, "CR 306.5b: its own printed loyalty"

    scenario.activate(ajani, index=0)  # "0: You gain 1 life."
    scenario.pass_until_resolved()  # the 0 ability itself
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == ["Ajani Resolute's triggered ability"]
    scenario.pass_until_resolved()  # the "whenever you gain life" trigger

    assert scenario.player("alice").life == 21
    assert ajani.loyalty == 3, "the 0 cost paid nothing, then the trigger added one"


def test_the_trigger_fires_for_any_life_gain_not_only_its_own_zero_ability():
    """CR 119.3: "whenever you gain life" is not scoped to Ajani's own `0` -
    a different source of life gain (staged here directly through `Game.
    gain_life`, the same primitive lifelink and every other life-gain effect
    in the pool goes through) fires the identical trigger."""
    scenario = Scenario().player("alice", battlefield=["Ajani Resolute"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ajani = scenario.creature("Ajani Resolute", "alice")
    alice = scenario.player("alice")

    scenario.game.gain_life(alice, 5)
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == ["Ajani Resolute's triggered ability"]
    scenario.pass_until_resolved()

    assert alice.life == 25
    assert ajani.loyalty == 3
