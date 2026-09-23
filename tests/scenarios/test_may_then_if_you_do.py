"""CR 118.12's general "you may `<clause>`. If you do, `<clause>`." merger:
Smuggler's Copter's own attack/block trigger, and Riddlesmith's identical
cast trigger.

Every CR number below was looked up with `mise run rules:find <n>` in the
session that wrote this file:

- **CR 118.12** - "Some spells, activated abilities, and triggered abilities
  read, '[Do something]. If [a player] [does, doesn't, or can't], [effect].'
  Or '[A player] may [do something]. If [that player] [does, doesn't, or
  can't], [effect].' The action [do something] is a cost, paid when the spell
  or ability resolves. The 'If [a player] [does, doesn't, or can't]' clause
  checks whether the player chose to pay an optional cost or started to pay a
  mandatory cost, regardless of what events actually occurred." Read
  literally here: accepting the draw runs the discard even though nothing
  about the discard depends on what the draw actually produced, and declining
  runs neither.
- **CR 508.1** - the active player declares attackers.
- **CR 509.1** - the defending player declares blockers.
- **CR 701.9a/701.9b** - discarding is the controller's own choice of which
  card, not the ability's - `_merge_may_then_if_you_do_clauses`'s own
  consequence is a plain `parse_clause_effect("discard a card")`, the same
  `CHOOSE_CARDS` question every other discard in this engine already asks.

Before this wave, `Smuggler's Copter`'s own "you may draw a card. If you do,
discard a card." had no multi-clause merger at all: no per-verb "if you do"
reader in `machines/effects.py` read a bare draw as the optional action, so
the whole ability was silent (`scripts/sweep_pool.py --effects`). Riddlesmith
prints the identical shape on a "whenever you cast an artifact spell" trigger
rather than an attack/block one, which is what isolates the merger itself
(`machines/effects._merge_may_then_if_you_do_clauses`) from the condition/
self-reference fix `tests/scenarios/test_this_kind_self_reference_triggers.py`
covers separately.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.keywords import crew_activation
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def crew(scenario: Scenario, vehicle, *creatures, username: str = "alice"):
    """Activate a Vehicle's crew ability, pay it, and let it resolve (CR
    702.122a) - the same three-call sequence `tests/scenarios/test_crew.py`
    already uses."""
    activation = crew_activation(scenario.game, vehicle, list(creatures), username)
    activation.begin_paying()
    activation.payment.pay()
    activation.activate()
    activation.resolve()
    return activation


def resolve_all(scenario: Scenario) -> None:
    while scenario.game.stack:
        scenario.resolve_top()


# --------------------------------------------------------------------------
# Smuggler's Copter: "Whenever this Vehicle attacks or blocks, you may draw
# a card. If you do, discard a card."
# --------------------------------------------------------------------------


def test_smugglers_copter_attack_accepted_draws_then_the_controller_chooses_the_discard():
    """Accepting the draw always runs the discard - and the discard is the
    controller's own choice of card (CR 701.9a), not fixed to whichever card
    was just drawn: alice's hand already holds a Mountain when she accepts,
    and scripts discarding *that* one, proving the `CHOOSE_CARDS` question is
    a genuine choice over her whole hand rather than a hardcoded "discard the
    card you just drew"."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Mountain"],
            library=["Forest"],
            battlefield=["Smuggler's Copter", "Grizzly Bears"],
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    copter = scenario.find("Smuggler's Copter", Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    crew(scenario, copter, bears)
    mountain = scenario.find("Mountain", Zone.HAND, "alice")
    scenario.will_take_the_may(True, source="Smuggler's Copter")
    scenario.will_choose_cards(mountain, source="Smuggler's Copter")

    scenario.attack_with(copter)
    resolve_all(scenario)

    alice = scenario.player("alice")
    assert alice.library == []
    assert [state.name for state in alice.hand] == ["Forest"]
    assert [state.name for state in alice.graveyard] == ["Mountain"]


def test_smugglers_copter_attack_declined_draws_and_discards_nothing():
    """CR 118.12: declining the optional draw means neither half happens."""
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Forest"],
            battlefield=["Smuggler's Copter", "Grizzly Bears"],
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    copter = scenario.find("Smuggler's Copter", Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    crew(scenario, copter, bears)
    scenario.will_take_the_may(False, source="Smuggler's Copter")

    scenario.attack_with(copter)
    resolve_all(scenario)

    alice = scenario.player("alice")
    assert [state.name for state in alice.library] == ["Forest"]
    assert alice.hand == []
    assert alice.graveyard == []


def test_smugglers_copter_block_accepted_draws_then_discards_too():
    """CR 509.1's own half of the compound condition: a Copter that blocks
    and never attacks still asks the same "you may draw a card. If you do,
    discard a card." question."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Grizzly Bears"])
        .player(
            "bob",
            library=["Forest"],
            battlefield=["Smuggler's Copter", "Grizzly Bears"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    attacker = scenario.creature("Grizzly Bears", "alice")
    copter = scenario.find("Smuggler's Copter", Zone.BATTLEFIELD, "bob")
    bears = scenario.creature("Grizzly Bears", "bob")
    crew(scenario, copter, bears, username="bob")
    scenario.will_take_the_may(True, source="Smuggler's Copter")

    scenario.attack_with(attacker)
    resolve_all(scenario)  # nothing to resolve from the bare attack itself

    scenario.start_at(Step.DECLARE_BLOCKERS)
    scenario.block(attacker, copter)
    resolve_all(scenario)

    bob = scenario.player("bob")
    assert bob.library == []
    assert bob.hand == []  # drew the Forest, then discarded it (only card in hand)
    assert [state.name for state in bob.graveyard] == ["Forest"]


# --------------------------------------------------------------------------
# Riddlesmith: "Whenever you cast an artifact spell, you may draw a card.
# If you do, discard a card." - the same merger, off a cast trigger rather
# than an attack/block one, so the condition/self-reference half of G5 is
# never exercised by this file at all.
# --------------------------------------------------------------------------


def _riddlesmith_board() -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=["Smuggler's Copter"],
            library=["Forest"],
            battlefield=["Riddlesmith", "Mountain", "Mountain"],
        )
        .player("bob")
    )


def test_riddlesmith_triggers_on_an_artifact_spell_cast_accepted():
    scenario = _riddlesmith_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Mountain", "Mountain")
    scenario.will_take_the_may(True, source="Riddlesmith")

    scenario.cast_onto_stack("Smuggler's Copter", *sources)
    resolve_all(scenario)

    alice = scenario.player("alice")
    assert alice.library == []
    assert alice.hand == []  # drew the Forest, then discarded it
    assert [state.name for state in alice.graveyard] == ["Forest"]
    assert any(state.name == "Smuggler's Copter" for state in scenario.game.battlefield)


def test_riddlesmith_triggers_on_an_artifact_spell_cast_declined():
    scenario = _riddlesmith_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Mountain", "Mountain")
    scenario.will_take_the_may(False, source="Riddlesmith")

    scenario.cast_onto_stack("Smuggler's Copter", *sources)
    resolve_all(scenario)

    alice = scenario.player("alice")
    assert [state.name for state in alice.library] == ["Forest"]
    assert alice.hand == []
    assert alice.graveyard == []


def test_riddlesmith_does_not_trigger_on_a_nonartifact_spell_cast():
    """ "you cast an artifact spell" (CR 205.2a) - a creature spell with no
    artifact type does not match, and Riddlesmith stays off the stack
    entirely: nothing else is pending once Grizzly Bears is cast."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Grizzly Bears"],
            battlefield=["Riddlesmith", "Forest", "Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Forest", "Forest")

    scenario.cast_onto_stack("Grizzly Bears", *sources)

    assert scenario.stack_names() == ["Grizzly Bears"]
    assert scenario.pending_triggers == []
