"""Two new trigger conditions this round: an active-voice "you put a counter
on a creature[ you control]" (CR 122.6) and "one or more of your opponents
are attacked" (CR 506.4/603.2c).

**Mikey & Leo, Chaos & Order** - "Whenever you put a counter on a creature
you control, draw a card. This ability triggers only once each turn." -
active voice, singular ("a counter", not "one or more"), restricted to the
controller's own board. `machines/triggers._COUNTERS_PUT_CONDITION` already
read the *passive* "one or more ... counters are put on ..." shape; this is
its active-voice sibling. The once-per-turn limiter is not new machinery at
all - `Game.once_per_turn_triggers` was already built for Caretaker's Talent
- so this file's job is only to prove the *condition* now fires.

**Ant-Man, Colony Commander** (Marvel Super Heroes, verified Modern/Pioneer/
Standard legal, not a listed tmt card, not in any `decks/*.txt`) - "Whenever
you put a +1/+1 counter on a creature, create a 1/1 green Insect creature
token. This ability triggers only once each turn." - the identical shape
with two differences that prove the reader generalises rather than being
fitted to Mikey & Leo's own sentence: a named counter kind ("a +1/+1
counter", not the kind-agnostic "a counter"), and *no* "you control" at all -
any creature's counter counts, the caster's opponents' included.

**Party Dude** - "Whenever one or more of your opponents are attacked, up to
one target attacking creature gets +X/+X until end of turn, where X is the
number of cards in your hand." "Attacked" (no "s") never matched the
engine's own `\\battacks?\\b` trigger-event word boundary, so this fired never.
The corner case worth proving isn't the happy path - it's that the ability
triggers **once per declared attack, not once per attacker** (CR 603.2c),
even though "one or more" sounds like it might count them.

CR numbers verified this session with `mise run rules:find`:

- **CR 122.6** - counters being put on an object covers both an activated/
  triggered ability putting them on and an object entering with them.
- **CR 603.2h** - "This ability triggers only once each turn" is CR 603.2h's
  own once-per-turn restriction, tracked per source and per printed text.
- **CR 508.1a** - the active player declares every attacker "all at once",
  which is why the whole declaration is one event, not one per attacker.
- **CR 506.4** - a planeswalker or a battle can itself "be attacked".
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter

from .harness import Scenario

# -- Mikey & Leo, Chaos & Order ----------------------------------------------


def test_putting_a_counter_on_your_own_creature_draws_a_card():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Plains"],
            battlefield=["Mikey & Leo, Chaos & Order", "Grizzly Bears"],
            library=["Forest", "Island"],
        )
        .player("bob")
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    hand_before = len(scenario.player("alice").hand)

    scenario.game.add_counters(bears, Counter.PLUS_ONE)
    scenario.pass_until_resolved()

    assert len(scenario.player("alice").hand) == hand_before + 1


def test_the_ability_triggers_only_once_each_turn():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Mikey & Leo, Chaos & Order", "Grizzly Bears", "Hill Giant"],
            library=["Forest", "Island", "Swamp"],
        )
        .player("bob")
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "alice")
    hand_before = len(scenario.player("alice").hand)

    scenario.game.add_counters(bears, Counter.PLUS_ONE)
    scenario.pass_until_resolved()
    assert len(scenario.player("alice").hand) == hand_before + 1

    scenario.game.add_counters(giant, Counter.PLUS_ONE)
    scenario.game.check_state_based_actions()
    assert scenario.game.pending_triggers == [], "already triggered once this turn"
    assert len(scenario.player("alice").hand) == hand_before + 1


def test_the_limiter_resets_next_turn():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Mikey & Leo, Chaos & Order", "Grizzly Bears"],
            library=["Forest", "Island", "Swamp", "Mountain"],
        )
        .player("bob", library=["Plains"])
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    hand_before = len(scenario.player("alice").hand)
    scenario.game.add_counters(bears, Counter.PLUS_ONE)
    scenario.pass_until_resolved()
    assert len(scenario.player("alice").hand) == hand_before + 1

    scenario.turn.advance_to(Step.CLEANUP)
    scenario.turn_based_actions()
    scenario.advance()  # bob's turn
    scenario.turn.advance_to(Step.CLEANUP)
    scenario.turn_based_actions()
    scenario.advance()  # back to alice
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.game.add_counters(bears, Counter.PLUS_ONE)
    scenario.pass_until_resolved()
    assert len(scenario.player("alice").hand) == hand_before + 2


def test_a_counter_on_an_opponents_creature_does_not_trigger_it():
    """ "a creature you control" - Mikey & Leo does not read like Ant-Man's
    own bare "a creature" below."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Mikey & Leo, Chaos & Order"], library=["Forest"])
        .player("bob", battlefield=["Grizzly Bears"])
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    hand_before = len(scenario.player("alice").hand)

    scenario.game.add_counters(bears, Counter.PLUS_ONE)
    scenario.game.check_state_based_actions()

    assert scenario.game.pending_triggers == []
    assert len(scenario.player("alice").hand) == hand_before


# -- Ant-Man, Colony Commander: a second printing, wider subject -------------


def test_ant_mans_own_counter_trigger_fires_off_an_opponents_creature_too():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Ant-Man, Colony Commander"])
        .player("bob", battlefield=["Grizzly Bears"])
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")

    # CR 122.6a: alice is the one putting it, on bob's creature.
    scenario.game.add_counters(bears, Counter.PLUS_ONE, putter="alice")
    scenario.pass_until_resolved()

    insects = [state for state in scenario.game.battlefield if "Insect" in state.subtypes]
    assert len(insects) == 1
    assert scenario.game.controller_of(insects[0]).username == "alice"


def test_ant_mans_kind_specific_counter_is_not_fooled_by_a_different_kind():
    """Ant-Man names "a +1/+1 counter" specifically - a different counter
    kind on a creature must not trigger it."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Ant-Man, Colony Commander", "Grizzly Bears"])
        .player("bob")
    ).build()
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.game.add_counters(bears, "stun")
    scenario.game.check_state_based_actions()

    assert scenario.game.pending_triggers == []
    insects = [state for state in scenario.game.battlefield if "Insect" in state.subtypes]
    assert insects == []


# -- Party Dude ---------------------------------------------------------------


def _party_dude_board():
    return (
        Scenario()
        .player(
            "alice",
            hand=["Plains", "Island"],
            battlefield=["Party Dude", "Grizzly Bears", "Hill Giant"],
        )
        .player("bob")
    )


def test_attacking_pumps_a_chosen_attacker_by_the_callers_hand_size():
    scenario = _party_dude_board().build()
    party_dude = scenario.find("Party Dude", Zone.BATTLEFIELD, "alice")
    party_dude.class_level = 3
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "alice")

    scenario.start_at(Step.DECLARE_ATTACKERS)
    # `Game.declare_attackers` puts the trigger on the stack (and chooses its
    # target) synchronously - before `attack_with` even returns - so the
    # target has to be queued as an ordinary `CHOOSE_TARGETS` answer
    # (`will_choose_targets`), not pre-registered through
    # `choose_trigger_targets`, whose own legality check would run before
    # Grizzly Bears is actually attacking.
    scenario.will_choose_targets(bears, source="Party Dude")
    scenario.attack_with(bears, giant)
    scenario.pass_until_resolved()

    assert scenario.game.power_of(bears) == 2 + 2  # base 2/2 plus X=2 cards in hand
    assert scenario.game.power_of(giant) == 3  # untouched


def test_the_trigger_fires_once_for_the_whole_declaration_not_once_per_attacker():
    scenario = _party_dude_board().build()
    party_dude = scenario.find("Party Dude", Zone.BATTLEFIELD, "alice")
    party_dude.class_level = 3
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "alice")

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.will_choose_targets(bears, source="Party Dude")
    scenario.attack_with(bears, giant)

    triggered = [ability for ability in scenario.game.stack if ability.source_name == "Party Dude"]
    assert len(triggered) == 1, "one declaration, one trigger, however many creatures attacked"

    scenario.pass_until_resolved()
    assert scenario.game.power_of(bears) == 4, "pumped once, not once per attacker"
    assert scenario.game.power_of(giant) == 3


def test_below_level_3_the_ability_does_not_exist_yet():
    """CR 716.2a: "As long as this Class is level N or greater, it has
    [Abilities]" - at level 1, Party Dude has none of its level 3 text."""
    scenario = _party_dude_board().build()
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "alice")

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(bears, giant)

    assert scenario.game.pending_triggers == []
    assert scenario.game.power_of(bears) == 2
