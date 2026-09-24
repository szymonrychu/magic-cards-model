"""Scenario: a spell whose only targeting text is on its cast/ETB trigger
refuses inline targets at cast time with the real reason.

CR 601.2c: the caster "announces their choice of an appropriate object or
player for each target **the spell requires**." A creature spell with no
targeting text of its own requires none - "target" printed only inside a
triggered ability is not the spell's own word. CR 115.1d: a triggered
ability's targets "are chosen as the ability is put on the stack; see rule
603.3d." CR 603.3/603.3d: a triggered ability is put on the stack "the next
time a player would receive priority" - for a cast trigger, that is after
casting finishes (CR 601.2i moves it there); for an enters-the-battlefield
trigger, only after the spell has resolved and the permanent is on the
battlefield (CR 603.6a/603.2). Both are a separate CR 601.2c-shaped
announcement from the spell's own, made later - never now, and never from
whatever was typed at the spell's own `choose_targets`.

Before this file: `Casting._check_targets` read the spell's own
`TargetingProfile` alone. A caster naming inline targets for Ulamog, the
Ceaseless Hunger's cast trigger, or Ravenous Chupacabra's ETB, was refused
with the generic "too many targets: N chosen where the spell takes at most
0" - true, but not the real reason, and it gave no hint that the right move
is to cast without targets and answer the trigger's own `CHOOSE_TARGETS`
decision once it is on the stack. `machines/casting.py`'s `_check_targets`
now asks `machines/targeting.py`'s `targeting_trigger_text` - which reads a
card's printed and keyword-expanded triggered abilities the same way
`Game.why_cannot_target_with_trigger` does, through this module's own
`profile_for_text` - whenever the spell's own profile takes no targets and
some were chosen anyway, and cites the real trigger and the real rule
instead.

Every CR number here was looked up with `mise run rules:find` in the session
that wrote it.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import DecisionKind, ScriptedAnswer
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

ULAMOG = "Ulamog, the Ceaseless Hunger"
ULAMOG_TRIGGER = "When you cast this spell, exile two target permanents."
CHUPACABRA = "Ravenous Chupacabra"
CHUPACABRA_TRIGGER = "When this creature enters, destroy target creature an opponent controls."
SOLITUDE = "Solitude"


def _ulamog_board():
    return (
        Scenario()
        .player("alice", hand=[ULAMOG], battlefield=["Wastes"] * 10)
        .player("bob", battlefield=["Grizzly Bears", "Mountain"])
    )


def _chupacabra_board():
    return (
        Scenario()
        .player("alice", hand=[CHUPACABRA], battlefield=["Swamp"] * 4)
        .player("bob", battlefield=["Elvish Mystic"])
    )


def _solitude_board():
    return (
        Scenario()
        .player("alice", hand=[SOLITUDE], battlefield=["Plains"] * 5)
        .player("bob", battlefield=["Grizzly Bears"])
    )


# -- Ulamog, the Ceaseless Hunger: a cast trigger -------------------------


def test_ulamog_with_inline_targets_is_refused_naming_its_cast_trigger():
    scenario = _ulamog_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    mountain = scenario.find("Mountain", Zone.BATTLEFIELD, "bob")

    with pytest.raises(ValueError) as excinfo:
        scenario.cast(ULAMOG, targets=[bears, mountain])

    message = str(excinfo.value)
    assert f"{ULAMOG} as a spell takes no targets (CR 601.2c)" in message
    assert ULAMOG_TRIGGER in message
    assert "CR 603.3d, 115.1d" in message
    assert "cast without targets" in message

    ulamog = scenario.find(ULAMOG, Zone.HAND, "alice")
    assert ulamog.zone is Zone.HAND, "a refused cast leaves the card where it was (CR 601.6)"


def test_ulamog_cast_without_targets_asks_for_its_cast_trigger_and_exiles_the_answer():
    scenario = _ulamog_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    mountain = scenario.find("Mountain", Zone.BATTLEFIELD, "bob")
    scenario.game.decisions.add(
        ScriptedAnswer(kind=DecisionKind.CHOOSE_TARGETS, value=(bears, mountain), player="alice")
    )

    sources = scenario.untapped_sources(*["Wastes"] * 10)
    ulamog = scenario.cast_onto_stack(ULAMOG, *sources)

    asked = [
        decision
        for decision in scenario.game.decisions.asked
        if decision.kind is DecisionKind.CHOOSE_TARGETS
    ]
    assert len(asked) == 1
    assert asked[0].player == "alice"

    scenario.pass_until_resolved()  # the cast trigger: exile the two chosen permanents
    assert bears.zone is Zone.EXILE
    assert mountain.zone is Zone.EXILE

    scenario.pass_until_resolved()  # Ulamog itself
    assert ulamog.zone is Zone.BATTLEFIELD


# -- Ravenous Chupacabra: an enters-the-battlefield trigger ---------------


def test_chupacabra_with_an_inline_target_is_refused_naming_its_etb_trigger():
    scenario = _chupacabra_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mystic = scenario.creature("Elvish Mystic", "bob")

    with pytest.raises(ValueError) as excinfo:
        scenario.cast(CHUPACABRA, targets=[mystic])

    message = str(excinfo.value)
    assert f"{CHUPACABRA} as a spell takes no targets (CR 601.2c)" in message
    assert CHUPACABRA_TRIGGER in message
    assert "CR 603.3d, 115.1d" in message

    chupacabra = scenario.find(CHUPACABRA, Zone.HAND, "alice")
    assert chupacabra.zone is Zone.HAND


def test_chupacabra_cast_without_targets_resolves_then_asks_and_destroys():
    scenario = _chupacabra_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mystic = scenario.creature("Elvish Mystic", "bob")
    scenario.game.decisions.add(
        ScriptedAnswer(kind=DecisionKind.CHOOSE_TARGETS, value=(mystic,), player="alice")
    )

    scenario.cast_and_resolve(CHUPACABRA, *scenario.untapped_sources(*["Swamp"] * 4))
    scenario.pass_until_resolved()  # the ETB trigger

    assert mystic.zone is Zone.GRAVEYARD


# -- generality: Solitude, an ETB not in the reported pair -----------------


def test_solitude_with_an_inline_target_is_refused_naming_its_etb_trigger():
    """Proves the fix reads *any* card's own ETB text, not Chupacabra's
    specifically: Solitude's trigger is differently worded ("up to one
    other target creature", an optional count, with a life-gain rider) and
    Solitude is not part of the reported pair above."""
    scenario = _solitude_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")

    with pytest.raises(ValueError) as excinfo:
        scenario.cast(SOLITUDE, targets=[bears])

    message = str(excinfo.value)
    assert f"{SOLITUDE} as a spell takes no targets (CR 601.2c)" in message
    assert "target" in message
    assert "creature" in message
    assert "CR 603.3d, 115.1d" in message

    solitude = scenario.find(SOLITUDE, Zone.HAND, "alice")
    assert solitude.zone is Zone.HAND


# -- controls: both existing refusals stay exactly as they were -----------


def test_a_genuinely_targeted_spell_given_too_many_targets_keeps_the_plain_message():
    """Lightning Bolt itself requires a target (CR 115.1a) - the spell's own
    profile has `max_targets == 1`, not 0, so this control never reaches the
    new branch at all."""
    scenario = (
        Scenario()
        .player("alice", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .player("bob", battlefield=["Grizzly Bears", "Elvish Mystic"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    mystic = scenario.creature("Elvish Mystic", "bob")

    with pytest.raises(ValueError, match="too many targets") as excinfo:
        scenario.cast("Lightning Bolt", targets=[bears, mystic])
    assert "takes no targets" not in str(excinfo.value)


def test_a_card_with_no_targeting_trigger_keeps_the_plain_message():
    """Memnite prints no text at all - no spell-level target, and no
    triggered ability of any kind to blame the refusal on - so the plain
    "too many targets" message is exactly what CR 601.2c still means here."""
    scenario = (
        Scenario()
        .player("alice", hand=["Memnite"], battlefield=[])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")

    with pytest.raises(ValueError, match="too many targets") as excinfo:
        scenario.cast("Memnite", targets=[bears])
    assert "takes no targets" not in str(excinfo.value)
