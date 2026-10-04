"""Fixture family module B."""

from __future__ import annotations


def _resolve_gamma(text):
    return ("gamma", text) if text.endswith("c") else None


def parse_seg_one(text):
    return ("seg1", text) if text.startswith("s") else None


def parse_seg_two(text):
    return ("seg2", text) if "t" in text else None


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
