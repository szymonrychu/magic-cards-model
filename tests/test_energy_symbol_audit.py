"""No printed non-mana symbol reaches `ManaCost.parse` from a parser path.

CR 107.14: "The energy symbol is {E}. It represents one energy counter." It
is not a mana symbol, and `ManaCost.parse` - a primitive - refuses it with a
`ValueError`. Before this audit, "you may pay {E}. If you do, ..." whose
consequence the energy reader could not read fell through to the ordinary-mana
twin (`_MAY_PAY_MANA_IF_YOU_DO_RE`), whose `(?:\\{[^}]+\\})+` group accepted
{E} and crashed the whole card - live in a game, and in `card_support`.

`ManaCost.try_parse` is the parser-facing entry: `None` for any text that
carries a symbol that is not a mana symbol, so each call site that parses
printed text captured by a regex reads it or declines, and never raises.
"""

import re

import pytest

from magic_cards_model.machines.cost import total_cost_for_phrase
from magic_cards_model.machines.effects import (
    _ability_effect_or_notice,
    _parse_may_pay_mana_if_you_do_clause,
    _parse_reflexive_pay_mana_clause,
    activated_effect_for,
    effect_for,
    trigger_effect_for,
)
from magic_cards_model.machines.keywords import _keyword_cost, keyword_abilities
from magic_cards_model.machines.triggers import activated_abilities_of, triggered_abilities_of
from magic_cards_model.models import Card
from magic_cards_model.models.mana import ManaCost
from magic_cards_model.support import card_support
from tests.cards import pool

_ENERGY = re.compile(r"\{E\}")


def _texts(printing: Card) -> list[str]:
    texts = [printing.oracle_text or ""]
    texts.extend(face.oracle_text or "" for face in printing.card_faces or [])
    return texts


def _energy_printings() -> list[Card]:
    unique = {printing.name: printing for printing in pool().values()}
    return [
        printing
        for _, printing in sorted(unique.items())
        if any(_ENERGY.search(text) for text in _texts(printing))
    ]


ENERGY_PRINTINGS = _energy_printings()


def test_the_pool_carries_every_energy_card_that_used_to_crash():
    names = {printing.name for printing in ENERGY_PRINTINGS}
    assert {
        "Hexgold Slith",
        "Conduit Goblin",
        "Cyclops Superconductor",
        "Maulfist Doorbuster",
        "Voltstorm Angel",
        "Aetherstream Leopard",
        "Smelted Chargebug",
        "Voltaic Brawler",
        "Riparian Tiger",
    } <= names


@pytest.mark.parametrize("printing", ENERGY_PRINTINGS, ids=lambda printing: printing.name)
def test_every_energy_printing_goes_through_every_dispatcher_without_raising(printing: Card):
    legendary = "Legendary" in (printing.type_line or "")
    for text in _texts(printing):
        effect_for(printing.name, text)
    for index, ability in enumerate(triggered_abilities_of(printing)):
        trigger_effect_for(printing.name, ability.event, ability.effect, legendary=legendary)
        del index
    for index, ability in enumerate(activated_abilities_of(printing)):
        activated_effect_for(printing.name, index, ability.effect, legendary=legendary)
        total_cost_for_phrase(ability.cost, payer="alice")
    for ability in keyword_abilities(printing):
        _keyword_cost(ability, "alice")


@pytest.mark.parametrize("printing", ENERGY_PRINTINGS, ids=lambda printing: printing.name)
def test_every_energy_printing_gets_a_verdict_from_card_support(printing: Card):
    support = card_support(printing)
    assert support.status in ("handled", "unaudited", "notice", "silent")


@pytest.mark.parametrize(
    "name",
    [
        "Hexgold Slith",
        "Conduit Goblin",
        "Cyclops Superconductor",
        "Maulfist Doorbuster",
        "Voltstorm Angel",
        "Aetherstream Leopard",
        "Smelted Chargebug",
        "Voltaic Brawler",
        "Riparian Tiger",
    ],
)
def test_the_energy_pay_clause_of_each_formerly_crashing_card_is_handled(name: str):
    """The pay clause is read, not merely survived: every clause of each of
    these cards resolves (the ETB "you get {E}" too), so the card is
    handled."""
    support = card_support(pool()[name])
    pay = [clause for clause in support.clauses if "you may pay {E}" in clause.text]
    assert pay, support.clauses
    assert all(clause.outcome == "handled" for clause in pay), pay
    assert support.status == "handled", support.clauses


# -- ManaCost.try_parse ------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "symbols"),
    [
        ("{2}{W}", ("{2}", "{W}")),
        ("{X}{R}", ("{X}", "{R}")),
        ("{W/P}", ("{W/P}",)),
        ("{2/U}{C}", ("{2/U}", "{C}")),
        ("{S}", ("{S}",)),
        ("", ()),
    ],
)
def test_try_parse_reads_mana_symbols_exactly_as_parse_does(text: str, symbols: tuple[str, ...]):
    parsed = ManaCost.try_parse(text)
    assert parsed is not None
    assert parsed == ManaCost.parse(text)
    assert tuple(str(symbol) for symbol in parsed.symbols) == symbols


@pytest.mark.parametrize("text", ["{E}", "{E}{E}", "{2}{E}", "{T}", "{Q}", "{W}{Q}", "{TK}"])
def test_try_parse_declines_any_text_carrying_a_non_mana_symbol(text: str):
    assert ManaCost.try_parse(text) is None
    with pytest.raises(ValueError, match="unsupported mana symbol"):
        ManaCost.parse(text)


# -- the mana twins accept mana symbols only ---------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "you may pay {E}. If you do, draw a card.",
        "you may pay {E}{E}. If you do, draw a card.",
        "you may pay {T}. If you do, draw a card.",
    ],
)
def test_the_if_you_do_mana_twin_never_reads_a_non_mana_symbol(text: str):
    assert _parse_may_pay_mana_if_you_do_clause(text) is None


@pytest.mark.parametrize(
    "text",
    [
        "you may pay {E}. When you do, draw a card.",
        "you may pay {E}{E}{E}. When you do, draw a card.",
        "you may pay {Q}. When you do, draw a card.",
    ],
)
def test_the_when_you_do_mana_twin_never_reads_a_non_mana_symbol(text: str):
    assert _parse_reflexive_pay_mana_clause(text) is None


@pytest.mark.parametrize(
    "text",
    [
        "you may pay {E}. If you do, it phases into the Blind Eternities until end of turn.",
        "you may pay {E}{E}. When you do, it phases into the Blind Eternities until end of turn.",
    ],
)
def test_an_energy_payment_whose_consequence_is_unread_never_raises(text: str):
    """Declined by the energy reader, it must not be routed to a mana twin;
    the whole dispatcher answers `None` or a notice, never a `ValueError`."""
    _ability_effect_or_notice(text)
