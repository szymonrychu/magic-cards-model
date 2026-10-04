"""Toy family module 'alpha' for the chains template tests."""


def a_first(text):
    return "a_first" if text == "a1" else None


def a_second(text):
    return "a_second" if text in ("a2", "both") else None


def a_spell(text, for_spell=None):
    return ("a_spell", for_spell) if text == "spell" else None


def a_boom(text):
    if text == "boom":
        raise ValueError("alpha exploded")
    return None
