"""Toy family module 'beta' for the chains template tests."""


def b_first(text):
    return "b_first" if text in ("b1", "both") else None


def b_second(text):
    return "b_second" if text == "b2" else None


def b_spell(text, *, for_spell):
    return ("b_spell", for_spell) if text == "spell" else None
