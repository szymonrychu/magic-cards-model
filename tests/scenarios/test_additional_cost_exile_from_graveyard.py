""" "As an additional cost to cast this spell, exile N cards from your
graveyard." (CR 118.8a), read generically off the printed sentence.

Read whole in this session with `mise run rules:find 118.8a`:

- **CR 118.8a** - "Any number of additional costs may be applied to a spell
  as it's being cast or to an ability as it's being activated. The
  controller of the spell or ability announces their intentions to pay any
  or all of those costs as described in rule 601.2b."

Abhorrent Oculus (Bloomburrow, Modern and Pioneer legal) is the required
proof: "As an additional cost to cast this spell, exile six cards from your
graveyard." The reader is not new work of this task's own - `machines/
cost.py`'s `_PHRASE_EXILE`/`cost_component_for_phrase`, reached through
`additional_cost_phrases`, already turns "exile `<count>` cards from your
`<zone>`" into a payable `CostComponent` for any count and any zone (Necropolis
Fiend's activation-side "Exile X cards from your graveyard", Seasoned
Pyromancer's "Exile this card from your graveyard", Force of Will's "Exile a
blue card from your hand" are the same reader, already proven on those
printings elsewhere in this suite) - so this file is corner cases on the
required card rather than a second-printing proof of a reader this task
widened, per this task's own note that a shared reader it does not touch
needs no fresh genericity proof.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.casting import keyword_cast_options
from magic_cards_model.machines.cost import additional_cost_phrases
from magic_cards_model.models import Zone
from magic_cards_model.models.mana import ManaCost
from tests.cards import card
from tests.scenarios.harness import Scenario

OCULUS = "Abhorrent Oculus"


def board(graveyard_count: int, *, hand_extra: tuple[str, ...] = ()) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=[OCULUS, *hand_extra],
            battlefield=["Island", "Island", "Island"],
            graveyard=["Mountain"] * graveyard_count,
            library=["Island"] * 10,
        )
        .player("bob", library=["Island"] * 6)
        .build()
    )


def test_the_sentence_is_read_as_an_additional_cost_phrase():
    (phrase,) = additional_cost_phrases(card(OCULUS))
    assert phrase == "exile six cards from your graveyard"


def test_abhorrent_oculus_is_no_longer_an_ignored_targeting_gap():
    """The keyword report side of the sweep: Flying is executed the ordinary
    way, and the additional cost is not a keyword line at all - nothing here
    should be reported understood=False."""
    from magic_cards_model.machines.targeting import profile_for_text

    profile = profile_for_text(card(OCULUS).oracle_text or "")
    assert profile.understood


def test_paying_the_additional_cost_exiles_six_cards_and_the_spell_reaches_the_stack():
    scenario = board(6)
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    six = list(alice.graveyard)

    casting = scenario.cast(OCULUS, exiling=six)
    assert casting.total_cost.mana == ManaCost.parse("{2}{U}")
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Island", "Island", "Island"))
    oculus = scenario.put_on_stack(casting)

    assert oculus.zone is Zone.STACK
    assert alice.graveyard == []
    exiled = scenario.game.exile
    assert {state.id for state in six} <= {state.id for state in exiled}


def test_a_graveyard_with_fewer_than_six_cards_cannot_pay_the_cost():
    """CR 118.3: a cost that cannot be paid in full is not paid for less -
    the same fail-closed shape `test_collect_evidence.py`'s own CR 701.59b
    refusal takes for a different exile-from-graveyard threshold."""
    scenario = board(5)
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    five = list(alice.graveyard)

    casting = scenario.cast(OCULUS, exiling=five)
    payment = casting.begin_paying()

    with pytest.raises(ValueError):
        scenario.pay_with(payment, *scenario.untapped_sources("Island", "Island", "Island"))


def test_choosing_fewer_than_six_of_a_larger_graveyard_is_refused():
    """A caster with eight cards in the graveyard still has to choose all
    six the cost asks for - CR 118.8a's additional cost is a fixed count,
    not "at least six"."""
    scenario = board(8)
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    only_four = list(alice.graveyard)[:4]

    casting = scenario.cast(OCULUS, exiling=only_four)
    payment = casting.begin_paying()

    with pytest.raises(ValueError):
        scenario.pay_with(payment, *scenario.untapped_sources("Island", "Island", "Island"))


def test_a_card_not_in_the_graveyard_cannot_be_exiled_for_the_cost():
    """A card named from the wrong zone (here, still in hand) is refused
    rather than silently accepted - CR 601.2h only spends what CR 601.2b
    actually chose from the named zone."""
    scenario = board(6, hand_extra=("Lightning Bolt",))
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    five_from_graveyard = list(alice.graveyard)[:5]
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "alice")

    casting = scenario.cast(OCULUS, exiling=[*five_from_graveyard, bolt])
    payment = casting.begin_paying()

    with pytest.raises(ValueError):
        scenario.pay_with(payment, *scenario.untapped_sources("Island", "Island", "Island"))


def test_the_mana_cost_is_unaffected_by_the_additional_cost():
    """CR 118.8a stacks an additional cost on top of the mana cost; it never
    replaces or reduces it (that is CR 601.2f's separate business, Emrakul's
    and Hollow One's own template, not this one)."""
    scenario = board(6)
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    six = list(alice.graveyard)

    casting = scenario.cast(OCULUS, exiling=six)

    assert casting.total_cost.mana == ManaCost.parse("{2}{U}")


def test_the_option_is_not_offered_as_an_alternative_or_keyword_cast():
    """This is a plain additional cost, not a `KeywordCastOption` - Abhorrent
    Oculus is always cast from hand for its mana cost plus the exile, never
    with a `use_keyword` alternative the way bestow or spectacle are."""
    assert keyword_cast_options(card(OCULUS)) == []


def test_no_graveyard_at_all_refuses_the_cast_outright():
    scenario = board(0)
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast(OCULUS, exiling=[])
    payment = casting.begin_paying()

    with pytest.raises(ValueError):
        scenario.pay_with(payment, *scenario.untapped_sources("Island", "Island", "Island"))
