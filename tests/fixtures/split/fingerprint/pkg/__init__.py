"""Fixture facade: re-exports every name, plus one that only the facade binds."""

from __future__ import annotations

from .dispatch import ladder_chain, ladder_ghost, ladder_plain
from .fam_a import helper, parse_alpha, parse_beta, parse_boom
from .fam_b import SEGS, _resolve_gamma, parse_seg_one, parse_seg_two


def parse_facade_only(text):
    return ("facade", text)


__all__ = [
    "SEGS",
    "_resolve_gamma",
    "helper",
    "ladder_chain",
    "ladder_ghost",
    "ladder_plain",
    "parse_alpha",
    "parse_beta",
    "parse_boom",
    "parse_facade_only",
    "parse_seg_one",
    "parse_seg_two",
]
