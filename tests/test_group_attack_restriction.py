"""`combat.is_group_attack_restriction_line` reads only *static* abilities
(CR 604.1, 508.1c).

No real printing carries "creatures [with power ...] can't attack [you]" as
the effect of an activated or triggered ability (Scryfall regex searches for
both shapes return nothing), so this is a parser-level test on sentences of
those shapes: their effect is a one-shot continuous effect of a resolving
ability (CR 611.2), never a standing restriction, and must not be applied
permanently from the battlefield.
"""

from magic_cards_model.machines.combat import is_group_attack_restriction_line


def test_a_static_line_is_a_restriction():
    assert is_group_attack_restriction_line("Creatures can't attack.")
    assert is_group_attack_restriction_line("Creatures with power 2 or less can't attack you.")


def test_an_activated_line_is_not_a_standing_restriction():
    assert not is_group_attack_restriction_line("{1}{W}: Creatures can't attack.")


def test_a_triggered_line_is_not_a_standing_restriction():
    assert not is_group_attack_restriction_line(
        "When this creature enters, creatures can't attack you."
    )
