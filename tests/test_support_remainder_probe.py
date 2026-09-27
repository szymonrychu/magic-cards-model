"""A dispatcher closure that drops or only notices part of its clause is not
`handled` (CR 608.2c: the controller follows every instruction of the text,
in order - an instruction the engine skips leaves the clause half-played).

Two probes, both read by `magic_cards_model.support`:

- **the marker**: every `machines/effects.py` closure built around a remainder
  it could not read carries `effect.unparsed_remainder = <text>`
  (`support.unparsed_remainder` finds it anywhere in the closure graph);
- **the ablation probe**: for a handled clause with more than one sentence,
  each trailing sentence of its resolution text (`support.probe_sentences`)
  is removed and the clause re-dispatched - the same closure back means the
  sentence was never read (`support.ignored_rider`).

Pride of Conquerors' city's-blessing "instead" and Summon: Knights of Round's
chapter V are the two reported examples; every other printing here is chosen
from the pool by what the probes say, never by name.
"""

import pytest

from magic_cards_model.machines.abilities import (
    ActivatedAbility,
    TriggeredAbility,
    parse_abilities,
)
from magic_cards_model.machines.effects import (
    activated_effect_for,
    activation_resolution_text,
    effect_for,
    spell_resolution_text,
    trigger_effect_for,
)
from magic_cards_model.machines.targeting import profile_for_text
from magic_cards_model.models.card import Type
from magic_cards_model.support import (
    _CLOSURE_WALK_LIMIT,
    _only_chooses_targets,
    _sentences,
    _without_span,
    card_support,
    ignored_rider,
    probe_sentences,
    same_closure,
    unparsed_remainder,
)
from tests.cards import card, pool

_REMAINDER = "unparsed remainder: "


def _is_spell(printing) -> bool:
    return bool(set(printing.types) & {Type.INSTANT, Type.SORCERY}) and not (
        set(printing.types) & {Type.ARTIFACT, Type.CREATURE, Type.ENCHANTMENT, Type.LAND}
    )


def _printings():
    return [pool()[name] for name in sorted({c.name for c in pool().values()})]


def _dispatches(printing):
    """(clause text, dispatch, effect, reads) for the spell text and every
    triggered/activated ability of `printing`, dispatched the way
    `support.classify_clauses` dispatches them (no X); `reads` is the text
    the dispatcher resolves, as `classify_clauses` hands it to the probe."""
    found = []
    if _is_spell(printing) and printing.oracle_text:
        text = printing.oracle_text
        found.append(
            (
                text,
                lambda t, n=printing.name: effect_for(n, t),
                effect_for(printing.name, text),
                spell_resolution_text(printing.name, text),
            )
        )
    index = 0
    for ability in parse_abilities(printing):
        if isinstance(ability, ActivatedAbility):
            i = index
            index += 1
            if ability.mana is not None:
                continue

            def dispatch(t, n=printing.name, i=i):
                return activated_effect_for(n, i, t)

            found.append(
                (
                    ability.effect,
                    dispatch,
                    dispatch(ability.effect),
                    activation_resolution_text(ability.effect),
                )
            )
        elif isinstance(ability, TriggeredAbility) and ability.event is not None:

            def dispatch(t, n=printing.name, e=ability.event):
                return trigger_effect_for(n, e, t)

            found.append((ability.effect, dispatch, dispatch(ability.effect), None))
    return found


def _clauses_with_reason(printing, prefix):
    return [
        clause
        for clause in card_support(printing).clauses
        if clause.reason and clause.reason.startswith(prefix)
    ]


# --- the reported examples ------------------------------------------------


def test_pride_of_conquerors_instead_rider_is_now_read():
    """These two were the reported examples: the mass pump used to read only
    "Creatures you control get +1/+1" and drop the whole city's-blessing
    "instead" sentence as an unparsed remainder (see `_mass_pump_spell_
    effect`'s own docstring and `tests/scenarios/test_mass_pump_instead_
    upgrade.py`, which plays both branches). `_parse_mass_pump_instead_
    upgrade` now reads it, so this clause is `handled`, not `notice`."""
    printing = card("Pride of Conquerors")
    effect = effect_for(printing.name, printing.oracle_text)
    assert unparsed_remainder(effect) is None
    (spell,) = [c for c in card_support(printing).clauses if c.kind == "spell"]
    assert spell.outcome == "handled"


def test_summon_knights_of_round_chapter_five_counter_sentence_is_now_read():
    """Chapter V used to pump the other creatures and drop the whole
    indestructible-counter sentence (see `_mass_pump_ability_effect`'s own
    docstring and `tests/scenarios/test_mass_pump_counter_on_each.py`, which
    plays it end to end). `_parse_mass_pump_counter_on_each` now reads it."""
    printing = card("Summon: Knights of Round")
    (chapter_five,) = [
        a
        for a in parse_abilities(printing)
        if isinstance(a, TriggeredAbility) and "indestructible counter" in a.effect
    ]
    effect = trigger_effect_for(printing.name, chapter_five.event, chapter_five.effect)
    assert unparsed_remainder(effect) is None
    (clause,) = [c for c in card_support(printing).clauses if c.text == chapter_five.text]
    assert clause.outcome == "handled"
    assert card_support(printing).status == "handled"


def test_the_marker_is_proven_on_a_third_printing():
    """The same shape on a printing that is neither reported example."""
    reported = {"Pride of Conquerors", "Summon: Knights of Round"}
    others = [
        printing.name
        for printing in _printings()
        if printing.name not in reported
        and any(unparsed_remainder(effect) for _, _, effect, _ in _dispatches(printing))
        and _clauses_with_reason(printing, _REMAINDER)
    ]
    assert others, "no third printing carries an unparsed remainder"


# --- the marker, at every site that builds a remainder notice -------------

#: Every closure in `machines/effects.py` that records a `LayerRemainderNotice`
#: (or `CastFromHandExileNotice`'s unread tail) at runtime for text it could
#: not read.
_REMAINDER_SITES = (
    "_mass_pump_ability_effect.<locals>.effect",
    "_mass_pump_spell_effect.<locals>.effect",
    "_parse_where_x_is_continuous_effect.<locals>.effect",
    "_compose_layer_effect_with_remainder.<locals>.layer_effect_with_remainder_notice",
    "_compose_layer_effect_with_remainder_for_ability.<locals>.layer_effect_with_remainder_notice",
    "_compose_layer_effect_with_remainder_for_ability.<locals>.layer_or_counter_instead",
    "_compose_layer_effect_with_remainder_for_mode.<locals>.layer_effect_with_remainder_notice",
    "_compose_layer_effect_with_remainder_for_ability_mode.<locals>."
    "layer_effect_with_remainder_notice",
    "_parse_cast_from_hand_then_exile_clause.<locals>.unread_tail_notice_only",
)


#: The sites whose closure exists only when a remainder was dropped - every
#: instance must carry the marker. The others build the same closure whether
#: or not the remainder read, and carry it only when it did not.
_ALWAYS_A_REMAINDER = frozenset(
    site
    for site in _REMAINDER_SITES
    if site.endswith(("layer_effect_with_remainder_notice", "unread_tail_notice_only"))
)


def _site_texts():
    """(site qualname, reader, text) - the real printed text of a pool
    printing that reaches each site's remainder-notice closure."""
    from magic_cards_model.machines import effects

    readers = {
        "_mass_pump_ability_effect": effects._mass_pump_ability_effect,
        "_mass_pump_spell_effect": effects._mass_pump_spell_effect,
        "_parse_where_x_is_continuous_effect": effects._parse_where_x_is_continuous_effect,
        "_compose_layer_effect_with_remainder": effects._compose_layer_effect_with_remainder,
        "_compose_layer_effect_with_remainder_for_ability": (
            effects._compose_layer_effect_with_remainder_for_ability
        ),
        "_compose_layer_effect_with_remainder_for_mode": (
            effects._compose_layer_effect_with_remainder_for_mode
        ),
        "_compose_layer_effect_with_remainder_for_ability_mode": (
            effects._compose_layer_effect_with_remainder_for_ability_mode
        ),
        "_parse_cast_from_hand_then_exile_clause": effects._parse_cast_from_hand_then_exile_clause,
    }
    texts = []
    for printing in _printings():
        for ability in parse_abilities(printing):
            own = getattr(ability, "effect", None) or ability.text
            texts.append(own)
            # Every trailing run of whole sentences too: a site whose head is
            # printed mid-ability (Taster of Wares' "That player exiles it.
            # If ...") is reached by the real printed words from there on.
            sentences = _sentences(own)
            texts.extend(" ".join(sentences[i:]) for i in range(1, len(sentences)))
        if printing.oracle_text:
            texts.append(printing.oracle_text)
            texts.extend(printing.oracle_text.split("\n"))
            texts.extend(
                line.lstrip("• ").strip()
                for line in printing.oracle_text.split("\n")
                if line.startswith("•")
            )
    return readers, texts


@pytest.mark.parametrize("site", _REMAINDER_SITES)
def test_every_remainder_notice_closure_carries_the_marker(site):
    """A closure that will record a remainder notice at runtime says so up
    front, so `support` never scores it `handled`."""
    readers, texts = _site_texts()
    reader = readers[site.split(".<locals>.")[0]]
    hits = 0
    reached = set()
    for text in texts:
        try:
            effect = reader(text)
        except Exception:  # noqa: BLE001 - a reader refusing a text is not this test's concern
            continue
        if getattr(effect, "__qualname__", "") != site:
            continue
        reached.add(text)
        marker = getattr(effect, "unparsed_remainder", None)
        if site in _ALWAYS_A_REMAINDER:
            assert marker, (site, text)
        if site in _CONDITION_GATED:
            assert bool(marker) is not _instead_condition_claimed(text), (site, text)
        if marker:
            hits += 1
    if site in _CONDITION_GATED:
        assert len(reached) >= 2, f"fewer than two pool printings reach {site}"
        return
    assert hits, f"no pool printing reaches {site} with a remainder it cannot read"


#: The site whose marker depends only on whether its "If <condition>, ...
#: instead" condition is one a reader claims: every pool printing of the
#: shape reads its condition now, so the site is proven by the marker being
#: absent exactly when `conditions.claims` answers True.
_CONDITION_GATED = frozenset(
    {"_compose_layer_effect_with_remainder_for_ability.<locals>.layer_or_counter_instead"}
)


def _instead_condition_claimed(text: str) -> bool:
    from magic_cards_model.machines import conditions
    from magic_cards_model.machines.effects import _LAYER_COUNTER_INSTEAD_UPGRADE_RE

    for sentence in _sentences(text):
        match = _LAYER_COUNTER_INSTEAD_UPGRADE_RE.fullmatch(sentence.rstrip(".").strip())
        if match is not None:
            return conditions.claims(match.group("condition").strip())
    raise AssertionError(f"no instead-upgrade sentence in {text!r}")


# --- the ablation probe ---------------------------------------------------


def _ablation_hits():
    hits = []
    for printing in _printings():
        for text, dispatch, effect, reads in _dispatches(printing):
            if effect is None or unparsed_remainder(effect):
                continue
            rider = ignored_rider(dispatch, text, effect, reads)
            if rider is not None:
                hits.append((printing, text, rider))
    return hits


def test_every_ablation_hit_in_the_pool_is_a_notice_naming_the_rider():
    """Whatever the probe finds in the pool is scored `notice` with the
    sentence it found as the reason - never left `handled`."""
    for printing, _, rider in _ablation_hits():
        assert any(
            clause.outcome == "notice" and clause.reason == _REMAINDER + rider
            for clause in card_support(printing).clauses
        ), (printing.name, rider)


def test_no_pool_clause_ignores_a_sentence_of_its_own_resolution_text():
    """Every sentence the probe ever found unread in the pool was a real gap
    and is read now: Do or Die's "They can't be regenerated." (CR 701.19c,
    `tests/scenarios/test_fra_s8b_separate_into_two_piles.py`), the copy
    trigger's "You may choose new targets for the copy." (CR 707.10c), and
    the Approach cycle's deck-construction line, which is not resolution
    text at all (`spell_resolution_text`)."""
    assert [(p.name, rider) for p, _, rider in _ablation_hits()] == []


#: The Approach cycle's printed text, handed whole to the reader that reads
#: its "you may exile ... If you do, ..." shape: that reader's regex takes
#: everything after "If you do," as its consequence, so on the raw printing
#: it also swallows the deck-construction line below - and answers anyway.
_SWALLOWING_READER_PRINTINGS = ("Dragon's Approach", "Sphinx's Approach")


@pytest.mark.parametrize("name", _SWALLOWING_READER_PRINTINGS)
def test_the_ablation_probe_catches_a_real_reader_that_swallows_a_sentence(name):
    """The probe's positive control, on a real reader and real printed text:
    `_parse_may_exile_self_and_named_copies_if_you_do_clause` handed the
    Approach cycle's whole oracle text builds the same closure with or
    without its "A deck can have any number of cards named ..." line, so the
    probe names that line. Through the real dispatcher it names nothing -
    `spell_resolution_text` never hands the reader that line at all."""
    from magic_cards_model.machines.effects import (
        _parse_may_exile_self_and_named_copies_if_you_do_clause as reader,
    )

    printing = card(name)
    text = printing.oracle_text
    (deck_line,) = [s for s in _sentences(text) if s.startswith("A deck can have")]
    effect = reader(text)
    assert effect is not None
    assert ignored_rider(reader, text, effect) == deck_line
    real = effect_for(printing.name, text)
    reads = spell_resolution_text(printing.name, text)
    assert deck_line not in reads
    assert ignored_rider(lambda t: effect_for(printing.name, t), text, real, reads) is None


def test_the_copy_trigger_reads_its_new_targets_permission():
    """CR 707.10/707.10c: a copy keeps the original's targets unless the
    effect says its controller may choose new ones - the permission
    sentence is part of what the closure does, not decoration."""
    codie = card("Codie, Ravenous Codex")
    (trigger,) = [a for a in parse_abilities(codie) if isinstance(a, TriggeredAbility)]
    (first, permission) = _sentences(trigger.effect)
    with_permission = trigger_effect_for(codie.name, trigger.event, trigger.effect)
    without = trigger_effect_for(codie.name, trigger.event, first)
    assert with_permission is not None and without is not None
    assert not same_closure(with_permission, without), permission


def test_a_kicker_rider_that_is_read_is_not_flagged():
    """No false positive: a spell whose "If this spell was kicked" sentence a
    reader composes into its closure keeps `handled`."""
    readers = []
    for printing in _printings():
        text = printing.oracle_text or ""
        if not _is_spell(printing) or "If this spell was kicked" not in text:
            continue
        effect = effect_for(printing.name, text)
        if effect is None or unparsed_remainder(effect):
            continue
        spells = [c for c in card_support(printing).clauses if c.kind == "spell"]
        if spells and all(c.outcome == "handled" for c in spells):
            readers.append(printing.name)
            assert (
                ignored_rider(
                    lambda t, n=printing.name: effect_for(n, t),
                    text,
                    effect,
                    spell_resolution_text(printing.name, text),
                )
                is None
            )
    assert len(readers) >= 2, readers


def _probed(text, reads=None):
    return [text[begin:stop] for begin, stop in probe_sentences(text, reads)]


def test_the_probe_removes_every_trailing_sentence_not_only_riders():
    """A reader whose regex swallows a plain trailing sentence is as blind
    as one that drops an "If ..." rider, so every sentence after the first
    is probed - not only if/otherwise/instead/unless ones."""
    text = (
        "Destroy target creature. It can't be regenerated. If that creature was a "
        'token, draw a card. Otherwise, you gain 2 life. It deals 2 damage "unless" '
        "you pay {1} instead."
    )
    assert _probed(text) == [
        "It can't be regenerated.",
        "If that creature was a token, draw a card.",
        "Otherwise, you gain 2 life.",
        'It deals 2 damage "unless" you pay {1} instead.',
    ]
    assert _probed("If you control a Forest, draw a card.") == []


def test_the_probe_skips_what_the_resolution_readers_are_never_handed():
    """A keyword line, reminder text, a separate ability printed on the
    spell: read by casting, a keyword machine or their own clause - removing
    one can never show a difference in the resolution closure."""
    for name in ("Faithless Looting", "Mage's Guile", "Command the Stage", "Raft Security Officer"):
        printing = card(name)
        for text, _, _, reads in _dispatches(printing):
            probed = _probed(text, reads)
            assert not any(
                word in sentence
                for sentence in probed
                for word in ("Flashback", "Cycling", "At the beginning", "This ability costs")
            ), (name, probed)


def test_a_stripped_cast_trigger_prefix_is_excluded_by_offset():
    """Dash Hopes' leading "When you cast this spell, ..." paragraph is a
    separate ability (CR 601.2i) - its sentences are never probed on the
    spell. Excluded by where they sit, not by their words: the same words
    printed again in the resolution text are probed there."""
    printing = card("Dash Hopes")
    text = printing.oracle_text
    reads = spell_resolution_text(printing.name, text)
    prefix, _, resolution = text.partition("\n")
    (repeated,) = [s for s in _sentences(prefix) if s.startswith("If")]
    assert _probed(text, reads) == _sentences(resolution)
    doubled = f"{text} {repeated}"
    assert _probed(doubled) == [*_sentences(resolution), repeated]


def test_same_closure_compares_recursively_by_value():
    first = effect_for("Lightning Bolt", "Lightning Bolt deals 3 damage to any target.")
    again = effect_for("Lightning Bolt", "Lightning Bolt deals 3 damage to any target.")
    other = effect_for("Lightning Bolt", "Lightning Bolt deals 4 damage to any target.")
    assert same_closure(first, again)
    assert not same_closure(first, other)


def test_only_a_bare_target_choice_is_exempt_from_the_closure_test():
    """A rider that only chooses targets ("If this spell was cast using
    teamwork, instead choose target creature card in your graveyard") is
    read when targets are announced (CR 601.2c), so the resolution closure
    coming back unchanged proves nothing about it. A sentence that names a
    target *and* does something with it - Wasteland Strangler's "If you do,
    target creature gets -3/-3 until end of turn." - is an instruction the
    closure must perform, and is judged by the closure like any other."""
    exempt, judged = set(), set()
    for printing in _printings():
        for text, _, effect, reads in _dispatches(printing):
            if effect is None:
                continue
            for begin, stop in probe_sentences(text, reads):
                ablated = _without_span(text, begin, stop)
                if profile_for_text(ablated) == profile_for_text(text):
                    continue
                sentence = text[begin:stop]
                if _only_chooses_targets(sentence, text, ablated):
                    exempt.add(printing.name)
                    assert "choose" in sentence.lower(), sentence
                else:
                    judged.add(printing.name)
    assert "Too Evil to Stay Dead" in exempt
    assert {"Wasteland Strangler", "Murk Strider", "Eldrazi Obligator"} <= judged
    (spell,) = [c for c in card_support(card("Too Evil to Stay Dead")).clauses if c.kind == "spell"]
    assert spell.outcome == "handled"


def test_a_closure_that_ignores_its_text_is_not_judged_by_ablation():
    """A dispatcher that answers the same closure for any text at all - a
    card's own row, read whole by hand (Delver of Secrets' upkeep reveal,
    Tishana's Tidebinder's counter-and-lose-abilities, each played through
    by its scenarios) - cannot show a sentence unread by giving the same
    answer without it."""
    checked = set()
    for printing in _printings():
        for text, dispatch, effect, reads in _dispatches(printing):
            if effect is None or not probe_sentences(text, reads):
                continue
            try:
                blind = dispatch("")
            except Exception:  # noqa: BLE001 - a dispatcher refusing empty text reads text
                continue
            if blind is None or not same_closure(blind, effect):
                continue
            assert ignored_rider(dispatch, text, effect, reads) is None, printing.name
            checked.add(printing.name.split(" // ")[0])
    assert {"Delver of Secrets", "Tishana's Tidebinder"} <= checked, checked


def test_every_probed_pool_clause_is_comparable_to_itself():
    """The ablation probe is only as good as `same_closure`: a closure that
    never compares equal to a second build of the very same text would read
    every sentence as consumed, and the probe would be blind there (it fails
    closed instead - `UnprobeableClosure`). Two builds from the same text
    carry equal-but-distinct values (a fresh `re.Match`, a plain
    parsed-description object, a callable pydantic modification) - all of
    them compare by value."""
    checked = 0
    blind = []
    for printing in _printings():
        for text, dispatch, effect, reads in _dispatches(printing):
            if effect is None or not probe_sentences(text, reads):
                continue
            checked += 1
            if not same_closure(effect, dispatch(text)):
                blind.append((printing.name, text))
    assert checked > 300, checked
    assert blind == []


def test_same_closure_tells_apart_two_lambdas_of_one_function():
    """Two closures sharing a `__qualname__` (two lambdas written in one
    function) are different code, never the same effect."""

    def build(which):
        if which:
            return lambda: 1
        return lambda: 2

    assert build(True).__qualname__ == build(False).__qualname__
    assert not same_closure(build(True), build(False))
    assert same_closure(build(True), build(True))


def test_a_closure_graph_too_large_to_walk_fails_closed():
    """`unparsed_remainder` stops after `_CLOSURE_WALK_LIMIT` values; a graph
    it could not finish walking may hold a remainder past the limit, so it
    answers with a reason rather than a clean bill."""
    text = "Lightning Bolt deals 3 damage to any target."
    many = [effect_for("Lightning Bolt", text) for _ in range(_CLOSURE_WALK_LIMIT)]
    assert unparsed_remainder(many[0]) is None
    reason = unparsed_remainder(many)
    assert reason is not None and "walk limit" in reason


def test_every_mode_is_judged_by_the_ablation_probe_too():
    """A mode is a clause of its own (CR 700.2a): its reader is asked the
    same closure questions - comparable to itself, no sentence ignored - for
    a modal spell's modes and a modal trigger's modes alike."""
    from magic_cards_model.machines.effects import (
        _parse_mode_with_shared_verb_fallback,
        modal_trigger_profile,
        mode_effect_body,
        parse_mode_effect,
    )
    from magic_cards_model.machines.modes import modal_profile
    from magic_cards_model.support import _first_reading

    probed = 0
    for printing in _printings():
        modal = modal_profile(printing)
        if modal is not None and modal.understood:
            for mode in modal.modes:

                def read(t, mode=mode, modal=modal):
                    moved = mode.model_copy(update={"text": t})
                    effect = parse_mode_effect(moved, 0)
                    return effect or _parse_mode_with_shared_verb_fallback(moved, modal.instruction)

                effect = read(mode.text)
                if effect is None or not probe_sentences(mode.text):
                    continue
                probed += 1
                assert same_closure(effect, read(mode.text)), (printing.name, mode.text)
                assert ignored_rider(read, mode.text, effect) is None, (printing.name, mode.text)
        for ability in parse_abilities(printing):
            if not isinstance(ability, TriggeredAbility):
                continue
            profile = modal_trigger_profile(ability.effect)
            if profile is None:
                continue
            for mode in profile.modes:
                body = mode_effect_body(mode)
                effect = _first_reading(body, card_name=printing.name)
                if effect is None or not probe_sentences(body):
                    continue
                probed += 1
                read = lambda t, n=printing.name: _first_reading(t, card_name=n)  # noqa: E731
                assert same_closure(effect, read(body)), (printing.name, body)
                assert ignored_rider(read, body, effect) is None, (printing.name, body)
    assert probed >= 10, probed
