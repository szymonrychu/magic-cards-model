"""Choice rows: modes printed as token characteristics, modal activations with
an activation instruction, and "the chosen <thing>" references.

**Token-characteristics modes** (CR 700.2): "choose one at random. Create a red
and white creature token with those characteristics. - 3/1 Human Warrior with
trample and haste. - ..." (Outlaws' Merriment) and "choose one that hasn't
been chosen this turn. Create a creature token with those characteristics."
(Genku, Future Shaper). The bullets are the modes; each says what the token
is. `fold_choice_rows` writes each bullet as the token-creation sentence it
stands for ("Create a 3/1 red and white Human Warrior creature token with
trample and haste.") under an ordinary "choose one ... -" instruction, so the
modal machinery (`machines/modes.py`, `Game._announce_trigger_modes`) and the
token reader read them like any other modal trigger. "At random" (the card's
own ruling: the mode is chosen at random as the ability is put on the stack,
CR 700.2b's moment) is applied by `Game._announce_trigger_modes`.

**A modal activation with an instruction** (CR 700.2a, CR 602.5b): "{G}:
Choose one. Activate only once each turn. - Until end of turn, this creature
becomes a Rhino ..." (Skinshifter). The instruction is not a mode; it is moved
after the bullets, where `abilities._INSTRUCTIONS` reads activation
instructions, and the header becomes the ordinary "Choose one -".
"""

from __future__ import annotations

import re

from ..phrases import with_indefinite_article

_BULLET = "•"

#: "choose one at random. Create a[n] [<colors>] creature token[s] with those
#: characteristics." at the end of a line.
_CHARACTERISTICS_HEADER_RE = re.compile(
    r"(?P<choose>choose one(?: at random| that hasn'?t been chosen(?: this turn)?)?)\.\s*"
    r"create (?P<count>an?|two|three) (?P<colors>(?:[a-z]+(?:, | and |, and | ))*?)"
    r"creature tokens? with those characteristics\.\s*$",
    re.IGNORECASE,
)
#: One bullet: "2/2 white Fox with vigilance." / "1/2 Human Rogue with haste
#: and "When this token enters, ..."" - power/toughness, the color and type
#: words, then what the token has.
_CHARACTERISTICS_BULLET_RE = re.compile(
    r"^•\s*(?P<pt>\d+/\d+) (?P<desc>[^\"]+?)(?: with (?P<with>.+))?$"
)
#: "<cost>: Choose one. Activate only ..." - a modal activated ability whose
#: activation instruction is printed on the instruction line.
_ACTIVATED_CHOOSE_ONE_HEADER_RE = re.compile(
    r"^(?P<head>[^:\"]+: choose one)\.\s*(?P<instruction>activate only [^.]+\.)\s*$",
    re.IGNORECASE,
)


def _bullets_after(lines: list[str], index: int) -> list[str]:
    bullets = []
    while index < len(lines) and lines[index].lstrip().startswith(_BULLET):
        bullets.append(lines[index].strip())
        index += 1
    return bullets


def _characteristics_mode(bullet: str, colors: str, plural: bool, count: str) -> str | None:
    text = bullet.strip()
    if text.endswith(".") and not text.endswith('."'):
        text = text[:-1]
    match = _CHARACTERISTICS_BULLET_RE.match(text)
    if match is None:
        return None
    body = " ".join(
        part for part in (match.group("pt"), colors.strip(), match.group("desc").strip()) if part
    )
    noun = "creature tokens" if plural else "creature token"
    lead = f"{count} {body}" if plural else with_indefinite_article(body)
    with_part = f" with {match.group('with')}" if match.group("with") else ""
    end = "" if with_part.endswith('."') else "."
    return f"{_BULLET} Create {lead} {noun}{with_part}{end}"


def _fold_characteristics(line: str, bullets: list[str]) -> list[str] | None:
    match = _CHARACTERISTICS_HEADER_RE.search(line)
    if match is None or len(bullets) < 2:
        return None
    count = match.group("count").lower()
    plural = count not in ("a", "an")
    modes = [
        _characteristics_mode(bullet, match.group("colors"), plural, count) for bullet in bullets
    ]
    if any(mode is None for mode in modes):
        return None
    header = f"{line[: match.start()]}{match.group('choose')} —"
    return [header, *[mode for mode in modes if mode is not None]]


def _fold_activated_choose_one(line: str, bullets: list[str]) -> list[str] | None:
    match = _ACTIVATED_CHOOSE_ONE_HEADER_RE.match(line.strip())
    if match is None or len(bullets) < 2:
        return None
    return [f"{match.group('head')} —", *bullets, match.group("instruction")]


def fold_choice_rows(lines: list[str]) -> list[str]:
    """`lines` with each token-characteristics modal block and each modal
    activation printing its instruction on the header rewritten as the
    ordinary modal shape (see the module docstring). Every other line is
    returned unchanged."""
    if not any("choose one" in line.lower() for line in lines):
        return lines
    folded: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        bullets = _bullets_after(lines, index + 1)
        block = None
        if bullets:
            block = _fold_characteristics(line, bullets) or _fold_activated_choose_one(
                line, bullets
            )
        if block is None:
            folded.append(line)
            index += 1
            continue
        # One newline-joined line, the shape `abilities._merge_modal_bullet_
        # lines` gives a modal header and its bullets.
        folded.append("\n".join(block))
        index += 1 + len(bullets)
    return folded
