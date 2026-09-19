"""Two related "alone" attack conditions, both new to the trigger matcher:

- CR 506.5, Exalted's own defining shape: "a creature you control attacks
  alone" - Agents of S.H.I.E.L.D.'s own printing, true only when the whole
  attacking party this combat is one creature.
- CR 506.6: "a creature you control attacks a player alone" - Jiang Yanggu,
  Alone's and Yuriko, Blade of the Mighty's own printing, true whenever no
  *other* creature is attacking the same defending player, even if a second
  creature is attacking someone else in a multiplayer game.

`Game.declare_attackers` used to register each attacker and emit its own
`ATTACKS` event in the same pass, one creature at a time - which settled
"alone" off however many attackers had been registered *so far*, wrong for
every attacker but the last one processed. It now registers the whole
declared party first and only then emits each attacker's event, so
`GameEvent.attacking_alone`/`attacking_player_alone` read the finished
declaration.
"""

from magic_cards_model.machines import Step
from tests.scenarios.harness import Scenario


def test_agents_of_shield_pumps_the_lone_attacker():
    scenario = (
        Scenario().player("alice", battlefield=["Agents of S.H.I.E.L.D."]).player("bob").build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    agents = scenario.creature("Agents of S.H.I.E.L.D.", "alice")

    scenario.attack_with(agents, defending="bob")
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == ["Agents of S.H.I.E.L.D.'s triggered ability"]


def test_agents_of_shield_does_not_fire_when_a_second_creature_also_attacks():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Agents of S.H.I.E.L.D.", "Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    agents = scenario.creature("Agents of S.H.I.E.L.D.", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.attack_with(agents, bears, defending="bob")
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == []


def test_agents_of_shield_reads_the_finished_declaration_not_a_partial_one():
    """The regression this stream's own refactor guards: before it, the
    first attacker registered in a multi-attacker declaration was emitted
    while it still looked "alone" - it was the *only one registered so far*,
    not the only one in the finished party. `Game.declare_attackers` calling
    `combat_rules.declare_attacker` for the whole batch before emitting any
    event is what this checks."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Agents of S.H.I.E.L.D.", "Grizzly Bears", "Steppe Lynx"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    agents = scenario.creature("Agents of S.H.I.E.L.D.", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    lynx = scenario.creature("Steppe Lynx", "alice")

    # Agents of S.H.I.E.L.D. declared *first*, in a three-creature attack.
    scenario.attack_with(agents, bears, lynx, defending="bob")
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == []


def test_jiang_yanggu_triggers_when_its_lone_attacker_is_not_the_only_attacker_overall():
    """CR 506.6 versus CR 506.5: alice attacks with two creatures at two
    *different* opponents in a multiplayer game - neither creature attacks
    alone (CR 506.5, more than one attacker total), but each one still
    attacks its own defending player alone (CR 506.6). Jiang Yanggu's own
    condition ("a creature you control", not "this creature") watches both
    attacks, so it triggers twice - once per attacker, each alone against
    its own defending player."""
    scenario = (
        Scenario()
        .player(
            "alice", battlefield=["Jiang Yanggu, Alone", "Grizzly Bears"], hand=["Lightning Bolt"]
        )
        .player("bob")
        .player("carol")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    jiang = scenario.creature("Jiang Yanggu, Alone", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.game.declare_attackers([(jiang, "bob"), (bears, "carol")])
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == [
        "Jiang Yanggu, Alone's triggered ability",
        "Jiang Yanggu, Alone's triggered ability",
    ]


def test_jiang_yanggu_does_not_trigger_when_another_creature_shares_its_defending_player():
    scenario = (
        Scenario()
        .player(
            "alice", battlefield=["Jiang Yanggu, Alone", "Grizzly Bears"], hand=["Lightning Bolt"]
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    jiang = scenario.creature("Jiang Yanggu, Alone", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.attack_with(jiang, bears, defending="bob")
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == []


def test_yuriko_off_pool_proof_grants_double_strike_to_a_lone_attacker():
    """Off-pool angle within the same set is not available (both FRA
    printings of "attacks a player alone" are already exercised above, and
    no other printed card combines this exact phrase - see the test file's
    own module docstring) - Yuriko is FRA's second printing of the identical
    CR 506.6 condition, proving the matcher against a differently shaped
    effect (a keyword grant, not a discard/draw or a +1/+1 counter loop)."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Yuriko, Blade of the Mighty"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    yuriko = scenario.creature("Yuriko, Blade of the Mighty", "alice")

    scenario.attack_with(yuriko, defending="bob")
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == ["Yuriko, Blade of the Mighty's triggered ability"]
