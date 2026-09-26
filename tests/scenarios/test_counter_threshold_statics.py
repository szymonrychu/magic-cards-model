"""SOS's counter-threshold anthem: "As long as there are `<N>` or more
`<kind>` counters on this `<type>`, `<group>` you control get
`<power>/<toughness>`." CR 611.3a's "isn't 'locked in'" own worked example -
the anthem is re-derived on every CR 613.5 computation, present exactly
while the source's own counter count clears the stated threshold, gone the
instant it doesn't (a counter removed mid-turn drops the buff immediately,
no duration and no lingering effect).

- **Comforting Counsel** - "Whenever you gain life, put a growth counter on
  this enchantment. As long as there are five or more growth counters on
  this enchantment, creatures you control get +3/+3."
- **Obscura Ascendancy** (off-pool generality proof) - "As long as there are
  five or more soul counters on this enchantment, Spirits you control get
  +3/+3." - a capitalised *subtype* list (CR 205.3) rather than the bare
  word "creatures", read through the identical `layers._filtered_anthem_
  builder` an ordinary "Other Dragons you control get +1/+1" anthem already
  uses, wrapped in the same threshold gate.

Every CR number below was looked up with `mise run rules:find` (on-disk CR
effective 2026-09-25) in the session that wrote this file:

- **CR 604.2** - a static ability's effects are active exactly as long as
  the source has the ability (here, always) and its own stated condition
  holds.
- **CR 611.3a** - "the effect ... isn't 'locked in'; it applies at any given
  moment to whatever its text indicates" - the reason this is asked fresh
  on every computation rather than fixed once.
- **CR 613.4c** - a static ability's own power/toughness-modifying effect
  lands in sublayer 7c, alongside ordinary counters and other pump effects.
- **CR 122.1** - the counters this file adds directly (`add_counters`) to
  set up each threshold, rather than through the card's own "whenever you
  gain life" trigger (already covered elsewhere as an unrelated mechanic).
- **CR 601.2f, 602.2b** - a cost reduction applied to an activated ability's
  own cost the same way CR 601.2f applies one to a spell's.

This file also carries Diary of Dreams' per-counter activation cost
reduction at the bottom - see that section's own docstring for why it is
bundled here rather than in a file of its own.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.mana import ManaCost
from tests.scenarios.harness import Scenario

COUNSEL = "Comforting Counsel"
ASCENDANCY = "Obscura Ascendancy"


def _computed(scenario, creature):
    return scenario.game.computed_board().of(creature)


def test_counsel_grants_plus_three_plus_three_at_five_growth_counters():
    scenario = (
        Scenario().player("alice", battlefield=[COUNSEL, "Grizzly Bears"]).player("bob").build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    counsel = scenario.find(COUNSEL, Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    counsel.add_counters("growth", 5)

    chars = _computed(scenario, bears)
    assert (chars.power, chars.toughness) == (2 + 3, 2 + 3)


def test_counsel_grants_nothing_below_five_growth_counters():
    scenario = (
        Scenario().player("alice", battlefield=[COUNSEL, "Grizzly Bears"]).player("bob").build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    counsel = scenario.find(COUNSEL, Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    counsel.add_counters("growth", 4)

    chars = _computed(scenario, bears)
    assert (chars.power, chars.toughness) == (2, 2)


def test_counsel_drops_the_anthem_the_instant_a_counter_is_removed():
    """CR 611.3a: not a duration - removing one growth counter below the
    threshold turns the anthem off immediately, mid-turn, no lingering."""
    scenario = (
        Scenario().player("alice", battlefield=[COUNSEL, "Grizzly Bears"]).player("bob").build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    counsel = scenario.find(COUNSEL, Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    counsel.add_counters("growth", 5)
    assert _computed(scenario, bears).power == 5

    counsel.remove_counters("growth", 1)
    assert _computed(scenario, bears).power == 2


def test_counsel_does_not_pump_an_opponents_creature():
    scenario = (
        Scenario()
        .player("alice", battlefield=[COUNSEL])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    counsel = scenario.find(COUNSEL, Zone.BATTLEFIELD, "alice")
    bob_bears = scenario.creature("Grizzly Bears", "bob")
    counsel.add_counters("growth", 5)

    chars = _computed(scenario, bob_bears)
    assert (chars.power, chars.toughness) == (2, 2)


def test_obscura_ascendancy_pumps_spirits_you_control_off_soul_counters():
    """The off-pool generality proof: a capitalised subtype list rather than
    the bare word "creatures", and a non-Spirit creature is left untouched."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[ASCENDANCY, "Supreme Phantom", "Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ascendancy = scenario.find(ASCENDANCY, Zone.BATTLEFIELD, "alice")
    phantom = scenario.creature("Supreme Phantom", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    ascendancy.add_counters("soul", 5)

    phantom_chars = _computed(scenario, phantom)
    bears_chars = _computed(scenario, bears)
    assert (phantom_chars.power, phantom_chars.toughness) == (1 + 3, 3 + 3), (
        "Supreme Phantom is a Spirit"
    )
    assert (bears_chars.power, bears_chars.toughness) == (2, 2), (
        "Grizzly Bears carries no Spirit type"
    )


def test_obscura_ascendancy_grants_nothing_below_five_soul_counters():
    scenario = (
        Scenario()
        .player("alice", battlefield=[ASCENDANCY, "Supreme Phantom"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ascendancy = scenario.find(ASCENDANCY, Zone.BATTLEFIELD, "alice")
    phantom = scenario.creature("Supreme Phantom", "alice")
    ascendancy.add_counters("soul", 4)

    chars = _computed(scenario, phantom)
    assert (chars.power, chars.toughness) == (1, 3)


# --------------------------------------------------------------------------
# A second counter-gated numeric mechanic sharing this file: SOS's Diary of
# Dreams, "{5}, {T}: Draw a card. This ability costs {1} less to activate
# for each page counter on this artifact." CR 601.2f's cost reduction via CR
# 602.2b, read off the ability's own source rather than a board-wide count
# (`abilities.ActivationCostReduction.self_counter_kind`, a third shape
# alongside the pre-existing "for each `<quality>` you control" and the
# equip-only "for each `<X>` ... the creature it targets"). Bundled here
# rather than a separate file because both this and the anthem above are
# "a counter count on the source gates a number", the same relationship
# `docs/engine-coverage.md`'s own wave sections already bundle kindred
# shapes under.
# --------------------------------------------------------------------------

DIARY = "Diary of Dreams"


def test_diary_of_dreams_costs_one_less_per_page_counter():
    scenario = (
        Scenario()
        .player("alice", battlefield=[DIARY, "Island", "Island"], library=["Forest"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    diary = scenario.find(DIARY, Zone.BATTLEFIELD, "alice")
    diary.add_counters("page", 3)
    alice = scenario.player("alice")
    cards_before = len(alice.hand)
    islands = scenario.untapped_sources("Island", "Island")

    # Printed {5} minus three page counters is {2} - two Islands pay it.
    scenario.activate(diary, *islands)
    scenario.resolve_top()

    assert len(alice.hand) == cards_before + 1
    assert diary.tapped


def test_diary_of_dreams_with_no_page_counters_still_costs_the_full_five():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[DIARY, "Island", "Island", "Island", "Island", "Island"],
            library=["Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    diary = scenario.find(DIARY, Zone.BATTLEFIELD, "alice")
    alice = scenario.player("alice")
    cards_before = len(alice.hand)
    islands = scenario.untapped_sources("Island", "Island", "Island", "Island", "Island")

    scenario.activate(diary, *islands)
    scenario.resolve_top()

    assert len(alice.hand) == cards_before + 1


def test_diary_of_dreams_reduced_cost_is_still_not_free_below_it():
    """Three page counters reduce {5} to {2}, not further - CR 601.2f floors
    a cost reduction at {0} per symbol, never below it. With only one Island,
    the (still real) {2} generic is unpayable, and CR 118.6 says an
    unaffordable activation is still a legal one to *attempt* (never
    reported as an activation restriction by `why_cannot_activate`) - the
    actual payment attempt is what refuses it."""
    scenario = Scenario().player("alice", battlefield=[DIARY, "Island"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    diary = scenario.find(DIARY, Zone.BATTLEFIELD, "alice")
    diary.add_counters("page", 3)
    assert scenario.game.activation_cost(diary, 0).mana == ManaCost.parse("{2}")

    (island,) = scenario.untapped_sources("Island")
    with pytest.raises(ValueError):
        scenario.activate(diary, island)
