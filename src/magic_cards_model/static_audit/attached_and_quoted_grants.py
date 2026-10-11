"""Aura/Equipment-attached rewrites and group quoted-ability grants (EP-01 R2,
T5): "Enchanted creature gets +X/+X, where X is ...", "Enchanted land is a 4/4
Elemental creature. It's still a land.", "Enchanted permanent has ward {1}.",
"Elves you control have "{T}: Add {B}."" (CR 303.4, CR 301.5, CR 613.1d,
CR 613.1f, CR 613.4c, CR 113.3d, CR 611.3).

A line is credited only when the PRODUCTION readers read every sentence of it:
`attached_grants.parse_attached_sentence` (the attached pumps, permanent
statics, type/ability rewrites and the one-shot "target X becomes ..." shape)
or `quoted_grants.parse_group_quoted_sentence`. A line with a sentence neither
reads stays unaudited.
"""

import functools
import re

from magic_cards_model.machines.abilities import self_normalized_effect_text

_ATTACHED_OR_GROUP_GATE = (
    "enchanted ",
    "equipped ",
    ' have "',
    ' has "',
    " have \u201c",
    " has \u201c",
    " becomes ",
    " loses ",
)
_ABILITY_WORD = re.compile(r"^[A-Z][\w' -]*? \u2014 ")
_SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s+(?=[A-Z])")


@functools.cache
def _sentences(line: str) -> tuple[str, ...]:
    """The line's sentences, never split inside a quoted ability."""
    parts: list[str] = []
    pieces = re.split(r'("[^"]*")', line)
    current = ""
    for piece in pieces:
        if piece.startswith('"') and piece.endswith('"') and len(piece) > 1:
            current += piece
            continue
        chunks = _SENTENCE_BREAK.split(piece)
        current += chunks[0]
        for chunk in chunks[1:]:
            parts.append(current)
            current = chunk
    parts.append(current)
    return tuple(part.strip() for part in parts if part.strip())


@functools.cache
def _reads(line: str) -> bool:
    from magic_cards_model.machines.layers.attached_grants import parse_attached_sentence
    from magic_cards_model.machines.layers.quoted_grants import parse_group_quoted_sentence

    def read(sentence: str) -> bool:
        return (
            parse_attached_sentence(sentence) is not None
            or parse_group_quoted_sentence(sentence) is not None
        )

    return read(line) or all(read(sentence) for sentence in _sentences(line))


def reads_attached_and_quoted_grants_line(
    printing, text: str, *, card_name: str | None = None, legendary: bool = False
) -> bool:
    lowered = text.lower()
    if not any(token in lowered for token in _ATTACHED_OR_GROUP_GATE):
        return False
    line = _ABILITY_WORD.sub("", text.lstrip("\u2022* ").strip(), count=1)
    name = card_name or printing.name
    return _reads(line) or _reads(self_normalized_effect_text(name, line, legendary=legendary))
