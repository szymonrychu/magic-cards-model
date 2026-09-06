"""The combat steps' turn-based actions: who is asked, and what happens when
they run on their own (CR 703.4i, 703.4j, 703.4k).

The manual declaration path - a scenario calling `attack_with` and `block` by
hand - is the other three combat files. This one is the mechanic the task is
about: the steps driving themselves.

Every rule cited here was looked up with `knowledge_search(type="rules")` in
the session that wrote the file. The spine of it:

- **CR 703.4i** - "Immediately after the declare attackers step begins, the
  active player declares attackers. See rule 508.1." CR 508.1: "First, the
  active player declares attackers. This turn-based action doesn't use the
  stack." CR 508.1a: "The active player chooses which creatures that they
  control, if any, will attack."
- **CR 703.4j** - "Immediately after the declare blockers step begins, the
  defending player declares blockers. See rule 509.1." CR 509.1: "First, the
  defending player declares blockers. This turn-based action doesn't use the
  stack." CR 802.4, for the multiplayer shape: "each defending player in APNAP
  order declares blockers as the declare blockers step begins".
- **CR 703.4k** - "Immediately after the combat damage step begins, each player
  in APNAP order announces how each attacking or blocking creature they control
  assigns its combat damage. See rule 510.1."
- **CR 508.2b / 509.2a** - the abilities that triggered on the declarations are
  put onto the stack before the active player gets priority, and CR 508.2 is
  then "Second, the active player gets priority."
- **CR 508.8** - "If no creatures are declared as attackers or put onto the
  battlefield attacking, skip the declare blockers and combat damage steps."
  CR 500.11: "To skip a step, phase, or turn is to proceed past it as though it
  didn't exist." CR 614.10a: "Anything scheduled for a skipped step, phase, or
  turn won't happen." The declare attackers step itself never skips - the rule
  names only the two steps after it.
- **CR 506.4** - a creature removed from combat stops being an attacking
  creature; that is not the same as never having been declared, which is what
  CR 508.8 keys off.

The declarations are questions the rules ask, not choices made while a spell
resolves, so they are scripted through `DecisionScript` the way the mulligan
declaration is (`tests/scenarios/test_mulligans.py`): a real answer a player
could give, matched to the question when the engine puts it.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.abilities import TriggerEvent
from magic_cards_model.machines.decisions import (
    Answer,
    Decision,
    DecisionKind,
    DecisionPending,
    DeclaredPair,
    ScriptedAnswer,
)
from magic_cards_model.machines.delayed import DelayedTrigger
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def attacking_board() -> Scenario:
    """Alice with two ground creatures, bob with one."""
    return (
        Scenario()
        .player("alice", battlefield=["Grizzly Bears", "Hill Giant"])
        .player("bob", battlefield=["Watchwolf"])
    )


def queue_declaration(
    scenario, kind: DecisionKind, value: object, player: str | None = None
) -> None:
    """Script one combat declaration, as the harness scripts a mulligan.

    `tests/scenarios/harness.py` has helpers for the choices made while a spell
    resolves, but a declaration is asked by the step's turn-based action, and
    this file is where the question is staged - straight onto the game's
    decision script, exactly as `test_mulligans.py` stages a mulligan.
    """
    scenario.game.decisions.add(ScriptedAnswer(kind=kind, value=value, player=player))


def watcher(scenario, event: TriggerEvent, text: str, controller: str = "alice"):
    """Stage a delayed trigger watching `event`, as a resolving spell would."""
    return scenario.game.create_delayed_trigger(
        DelayedTrigger(
            text=text,
            effect="unmodelled",
            event=event,
            controller=controller,
            source_name="a resolving spell",
        )
    )


# -- the declare attackers step asks (CR 703.4i, 508.1) ----------------------


def test_the_declare_attackers_step_asks_who_attacks():
    """The question goes to the active player as the step begins (CR 703.4i).

    A scripted declaration is performed by the turn-based action: the creature
    becomes an attacking creature (CR 508.1k), attacking causes it to tap (CR
    508.1f), and the abilities that triggered on attackers being declared go on
    the stack before the active player gets priority (CR 508.2b).
    """
    scenario = attacking_board().build()
    bears = scenario.creature("Grizzly Bears")
    watcher(scenario, TriggerEvent.ATTACKS, "Whenever this creature attacks, note it.")
    queue_declaration(scenario, DecisionKind.DECLARE_ATTACKERS, [(bears, "bob")])

    scenario.start_at(Step.BEGINNING_OF_COMBAT)
    step = scenario.advance()

    assert step is Step.DECLARE_ATTACKERS
    asked = scenario.questions_asked()
    assert [(d.kind, d.player) for d in asked] == [(DecisionKind.DECLARE_ATTACKERS, "alice")]
    assert scenario.game.is_attacking(bears)
    assert bears.tapped, "CR 508.1f: attacking simply causes creatures to become tapped"
    assert scenario.stack_names() == ["a resolving spell's triggered ability"]


def test_the_declaration_names_who_each_creature_attacks():
    """CR 508.1b: the active player announces which player each one is attacking."""
    scenario = attacking_board().build()
    bears = scenario.creature("Grizzly Bears")
    giant = scenario.creature("Hill Giant")
    queue_declaration(scenario, DecisionKind.DECLARE_ATTACKERS, [(bears, "bob"), (giant, "bob")])

    scenario.start_at(Step.BEGINNING_OF_COMBAT)
    scenario.advance()

    attacks = scenario.game.combat.attacks
    assert [attack.attacker_id for attack in attacks] == [bears.id, giant.id]
    assert all(attack.defender == scenario.game.attack_target("bob") for attack in attacks)


def test_an_illegal_scripted_declaration_is_refused():
    """A tapped creature cannot be declared (CR 508.1a), however it is declared.

    The declaration the rules ask for is still a declaration: CR 508.1's
    "If at any point during the declaration ... a player ... makes an illegal
    choice" makes the whole thing illegal, and `declare_attackers` refuses it.
    The scenario stops at that boundary rather than past it - an engine with no
    player agent raises instead of picking something.
    """
    scenario = attacking_board().build()
    bears = scenario.creature("Grizzly Bears")
    queue_declaration(scenario, DecisionKind.DECLARE_ATTACKERS, [(bears, "bob")])

    scenario.start_at(Step.BEGINNING_OF_COMBAT)
    bears.tap()
    with pytest.raises(ValueError, match="tapped"):
        scenario.advance()

    assert not scenario.game.is_attacking(bears)
    assert scenario.game.combat.attacks == []


# -- an empty declaration skips the rest of combat (CR 508.8) -----------------


def test_an_unanswered_declaration_attacks_nobody_and_skips_the_rest_of_combat():
    """CR 508.1a's "if any" makes an empty declaration legal - and CR 508.8
    then skips the declare blockers and combat damage steps.

    "To skip a step ... is to proceed past it as though it didn't exist" (CR
    500.11), so one advance from the declare attackers step lands in the end of
    combat step: no declare blockers question was ever put, no combat damage
    was dealt.
    """
    scenario = attacking_board().build()
    scenario.start_at(Step.BEGINNING_OF_COMBAT)
    scenario.advance()

    assert scenario.attackers() == []
    step = scenario.advance()

    assert step is Step.END_OF_COMBAT
    assert scenario.player("bob").life == 20
    kinds = [d.kind for d in scenario.questions_asked()]
    assert DecisionKind.DECLARE_BLOCKERS not in kinds, "the skipped step asks nothing"


def test_a_declared_attacker_keeps_the_combat_steps():
    """CR 508.8 only skips when nobody was declared - one attacker is enough."""
    scenario = attacking_board().build()
    bears = scenario.creature("Grizzly Bears")
    queue_declaration(scenario, DecisionKind.DECLARE_ATTACKERS, [(bears, "bob")])

    scenario.start_at(Step.BEGINNING_OF_COMBAT)
    scenario.advance()
    step = scenario.advance()

    assert step is Step.DECLARE_BLOCKERS
    assert scenario.game.is_attacking(bears)


def test_an_attacker_removed_from_combat_does_not_unskip_the_rest():
    """CR 506.4 takes the creature out of combat; CR 508.8 still reads the
    declaration that put it there.

    "declared as attackers" happened - the declaration was made, and a
    declaration is not undone by the attacker later leaving. So the steps
    follow even though nobody is attacking any more.
    """
    scenario = attacking_board().build()
    bears = scenario.creature("Grizzly Bears")
    queue_declaration(scenario, DecisionKind.DECLARE_ATTACKERS, [(bears, "bob")])

    scenario.start_at(Step.BEGINNING_OF_COMBAT)
    scenario.advance()
    scenario.game.combat.remove(bears.id)  # CR 506.4
    assert scenario.attackers() == []

    step = scenario.advance()

    assert step is Step.DECLARE_BLOCKERS


def test_a_manual_path_game_does_not_skip_its_steps():
    """The skip belongs to the automatic path only.

    A scenario driving combat by hand declares its attackers in whatever way it
    likes, and its declare blockers step has to be there when it steps into it.
    This is the contract that keeps the other three combat files working.
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.BEGINNING_OF_COMBAT)
    scenario.advance()

    step = scenario.advance()

    assert step is Step.DECLARE_BLOCKERS


# -- the declare blockers step asks (CR 703.4j, 509.1) ------------------------


def test_the_declare_blockers_step_asks_the_defending_player():
    """The question goes to the player being attacked, as the step begins.

    A scripted block is performed by the turn-based action, and CR 509.2a puts
    the abilities that triggered on blockers being declared onto the stack
    before the active player gets priority.
    """
    scenario = attacking_board().build()
    bears = scenario.creature("Grizzly Bears", "alice")
    wolf = scenario.creature("Watchwolf", "bob")
    watcher(scenario, TriggerEvent.BLOCKS, "Whenever this creature blocks, note it.")
    queue_declaration(scenario, DecisionKind.DECLARE_ATTACKERS, [(bears, "bob")])

    scenario.start_at(Step.BEGINNING_OF_COMBAT)
    scenario.advance()
    queue_declaration(scenario, DecisionKind.DECLARE_BLOCKERS, [(wolf, bears)], "bob")
    step = scenario.advance()

    assert step is Step.DECLARE_BLOCKERS
    asked = scenario.questions_asked()
    assert [(d.kind, d.player) for d in asked] == [
        (DecisionKind.DECLARE_ATTACKERS, "alice"),
        (DecisionKind.DECLARE_BLOCKERS, "bob"),
    ]
    assert scenario.game.is_blocking(wolf)
    assert scenario.stack_names() == ["a resolving spell's triggered ability"]


def test_each_defending_player_is_asked_in_apnap_order():
    """CR 802.4: with more than one player being attacked, each declares in
    APNAP order as the step begins.

    The active player is first in that order and cannot be a defender, so the
    defending players are visited in turn order after them.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Grizzly Bears", "Hill Giant"])
        .player("bob")
        .player("carol")
        .build()
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "alice")
    queue_declaration(scenario, DecisionKind.DECLARE_ATTACKERS, [(bears, "carol"), (giant, "bob")])

    scenario.start_at(Step.BEGINNING_OF_COMBAT)
    scenario.advance()
    queue_declaration(scenario, DecisionKind.DECLARE_BLOCKERS, [], "bob")
    queue_declaration(scenario, DecisionKind.DECLARE_BLOCKERS, [], "carol")
    step = scenario.advance()

    assert step is Step.DECLARE_BLOCKERS
    blockers_asked = [
        (d.kind, d.player)
        for d in scenario.questions_asked()
        if d.kind is DecisionKind.DECLARE_BLOCKERS
    ]
    assert blockers_asked == [
        (DecisionKind.DECLARE_BLOCKERS, "bob"),
        (DecisionKind.DECLARE_BLOCKERS, "carol"),
    ]


def test_a_block_is_only_legal_against_an_attacker_defending_that_player():
    """CR 509.1a: a creature blocks only attackers attacking it or something it
    protects, and CR 802.4a keeps the defenders' declarations to their own
    attackers.

    Carol names Bob's wolf as her blocker, and the whole declaration is illegal
    (CR 509.1's steps) - the scenario stops at the refusal rather than past it.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Grizzly Bears"])
        .player("bob", battlefield=["Watchwolf"])
        .player("carol")
        .build()
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    wolf = scenario.creature("Watchwolf", "bob")
    queue_declaration(scenario, DecisionKind.DECLARE_ATTACKERS, [(bears, "carol")])

    scenario.start_at(Step.BEGINNING_OF_COMBAT)
    scenario.advance()
    queue_declaration(scenario, DecisionKind.DECLARE_BLOCKERS, [(wolf, bears)], "carol")

    with pytest.raises(ValueError, match="not controlled by carol"):
        scenario.advance()


# -- combat damage runs on its own (CR 703.4k, 510) ---------------------------


def test_the_whole_combat_drives_through_advance_with_correct_life_totals():
    """One attacker blocked, one unblocked: the three combat steps run in order
    from `advance()` alone.

    The blocked Hill Giant trades with the Watchwolf (CR 510.2: "all combat
    damage that's been assigned is dealt simultaneously"), and the unblocked
    Grizzly Bears deal 2 to bob (CR 120.2a: "Each attacking and blocking
    creature deals combat damage equal to its power during the combat damage
    step"). The trade is cleaned up by state-based actions at the next check
    (CR 704.5f), which the advance into the end of combat step performs.
    """
    scenario = attacking_board().build()
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "alice")
    wolf = scenario.creature("Watchwolf", "bob")
    queue_declaration(scenario, DecisionKind.DECLARE_ATTACKERS, [(giant, "bob"), (bears, "bob")])

    scenario.start_at(Step.BEGINNING_OF_COMBAT)
    scenario.advance()
    queue_declaration(scenario, DecisionKind.DECLARE_BLOCKERS, [(wolf, giant)], "bob")

    assert scenario.advance() is Step.DECLARE_BLOCKERS
    assert scenario.advance() is Step.COMBAT_DAMAGE
    assert scenario.player("bob").life == 18
    assert scenario.player("alice").life == 20

    scenario.advance()
    assert scenario.find("Hill Giant", Zone.GRAVEYARD) is not None
    assert scenario.find("Watchwolf", Zone.GRAVEYARD, "bob") is not None
    assert scenario.find("Grizzly Bears", Zone.BATTLEFIELD) is not None


def test_the_unblocked_creature_deals_damage_in_the_automatic_combat_damage_step():
    """The combat damage step's turn-based action runs from the step alone.

    With nothing scripted at all - no blocks - the bears still hit bob for 2,
    which is CR 703.4k doing its work without a caller.
    """
    scenario = attacking_board().build()
    bears = scenario.creature("Grizzly Bears", "alice")
    queue_declaration(scenario, DecisionKind.DECLARE_ATTACKERS, [(bears, "bob")])

    scenario.start_at(Step.BEGINNING_OF_COMBAT)
    scenario.advance()
    scenario.advance()  # declare blockers: bob declares nobody
    assert scenario.advance() is Step.COMBAT_DAMAGE

    assert scenario.player("bob").life == 18


# -- a scripted declaration accepts a `Player` object, not only a username ---
#
# `Game.declare_attackers` is typed `Targetable | str` for the defender, where
# `Targetable = CardState | Player` - a `Player` object is exactly as legal a
# defender as a username string. `Game._resolve_declaration` used to resolve
# only `CardState | TargetRef | str`, so a scripted declaration naming a
# `Player` object fell through to the `find_by_id` fallback and raised,
# claiming no such permanent existed. `Scenario.attack_with` never caught it
# because it calls `Game.declare_attackers` directly, bypassing `_resolve_
# declaration` entirely - only the turn-based-action path here goes through it.


def test_a_scripted_attack_may_name_a_player_object_as_the_defender():
    """The exact regression: a `Player` object, not a username, staged as the
    defender through the turn-based action's own decision machinery."""
    scenario = attacking_board().build()
    bears = scenario.creature("Grizzly Bears", "alice")
    bob = scenario.player("bob")
    queue_declaration(scenario, DecisionKind.DECLARE_ATTACKERS, [(bears, bob)])

    scenario.start_at(Step.BEGINNING_OF_COMBAT)
    scenario.advance()

    assert scenario.game.is_attacking(bears)
    assert scenario.game.combat.attacks[0].defender.username == "bob"


# -- the tape answers a combat declaration (Answer.pairs, DeclaredPair) -----
#
# `Answer.pairs` used to be `tuple[tuple[UUID, UUID], ...]`, which cannot name
# a player at all - the overwhelmingly common defender for an attack.
# `DeclaredPair` widens it: `defender_card` for a card (a blocker's attacker,
# always - CR 509.1a), `defender_player` for a player, exactly one set.


def test_a_recorded_tape_declares_an_attack_on_a_player():
    """A `DeclaredPair` naming `defender_player` replays an ordinary attack on
    a player - the case a bare id pair could never express at all."""
    scenario = attacking_board().build()
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.game.decisions.recorded = [
        Answer(
            seq=0,
            kind=DecisionKind.DECLARE_ATTACKERS,
            player="alice",
            pairs=(DeclaredPair(creature=bears.id, defender_player="bob"),),
        )
    ]

    scenario.start_at(Step.BEGINNING_OF_COMBAT)
    scenario.advance()

    assert scenario.game.decisions.consumed == 1
    assert scenario.game.is_attacking(bears)
    assert scenario.game.combat.attacks[0].defender.username == "bob"


def test_a_recorded_tape_declares_a_block():
    """A `DeclaredPair` naming `defender_card` replays a block - the blocker
    by its own id, the attacker it blocks by `defender_card`."""
    scenario = attacking_board().build()
    bears = scenario.creature("Grizzly Bears", "alice")
    wolf = scenario.creature("Watchwolf", "bob")
    queue_declaration(scenario, DecisionKind.DECLARE_ATTACKERS, [(bears, "bob")])
    scenario.start_at(Step.BEGINNING_OF_COMBAT)
    scenario.advance()
    scenario.game.decisions.recorded = [
        Answer(
            seq=0,
            kind=DecisionKind.DECLARE_BLOCKERS,
            player="bob",
            pairs=(DeclaredPair(creature=wolf.id, defender_card=bears.id),),
        )
    ]

    scenario.advance()

    assert scenario.game.decisions.consumed == 1
    assert scenario.game.is_blocking(wolf)
    assert scenario.game.is_blocked(bears)


def test_pause_when_unanswered_raises_decision_pending_for_declare_attackers():
    """With nothing scripted, no tape, and no provider, `pause_when_unanswered`
    turns CR 703.4i's declaration into a raised `DecisionPending` - the same
    proof given for `ask_mulligan` and `ask_trigger_order`, here for `_ask_
    declaration`, which reaches this point through neither `Game.ask` nor a
    provider (see the next section).
    """
    scenario = attacking_board().build()
    scenario.game.decisions.pause_when_unanswered = True

    with pytest.raises(DecisionPending) as excinfo:
        scenario.start_at(Step.BEGINNING_OF_COMBAT)
        scenario.advance()

    pending = excinfo.value.pending
    assert pending.decision.kind is DecisionKind.DECLARE_ATTACKERS
    assert pending.decision.player == "alice"
    assert "703.4i" in pending.rule


# -- the live-deployment gate (finding 1): no provider for either declaration -
#
# `_ask_declaration` deliberately never consults `script.provider` - see its
# own docstring for why: the API's `MailboxProvider.decide` blocks the calling
# thread for the full timeout regardless of kind, and `DECLARE_ATTACKERS`/
# `DECLARE_BLOCKERS` are absent from the API's own `ANSWERABLE_KINDS`, so a
# live seat has no transport to answer either through the mailbox `script.
# provider` stands in for. Consulting it here would stall every live game's
# combat for the full timeout, twice per combat, for nothing a seat could
# ever answer. These two tests are the gate: a provider installed here is
# never asked, for either declaration.


class _AnyProviderWouldAnswer:
    """A decision provider that would happily answer any kind put to it.

    Not a mock of the engine: like `DecisionScript`, it stands in for a real
    seat and performs no engine behaviour itself - it only records what it was
    asked, so a test can prove it was never asked anything at all.
    """

    def __init__(self) -> None:
        self.seen: list[Decision] = []

    def decide(self, decision: Decision) -> object:
        self.seen.append(decision)
        return ()


def test_a_provider_is_never_consulted_for_declare_attackers():
    scenario = attacking_board().build()
    provider = _AnyProviderWouldAnswer()
    scenario.game.decisions.provider = provider

    scenario.start_at(Step.BEGINNING_OF_COMBAT)
    scenario.advance()

    assert provider.seen == [], "DECLARE_ATTACKERS must never reach script.provider"
    # Nothing scripted, no tape, no provider consulted: `default_answer`'s
    # "declare nobody" is what actually happened (CR 508.1's "if any").
    assert scenario.game.combat.attacks == []


def test_a_provider_is_never_consulted_for_declare_blockers():
    scenario = attacking_board().build()
    bears = scenario.creature("Grizzly Bears", "alice")
    queue_declaration(scenario, DecisionKind.DECLARE_ATTACKERS, [(bears, "bob")])
    provider = _AnyProviderWouldAnswer()
    scenario.game.decisions.provider = provider

    scenario.start_at(Step.BEGINNING_OF_COMBAT)
    scenario.advance()
    scenario.advance()  # declare blockers

    assert provider.seen == [], "DECLARE_BLOCKERS must never reach script.provider"
    assert list(scenario.game.combat.attacks[0].blockers) == []
