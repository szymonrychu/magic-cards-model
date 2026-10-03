"""The support classifier reads a clause's own gate before crediting its
effect: an intervening "if" the engine cannot read (CR 603.4) and an
activation instruction it cannot check (CR 602.1b) each leave the clause
failing closed at runtime, so neither may score `handled`.

Every printing is chosen from the pool by what the engine's own probes say
about it (`triggers.intervening_if_readable`,
`Game.unread_activation_restrictions`), never by name, and each probe is
proven on at least two printings.
"""

from magic_cards_model.machines.abilities import (
    ActivatedAbility,
    TriggeredAbility,
    parse_abilities,
)
from magic_cards_model.machines.effects import activated_effect_for, trigger_effect_for
from magic_cards_model.machines.triggers import intervening_if_readable
from magic_cards_model.models import CardState, Game, Player, Zone
from magic_cards_model.support import card_support, classify_clauses
from tests.cards import pool


def _printings():
    return [pool()[name] for name in sorted({c.name for c in pool().values()})]


def _unread_ifs():
    """(printing, ability) for every pool trigger whose intervening "if" no
    reader claims."""
    return [
        (printing, ability)
        for printing in _printings()
        for ability in parse_abilities(printing)
        if isinstance(ability, TriggeredAbility)
        and (ability.intervening_if or "").strip()
        and not intervening_if_readable(printing, ability)
    ]


def _throwaway_source(printing) -> tuple[Game, CardState]:
    game = Game(
        players=[Player(username="you"), Player(username="opponent")],
        schema_version=Game.CURRENT_SCHEMA_VERSION,
    )
    source = CardState(card=printing, zone=Zone.BATTLEFIELD, controller="you", owner="you")
    source.bind_to_game(game)
    game.battlefield.append(source)
    return game, source


def _unread_restrictions():
    """(printing, ability, unread) for every pool activated ability carrying
    an activation instruction the engine does not check."""
    found = []
    for printing in _printings():
        for ability in parse_abilities(printing):
            if not isinstance(ability, ActivatedAbility) or not ability.instructions:
                continue
            if ability.mana is not None and ability.loyalty is None:
                continue
            game, source = _throwaway_source(printing)
            unread = game.unread_activation_restrictions(ability, source)
            if unread:
                found.append((printing, ability, unread))
    return found


def _clause_for(printing, text):
    return [c for c in card_support(printing).clauses if c.text == text]


def _effect_is_readable(printing, ability) -> bool:
    if isinstance(ability, TriggeredAbility):
        return trigger_effect_for(printing.name, ability.event, ability.effect) is not None
    return activated_effect_for(printing.name, 0, ability.effect) is not None


# --- (a) intervening "if" -------------------------------------------------


def test_the_pool_carries_at_least_two_unread_intervening_ifs_on_readable_effects():
    readable = [(p, a) for p, a in _unread_ifs() if _effect_is_readable(p, a)]
    assert len({p.name for p, _ in readable}) >= 2, readable


def test_an_unread_intervening_if_is_never_handled():
    """CR 603.4: the ability triggers only if the condition is true - one the
    engine cannot read records an InterveningIfNotice and never triggers, so
    the clause fails closed however well its effect reads."""
    cases = _unread_ifs()
    assert cases
    for printing, ability in cases:
        clauses = _clause_for(printing, ability.text)
        assert clauses, (printing.name, ability.text)
        for clause in clauses:
            assert clause.outcome != "handled", (printing.name, clause)
            assert clause.status != "handled"


def test_an_unread_intervening_if_on_a_readable_effect_is_a_notice_naming_the_clause():
    cases = [(p, a) for p, a in _unread_ifs() if _effect_is_readable(p, a)]
    checked = set()
    for printing, ability in cases:
        for clause in _clause_for(printing, ability.text):
            if clause.outcome in ("silent", "unmatchable_condition", "quoted_effect"):
                continue  # already worse - the worse verdict stands
            assert clause.outcome == "notice", (printing.name, clause)
            assert ability.intervening_if.strip() in clause.reason
            assert "CR 603.4" in clause.reason
            checked.add(printing.name)
    assert len(checked) >= 2, checked


def test_an_unread_intervening_if_never_raises_a_worse_verdict():
    """Take the worse: an unread "if" on an effect nothing reads leaves the
    clause silent - the notice never lifts it."""
    checked = set()
    for printing, ability in _unread_ifs():
        if _effect_is_readable(printing, ability):
            continue
        for outcome in classify_clauses(printing):
            if outcome.text == ability.text:
                assert outcome.category == "silent", (printing.name, outcome)
                checked.add(printing.name)
    assert checked


def test_a_readable_intervening_if_leaves_a_handled_clause_handled():
    """No false positive: a trigger whose intervening "if" a reader answers
    (Ocelot Pride's "you gained life this turn") keeps its own verdict."""
    printing = pool()["Ocelot Pride"]
    triggers = [
        a
        for a in parse_abilities(printing)
        if isinstance(a, TriggeredAbility) and (a.intervening_if or "").strip()
    ]
    assert triggers
    assert all(intervening_if_readable(printing, a) for a in triggers)
    for ability in triggers:
        for clause in _clause_for(printing, ability.text):
            assert clause.outcome == "handled", clause


# --- (b) activation restrictions -----------------------------------------


def test_the_pool_carries_at_least_two_unread_restrictions_on_readable_effects():
    readable = [(p, a) for p, a, _ in _unread_restrictions() if _effect_is_readable(p, a)]
    assert len({p.name for p, _ in readable}) >= 2, readable


def test_an_unread_activation_restriction_is_never_handled():
    """CR 602.1b: activation instructions function at all times - the runtime
    refuses an activation whose instruction it cannot check, so the clause
    fails closed however well its effect reads."""
    cases = _unread_restrictions()
    assert cases
    for printing, ability, _ in cases:
        clauses = _clause_for(printing, ability.text)
        assert clauses, (printing.name, ability.text)
        for clause in clauses:
            assert clause.outcome != "handled", (printing.name, clause)


def test_an_unread_restriction_on_a_readable_effect_is_a_notice_naming_each_restriction():
    checked = set()
    for printing, ability, unread in _unread_restrictions():
        if not _effect_is_readable(printing, ability):
            continue
        for clause in _clause_for(printing, ability.text):
            if clause.outcome in ("silent", "unmatchable_condition", "quoted_effect"):
                continue
            assert clause.outcome == "notice", (printing.name, clause)
            for restriction in unread:
                assert restriction in clause.reason
            assert "CR 602.1b" in clause.reason
            checked.add(printing.name)
    assert len(checked) >= 2, checked


def test_a_read_activation_instruction_leaves_the_clause_alone():
    """No false positive: an activated ability whose instructions the engine
    reads ("Activate only as a sorcery", "Activate only during your turn")
    is judged on its effect alone."""
    checked = set()
    for printing in _printings():
        for ability in parse_abilities(printing):
            if not isinstance(ability, ActivatedAbility) or not ability.instructions:
                continue
            if ability.mana is not None and ability.loyalty is None:
                continue
            game, source = _throwaway_source(printing)
            if game.unread_activation_restrictions(ability, source):
                continue
            for clause in _clause_for(printing, ability.text):
                assert "CR 602.1b" not in clause.reason, (printing.name, clause)
                checked.add(printing.name)
    assert len(checked) >= 2
