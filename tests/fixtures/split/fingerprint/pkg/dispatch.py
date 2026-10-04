"""Fixture package ladders: same bodies as mono.py, names imported from families."""

from __future__ import annotations

from .fam_a import helper, parse_alpha, parse_beta, parse_boom
from .fam_b import SEGS, _resolve_gamma, parse_seg_two


def ladder_plain(text, for_spell=False):
    helper(text)
    if (r := parse_alpha(text, for_spell=for_spell)) is not None:
        return r
    if (r := parse_beta(text)) is not None:
        return r
    if (r := parse_boom(text)) is not None:
        return r
    return _resolve_gamma(text)


def ladder_chain(text, for_spell=False):
    if (r := parse_alpha(text)) is not None:
        return r
    if (r := SEGS.run("mid", text)) is not None:
        return r
    if (r := parse_beta(text)) is not None:
        return r
    if (r := parse_seg_two(text)) is not None:
        return r
    return _resolve_gamma(text)


def ladder_ghost(text):
    if (r := parse_alpha(text)) is not None:
        return r
    if (r := parse_facade_only(text)) is not None:  # noqa: F821 - bound only by the facade
        return r
    return None
