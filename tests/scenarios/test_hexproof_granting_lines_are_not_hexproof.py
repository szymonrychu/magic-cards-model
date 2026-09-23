"""A static line that *mentions* hexproof does not give its own object hexproof.

The regression (prod, engine b4316b8): an opponent's Devourer of Destiny was
cast with Kaito, Bane of Nightmares on the board and its cast trigger never
went on the stack. Kaito prints "During your turn, as long as Kaito has one or
more loyalty counters on him, he's a 3/4 Ninja creature and has hexproof." -
and `hexproof_abilities_in` counted any line with the word "hexproof" in it as
the keyword itself, so Kaito had hexproof on every turn, the only coloured
permanent on the board was untargetable, and CR 603.3d removed the trigger.
The same misread made Shadowspear ("... lose hexproof ...") and every
hexproof *granter* (Asceticism, Marwyn, Dragonfire Blade) hexproof itself.

Verified this session with `mise run rules:find`:

- CR 702.1: a keyword ability is one where "the object lists only the name of
  the ability as a 'keyword'" - so hexproof the object *has* is a keyword
  line, not a sentence.
- CR 604.1 / CR 113.3d: static abilities "are written as statements"; a
  statement granting hexproof creates a continuous effect, which is what
  gives hexproof - to whatever it names, and only while its condition holds.
- CR 702.11b: "'Hexproof' on a permanent means 'This permanent can't be the
  target of spells or abilities your opponents control.'"
- CR 603.3d: a triggered ability with no legal choice for a required target
  "is simply removed from the stack".
- CR 603.2: "Whenever a game event or game state matches a triggered
  ability's trigger event, that ability automatically triggers."
"""

import re

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.casting import hexproof_abilities_in
from magic_cards_model.models import Zone
from tests.cards import pool
from tests.scenarios.harness import Scenario

_REMINDER = re.compile(r"\([^)]*\)")


def _alice_casts(card: str, mana: list[str], bob_battlefield: list[str]) -> Scenario:
    scenario = (
        Scenario()
        .player("alice", library=["Forest"] * 3, hand=[card], battlefield=mana)
        .player("bob", library=["Forest"], battlefield=bob_battlefield)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


# -- the reported card ------------------------------------------------------


def test_devourer_of_destiny_exiles_kaito_on_its_casters_turn():
    """Kaito's hexproof is his controller's-turn clause; on alice's turn he is a
    plain coloured planeswalker, so Devourer's cast trigger goes on the stack
    and exiles him."""
    scenario = _alice_casts(
        "Devourer of Destiny",
        ["Sol Ring"] + ["Forest"] * 5,
        ["Kaito, Bane of Nightmares", "Island"],
    )
    kaito = scenario.find("Kaito, Bane of Nightmares", Zone.BATTLEFIELD, "bob")

    scenario.cast_onto_stack(
        "Devourer of Destiny", *scenario.untapped_sources("Sol Ring", *["Forest"] * 5)
    )
    assert scenario.stack_names() == [
        "Devourer of Destiny",
        "Devourer of Destiny's triggered ability",
    ]
    assert scenario.game.hexproof_refusal(kaito, "alice", None) is None

    scenario.pass_until_resolved()
    assert kaito.zone is Zone.EXILE


# -- the same template on other cards --------------------------------------


def test_ugin_eye_of_the_storms_exiles_kaito_too():
    """Same "permanent that's one or more colors" wording, a different card."""
    scenario = _alice_casts(
        "Ugin, Eye of the Storms", ["Wastes"] * 7, ["Kaito, Bane of Nightmares"]
    )
    kaito = scenario.find("Kaito, Bane of Nightmares", Zone.BATTLEFIELD, "bob")
    scenario.choose_trigger_targets("Ugin, Eye of the Storms", [kaito])

    scenario.cast_onto_stack("Ugin, Eye of the Storms", *scenario.untapped_sources(*["Wastes"] * 7))
    assert "Ugin, Eye of the Storms's triggered ability" in scenario.stack_names()

    scenario.pass_until_resolved()
    assert kaito.zone is Zone.EXILE


@pytest.mark.parametrize("granter", ["Dragonfire Blade", "Shadowspear"])
def test_world_breaker_exiles_an_artifact_whose_text_mentions_hexproof(granter):
    """Dragonfire Blade's "Equipped creature ... has hexproof from monocolored"
    is about the creature, and Shadowspear's "... lose hexproof ..." takes it
    away - neither Equipment is hexproof, so a green World Breaker hits it."""
    scenario = _alice_casts("World Breaker", ["Forest"] * 7, [granter])
    artifact = scenario.find(granter, Zone.BATTLEFIELD, "bob")
    scenario.choose_trigger_targets("World Breaker", [artifact])

    scenario.cast_onto_stack("World Breaker", *scenario.untapped_sources(*["Forest"] * 7))
    assert "World Breaker's triggered ability" in scenario.stack_names()

    scenario.pass_until_resolved()
    assert artifact.zone is Zone.EXILE


def test_ulamog_exiles_two_permanents_that_only_grant_hexproof_to_others():
    """Asceticism ("Creatures you control have hexproof.") grants it to other
    objects, not itself; Shadowspear only takes it away."""
    scenario = _alice_casts(
        "Ulamog, the Ceaseless Hunger",
        ["Wastes"] * 10,
        ["Asceticism", "Marwyn, the Preserver", "Shadowspear"],
    )
    asceticism = scenario.find("Asceticism", Zone.BATTLEFIELD, "bob")
    shadowspear = scenario.find("Shadowspear", Zone.BATTLEFIELD, "bob")
    marwyn = scenario.find("Marwyn, the Preserver", Zone.BATTLEFIELD, "bob")
    # Asceticism does give Marwyn - a creature - hexproof, so she is the one
    # object here that really has it.
    assert scenario.game.hexproof_refusal(marwyn, "alice", None) is not None
    assert scenario.game.hexproof_refusal(asceticism, "alice", None) is None

    scenario.game.choose_trigger_targets("Ulamog, the Ceaseless Hunger", [asceticism, shadowspear])
    scenario.cast_onto_stack(
        "Ulamog, the Ceaseless Hunger", *scenario.untapped_sources(*["Wastes"] * 10)
    )
    assert "Ulamog, the Ceaseless Hunger's triggered ability" in scenario.stack_names()

    scenario.pass_until_resolved()
    assert asceticism.zone is Zone.EXILE
    assert shadowspear.zone is Zone.EXILE


def test_granted_hexproof_still_counts():
    """The fix must not lose hexproof that a continuous effect really grants:
    Asceticism's creature, Gladecover Scout's own keyword line."""
    scenario = _alice_casts(
        "Devourer of Destiny",
        ["Sol Ring"] + ["Forest"] * 5,
        ["Asceticism", "Grizzly Bears", "Gladecover Scout"],
    )
    bears = scenario.creature("Grizzly Bears", "bob")
    scout = scenario.creature("Gladecover Scout", "bob")
    assert scenario.game.hexproof_refusal(bears, "alice", None) is not None
    assert scenario.game.hexproof_refusal(scout, "alice", None) is not None


# -- pool-wide guards -------------------------------------------------------


def _printed_lines(card) -> list[str]:
    texts = [card.oracle_text or ""] + [face.oracle_text or "" for face in card.card_faces or []]
    return [line for text in texts for line in text.splitlines()]


def _keyword_shaped(line: str) -> bool:
    """CR 702.1's shape: a list of keyword names, no sentence."""
    text = _REMINDER.sub("", line).strip()
    return bool(text) and not re.search(r"[.:]", text)


def test_only_keyword_lines_in_the_pool_carry_hexproof():
    """Every pool printing: the lines `hexproof_abilities_in` reads hexproof
    from are CR 702.1 keyword lines, never a statement that mentions it."""
    offenders = []
    for name, card in sorted(pool().items()):
        for line in _printed_lines(card):
            plain, qualities = hexproof_abilities_in([line])
            if (plain or qualities) and not _keyword_shaped(line):
                offenders.append(f"{name}: {line}")
    assert offenders == []


def _unconditional_cast_trigger_cards() -> list[str]:
    """Pool cards printing a "When you cast this spell" trigger that is not a
    keyword's reminder text and has no intervening "if" (CR 603.4)."""
    names = []
    for name, card in sorted(pool().items()):
        if "//" in name:
            continue
        for line in _printed_lines(card):
            text = _REMINDER.sub("", line)
            match = re.search(r"when you cast this spell,? (?P<rest>.*)", text, re.IGNORECASE)
            if match and not match.group("rest").lower().startswith("if "):
                names.append(name)
                break
    return names


_LANDS = ["Plains", "Island", "Swamp", "Mountain", "Forest", "Wastes"] * 3
_BOB = ["Kaito, Bane of Nightmares", "Dragonfire Blade", "Shadowspear", "Forest"]


@pytest.mark.parametrize("name", _unconditional_cast_trigger_cards())
def test_every_pool_cast_trigger_fires_when_cast(name):
    """Cast each such card on a board where the opponent's only coloured
    non-creature permanent is Kaito and the only artifacts are hexproof
    *granters*; its cast trigger must reach the stack (CR 603.2)."""
    scenario = (
        Scenario()
        .player("alice", library=["Forest"] * 5, hand=[name], battlefield=_LANDS)
        .player("bob", library=["Forest"] * 5, battlefield=_BOB)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.cast_onto_stack(name, auto=True)
    triggered = [item for item in scenario.stack_names() if item == f"{name}'s triggered ability"]
    assert triggered, f"{name}'s cast trigger never reached the stack: {scenario.stack_names()}"
