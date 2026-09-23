"""Scenario: "Whenever you get one or more <counter kind>" - a player-counter
trigger condition, CR 122.6's own event from the player's side of the sentence
rather than a permanent's.

Before this file, `Game.add_player_counters` (`models/game.py`) put counters
on a player, replacement effects included, and emitted nothing - so a card
whose whole ability was watching for that event, energy's own shape chief
among them, silently never triggered. `machines/triggers.py` had no matcher
for the condition at all: `_unread_trigger_events` dropped it, the same way
it dropped a permanent's own "counters are put on this creature" before
`ExtraTriggerEvent.COUNTERS_PUT` existed.

Two real, currently-legal printings carry the exact shape, oracle text
verified with `scripts/add_card.py` against Scryfall:

- **Fabrication Module** (Modern/Pioneer-legal artifact, `{3}`): "Whenever you
  get one or more {E} (energy counters), put a +1/+1 counter on target
  creature you control.\\n{4}, {T}: You get {E}." Its own activated ability is
  the real energy source this file drives case (d) with - "{4}, {T}: You get
  {E}." already resolves through `machines/effects._ENERGY_RE`'s existing
  `game.add_player_counters(player, Counter.ENERGY, amount)` call, so nothing
  about *getting* the energy needed to change; only the *event* that getting
  it now raises is new.
- **Territorial Gorger** (Modern/Pioneer-legal creature, `{3}{R}`, 2/2,
  trample): "Whenever you get one or more {E} (energy counters), this
  creature gets +2/+2 until end of turn." The second printing proves the
  reader is keyed on the condition's shape and the counter kind, not on
  Fabrication Module's own sentence: its effect clause is completely
  different (a pump, not a counter), and it carries reminder text
  Fabrication Module's trigger condition does too - both are stripped by
  `machines/abilities.parse_abilities` before either module ever sees the
  condition text, which is why `you get one or more {e}` (case-normalised,
  no trailing "(energy counters)") is the literal string
  `_PLAYER_COUNTERS_PUT_CONDITION` matches.

Cases (e)-(h) exercise the matcher and the emit guard directly against
`Game.add_player_counters` - the same real, production entry point Fabrication
Module's own activated ability calls - rather than hunting for a second real
card for every corner of CR 603.2c/603.2g/109.5: `tests/scenarios/
test_counter_placement_triggers.py`'s own `counters_put` helper sets this
precedent for a permanent's counters-put condition, staging the event through
the engine's own dispatcher instead of a bespoke card for each shape.

Every CR number below was looked up with `mise run rules:find <n>` against
the checksum-verified rules pull in the session that wrote this file:

- **CR 107.14** - "The energy symbol is {E}. It represents one energy
  counter."
- **CR 122.6** - "counters being put on an object" (also read as "or player" -
  CR 122.1's own "some kinds of counters are normally placed on players
  rather than on objects").
- **CR 603.2c** - "An ability triggers only once each time its trigger event
  occurs. However, it can trigger repeatedly if one event contains multiple
  occurrences" - two {E} in one instruction is one occurrence with a count,
  not two occurrences.
- **CR 603.2g** - "An ability triggers only if its trigger event actually
  occurs. An event that's prevented or replaced won't trigger anything" - a
  replacement (or a bare zero-amount call) that leaves nothing to get raises
  no event and triggers nothing.
- **CR 109.5** - "you"/"your" on an object's text is the object's controller
  (for a triggered ability, the controller when it triggered) - which is why
  an opponent's own energy never matches "whenever *you* get".
"""

from magic_cards_model.machines import Step
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def board() -> Scenario:
    """Alice controls both printings and enough mana to activate Fabrication
    Module's own energy-granting ability; bob is the opponent case (f) needs."""
    return (
        Scenario()
        .player(
            "alice",
            battlefield=["Fabrication Module", "Territorial Gorger"] + ["Mountain"] * 4,
        )
        .player("bob")
    )


def test_fabrication_module_activation_triggers_both_energy_conditions():
    """(d) Fabrication Module's own "{4}, {T}: You get {E}." resolved for
    real triggers both energy conditions in the pool at once: Fabrication
    Module's own "put a +1/+1 counter on target creature you control", and
    Territorial Gorger's own "+2/+2 until end of turn" - the same event,
    matched by two differently-worded printings.
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    module = scenario.creature("Fabrication Module", "alice")
    gorger = scenario.creature("Territorial Gorger", "alice")
    mana = scenario.untapped_sources("Mountain", "Mountain", "Mountain", "Mountain")

    assert scenario.player("alice").counters[Counter.ENERGY] == 0

    scenario.activate(module, *mana)
    scenario.resolve_top()  # "{4}, {T}: You get {E}." - not a mana ability, goes on the stack

    assert scenario.player("alice").counters[Counter.ENERGY] == 1

    # `resolve_top` already ran the engine's own CR 704.3 priority-passing
    # loop, which is what puts a pending trigger onto the stack in the first
    # place - so both abilities are on `game.stack` already, Fabrication
    # Module's own already auto-targeted at the only legal target on the
    # board (Territorial Gorger).
    assert {ability.source_name for ability in scenario.game.stack} == {
        "Fabrication Module",
        "Territorial Gorger",
    }
    while scenario.game.stack:
        scenario.resolve_top()

    assert gorger.counters == {"+1/+1": 1}
    board_state = scenario.game.computed_board().of(gorger)
    # Printed 2/2, one +1/+1 counter, +2/+2 until end of turn: 2+1+2 = 5.
    assert (board_state.power, board_state.toughness) == (5, 5)


def test_two_energy_in_one_instruction_is_one_trigger_each():
    """(e) CR 603.2c: `Game.add_player_counters(alice, ENERGY, 2)` is one
    instruction with a count of two, not two instructions - each condition in
    the pool trigger once, not twice."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")

    scenario.game.add_player_counters(alice, Counter.ENERGY, 2)

    assert [trigger.source_name for trigger in scenario.pending_triggers].count(
        "Fabrication Module"
    ) == 1
    assert [trigger.source_name for trigger in scenario.pending_triggers].count(
        "Territorial Gorger"
    ) == 1


def test_an_opponents_energy_does_not_trigger_your_own_whenever_you_get():
    """(f) CR 109.5: "you" on Fabrication Module's and Territorial Gorger's
    own text is *their controller* (alice), not just any player - bob
    getting {E} of his own matches neither condition."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bob = scenario.player("bob")

    scenario.game.add_player_counters(bob, Counter.ENERGY, 3)

    assert scenario.pending_triggers == []


def test_a_different_counter_kind_does_not_trigger_the_energy_condition():
    """(g) Both printed conditions name {E} specifically - a poison counter
    reaching the same player, through the same real `Game` method, is a
    counter arriving with the wrong kind and matches neither."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")

    scenario.game.add_player_counters(alice, Counter.POISON, 1)

    assert alice.counters[Counter.POISON] == 1
    assert scenario.pending_triggers == []


def test_a_reduction_to_zero_emits_no_event_and_triggers_nothing():
    """(h) CR 603.2g: an event that never actually happens triggers nothing.
    `Game.add_player_counters`'s own replacement step can bring `event.amount`
    to zero or less (CR 614.1a's "doesn't happen at all" shape); this proves
    the guard on the far side of that step - the one `_emit_player_counters_
    put` shares with `_emit_counters_put`'s own "amount <= 0" line - by
    calling the real entry point with nothing left to get."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")

    total = scenario.game.add_player_counters(alice, Counter.ENERGY, 0)

    assert total == 0
    assert alice.counters[Counter.ENERGY] == 0
    assert scenario.pending_triggers == []
