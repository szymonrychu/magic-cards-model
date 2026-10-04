"""Fixture monolith: parsers, a Chain-like object and two ladders in one file."""

from __future__ import annotations


def parse_alpha(text, for_spell=False):
    return ("alpha", text) if text.startswith("a") else None


def parse_beta(text):
    return ("beta", text) if "b" in text else None


def _resolve_gamma(text):
    return ("gamma", text) if text.endswith("c") else None


def parse_seg_one(text):
    return ("seg1", text) if text.startswith("s") else None


def parse_seg_two(text):
    return ("seg2", text) if "t" in text else None


def parse_boom(text):
    raise ValueError(text)


def helper(text):
    return text


class Chain:
    """Duck-typed stand-in for the P0-T05 Chain template."""

    def __init__(self, segments):
        self._segments = segments

    def segment_rungs(self, segment):
        return self._segments[segment]

    def run(self, segment, value, **kwargs):
        for rung in self.segment_rungs(segment):
            result = rung(value)
            if result is not None:
                return result
        return None


SEGS = Chain({"mid": (parse_seg_one, parse_seg_two)})


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
