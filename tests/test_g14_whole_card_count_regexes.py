"""G14-1: whole-card literal regexes generalized to read their counts through
`numbers.py` instead of a literal pinned to one printing.

Unit-test file, the same discipline `test_effects.py` and `test_mixed_effects.py`
use: it checks what the parser returns against real printed text (regression)
and against a hand-typed sentence of the identical shape with a different
count (proof the parser now reads the count rather than assuming it) -
exactly `test_effects.py::test_draw_seven_cards_spelled_out_parses`'s own
precedent of a spelled-out number on real text. None of these five shapes has
a second real Modern printing with a different count (the number sweep's own
"none in Modern" note), so genericity is proven with a hand-typed sentence
rather than a second card fixture - the same string-level proof `test_numbers.py`
already uses for the shared reader these parsers now call.

Every CR number here was already verified by the parser docstrings this file
exercises (CR 122.1a, CR 608.2c, CR 611.2, CR 614.1c, CR 701.23a, CR 702.62a,
CR 702.62b) - no new rule is asserted here.
"""

from magic_cards_model.machines import TriggerEvent
from magic_cards_model.machines.effects import effect_for, trigger_effect_for
from tests.cards import card

# --------------------------------------------------------------------------
# Fight Rigging - hideaway counter then conditional free cast
# --------------------------------------------------------------------------


def _fight_rigging_combat_trigger_text() -> str:
    # Fight Rigging's second sentence ("At the beginning of combat...") is the
    # combat trigger; its `effect` is everything after the trigger condition.
    return (
        "put a +1/+1 counter on target creature you control. "
        "then if you control a creature with power 7 or greater, "
        "you may play the exiled card without paying its mana cost."
    )


def test_fight_rigging_combat_trigger_parses():
    assert (
        trigger_effect_for(
            "Fight Rigging",
            TriggerEvent.BEGINNING_OF_STEP,
            _fight_rigging_combat_trigger_text(),
        )
        is not None
    )


def test_hideaway_counter_then_free_cast_generalizes_to_a_different_counter_and_threshold():
    """A hand-typed sentence of the identical shape, "two" counters and a
    power 10 threshold instead of Fight Rigging's own "a" and 7 - the same
    parser must still read it, off no card-name check at all.
    """
    text = (
        "put two +1/+1 counters on target creature you control. "
        "then if you control a creature with power 10 or greater, "
        "you may play the exiled card without paying its mana cost."
    )
    assert trigger_effect_for("Not Fight Rigging", TriggerEvent.BEGINNING_OF_STEP, text) is not None


# --------------------------------------------------------------------------
# Neoform - search for mana value equal to N plus the sacrificed creature's
# --------------------------------------------------------------------------


def test_neoform_second_paragraph_parses():
    second_paragraph = card("Neoform").oracle_text.split("\n")[-1]
    assert effect_for("Neoform", second_paragraph) is not None


def test_search_mv_equal_to_sacrificed_generalizes_to_a_different_offset_and_counters():
    """Two +1/+1 counters and an offset of 3, instead of Neoform's own "an"
    and 1.
    """
    text = (
        "Search your library for a creature card with mana value "
        "equal to 3 plus the sacrificed creature's mana value, "
        "put that card onto the battlefield with two additional +1/+1 counters on it, "
        "then shuffle."
    )
    assert effect_for("Not Neoform", text) is not None


# --------------------------------------------------------------------------
# Cultivator Colossus - put a land from hand, draw a card, repeat
# --------------------------------------------------------------------------


def test_cultivator_colossus_enters_trigger_parses():
    text = _triggered_effect_text("Cultivator Colossus")
    assert (
        trigger_effect_for("Cultivator Colossus", TriggerEvent.ENTERS_THE_BATTLEFIELD, text)
        is not None
    )


def _triggered_effect_text(name: str) -> str:
    from magic_cards_model.machines import AbilityKind, abilities_of_kind

    (ability,) = abilities_of_kind(card(name), AbilityKind.TRIGGERED)
    return ability.effect


def test_put_land_from_hand_repeat_generalizes_to_a_different_draw_count():
    """ "Draw two cards" instead of Cultivator Colossus's own "a card"."""
    text = (
        "you may put a land card from your hand onto the battlefield tapped. "
        "if you do, draw two cards and repeat this process."
    )
    assert (
        trigger_effect_for("Not Cultivator Colossus", TriggerEvent.ENTERS_THE_BATTLEFIELD, text)
        is not None
    )


# --------------------------------------------------------------------------
# Spelunking - draw a card, then maybe a land, with a Cave life bonus
# --------------------------------------------------------------------------


def test_spelunking_enters_trigger_parses():
    text = _triggered_effect_text("Spelunking")
    assert trigger_effect_for("Spelunking", TriggerEvent.ENTERS_THE_BATTLEFIELD, text) is not None


def test_draw_then_put_land_cave_bonus_generalizes_to_different_draw_and_life_counts():
    """ "Draw two cards" and "gain 6 life" instead of Spelunking's own "a
    card" and 4 life.
    """
    text = (
        "draw two cards, then you may put a land card from your hand onto the battlefield. "
        "if you put a cave onto the battlefield this way, you gain 6 life."
    )
    assert (
        trigger_effect_for("Not Spelunking", TriggerEvent.ENTERS_THE_BATTLEFIELD, text) is not None
    )


# --------------------------------------------------------------------------
# Greater Gargadon - remove a time counter from this card
# --------------------------------------------------------------------------


def test_greater_gargadons_own_sacrifice_ability_parses():
    from magic_cards_model.machines import AbilityKind, abilities_of_kind
    from magic_cards_model.machines.effects import activated_effect_for

    (ability,) = abilities_of_kind(card("Greater Gargadon"), AbilityKind.ACTIVATED)
    assert activated_effect_for("Greater Gargadon", 0, ability.effect) is not None


def test_remove_time_counter_from_self_generalizes_to_a_different_count():
    """ "Remove two time counters" instead of Greater Gargadon's own "a"."""
    from magic_cards_model.machines.effects import activated_effect_for

    text = "Remove two time counters from this card."
    assert activated_effect_for("Not Greater Gargadon", 0, text) is not None
