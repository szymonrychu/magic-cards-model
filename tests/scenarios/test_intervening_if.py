"""CR 603.4: the intervening *if* fails closed when it cannot be read.

Every CR number below was looked up with `knowledge_search(type="rules")` in the
session that wrote this file.

- **CR 603.4** - "A triggered ability may read 'When/Whenever/At [trigger
  event], if [condition], [effect].' When the trigger event occurs, the
  ability checks whether the stated condition is true. The ability trigg[ers
  only if it's true]."
- **CR 608.2a** - "If a triggered ability has an intervening 'if' clause, it
  checks whether the clause's condition is true. If it isn't, the ability is
  removed from the stack and does nothing." - the same clause, checked again
  on resolution.

`machines/triggers.intervening_if_holds` used to read anything it did not
recognise as *true* - fail-open - which is how an unkicked Sowing Mycospawn
exiled a land (see `test_cast_triggers.py`). The default is now the opposite:
a clause it cannot read is treated as *false*, and the refusal is recorded on
`Game.intervening_if_notices` (`InterveningIfNotice`) so the gap is visible
rather than indistinguishable from a legal "the condition was false".

Of the pool's seven cards with an intervening *if*:

- **evaluated for real**: Ocelot Pride ("you gained life this turn", tracked by
  `Game.life_gained_this_turn`), Thopter Assembly ("you control no Thopters
  other than this creature", already read before this fix), Sowing Mycospawn
  ("it was kicked", CR 702.33d, read off `Game.cast_record(spell).kicked`),
  Vexing Bauble and Wistfulness's two abilities ("[no] mana [of a color] was
  spent to cast it", CR 601.2h, read off
  `Game.cast_record(spell).mana_spent` - see `test_mana_spent_intervening_if.py`
  for these last two), and, as of W14, Alania, Divergent Storm ("it's the
  first instant spell, the first sorcery spell, or the first Otter spell
  other than Alania you've cast this turn" - `_first_spell_this_turn_holds`
  reads this shape once `machines/abilities._INTERVENING_IF_CAST_THIS_TURN_
  BOUNDARY` hands it the *whole* clause instead of truncating at the clause's
  own first internal comma; see `tests/scenarios/test_alania_divergent_storm.py`
  for the fixed trigger actually firing), and Ruby, Daring Tracker
  ("Whenever Ruby attacks **while** you control a creature with power 4 or
  greater, Ruby gets +2/+2 until end of turn." - CR 603.4's clause spelled
  with "while" in place of "if", and folded into the trigger condition
  itself rather than sitting after a comma. `_CONDITION_WHILE_CLAUSE` in
  `machines/abilities.py` splits it off the same way the "if" shape already
  is, so it reaches the same `intervening_if_holds`; `_control_creature_
  with_power_holds` in `machines/triggers.py` is the new clause shape
  itself, CR 208.1's power compared against every creature the controller
  has right now).
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

# -- evaluated for real -------------------------------------------------------


def test_a_true_intervening_if_still_lets_the_ability_trigger():
    """Control: Ocelot Pride's clause is read, and when it genuinely holds the
    ability still triggers - the fail-closed default above is only for
    clauses this module cannot read, not a blanket refusal.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Ocelot Pride"])
        .player("bob")
        .manual_turn_based_actions()
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.gain_life("alice", 1)

    scenario.start_at(Step.POSTCOMBAT_MAIN)
    scenario.advance()  # the end step begins

    assert scenario.stack_names() == ["Ocelot Pride's triggered ability"]
    assert scenario.game.intervening_if_notices == []


def test_life_gained_through_player_gain_life_still_makes_the_condition_true():
    """The exact reported regression: CR 603.4's "if you gained life this
    turn" was implemented against `Game.life_gained_this_turn`, populated only
    in `Game.gain_life` - but Guide of Souls's ETB trigger ("you gain 1 life
    and get {E}") is a parsed player-effect clause that calls
    `Player.gain_life` directly (`machines/effects.py`), never routing through
    `Game.gain_life`. Two Guide of Souls take alice from 20 to 22, and Ocelot
    Pride's end step trigger must still see that a gain happened and go on the
    stack - CR 119.9 does not care which code path caused the gain, only that
    a source did.

    `Player.gain_life` is now the one place a life total goes up (`Game.gain_life`
    calls it too, after replacements), so every path - the parsed effect
    included - records CR 119.9's "this turn" fact the same way.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Grizzly Bears"],
            battlefield=["Guide of Souls", "Guide of Souls", "Ocelot Pride", "Forest", "Forest"],
        )
        .player("bob")
        .manual_turn_based_actions()
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Forest", "Forest")

    assert scenario.player("alice").life == 20
    scenario.cast_and_resolve("Grizzly Bears", *sources)
    assert scenario.stack_names() == [
        "Guide of Souls's triggered ability",
        "Guide of Souls's triggered ability",
    ]

    scenario.pass_until_resolved()
    assert scenario.player("alice").life == 21
    scenario.pass_until_resolved()
    assert scenario.player("alice").life == 22
    assert scenario.game.life_gained_this_turn == {"alice"}

    scenario.start_at(Step.POSTCOMBAT_MAIN)
    scenario.advance()  # the end step begins

    assert scenario.stack_names() == ["Ocelot Pride's triggered ability"]
    assert scenario.game.intervening_if_notices == []


def test_no_life_gained_this_turn_the_trigger_does_not_fire():
    """The negative: no life gained means Ocelot Pride's condition is false,
    CR 608.2a removes the ability instead of putting it on the stack, and
    nothing is silently mis-recorded as an engine gap.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Ocelot Pride"])
        .player("bob")
        .manual_turn_based_actions()
        .build()
    )
    scenario.start_at(Step.POSTCOMBAT_MAIN)
    scenario.advance()  # the end step begins

    assert scenario.stack_names() == []
    assert scenario.game.intervening_if_notices == []


def test_life_gained_last_turn_does_not_carry_into_this_turn():
    """CR 119.9's "this turn" is per turn: a gain on alice's first turn must
    not make the condition true on her second end step.

    `Game.advance()` clears `life_gained_this_turn` whenever `turns_taken`
    changes (see the comment by that reset in `models/game.py`), so this
    walks real turns with `advance()` - not `start_at`, which only moves the
    step pointer within one turn - resolving Ocelot Pride's first-turn
    trigger along the way so the stack is clear to keep advancing.
    """
    scenario = (
        Scenario()
        .player("alice", library=["Forest"], battlefield=["Ocelot Pride"])
        .player("bob", library=["Forest"])
        .manual_turn_based_actions()
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.gain_life("alice", 1)
    scenario.start_at(Step.POSTCOMBAT_MAIN)
    scenario.advance()  # alice's first end step
    assert scenario.stack_names() == ["Ocelot Pride's triggered ability"]
    scenario.pass_until_resolved()
    assert scenario.stack_names() == []

    for _ in range(40):
        if scenario.game.turn.active_player == "alice" and scenario.step is Step.POSTCOMBAT_MAIN:
            break
        scenario.advance()
        assert scenario.stack_names() == []  # nothing else on this bare board ever triggers
    else:
        raise AssertionError("never made it back to alice's postcombat main")

    scenario.advance()  # alice's second end step

    assert scenario.stack_names() == []
    assert scenario.game.intervening_if_notices == []


def test_lifelink_damage_also_makes_the_condition_true():
    """Ocelot Pride itself has lifelink (CR 702.15b): combat damage it deals
    routes through `Game.deal_damage_to_player` -> `Game.gain_life`, the path
    that already worked before this fix. Kept here as the check the task
    asked for - lifelink is not a third, separately broken path.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Ocelot Pride"])
        .player("bob", life=20)
        .manual_turn_based_actions()
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    ocelot = scenario.creature("Ocelot Pride", "alice")
    scenario.attack_with(ocelot)
    scenario.no_blocks()
    scenario.combat_damage()

    assert scenario.player("alice").life == 21  # 20 + 1 lifelink
    assert scenario.game.life_gained_this_turn == {"alice"}

    scenario.start_at(Step.POSTCOMBAT_MAIN)
    scenario.advance()  # the end step begins

    assert scenario.stack_names() == ["Ocelot Pride's triggered ability"]
    assert scenario.game.intervening_if_notices == []


# -- Ruby, Daring Tracker: "while", not "if" ----------------------------------


def test_ruby_gets_the_pump_while_controlling_a_big_creature():
    """Batterhorn is a 4/4 - CR 208.1's power meets the printed "4 or
    greater" - so Ruby's attack trigger both goes on the stack and, once it
    resolves, actually applies its own +2/+2 (CR 122.1a's own layer, checked
    through the computed board so a pumped Ruby genuinely reads 3/4)."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Ruby, Daring Tracker", "Batterhorn"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    ruby = scenario.creature("Ruby, Daring Tracker")

    scenario.attack_with(ruby)
    assert scenario.stack_names() == ["Ruby, Daring Tracker's triggered ability"]
    assert scenario.game.intervening_if_notices == []

    while scenario.game.stack:
        scenario.resolve_top()

    characteristics = scenario.game.characteristics_of(ruby)
    assert (characteristics.power, characteristics.toughness) == (3, 4)


def test_ruby_never_triggers_without_a_big_creature():
    """Grizzly Bears is a 2/2 - CR 603.4's own condition check happens *as
    the trigger event occurs*, so a false "while" clause never puts the
    ability on the stack at all, the same way an ordinary false "if" clause
    would not (CR 603.4: "The ability triggers only if it's true")."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Ruby, Daring Tracker", "Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    ruby = scenario.creature("Ruby, Daring Tracker")

    scenario.attack_with(ruby)

    assert scenario.stack_names() == []
    assert scenario.game.intervening_if_notices == []


def test_ruby_rechecks_the_condition_on_resolution():
    """CR 608.2a rechecks the same clause a second time, as the ability
    resolves: exiling Batterhorn between the trigger and the resolution
    takes the board back under power 4, and the ability "is removed from
    the stack and does nothing" - Ruby never gets bigger."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Swords to Plowshares"],
            battlefield=["Ruby, Daring Tracker", "Batterhorn", "Plains"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    ruby = scenario.creature("Ruby, Daring Tracker")
    batterhorn = scenario.creature("Batterhorn")

    scenario.attack_with(ruby)
    assert scenario.stack_names() == ["Ruby, Daring Tracker's triggered ability"]

    scenario.start_at(Step.POSTCOMBAT_MAIN)
    (plains,) = scenario.untapped_sources("Plains")
    scenario.cast_and_resolve("Swords to Plowshares", plains, targets=[batterhorn])
    assert batterhorn.zone is Zone.EXILE

    scenario.resolve_top()  # Ruby's own attack trigger, rechecked and refused

    characteristics = scenario.game.characteristics_of(ruby)
    assert (characteristics.power, characteristics.toughness) == (1, 2)


# -- "you've cast N or more spells this turn", with no spell type ------------
#
# Loan Shark (verified off its Scryfall printing): "When this creature enters,
# if you've cast two or more spells this turn, draw a card." Arclight Phoenix's
# "three or more instant and sorcery spells" was the only shape read, with the
# type list mandatory, so an untyped count fell through to `_fail_closed` and
# never drew. Two, not three: a different count than the pool's Phoenix.


def loan_shark_board() -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Bolt", "Loan Shark"],
            battlefield=["Mountain", "Island", "Island", "Island", "Island"],
            library=["Grizzly Bears", "Grizzly Bears"],
        )
        .player("bob")
    )


def test_loan_shark_draws_when_it_is_the_second_spell_this_turn():
    """CR 603.4: the clause is true as it enters - Lightning Bolt and Loan
    Shark itself are two spells alice cast this turn."""
    scenario = loan_shark_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    scenario.cast_and_resolve(
        "Lightning Bolt",
        *scenario.untapped_sources("Mountain"),
        targets=[scenario.player("bob")],
    )

    scenario.cast_and_resolve(
        "Loan Shark", *scenario.untapped_sources("Island", "Island", "Island", "Island")
    )
    scenario.pass_until_resolved()

    assert [state.name for state in alice.hand] == ["Grizzly Bears"]
    assert scenario.game.intervening_if_notices == []


def test_loan_shark_alone_is_one_spell_and_draws_nothing():
    """The false case is read, not refused: one spell is fewer than two, so
    nothing triggers and no notice is recorded."""
    scenario = loan_shark_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")

    scenario.cast_and_resolve(
        "Loan Shark", *scenario.untapped_sources("Island", "Island", "Island", "Island")
    )
    scenario.pass_until_resolved()

    assert [state.name for state in alice.hand] == ["Lightning Bolt"]
    assert scenario.pending_triggers == []
    assert scenario.game.intervening_if_notices == []


# -- a counter count printed as "N or more" ----------------------------------
#
# CR 603.4's clause as a count of counters on the source. Ayara's Oathsworn
# prints the comparison first ("fewer than four"); most cards print it after
# the number ("five or more"), and that suffix was never read, so the clause
# fell through to `_fail_closed`.
#
# Lightning Coils (verified off its Scryfall printing): "At the beginning of
# your upkeep, if this artifact has five or more charge counters on it, remove
# all of them from it and create that many 3/1 red Elemental creature tokens
# with haste. ..." Five, not Earthbender Ascension's four. Its effect fails
# closed on "that many" (a different gap); what is under test here is only
# whether the ability triggers.


def lightning_coils_board(charge: int) -> Scenario:
    scenario = (
        Scenario()
        .player("alice", battlefield=["Lightning Coils"])
        .player("bob")
        .manual_turn_based_actions()
        .build()
    )
    coils = scenario.find("Lightning Coils", Zone.BATTLEFIELD, "alice")
    coils.add_counters("charge", charge)
    return scenario


def test_five_charge_counters_trigger_lightning_coils_at_upkeep():
    scenario = lightning_coils_board(5)

    scenario.advance()  # the untap step ends and alice's upkeep begins

    assert scenario.step is Step.UPKEEP
    assert scenario.stack_names() == ["Lightning Coils's triggered ability"]
    assert scenario.game.intervening_if_notices == []


def test_four_charge_counters_do_not_trigger_lightning_coils():
    """Four is fewer than five: the clause is read and is false, so the
    ability does not trigger and nothing is refused."""
    scenario = lightning_coils_board(4)

    scenario.advance()  # the untap step ends and alice's upkeep begins

    assert scenario.step is Step.UPKEEP
    assert scenario.stack_names() == []
    assert scenario.game.intervening_if_notices == []
