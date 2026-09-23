"""A resolving instant or sorcery whose printed text no parser reads leaves a
notice behind rather than going to the graveyard with no trace.

Stock Up did exactly that in a live game: `effect_for` returned nothing, and
`Game.resolve` dropped the `None`, so the spell resolved, did nothing and said
nothing. A triggered or activated ability in the same position already records
an `UnmodeledTriggerEffectNotice`; a spell now records the same notice, on the
same `Game.unmodeled_trigger_effect_notices` list, with the spell's own id,
name and whole printed text (none of it ran).

The vehicle is chosen, not named. Ponder was the first, until the
look-top-and-put-back wave gave it a reader; Strix Serenade the second, until
S14's counterspell riders read it; Flame Sweep would have been the third, and
the owner rule (every Modern, Pioneer and Standard card fully supported) means
any in-format card is only waiting its turn. So `_unread_spell` picks, from
the real printings in the pool, an instant or sorcery that exists in none of
those three formats (`support.in_target_formats`) and that `card_support`
reports silent with `effect_for` reading nothing - an ante card or
Shahrazad's subgame, rules this engine is not asked to play. It fails with a
clear message only if the pool has no such card left.

Not every `None` is a gap, and the notice must not fire for these:

- a permanent spell, which becomes a permanent as it resolves (CR 608.3a);
  its abilities are judged on their own when they trigger;
- a spell whose resolution leaves a replacement effect (Plagiarize, CR
  614.1a) - `effect_for` reads it, and resolving it creates the effect.

Every CR number above was read in full with `mise run rules:find` in the
session that wrote this file.
"""

import re

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.effects import UnmodeledTriggerEffectNotice, effect_for
from magic_cards_model.models import Card, Zone
from magic_cards_model.support import card_support, in_target_formats
from tests.cards import pool
from tests.scenarios.harness import Scenario

_BASIC_FOR = {"W": "Plains", "U": "Island", "B": "Swamp", "R": "Mountain", "G": "Forest"}


def _lands_paying(mana_cost: str) -> list[str] | None:
    """Basic lands that pay `mana_cost` exactly - generic mana out of the
    first coloured symbol's basic - or `None` for any symbol a basic can't
    simply pay (X, hybrid, Phyrexian, colourless, snow)."""
    symbols = re.findall(r"\{([^}]+)\}", mana_cost)
    coloured = [symbol for symbol in symbols if symbol in _BASIC_FOR]
    if not coloured:
        return None
    lands: list[str] = []
    for symbol in symbols:
        if symbol in _BASIC_FOR:
            lands.append(_BASIC_FOR[symbol])
        elif symbol.isdigit():
            lands.extend([_BASIC_FOR[coloured[0]]] * int(symbol))
        else:
            return None
    return lands


def _unread_spell() -> tuple[Card, list[str]]:
    """The first (by name) out-of-format, untargeted, single-faced instant or
    sorcery in the pool that no parser reads, with the lands that pay for it."""
    seen: set[str] = set()
    for _, printing in sorted(pool().items()):
        if printing.name in seen:
            continue
        seen.add(printing.name)
        if in_target_formats(printing) or printing.card_faces or printing.keywords:
            continue
        if not {"Instant", "Sorcery"} & set(printing.type_line.split()):
            continue
        text = printing.oracle_text or ""
        if not text.strip() or "target" in text.lower():
            continue
        lands = _lands_paying(printing.mana_cost or "")
        if lands is None:
            continue
        if effect_for(printing.name, text) is not None:
            continue
        if card_support(printing).status != "silent":
            continue
        return printing, lands
    pytest.fail(
        "no out-of-format, untargeted instant or sorcery in the pool is still unread: "
        "add a real printing of one (an ante card, a subgame) with scripts/add_card.py"
    )


def test_an_unread_spell_records_a_notice_naming_its_whole_text():
    printing, lands = _unread_spell()
    scenario = (
        Scenario().player("alice", hand=[printing.name], battlefield=lands).player("bob").build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    spell = scenario.cast_and_resolve(printing.name, *scenario.untapped_sources(*lands))

    assert spell.zone is Zone.GRAVEYARD
    assert [player.life for player in scenario.game.players] == [20, 20]
    assert scenario.game.unmodeled_trigger_effect_notices == [
        UnmodeledTriggerEffectNotice(
            source_id=spell.id,
            source_name=printing.name,
            text=spell.oracle_text,
        )
    ]


def test_a_spell_that_leaves_a_replacement_effect_records_no_notice():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Plagiarize"],
            library=["Forest", "Island"],
            battlefield=["Island"] * 4,
        )
        .player("bob", library=["Swamp", "Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.cast_and_resolve(
        "Plagiarize", *scenario.untapped_sources(*["Island"] * 4), targets=["bob"]
    )

    assert scenario.game.created_replacements, "the replacement is what Plagiarize does"
    assert scenario.game.unmodeled_trigger_effect_notices == []


def test_a_spell_a_parser_reads_records_no_notice():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Stock Up"],
            library=["Forest", "Island", "Swamp", "Mountain", "Plains"],
            battlefield=["Island"] * 3,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.cast_and_resolve("Stock Up", *scenario.untapped_sources(*["Island"] * 3))

    assert scenario.game.unmodeled_trigger_effect_notices == []


def test_a_permanent_spell_records_no_notice_as_it_enters():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Codecracker Hound"],
            library=["Lightning Bolt", "Forest"],
            battlefield=["Island"] * 3,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    hound = scenario.cast_and_resolve(
        "Codecracker Hound", *scenario.untapped_sources(*["Island"] * 3)
    )
    scenario.pass_until_resolved()

    assert hound.zone is Zone.BATTLEFIELD
    assert scenario.game.unmodeled_trigger_effect_notices == []
