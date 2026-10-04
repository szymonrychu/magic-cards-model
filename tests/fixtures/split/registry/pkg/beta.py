"""Fixture family beta."""

from __future__ import annotations


def parse_b_one(text):
    return ("b_one", text) if "x" in text else None


def parse_b_two(text):
    return ("b_two", text) if "b" in text else None


def parse_b_three(text):
    return ("b_three", text) if text == "bthree" else None


def parse_b_four(text):
    return (("b_four", text),) if text == "bfour" else None


def parse_b_lazy(text):
    return ("b_lazy", text) if text == "lazy" else None


def parse_b_fs(text, *, for_spell):
    return ("b_fs", text, for_spell) if text == "bfs" else None


def parse_b_true(text, *, for_spell):
    return ("b_true", text, for_spell) if text == "bt" else None


def parse_b_clause(clause):
    return ("b_clause", clause) if clause == "bc" else None
