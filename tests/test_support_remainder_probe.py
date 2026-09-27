"""A dispatcher closure that drops or only notices part of its clause is not
`handled` (CR 608.2c: the controller follows every instruction of the text,
in order - an instruction the engine skips leaves the clause half-played).

Two probes, both read by `magic_cards_model.support`:

- **the marker**: every `machines/effects.py` closure built around a remainder
  it could not read carries `effect.unparsed_remainder = <text>`
  (`support.unparsed_remainder` finds it anywhere in the closure graph);
- **the ablation probe**: for a handled clause with more than one sentence,
  each trailing rider sentence ("If ...", "Otherwise ...", or one containing
  "instead"/"unless") is removed and the clause re-dispatched - the same
  closure back means the rider was never read (`support.ignored_rider`).

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
    effect_for,
    trigger_effect_for,
)
from magic_cards_model.models.card import Type
from magic_cards_model.support import (
    _sentences,
    _without_sentence,
    card_support,
    ignored_rider,
    rider_sentences,
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
    """(clause text, dispatch, effect) for the spell text and every
    triggered/activated ability of `printing`, dispatched the way
    `support.classify_clauses` dispatches them (no X)."""
    found = []
    if _is_spell(printing) and printing.oracle_text:
        text = printing.oracle_text
        found.append(
            (text, lambda t, n=printing.name: effect_for(n, t), effect_for(printing.name, text))
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

            found.append((ability.effect, dispatch, dispatch(ability.effect)))
        elif isinstance(ability, TriggeredAbility) and ability.event is not None:

            def dispatch(t, n=printing.name, e=ability.event):
                return trigger_effect_for(n, e, t)

            found.append((ability.effect, dispatch, dispatch(ability.effect)))
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
        and any(unparsed_remainder(effect) for _, _, effect in _dispatches(printing))
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
        for text, dispatch, effect in _dispatches(printing):
            if effect is None or unparsed_remainder(effect):
                continue
            rider = ignored_rider(dispatch, text, effect)
            if rider is not None:
                hits.append((printing, text, rider))
    return hits


def test_every_ablation_hit_in_the_pool_is_a_notice_naming_the_rider():
    """Whatever the probe finds in the pool is scored `notice` with the rider
    it found as the reason - never left `handled`."""
    for printing, _, rider in _ablation_hits():
        assert any(
            clause.outcome == "notice" and clause.reason == _REMAINDER + rider
            for clause in card_support(printing).clauses
        ), (printing.name, rider)


#: Real printings whose rider the engine used to drop and now reads (Hidden
#: Blade's Assassin deathtouch, Lorehold Excavation's "Otherwise" damage,
#: Vexing Arcanix's name branch) - the probe's own positive control.
_ONCE_DROPPED = ("Hidden Blade", "Lorehold Excavation", "Vexing Arcanix")


@pytest.mark.parametrize("name", _ONCE_DROPPED)
def test_the_ablation_probe_catches_a_dispatcher_that_drops_the_rider(name):
    """The pool has no ignored rider left, so the probe is proven on the texts
    whose riders were the last ones dropped: asked through a dispatcher that
    answers every text the way the real one answers it without the rider -
    exactly what the old readers did - the probe names the rider; asked
    through the real dispatcher it names nothing."""
    printing = card(name)
    checked = 0
    for text, dispatch, effect in _dispatches(printing):
        for rider in rider_sentences(text):
            ablated = _without_sentence(text, rider)
            dropped = dispatch(ablated)
            if dropped is None or effect is None or same_closure(dropped, effect):
                continue

            def dropping(t, dispatch=dispatch, rider=rider):
                return dispatch(_without_sentence(t, rider) if rider in t else t)

            assert ignored_rider(dropping, text, dropped) == rider, (name, rider)
            assert ignored_rider(dispatch, text, effect) is None, (name, rider)
            checked += 1
    assert checked, name


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
            assert ignored_rider(lambda t, n=printing.name: effect_for(n, t), text, effect) is None
    assert len(readers) >= 2, readers


def test_rider_sentences_are_the_trailing_if_otherwise_instead_unless_sentences():
    text = (
        "Destroy target creature. It can't be regenerated. If that creature was a "
        'token, draw a card. Otherwise, you gain 2 life. It deals 2 damage "unless" '
        "you pay {1} instead."
    )
    assert rider_sentences(text) == [
        "If that creature was a token, draw a card.",
        "Otherwise, you gain 2 life.",
        'It deals 2 damage "unless" you pay {1} instead.',
    ]
    assert rider_sentences("If you control a Forest, draw a card.") == []
    assert (
        rider_sentences(
            "Ascend (If you control ten or more permanents, you get the city's blessing.)\n"
            "Creatures you control get +1/+1 until end of turn."
        )
        == []
    )


def test_same_closure_compares_recursively_by_value():
    first = effect_for("Lightning Bolt", "Lightning Bolt deals 3 damage to any target.")
    again = effect_for("Lightning Bolt", "Lightning Bolt deals 3 damage to any target.")
    other = effect_for("Lightning Bolt", "Lightning Bolt deals 4 damage to any target.")
    assert same_closure(first, again)
    assert not same_closure(first, other)


def test_a_rider_the_target_announcement_reads_is_not_flagged():
    """No false positive: a rider that only changes what the spell or ability
    may target (CR 601.2c - "If this spell was cast using teamwork, instead
    choose target creature card in your graveyard") is read when targets are
    announced, not by the resolution closure, so the closure coming back
    unchanged proves nothing. Too Evil to Stay Dead's teamwork scenarios
    (`tests/scenarios/test_teamwork_riders.py`) play both branches."""
    from magic_cards_model.machines.targeting import profile_for_text

    read_by_targeting = set()
    for printing in _printings():
        for text, _dispatch, effect in _dispatches(printing):
            if effect is None or unparsed_remainder(effect):
                continue
            for rider in rider_sentences(text):
                ablated = _without_sentence(text, rider)
                if profile_for_text(ablated) == profile_for_text(text):
                    continue
                read_by_targeting.add(printing.name)
                assert not any(
                    clause.reason == _REMAINDER + rider for clause in card_support(printing).clauses
                ), (printing.name, rider)
    assert "Too Evil to Stay Dead" in read_by_targeting
    (spell,) = [c for c in card_support(card("Too Evil to Stay Dead")).clauses if c.kind == "spell"]
    assert spell.outcome == "handled"


def test_a_closure_that_ignores_its_text_is_not_judged_by_ablation():
    """A dispatcher that answers the same closure for any text at all - a
    card's own row, read whole by hand (Delver of Secrets' upkeep reveal,
    Tishana's Tidebinder's counter-and-lose-abilities, each played through
    by its scenarios) - cannot show a rider unread by giving the same answer
    without it."""
    checked = set()
    for printing in _printings():
        for text, dispatch, effect in _dispatches(printing):
            if effect is None or not rider_sentences(text):
                continue
            try:
                blind = dispatch("")
            except Exception:  # noqa: BLE001 - a dispatcher refusing empty text reads text
                continue
            if blind is None or not same_closure(blind, effect):
                continue
            assert ignored_rider(dispatch, text, effect) is None, printing.name
            checked.add(printing.name.split(" // ")[0])
    assert {"Delver of Secrets", "Tishana's Tidebinder"} <= checked, checked
