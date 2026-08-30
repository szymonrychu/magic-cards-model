"""Reading modal structure off real oracle text (CR 700.2).

Every profile here is parsed from the printing in tests/fixtures/cards, so a
case only holds if the real card really says what the test claims it says.
"""

import pytest

from magic_cards_model.machines.modes import (
    Mode,
    modal_profile,
    mode_rules_text,
)
from tests.cards import card


def modal(name: str):
    profile = modal_profile(card(name))
    assert profile is not None, f"{name} did not parse as a modal card"
    return profile


# -- the instruction line ---------------------------------------------------


def test_choose_one_reads_every_bullet_as_a_mode():
    """CR 700.2: two or more options in a bulleted list, with instructions."""
    profile = modal("Thraben Charm")

    assert profile.instruction.startswith("Choose one")
    assert profile.allowed_range() == (1, 1)
    assert [mode.number for mode in profile.modes] == [1, 2, 3]
    assert profile.modes[1].text == "Destroy target enchantment."


def test_choose_two_asks_for_exactly_two_of_four():
    profile = modal("Kozilek's Command")

    assert profile.allowed_range() == (2, 2)
    assert len(profile.modes) == 4


def test_choose_one_or_both_takes_either_or_both():
    """Deafening Clarion prints "Choose one or both -" over two modes."""
    profile = modal("Deafening Clarion")

    assert profile.allowed_range() == (1, 2)


def test_choose_one_or_more_takes_up_to_every_mode():
    profile = modal("Blessed Alliance")

    assert profile.allowed_range() == (1, 3)


def test_a_card_with_no_bulleted_list_is_not_modal():
    assert modal_profile(card("Lightning Bolt")) is None
    assert modal_profile(card("Grizzly Bears")) is None


# -- CR 700.2d: repeating a mode -------------------------------------------


def test_a_repeated_mode_is_refused_by_default():
    """CR 700.2d: normally a player can't choose the same mode twice."""
    with pytest.raises(ValueError, match="chosen twice"):
        modal("Kozilek's Command").resolve([1, 1])


def test_a_card_that_says_so_allows_the_same_mode_more_than_once():
    """Mystic Confluence prints that line, so CR 700.2d's exception applies."""
    profile = modal("Mystic Confluence")

    assert profile.repeatable
    chosen = profile.resolve([3, 3, 3])

    assert [mode.number for mode in chosen] == [3, 3, 3]


def test_a_card_without_that_line_is_not_repeatable():
    assert not modal("Cryptic Command").repeatable


# -- how many modes ---------------------------------------------------------


def test_too_few_modes_is_refused():
    with pytest.raises(ValueError, match="too few modes"):
        modal("Kozilek's Command").resolve([1])


def test_too_many_modes_is_refused():
    with pytest.raises(ValueError, match="too many modes"):
        modal("Kozilek's Command").resolve([1, 2, 3])


def test_one_mode_too_many_on_a_choose_one_card():
    with pytest.raises(ValueError, match="too many modes"):
        modal("Abrade").resolve([1, 2])


def test_no_modes_at_all_is_too_few():
    with pytest.raises(ValueError, match="too few modes"):
        modal("Abrade").resolve([])


# -- naming a mode ----------------------------------------------------------


def test_a_mode_number_off_the_end_is_unknown():
    with pytest.raises(ValueError, match="there is no mode 5"):
        modal("Kozilek's Command").resolve([1, 5])


def test_a_mode_this_card_does_not_have_is_unknown():
    with pytest.raises(ValueError, match="is not a mode of this spell"):
        modal("Abrade").resolve(["Counter target spell."])


def test_a_mode_can_be_named_by_a_piece_of_its_text():
    (chosen,) = modal("Abrade").resolve(["destroy target artifact"])

    assert chosen.number == 2


def test_a_mode_from_another_card_is_not_this_card_s_mode():
    other = Mode(number=1, text="Counter target spell.")

    with pytest.raises(ValueError, match="is not a mode of this spell"):
        modal("Abrade").resolve([other])


# -- CR 702.42a entwine, CR 702.120a escalate -------------------------------


def test_entwine_is_read_off_the_card():
    """CR 702.42a: choose all modes instead of the number specified."""
    profile = modal("Tooth and Nail")

    assert profile.entwine_cost == "{2}"
    assert profile.allowed_range() == (1, 1)
    assert profile.allowed_range(entwined=True) == (2, 2)


def test_entwine_lets_both_modes_be_chosen():
    chosen = modal("Tooth and Nail").resolve([1, 2], entwined=True)

    assert [mode.number for mode in chosen] == [1, 2]


def test_both_modes_are_still_too_many_without_the_entwine_cost():
    with pytest.raises(ValueError, match="too many modes"):
        modal("Tooth and Nail").resolve([1, 2])


def test_entwine_cannot_be_claimed_on_a_card_without_it():
    with pytest.raises(ValueError, match="no entwine cost"):
        modal("Kozilek's Command").resolve([1, 2], entwined=True)


def test_a_mana_escalate_cost_is_read_off_the_card():
    """CR 702.120a: an additional cost for each mode beyond the first."""
    assert modal("Blessed Alliance").escalate_cost == "{2}"


def test_an_escalate_cost_that_is_not_mana_is_read_too():
    """Collective Brutality escalates for a discard rather than for mana."""
    profile = modal("Collective Brutality")

    assert profile.escalate_cost == "Discard a card"
    assert profile.allowed_range() == (1, 3)


def test_escalate_does_not_change_how_many_modes_may_be_chosen():
    """Escalate changes what is paid, not what "choose one or more" allows."""
    chosen = modal("Blessed Alliance").resolve([1, 2, 3])

    assert len(chosen) == 3


# -- preparing a mode's text for the target parser --------------------------


def test_an_ability_a_mode_grants_is_not_read_as_the_mode_s_own():
    """Kozilek's Command's tokens have "Sacrifice this token: Add {C}."."""
    mode = modal("Kozilek's Command").modes[0]

    assert ":" in mode.text
    assert ":" not in mode_rules_text(mode)


def test_x_in_a_mode_is_substituted_once_the_caster_announces_it():
    """CR 107.3a: X has no value until its caster chooses one."""
    mode = modal("Kozilek's Command").modes[3]

    assert mode.text == "Exile up to X target cards from graveyards."
    assert mode_rules_text(mode, 3) == "Exile up to 3 target cards from graveyards."
    assert "X" in mode_rules_text(mode)
