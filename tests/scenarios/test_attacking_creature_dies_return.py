"""Ares, God of War (task C02-T7): "Ares attacks each combat if able."
"Whenever an attacking creature you control dies, return that card to its
owner's hand."

The first sentence is CR 201.5c's *shortened* legendary self-reference (the
printed line uses only "Ares", not the comma-suffixed "Ares, God of War")
onto CR 508.1d's own requirement, which `machines/combat.py`'s
`_attack_requirement_match` reads off every permanent's computed ability
lines (`test_attack_requirements.py`'s Juggernaut proof, whose own printed
line already spells out "This creature attacks..." and never exercises this
path). That reader now checks a line's subject against `""`, `"this
creature"`, `"this permanent"`, or every name `_self_reference_names` reads
off the creature - the same CR 201.5c short-name vocabulary
`_evasion_restriction_sentences` and friends already use - so "Ares" alone
matches `"Ares, God of War"`'s own short form, and
`test_ares_is_not_yet_forced_to_attack_by_the_engine` below now proves the
engine actually enforces the requirement rather than merely allowing a
declaration that happens to obey it.

The second sentence is `_RETURN_THAT_CARD_TO_OWNERS_HAND_RE`/`_parse_return_
that_card_to_owners_hand_clause`, already `handled`: "that card" is CR 400.7/
607.1 anaphora onto the `DIES` event's own subject (the same id, carried
across the battlefield-to-graveyard move; only `zone_change_stamp` is fresh).
Proven by actually driving a creature through combat to its death, with Ares
declared as an attacker by the ordinary scripted declaration (not relying on
the blocked enforcement above - CR 508.1d never requires the *engine* to
force the choice for this to be a legal, in-fact declaration).

Every rule cited here was looked up with `mise run rules:find` in the session
that wrote this file:

- **CR 508.1d** - an "attacks each combat if able" requirement; an
  attackers declaration that could obey it and doesn't is illegal.
- **CR 201.5/201.5c** - a card refers to itself by its own name, or (a
  legendary permanent) a shortened version of it.
- **CR 700.4/701.21a** - a creature "dies" when a state-based action puts it
  from the battlefield into a graveyard; **CR 603.6b** - a triggered ability
  triggers off that event.
- **CR 510.2/510.4** - combat damage is dealt simultaneously, then state-based
  actions (CR 704.5f) put lethally-damaged creatures into their graveyards.
- **CR 400.7** - an object that changes zones becomes a new object; the DIES
  event's own subject id is what "that card" reaches back to, still tracked
  after the move.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import DecisionKind, ScriptedAnswer
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _queue_declaration(
    scenario: Scenario, kind: DecisionKind, value: object, player: str | None = None
) -> None:
    scenario.game.decisions.add(ScriptedAnswer(kind=kind, value=value, player=player))


def test_declaring_ares_obeys_the_requirement():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Ares, God of War"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    ares = scenario.creature("Ares, God of War", "alice")

    scenario.attack_with(ares)

    assert scenario.attackers() == [ares]


def test_ares_is_forced_to_attack_by_the_engine():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Ares, God of War"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)

    with pytest.raises(ValueError, match=r"CR 508\.1d"):
        scenario.attack_with()


def test_an_attacking_creature_alice_controls_that_dies_returns_to_hand():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Ares, God of War", "Grizzly Bears"])
        .player("bob", battlefield=["Craw Wurm"])
        .build()
    )
    ares = scenario.creature("Ares, God of War", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    wurm = scenario.creature("Craw Wurm", "bob")

    _queue_declaration(scenario, DecisionKind.DECLARE_ATTACKERS, [(ares, "bob"), (bears, "bob")])
    scenario.start_at(Step.BEGINNING_OF_COMBAT)
    scenario.advance()  # declare attackers
    _queue_declaration(scenario, DecisionKind.DECLARE_BLOCKERS, [(wurm, bears)], "bob")

    assert scenario.advance() is Step.DECLARE_BLOCKERS
    assert scenario.advance() is Step.COMBAT_DAMAGE

    # Craw Wurm (6/4) kills Grizzly Bears (2/2) outright; Grizzly Bears'
    # own 2 damage doesn't kill Craw Wurm. `advance()` already ran the
    # combat damage step's own state-based-action check (CR 704.5f) on its
    # way here, so Grizzly Bears is already in the graveyard.
    assert bears.zone is Zone.GRAVEYARD
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()

    assert bears.zone is Zone.HAND
    assert bears.owner == "alice"
    assert wurm.zone is Zone.BATTLEFIELD
    assert ares.zone is Zone.BATTLEFIELD
