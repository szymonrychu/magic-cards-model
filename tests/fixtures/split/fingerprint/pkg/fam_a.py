"""Fixture family module A."""

from __future__ import annotations


def parse_alpha(text, for_spell=False):
    return ("alpha", text) if text.startswith("a") else None


def parse_beta(text):
    return ("beta", text) if "b" in text else None


def parse_boom(text):
    raise ValueError(text)


def helper(text):
    return text
