"""Sagas (CR 714): lore counters, chapter abilities, and the sacrifice that
ends them - History of Benalia is the pool's only one.

Every CR number below was looked up with `knowledge_search(q="...",
type="rules")` in the session that wrote this file:

- **CR 303.5** - "Some enchantments have the subtype 'Saga.'"
- **CR 714.2** - "A chapter symbol is a keyword ability that represents a
  triggered ability referred to as a chapter ability."
- **CR 107.15a** - "'{rN}-[Effect]' means 'When one or more lore counters
  are put onto this Saga, if the number of lore counters on it was less
  than N and became at least N, [effect].'"
- **CR 714.3a** - "Each Saga without read ahead has the intrinsic ability
  'This Saga enters with a lore counter on it.'" (a CR 614.1c replacement
  effect, applied as the Saga arrives).
- **CR 703.4f / 505.4 / 714.3c** - "Immediately after a player's precombat
  main phase begins, that player puts a lore counter on each Saga
  enchantment they control with one or more chapter abilities."
- **CR 714.2d** - "A Saga's final chapter number is the greatest value among
  chapter abilities it has."
- **CR 714.4 / 704.5s** - a Saga at or past its final chapter number, and
  not the source of a chapter ability that has triggered but not yet left
  the stack, is put into its owner's graveyard as a state-based action.
- **CR 122.6** - counters put on as an object enters count as counters
  "being put on" it, for a trigger condition's purposes - what makes CR
  714.3a's own intrinsic lore counter fire chapter I at all.

History of Benalia: "(As this Saga enters and after your draw step, add a
lore counter. Sacrifice after III.) I, II - Create a 2/2 white Knight
creature token with vigilance. III - Knights you control get +2/+1 until
end of turn."
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def _cast_history_of_benalia() -> Scenario:
    scenario = (
        Scenario()
        .player("alice", hand=["History of Benalia"], battlefield=["Plains"] * 3)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Plains", "Plains", "Plains")
    scenario.cast_and_resolve("History of Benalia", *sources)
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()
    return scenario


def test_entering_puts_on_the_first_lore_counter_and_triggers_chapter_one():
    """CR 714.3a's intrinsic lore counter, and CR 107.15a's chapter I
    reading it as "one or more lore counters ... put onto this Saga"
    (CR 122.6) the instant it arrives - a 2/2 vigilant Knight, with no
    turn-based action needed at all."""
    scenario = _cast_history_of_benalia()
    saga = scenario.find("History of Benalia", Zone.BATTLEFIELD)

    assert saga.counters[Counter.LORE] == 1
    knights = [p for p in scenario.game.battlefield if p.name == "Knight Token"]
    assert len(knights) == 1
    characteristics = scenario.game.characteristics_of(knights[0])
    assert (characteristics.power, characteristics.toughness) == (2, 2)
    assert "Vigilance" in characteristics.abilities


def test_precombat_main_is_wired_to_add_a_lore_counter():
    """CR 703.4f's own turn-based action, run through the harness's
    single-step helper (`Game.turn_based_actions`, the same dispatcher a
    real `Game.advance` calls for whatever step it just entered) rather than
    `game.saga_lore_step()` directly, so it is the `Step.PRECOMBAT_MAIN`
    wiring itself under test, not just the underlying method.

    The Saga starts already on the battlefield (CR 714.3a's own intrinsic
    lore counter fires as part of `Scenario.player`'s own build, the same
    replacement `_cast_history_of_benalia`'s ETB path exercises above) so
    this one call's effect - one more counter, nothing else - is isolated
    from the cast and its own trigger.
    """
    scenario = Scenario().player("alice", battlefield=["History of Benalia"]).player("bob").build()
    saga = scenario.find("History of Benalia", Zone.BATTLEFIELD)
    assert saga.counters[Counter.LORE] == 1

    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.turn_based_actions()

    assert saga.counters[Counter.LORE] == 2


def test_chapter_three_pumps_the_knights_then_the_saga_is_put_into_the_graveyard():
    """The third lore counter crosses chapter III's own threshold - "Knights
    you control get +2/+1 until end of turn" - and CR 714.4/704.5s then
    finds the Saga at its final chapter number with nothing left owed to
    it, so it goes to its owner's graveyard as a state-based action, not a
    sacrifice a player chose (CR 704.5s never uses that word).

    `Game.saga_lore_step` is called directly here, in place of driving two
    full opposing turns through `Game.advance` (which the wiring test above
    already covers on its own) - CR 703.4f is turn-agnostic once it fires,
    reading only "the active player" and "a Saga they control", so calling
    it twice more is the identical production behaviour two more of alice's
    precombat mains would produce.
    """
    scenario = _cast_history_of_benalia()
    saga = scenario.find("History of Benalia", Zone.BATTLEFIELD)

    for _ in range(2):
        scenario.game.saga_lore_step()
        scenario.game.put_triggers_on_stack()
        while scenario.game.stack:
            scenario.resolve_top()

    assert saga.zone is Zone.GRAVEYARD
    knights = [p for p in scenario.game.battlefield if p.name == "Knight Token"]
    assert len(knights) == 2
    for knight in knights:
        characteristics = scenario.game.characteristics_of(knight)
        assert (characteristics.power, characteristics.toughness) == (4, 3)


def test_a_saga_below_its_final_chapter_number_is_never_swept_up():
    """CR 714.4's own floor: one lore counter (chapter I only) is nowhere
    near History of Benalia's final chapter number of 3, so the ordinary
    state-based action sweep leaves it alone."""
    scenario = _cast_history_of_benalia()
    saga = scenario.find("History of Benalia", Zone.BATTLEFIELD)

    gone = scenario.state_based_actions()

    assert saga not in gone
    assert saga.zone is Zone.BATTLEFIELD
