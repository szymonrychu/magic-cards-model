""" "Whenever [X] becomes tapped[, ...]" - CR 701.26a's tap action read as a
trigger event (`TriggerEvent.BECOMES_TAPPED`), widened this task beyond the
self-referential-only form `machines/triggers.py` used to read:

- Captain America, Living Legend's own "Whenever a creature you control
  becomes tapped during your turn, if it's the first time that creature has
  become tapped this turn, untap it." - a non-self subject, gated by "during
  your turn" and a per-turn "first time" intervening if
  (`Game.became_tapped_count_this_turn`).
- Hawkeye's Bow's own "Whenever equipped creature becomes tapped, it deals 1
  damage to each opponent." - CR 301.5a's "equipped creature" subject,
  resolved off `CardState.attached_to`.
- Agent Maria Hill's own "Whenever Agent Maria Hill becomes tapped to pay a
  teamwork cost, put a +1/+1 counter on her and draw a card." - the
  self-referential form, narrowed to *why* she was tapped
  (`GameEvent.tapped_for_teamwork`, set only by `machines/teamwork.py`'s own
  cost component).
- Magda, Brazen Outlaw's own "Whenever a Dwarf you control becomes tapped,
  create a Treasure token." - the off-pool proof that the widened "a
  `<subtype>` you control becomes tapped" subject generalises past this
  task's own cards (`triggers._required_becomes_tapped_subtype`). Legal in
  Modern and Pioneer; not in any `magic-cards-model-api` deck list.

Every CR number below was looked up with `mise run rules:find` in the
session that wrote this file.

- **CR 701.26a** - tapping a permanent, the event itself.
- **CR 508.1** - declaring attackers taps the attacker (CR 508.1a), which is
  where the engine's own `BECOMES_TAPPED` event comes from in every test
  below that uses combat rather than a cost.
- **CR 603.4** - an intervening *if* is checked both when the ability would
  trigger and again on resolution; a clause false at the first check never
  even goes on the stack.
- **CR 301.5a** - Equipment's "equipped creature".
- **CR 118.8a/CR 118.3** - an additional cost, paid alongside affordability.

A resolution-time "tap target `<X>`" effect (as opposed to a cost's own tap,
or combat's) does not yet raise `BECOMES_TAPPED` anywhere in this engine -
noted as a dated `MEMORY.md` line rather than silently fixed here, since
auditing every tap call site in `machines/effects.py` is a wider change than
this task's own three templates. Every test below uses a tap this engine
already does emit the event for: combat's attack-declaration tap, or a
cost's own `ComponentKind.TAP` payment.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario, mana_from

# --------------------------------------------------------------------------
# Captain America, Living Legend
# --------------------------------------------------------------------------


def test_captain_america_untaps_a_creature_the_first_time_it_taps_this_turn():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=["Captain America, Living Legend", "Hill Giant"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    giant = scenario.creature("Hill Giant", "alice")

    scenario.attack_with(giant, defending="bob")
    assert giant.tapped
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == ["Captain America, Living Legend's triggered ability"]
    scenario.resolve_top()

    assert not giant.tapped  # untapped, its first tap this turn


def test_captain_america_does_not_untap_a_second_tap_the_same_turn():
    """CR 603.4: the intervening if is checked again as the ability would
    trigger a second time - the count is now 2, so it never even goes on
    the stack."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Team Tactics"],
            battlefield=["Captain America, Living Legend", "Hill Giant", "Mountain", "Mountain"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    giant = scenario.creature("Hill Giant", "alice")

    scenario.attack_with(giant, defending="bob")
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()
    assert not giant.tapped  # first tap, untapped by Captain America

    # A second tap this same turn, still while holding priority in combat:
    # Hill Giant (now untapped again, still attacking) pays a Teamwork cost.
    casting = scenario.cast("Team Tactics")
    casting.pay_teamwork([giant])  # 3 power, Teamwork 1
    casting.choose_targets([giant])
    payment = casting.begin_paying()
    for source in scenario.untapped_sources("Mountain", "Mountain"):
        payment.tap_for_mana(source, mana_from(source))
    payment.pay()
    scenario.put_on_stack(casting)
    assert giant.tapped
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == ["Team Tactics"], (
        "the second tap this turn never triggers Captain America"
    )


def test_captain_america_does_not_untap_an_opponents_creature():
    """ "a creature you control" - CR 700.7 is not read here at all; this is
    an ordinary controller clause, checked the normal way."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        # bob first, so it is his turn by default and his own creature may
        # attack - CA's own "you control" is what this test is about.
        .player("bob", battlefield=["Hill Giant"])
        .player("alice", battlefield=["Captain America, Living Legend"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    giant = scenario.creature("Hill Giant", "bob")

    scenario.attack_with(giant, defending="alice")
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == []


# --------------------------------------------------------------------------
# Hawkeye's Bow: "Whenever equipped creature becomes tapped, it deals 1
# damage to each opponent."
# --------------------------------------------------------------------------


def test_hawkeyes_bow_deals_damage_when_the_equipped_creature_taps_attacking():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=["Hawkeye's Bow", "Hill Giant", "Mountain"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bow = scenario.find("Hawkeye's Bow", Zone.BATTLEFIELD, "alice")
    giant = scenario.creature("Hill Giant", "alice")
    bob_life_before = scenario.player("bob").life

    from magic_cards_model.machines.keywords import equip_activation

    activation = equip_activation(scenario.game, bow, giant, "alice")
    payment = activation.begin_paying()
    for source in scenario.untapped_sources("Mountain"):
        payment.tap_for_mana(source, mana_from(source))
    payment.pay()
    activation.activate()
    activation.resolve()
    assert bow.is_attached

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(giant, defending="bob")
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == ["Hawkeye's Bow's triggered ability"]
    scenario.resolve_top()

    assert scenario.player("bob").life == bob_life_before - 1


def test_hawkeyes_bow_does_not_fire_for_the_equipment_itself_tapping():
    """Hawkeye's Bow has no `{T}` ability of its own, so there is no tap of
    the Equipment itself to accidentally credit - this checks the condition
    reads `source.attached_to`, not `source.id`, by tapping a creature the
    Bow is *not* attached to and confirming nothing triggers."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Hawkeye's Bow", "Hill Giant"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    giant = scenario.creature("Hill Giant", "alice")
    bow = scenario.find("Hawkeye's Bow", Zone.BATTLEFIELD, "alice")
    assert not bow.is_attached

    scenario.attack_with(giant, defending="bob")
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == []


# --------------------------------------------------------------------------
# Agent Maria Hill: "Whenever Agent Maria Hill becomes tapped to pay a
# teamwork cost, put a +1/+1 counter on her and draw a card."
# --------------------------------------------------------------------------


def test_agent_maria_hill_triggers_when_tapped_to_pay_teamwork():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Team Tactics"],
            battlefield=["Agent Maria Hill", "Mountain", "Mountain"],
            library=["Forest"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    maria = scenario.creature("Agent Maria Hill", "alice")
    hand_before = len(scenario.player("alice").hand)

    casting = scenario.cast("Team Tactics")
    casting.pay_teamwork([maria])  # 1 power, Teamwork 1
    casting.choose_targets([maria])
    payment = casting.begin_paying()
    for source in scenario.untapped_sources("Mountain", "Mountain"):
        payment.tap_for_mana(source, mana_from(source))
    payment.pay()
    scenario.put_on_stack(casting)
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == [
        "Team Tactics",
        "Agent Maria Hill's triggered ability",
    ]
    scenario.resolve_top()  # Agent Maria Hill's own trigger resolves first (LIFO)

    assert maria.power == 3  # 2/1 base, +1/+1 counter
    # Team Tactics is still on the stack; its own draw did not happen yet -
    # only Agent Maria Hill's own "draw a card" from her trigger has.
    assert len(scenario.player("alice").hand) == hand_before - 1 + 1  # cast, then drew one


def test_agent_maria_hill_does_not_trigger_for_an_ordinary_tap():
    """Tapped by attacking, not to pay a teamwork cost - `GameEvent.
    tapped_for_teamwork` is false, so the narrower condition does not hold
    even though the plain self-referential "becomes tapped" would."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Agent Maria Hill"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    maria = scenario.creature("Agent Maria Hill", "alice")

    scenario.attack_with(maria, defending="bob")
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == []


# --------------------------------------------------------------------------
# Off-pool proof: Magda, Brazen Outlaw's "Whenever a Dwarf you control
# becomes tapped, create a Treasure token." - the widened non-self,
# subtype-qualified "a `<subtype>` you control becomes tapped" subject,
# proven on a real printing outside this task's own MSH cards.
# --------------------------------------------------------------------------


def test_magda_creates_a_treasure_when_a_dwarf_she_controls_taps():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Magda, Brazen Outlaw"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    magda = scenario.creature("Magda, Brazen Outlaw", "alice")

    scenario.attack_with(magda, defending="bob")
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == ["Magda, Brazen Outlaw's triggered ability"]
    scenario.resolve_top()

    treasures = [
        state
        for state in scenario.game.permanents_controlled_by("alice")
        if "Treasure" in state.subtypes
    ]
    assert len(treasures) == 1


def test_magda_does_not_trigger_for_a_non_dwarf_creature_tapping():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Magda, Brazen Outlaw", "Hill Giant"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    giant = scenario.creature("Hill Giant", "alice")

    scenario.attack_with(giant, defending="bob")
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == []
