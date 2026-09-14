"""The oracle-text sentence parse behind every board computation is memoised.

`abilities.layer_readable_sentences` and `layers._effect_sentences` are pure
functions of printed text and their flags, and the layer engine asks them the
same questions for every permanent every time a board is computed. Both are
memoised on every argument that shapes the answer, bounded, and hand each
caller its own list so nobody can edit the cached answer.

Checked against every printing in the card pool, not a sample.
"""

from __future__ import annotations

from collections.abc import Iterator

from magic_cards_model.machines import abilities, layers
from tests.cards import pool


def _texts() -> Iterator[tuple[str | None, str, list[str]]]:
    yield None, "", []
    for card in pool().values():
        for _, text in abilities._faces(card):
            yield text, card.name, list(card.keywords)


def test_layer_readable_sentences_memo_matches_the_uncached_parse():
    for text, name, keywords in _texts():
        for static_only in (False, True):
            for card_name in (None, name):
                for known in (None, keywords):
                    expected = abilities._layer_readable_sentences_uncached(
                        text, known, static_only=static_only, card_name=card_name
                    )
                    for _ in range(2):
                        assert (
                            abilities.layer_readable_sentences(
                                text, known, static_only=static_only, card_name=card_name
                            )
                            == expected
                        ), (text, static_only, card_name, known)


def test_effect_sentences_memo_matches_the_uncached_parse():
    for text, name, _ in _texts():
        for static_only in (False, True):
            for card_name in (None, name):
                expected = layers._effect_sentences_uncached(
                    text, static_only=static_only, card_name=card_name
                )
                for _ in range(2):
                    assert (
                        layers._effect_sentences(text, static_only=static_only, card_name=card_name)
                        == expected
                    ), (text, static_only, card_name)


def _sentenced_text() -> str:
    for text, _, _ in _texts():
        if text and len(layers._effect_sentences_uncached(text, static_only=True)) >= 1:
            return text
    raise AssertionError("no printing in the pool has a static sentence")


def test_editing_a_returned_sentence_list_does_not_reach_the_memo():
    text = _sentenced_text()
    expected_layer = abilities._layer_readable_sentences_uncached(text, None, static_only=True)
    expected_effect = layers._effect_sentences_uncached(text, static_only=True)

    for read, expected in (
        (lambda: abilities.layer_readable_sentences(text, static_only=True), expected_layer),
        (lambda: layers._effect_sentences(text, static_only=True), expected_effect),
    ):
        first = read()
        first.append("poison")
        first[0] = "poison"
        assert read() == expected
        assert read() is not read()


def test_the_memos_are_bounded_and_actually_hit():
    text = _sentenced_text()
    for memo, read in (
        (
            abilities._layer_readable_sentences_memo,
            lambda: abilities.layer_readable_sentences(text, static_only=True),
        ),
        (layers._effect_sentences_memo, lambda: layers._effect_sentences(text, static_only=True)),
    ):
        assert memo.cache_info().maxsize is not None
        read()
        hits = memo.cache_info().hits
        read()
        assert memo.cache_info().hits == hits + 1
