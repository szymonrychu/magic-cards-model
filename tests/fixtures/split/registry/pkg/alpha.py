"""Fixture family alpha."""

from __future__ import annotations


def _tag(fn):
    return fn


def parse_a_one(text):
    return ("a_one", text) if text.startswith("a") else None


def parse_a_two(text):
    return ("a_two", text) if "x" in text else None


def parse_a_three(text):
    return ("a_three", text) if text == "three" else None


@_tag
def parse_a_four(text):
    return ("a_four", text) if text == "four" else None


def parse_a_fs(text, *, for_spell):
    return ("a_fs", text, for_spell) if text == "fs" else None


def parse_a_true(text, *, for_spell):
    return ("a_true", text, for_spell) if text == "ft" else None


def parse_a_false(text, *, for_spell):
    return ("a_false", text, for_spell) if text == "ff" else None


def parse_a_plain(text):
    return ("a_plain", text) if text == "plain" else None


def parse_a_clause(clause):
    return ("a_clause", clause) if clause == "ac" else None
