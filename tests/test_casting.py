import pytest

from magic_cards_model.machines import Casting, CastingStep, CostStep
from magic_cards_model.machines.cost import (
    TotalCost,
    pay_life_cost,
    sacrifice_cost,
)
from magic_cards_model.models import CardState, Color, ManaCost, Zone
from tests.cards import card_state


def spell_in_hand() -> CardState:
    """Ragavan, a {R} creature."""
    return card_state("Ragavan, Nimble Pilferer", Zone.HAND)


def source() -> CardState:
    return card_state("Mountain", Zone.BATTLEFIELD)


def test_casting_walks_the_announcement_steps_in_order():
    casting = Casting(spell=spell_in_hand(), caster="alice")
    assert casting.step is CastingStep.PROPOSED

    casting.choose_modes([])
    assert casting.step is CastingStep.MODES

    casting.choose_targets([])
    assert casting.step is CastingStep.TARGETS

    payment = casting.determine_cost()
    assert casting.step is CastingStep.COST_DETERMINED
    assert payment.cost == ManaCost.parse("{R}")  # Ragavan costs {R}


def test_a_spell_reaches_the_stack_once_its_cost_is_paid():
    casting = Casting(spell=spell_in_hand(), caster="alice")
    payment = casting.begin_paying()

    payment.tap_for_mana(source(), [Color.RED])
    payment.pay()
    on_stack = casting.cast()

    assert casting.step is CastingStep.CAST
    assert on_stack.zone is Zone.STACK


def test_a_spell_cannot_be_cast_before_it_is_paid_for():
    casting = Casting(spell=spell_in_hand(), caster="alice")
    casting.begin_paying()

    with pytest.raises(ValueError, match="before the cost is paid"):
        casting.cast()


def test_x_is_locked_in_when_the_cost_is_determined():
    spell = spell_in_hand()
    casting = Casting(spell=spell, caster="alice")

    payment = casting.determine_cost(x_value=3)

    # Ragavan has no X, so the total is unchanged, but the value is recorded.
    assert casting.x_value == 3
    assert payment.cost.x_count == 0


def test_cancelling_rewinds_the_spell_and_untaps_its_sources():
    spell = spell_in_hand()
    casting = Casting(spell=spell, caster="alice")
    payment = casting.begin_paying()
    mana_source = source()
    payment.tap_for_mana(mana_source, [Color.RED])

    casting.cancel()

    assert casting.step is CastingStep.CANCELLED
    assert payment.step is CostStep.CANCELLED
    assert mana_source.untapped
    assert spell.zone is Zone.HAND  # never left the hand


def test_announcement_steps_cannot_repeat_or_go_backwards():
    casting = Casting(spell=spell_in_hand(), caster="alice")
    casting.choose_targets([])

    with pytest.raises(ValueError, match="cannot go back"):
        casting.choose_modes([])
    with pytest.raises(ValueError, match="cannot go back"):
        casting.choose_targets([])


def test_a_finished_casting_is_closed():
    casting = Casting(spell=spell_in_hand(), caster="alice")
    payment = casting.begin_paying()
    payment.tap_for_mana(source(), [Color.RED])
    payment.pay()
    casting.cast()

    with pytest.raises(ValueError, match="already"):
        casting.cancel()


# -- costs other than mana (CR 118.3, 601.2b, 601.2f) ----------------------


def test_an_additional_mana_cost_is_added_to_the_total():
    """Kicker is an additional cost of mana only (CR 118.8a)."""
    casting = Casting(spell=spell_in_hand(), caster="alice")
    casting.add_additional_cost(ManaCost.parse("{4}"))

    assert casting.total_cost.mana == ManaCost.parse("{4}{R}")


def test_an_additional_cost_carries_its_components_into_the_payment():
    creature = card_state("Grizzly Bears", Zone.BATTLEFIELD, controller="alice")
    casting = Casting(spell=spell_in_hand(), caster="alice")
    casting.add_additional_cost(TotalCost.of(None, sacrifice_cost(creature)))

    payment = casting.determine_cost()

    assert payment.cost == ManaCost.parse("{R}")
    assert payment.components[0].cards == [creature]
    assert payment.components[0].payer == "alice"


def test_an_alternative_cost_replaces_the_printed_mana_cost():
    """CR 118.9: pay this instead of the mana cost."""
    casting = Casting(spell=spell_in_hand(), caster="alice")
    casting.choose_alternative_cost(TotalCost.of(None, pay_life_cost(3)))

    assert casting.total_cost.mana == ManaCost()
    assert casting.base_cost == ManaCost.parse("{R}")  # CR 118.9c: unchanged


def test_only_one_alternative_cost_can_apply():
    """CR 118.9a."""
    casting = Casting(spell=spell_in_hand(), caster="alice")
    casting.choose_alternative_cost(ManaCost())

    with pytest.raises(ValueError, match="only one alternative cost"):
        casting.choose_alternative_cost(ManaCost())


def test_additional_costs_apply_on_top_of_an_alternative_cost():
    """CR 118.9d."""
    casting = Casting(spell=spell_in_hand(), caster="alice")
    casting.choose_alternative_cost(ManaCost.parse("{1}"))
    casting.add_additional_cost(ManaCost.parse("{2}"))
    casting.reduce_cost("{1}")

    assert casting.total_cost.mana == ManaCost.parse("{2}")


def test_a_reduction_does_not_eat_the_coloured_pip():
    """CR 118.7a, on a real card: Ragavan still costs {R} however cheap it gets."""
    casting = Casting(spell=spell_in_hand(), caster="alice")
    casting.reduce_cost("{3}")

    assert casting.total_cost.mana == ManaCost.parse("{R}")


# -- CR 601.2b: modes are announced as the spell is cast -------------------


def modal_spell(name: str = "Kozilek's Command") -> CardState:
    return card_state(name, Zone.HAND)


def test_a_modal_spell_records_the_modes_it_was_cast_with():
    """CR 700.2a: the controller chooses the modes as part of casting."""
    casting = Casting(spell=modal_spell("Abrade"), caster="alice")

    casting.choose_modes([2])

    assert casting.step is CastingStep.MODES
    assert casting.chosen_mode_numbers == [2]
    assert casting.chosen_modes == ["Destroy target artifact."]


def test_a_spell_that_is_not_modal_has_no_modes_to_choose():
    casting = Casting(spell=spell_in_hand(), caster="alice")

    with pytest.raises(ValueError, match="is not a modal spell"):
        casting.choose_modes([1])


def test_too_few_modes_is_refused_at_announcement():
    casting = Casting(spell=modal_spell(), caster="alice")

    with pytest.raises(ValueError, match="too few modes"):
        casting.choose_modes([1])


def test_too_many_modes_is_refused_at_announcement():
    casting = Casting(spell=modal_spell(), caster="alice")

    with pytest.raises(ValueError, match="too many modes"):
        casting.choose_modes([1, 2, 3])


def test_the_same_mode_twice_is_refused_at_announcement():
    """CR 700.2d."""
    casting = Casting(spell=modal_spell(), caster="alice")

    with pytest.raises(ValueError, match="chosen twice"):
        casting.choose_modes([2, 2])


def test_an_unknown_mode_is_refused_at_announcement():
    casting = Casting(spell=modal_spell(), caster="alice")

    with pytest.raises(ValueError, match="there is no mode 9"):
        casting.choose_modes([1, 9])


def test_a_refused_mode_choice_leaves_the_casting_where_it_was():
    """CR 601.6: an announcement that cannot be completed happened at all."""
    casting = Casting(spell=modal_spell(), caster="alice")

    with pytest.raises(ValueError):
        casting.choose_modes([1, 1])

    assert casting.chosen_modes == []
    casting.choose_modes([1, 2])  # still castable, the same way
    assert casting.chosen_mode_numbers == [1, 2]


def test_targets_cannot_be_chosen_before_the_modes_are():
    """CR 601.2b runs before CR 601.2c, and CR 700.2c makes it matter."""
    casting = Casting(spell=modal_spell("Abrade"), caster="alice")
    bears = card_state("Grizzly Bears", Zone.BATTLEFIELD, controller="bob")

    with pytest.raises(ValueError, match="modes must be announced"):
        casting.choose_targets([bears])


def test_targeting_follows_the_chosen_modes():
    """CR 700.2c: only the chosen modes ask for targets."""
    casting = Casting(spell=modal_spell("Cryptic Command"), caster="alice")

    casting.choose_modes([3, 4])  # tap all creatures, draw a card

    assert casting.targeting.max_targets == 0
    with pytest.raises(ValueError, match="too many targets"):
        casting.choose_targets(["bob"])


def test_a_mode_that_targets_accepts_its_own_target():
    casting = Casting(spell=modal_spell("Abrade"), caster="alice")
    bears = card_state("Grizzly Bears", Zone.BATTLEFIELD, controller="bob")

    casting.choose_modes([1])
    casting.choose_targets([bears])

    assert casting.step is CastingStep.TARGETS
    assert casting.targets[0].card_id == bears.id


def test_choose_targets_stamps_from_the_card_state_with_no_game_at_all():
    """`Casting` runs with `game=None` on this pure-announcement path (every
    test above), so the CR 400.7 zone-change stamp `TargetRef.to_card`
    attaches at announcement must come straight off the live `CardState`
    handed to `choose_targets` - never from a `self.game` lookup, which would
    raise `AttributeError` here since there is no game to look anything up
    in. `bears` was never touched by a game either; its own
    `zone_change_stamp` is exactly what a resolving spell would need to
    judge this target legal later (CR 608.2b)."""
    casting = Casting(spell=modal_spell("Abrade"), caster="alice")
    bears = card_state("Grizzly Bears", Zone.BATTLEFIELD, controller="bob")

    casting.choose_modes([1])
    casting.choose_targets([bears])  # must not raise AttributeError

    assert casting.targets[0].zone_change_stamp == bears.zone_change_stamp


def test_the_other_modes_target_is_still_illegal():
    """Abrade's artifact mode cannot be aimed at a creature."""
    casting = Casting(spell=modal_spell("Abrade"), caster="alice")
    bears = card_state("Grizzly Bears", Zone.BATTLEFIELD, controller="bob")

    casting.choose_modes([2])

    with pytest.raises(ValueError, match="needs an artifact"):
        casting.choose_targets([bears])


def test_x_announced_with_the_modes_counts_a_modes_targets():
    """Kozilek's Command exiles "up to X target cards from graveyards"."""
    casting = Casting(spell=modal_spell(), caster="alice")

    casting.choose_modes([3, 4], x_value=1)

    assert casting.x_value == 1
    assert casting.targeting.max_targets == 2  # one creature, one card


def test_x_announced_with_the_modes_survives_cost_determination():
    casting = Casting(spell=modal_spell(), caster="alice")
    casting.choose_modes([2, 3], x_value=2)

    payment = casting.determine_cost()

    assert casting.x_value == 2
    assert payment.cost == ManaCost.parse("{2}{C}{C}")  # {X}{C}{C} with X=2


def test_cost_choices_cannot_be_made_after_targets_are_chosen():
    """CR 601.2b happens before CR 601.2c, not after."""
    casting = Casting(spell=spell_in_hand(), caster="alice")
    casting.choose_targets([])

    with pytest.raises(ValueError, match="cannot go back"):
        casting.add_additional_cost(ManaCost.parse("{1}"))
