""" "Until your next turn, whenever a creature attacks you or a planeswalker
you control, it gets -N/-0 until end of turn." - CR 603.7's delayed triggered
ability mechanism carrying two independent durations at once (CR 603.7b): the
*watch* itself lasts until the creating ability's own controller's next turn,
firing on every matching attack until then; each individual pump it grants,
once fired, lasts only until that attack's own ordinary end of turn.

Every rule below was looked up with `mise run rules:find` in the session that
wrote this file:

- **CR 603.7** - an effect may create a delayed triggered ability.
- **CR 603.7b** - "A delayed triggered ability will trigger only once ... unless
  it has a stated duration, such as 'this turn'" - the stated duration here
  ("until your next turn") is what keeps this one firing on every attack, not
  just the first, and its own end is the *start* of the granting player's
  next turn - exactly what the printed words say, not CR 800.4m, which reads
  similarly but is scoped to what happens to such a duration when the player
  it names has left the game entirely (this file never has a player leave).
- **CR 508.3d** - a triggered ability of a permanent that isn't attacking can
  trigger on a creature attacking, among other events.
- **CR 306.6 / CR 508.5** - "a planeswalker you control" among the things a
  creature can attack, alongside the controlling player themselves.
- **CR 611.2a** - the pump itself is an ordinary "until end of turn" continuous
  effect once it exists, independent of how long the watch that produced it
  lasts.

Two real printings, same sentence, different magnitude and different kind of
source ability - proof this is CR 603.7's general delayed-trigger machinery,
not something wired to a planeswalker's own loyalty cost:

- **Jace, Reality Sculptor** - `-3: Until your next turn, whenever a creature
  attacks you or a planeswalker you control, it gets -5/-0 until end of
  turn.` - an activated loyalty ability.
- **Tamiyo Meets the Story Circle** - Saga chapter I, the identical sentence
  with "-2/-0" - a triggered ability (CR 714.2's chapter ability), not an
  activation at all.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.abilities import TriggerEvent
from tests.scenarios.harness import Scenario


def _advance_until(scenario: Scenario, predicate) -> None:
    """Advance until `predicate(scenario)` holds. `automatic_turn_based_actions`
    is on (the default), so every step's own CR 703.3 action runs as it is
    reached, with no attacker ever auto-declared (CR 508.1a: an unscripted
    declaration is "no attackers") - combat has to be driven by hand."""
    while not predicate(scenario):
        scenario.advance()


def _resolve_the_stack(scenario: Scenario) -> None:
    while scenario.game.stack:
        scenario.resolve_top()


# --------------------------------------------------------------------------
# Jace, Reality Sculptor's -3: an activated ability creating the watch
# --------------------------------------------------------------------------


def _jace_board() -> Scenario:
    return (
        Scenario()
        .player("alice", battlefield=["Jace, Reality Sculptor"], library=["Island"] * 5)
        .player(
            "bob",
            battlefield=["Grizzly Bears", "Watchwolf"],
            library=["Forest"] * 5,
        )
    )


def _activate_jaces_minus_three(scenario: Scenario) -> None:
    jace = scenario.creature("Jace, Reality Sculptor", "alice")
    scenario.activate(jace, index=1, username="alice")
    _resolve_the_stack(scenario)


def test_activating_jaces_minus_three_creates_the_watch():
    scenario = _jace_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    _activate_jaces_minus_three(scenario)

    (trigger,) = scenario.game.delayed_triggers.triggers
    assert trigger.event is TriggerEvent.ATTACKS
    assert trigger.controller == "alice"
    assert trigger.defending_controller_only is True
    assert trigger.expires_end_of_next_turn is True
    assert trigger.remaining is None, "a stated duration (CR 603.7b), not a one-shot"


def test_a_creature_attacking_the_controller_gets_the_pump():
    scenario = _jace_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _activate_jaces_minus_three(scenario)

    _advance_until(
        scenario,
        lambda s: s.turn.active_player == "bob" and s.step is Step.DECLARE_ATTACKERS,
    )
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.attack_with(bears, defending="alice")
    _resolve_the_stack(scenario)

    characteristics = scenario.game.characteristics_of(bears)
    assert (characteristics.power, characteristics.toughness) == (2 - 5, 2)


def test_a_creature_attacking_a_planeswalker_the_controller_controls_gets_the_pump():
    """CR 508.5/306.6's other half of "you or a planeswalker you control" -
    attacking Jace himself, rather than alice, still qualifies."""
    scenario = _jace_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _activate_jaces_minus_three(scenario)
    jace = scenario.creature("Jace, Reality Sculptor", "alice")

    _advance_until(
        scenario,
        lambda s: s.turn.active_player == "bob" and s.step is Step.DECLARE_ATTACKERS,
    )
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.attack_with(bears, defending=jace)
    _resolve_the_stack(scenario)

    characteristics = scenario.game.characteristics_of(bears)
    assert (characteristics.power, characteristics.toughness) == (2 - 5, 2)


def test_a_creature_attacking_someone_else_does_not_get_the_pump():
    """`defending_controller_only` has to actually discriminate: a third
    player, carol, is neither alice herself nor a planeswalker alice
    controls, so bob attacking *her* leaves the trigger unmatched - no
    ability on the stack, no pump."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Jace, Reality Sculptor"], library=["Island"] * 5)
        .player("bob", battlefield=["Grizzly Bears"], library=["Forest"] * 5)
        .player("carol", library=["Plains"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _activate_jaces_minus_three(scenario)
    (watch_before,) = scenario.game.delayed_triggers.triggers

    _advance_until(
        scenario,
        lambda s: s.turn.active_player == "bob" and s.step is Step.DECLARE_ATTACKERS,
    )
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.attack_with(bears, defending="carol")

    assert scenario.game.stack == [], "no ATTACKS-watching trigger should have matched"
    characteristics = scenario.game.characteristics_of(bears)
    assert (characteristics.power, characteristics.toughness) == (2, 2)
    # The watch itself is untouched - it did not spend a firing on a non-match.
    (watch_after,) = scenario.game.delayed_triggers.triggers
    assert watch_after == watch_before


def test_the_trigger_fires_again_on_a_second_qualifying_attack():
    """CR 603.7b's stated duration: `remaining=None` lets it fire on every
    matching attack, not just the first - two attackers declared in the same
    combat each get their own pump."""
    scenario = _jace_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _activate_jaces_minus_three(scenario)

    _advance_until(
        scenario,
        lambda s: s.turn.active_player == "bob" and s.step is Step.DECLARE_ATTACKERS,
    )
    bears = scenario.creature("Grizzly Bears", "bob")
    wolf = scenario.creature("Watchwolf", "bob")
    scenario.attack_with(bears, wolf, defending="alice")
    _resolve_the_stack(scenario)

    bears_characteristics = scenario.game.characteristics_of(bears)
    wolf_characteristics = scenario.game.characteristics_of(wolf)
    assert (bears_characteristics.power, bears_characteristics.toughness) == (2 - 5, 2)
    assert (wolf_characteristics.power, wolf_characteristics.toughness) == (3 - 5, 3)


def test_each_pump_expires_at_the_ordinary_end_of_turn_even_though_the_watch_persists():
    """The pump granted to bob's attacker has its own plain `Duration.
    UNTIL_END_OF_TURN` (CR 611.2a) - it is gone by bob's own cleanup, well
    before alice's next turn (and so the watch itself) would end."""
    scenario = _jace_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _activate_jaces_minus_three(scenario)

    _advance_until(
        scenario,
        lambda s: s.turn.active_player == "bob" and s.step is Step.DECLARE_ATTACKERS,
    )
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.attack_with(bears, defending="alice")
    _resolve_the_stack(scenario)
    assert scenario.game.characteristics_of(bears).power == 2 - 5

    # CLEANUP's own CR 514 action already ran as this step was reached
    # (automatic_turn_based_actions) - the pump is a plain "until end of turn"
    # effect and is swept there.
    _advance_until(scenario, lambda s: s.turn.active_player == "bob" and s.step is Step.CLEANUP)

    characteristics = scenario.game.characteristics_of(bears)
    assert (characteristics.power, characteristics.toughness) == (2, 2)
    # The watch itself is untouched by an ordinary cleanup - only alice's own
    # next turn beginning ends it (CR 603.7b's stated duration), and that has
    # not happened yet.
    assert len(scenario.game.delayed_triggers.triggers) == 1


def test_the_watch_stops_firing_once_the_granting_players_own_next_turn_has_begun():
    scenario = _jace_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _activate_jaces_minus_three(scenario)
    turns_taken = scenario.turn.turns_taken

    # bob's turn: the watch is still live, so this attack does get pumped.
    _advance_until(
        scenario,
        lambda s: s.turn.active_player == "bob" and s.step is Step.DECLARE_ATTACKERS,
    )
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.attack_with(bears, defending="alice")
    _resolve_the_stack(scenario)
    assert scenario.game.characteristics_of(bears).power == 2 - 5

    # Walk into alice's own next turn - CR 603.7b's stated-duration boundary,
    # `Game.begin_turn_for`, drops the watch outright.
    _advance_until(
        scenario,
        lambda s: s.turn.turns_taken > turns_taken and s.turn.active_player == "alice",
    )
    assert scenario.game.delayed_triggers.triggers == []

    # bob's next turn again: the same creature attacking again gets nothing.
    _advance_until(
        scenario,
        lambda s: s.turn.active_player == "bob" and s.step is Step.DECLARE_ATTACKERS,
    )
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.attack_with(bears, defending="alice")

    assert scenario.game.stack == [], "the watch expired - nothing left to trigger"
    assert scenario.game.characteristics_of(bears).power == 2


# --------------------------------------------------------------------------
# Tamiyo Meets the Story Circle's chapter I: a triggered (Saga) ability
# creating the identical watch, proving this is CR 603.7's general
# mechanism and not something specific to a planeswalker's own cost.
# --------------------------------------------------------------------------


def _tamiyo_board() -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=["Tamiyo Meets the Story Circle"],
            battlefield=["Island", "Island"],
            library=["Island"] * 5,
        )
        .player("bob", battlefield=["Grizzly Bears"], library=["Forest"] * 5)
    )


def _cast_tamiyo_and_resolve_chapter_one(scenario: Scenario) -> None:
    sources = scenario.untapped_sources("Island", "Island", username="alice")
    scenario.cast_and_resolve("Tamiyo Meets the Story Circle", *sources)
    scenario.game.put_triggers_on_stack()
    _resolve_the_stack(scenario)


def test_tamiyo_chapter_one_creates_the_watch():
    scenario = _tamiyo_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    _cast_tamiyo_and_resolve_chapter_one(scenario)

    (trigger,) = scenario.game.delayed_triggers.triggers
    assert trigger.event is TriggerEvent.ATTACKS
    assert trigger.controller == "alice"
    assert trigger.defending_controller_only is True
    assert trigger.expires_end_of_next_turn is True
    assert trigger.remaining is None, "a stated duration (CR 603.7b), not a one-shot"


def test_a_creature_attacking_tamiyos_controller_gets_the_pump():
    """A different magnitude off the same sentence - proof the parser reads
    the shape, not Jace's exact "-5/-0"."""
    scenario = _tamiyo_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _cast_tamiyo_and_resolve_chapter_one(scenario)

    _advance_until(
        scenario,
        lambda s: s.turn.active_player == "bob" and s.step is Step.DECLARE_ATTACKERS,
    )
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.attack_with(bears, defending="alice")
    _resolve_the_stack(scenario)

    characteristics = scenario.game.characteristics_of(bears)
    assert (characteristics.power, characteristics.toughness) == (2 - 2, 2)


def test_a_creature_attacking_someone_other_than_tamiyos_controller_does_not_get_the_pump():
    """The same discrimination Jace's own version needed, proven again off a
    Saga's chapter trigger instead of a loyalty ability."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Tamiyo Meets the Story Circle"],
            battlefield=["Island", "Island"],
            library=["Island"] * 5,
        )
        .player("bob", battlefield=["Grizzly Bears"], library=["Forest"] * 5)
        .player("carol", library=["Plains"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _cast_tamiyo_and_resolve_chapter_one(scenario)

    _advance_until(
        scenario,
        lambda s: s.turn.active_player == "bob" and s.step is Step.DECLARE_ATTACKERS,
    )
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.attack_with(bears, defending="carol")

    assert scenario.game.stack == [], "no ATTACKS-watching trigger should have matched"
    characteristics = scenario.game.characteristics_of(bears)
    assert (characteristics.power, characteristics.toughness) == (2, 2)
