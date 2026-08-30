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
  and Vexing Bauble and Wistfulness's two abilities ("[no] mana [of a color]
  was spent to cast it", CR 601.2h, read off
  `Game.cast_record(spell).mana_spent` - see `test_mana_spent_intervening_if.py`
  for these last two).
- **fail closed, audibly**: Alania, Divergent Storm ("it's the first instant
  spell, the first sorcery spell, or the first Otter spell other than Alania
  you've cast this turn" - `_first_spell_this_turn_holds` reads this shape,
  but `machines/abilities._parse_triggered` splits the intervening *if* on its
  *own* internal commas and never hands it the whole clause; see the
  pre-existing `xfail`,
  `tests/test_abilities.py::test_an_intervening_if_with_internal_commas_splits_correctly`).
"""

from magic_cards_model.machines import Step
from tests.scenarios.harness import Scenario

# -- fails closed, audibly ---------------------------------------------------


def test_alania_fails_closed_because_the_clause_is_not_split_correctly():
    """Alania, Divergent Storm's clause is a genuinely readable shape -
    `machines/triggers._first_spell_this_turn_holds` reads "it's the first
    [type] spell ... you've cast this turn" - but a separate, pre-existing
    parser gap (`test_an_intervening_if_with_internal_commas_splits_correctly`
    in `tests/test_abilities.py`) truncates the clause at its own first comma
    before it ever reaches here, so what arrives is just "it's the first
    instant spell" with no "you've cast this turn" to anchor it. Unreadable,
    so it fails closed - the same safe outcome as the truly-untrackable
    clauses above, for a different underlying reason.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Forest"],
            hand=["Lightning Bolt"],
            battlefield=["Alania, Divergent Storm"] + ["Mountain"] * 4,
        )
        .player("bob", library=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (mountain,) = scenario.untapped_sources("Mountain")
    alania = scenario.creature("Alania, Divergent Storm", "alice")

    scenario.cast_onto_stack("Lightning Bolt", mountain, targets=[scenario.player("bob")])

    assert scenario.stack_names() == ["Lightning Bolt"]
    assert scenario.pending_triggers == []
    assert len(scenario.game.intervening_if_notices) == 1
    assert scenario.game.intervening_if_notices[0].source_id == alania.id


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
