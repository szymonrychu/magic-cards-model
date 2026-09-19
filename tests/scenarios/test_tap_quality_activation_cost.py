"""Scenario: an activated ability whose own cost taps N (or X) *chosen*
untapped permanents matching a printed quality - "Tap four untapped Advisors
you control" (Persistent Petitioners), "Tap X untapped artifacts you
control" (Merchant's Dockhand) - as opposed to the bare `{T}` symbol
(CR 107.5's fixed "tap this permanent", no choice involved at all).

`machines/cost.py`'s `_PHRASE_TAP`/`tap_cost` already parse this sentence
into a `TAP`-kind `CostComponent` with a `requirement` and a `required`
count, exactly the way `_PHRASE_SACRIFICE`/`_PHRASE_DISCARD` do for
"sacrifice"/"discard" - and `Casting._printed_additional_costs`
(`machines/casting.py`) already fills such a component from a caller-
supplied `tapping` pool when the *cost to cast a spell* prints this shape
(Swallow Whole's own "Tap an untapped creature you control"). `Game.
activation_cost`/`Game.begin_activating` had the matching pools for
`SACRIFICE`/`DISCARD`/`EXILE` (`sacrificing`/`discarding`/`exiling`), but
none for `TAP` - so an *activated* ability with this shape built a
`CostComponent` with an empty `cards` list and no way for a caller to fill
it: `component.why_not` always refused with "needs N card(s) chosen, 0
given", and the ability could never be activated at all.

Every CR number below was looked up with `mise run rules:find` in the
session that wrote this file:

- **CR 601.2b / CR 602.2b** - costs are chosen as the spell/ability is
  announced, before anything is paid.
- **CR 118.3** - a cost is paid by fulfilling every choice it requires; a
  cost that cannot be fulfilled cannot be paid.
- **CR 107.5** - the tap symbol `{T}` means "Tap this permanent", never a
  choice - the plain-English "Tap `<count>` untapped `<quality>` you
  control" sentence these cards print is a different thing: CR 601.2b's own
  choice of *which* permanents.
- **CR 701.26a** - "To tap a permanent, turn it sideways ... Only untapped
  permanents can be tapped."
- **CR 701.17a** - milling, Persistent Petitioners' own effect once its cost
  is paid.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.triggers import AbilityOnStack
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_persistent_petitioners_taps_four_chosen_advisors_to_pay_its_cost():
    """Four copies of Persistent Petitioners (CR 201.3's "any number of
    cards named Persistent Petitioners" lets a real deck run more than four)
    satisfy "Tap four untapped Advisors you control" among themselves - the
    sentence names no "other", so the activating copy may be one of the
    four chosen.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Persistent Petitioners"] * 4,
        )
        .player("bob", library=["Island"] * 15)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    petitioners = [c for c in scenario.game.battlefield if c.name == "Persistent Petitioners"]
    assert len(petitioners) == 4
    assert all(not p.tapped for p in petitioners)

    ability = scenario.activate(
        petitioners[0], index=1, tapping_for_cost=petitioners, targets=["bob"]
    )
    assert isinstance(ability, AbilityOnStack)
    assert all(p.tapped for p in petitioners), "the cost is paid on activation (CR 602.2b)"

    scenario.pass_until_resolved()

    bob = scenario.player("bob")
    assert len(bob.graveyard) == 12, "CR 701.17a: milling moves cards to the graveyard"
    assert len(bob.library) == 3


def test_merchant_dockhands_x_cost_taps_the_chosen_untapped_artifacts():
    """Merchant's Dockhand (off-pool, modern-legal): "{3}{U}, {T}, Tap X
    untapped artifacts you control: ..." Announcing X=2 requires tapping
    exactly two other untapped artifacts, chosen by the activating player
    (CR 601.2b) rather than fixed by the sentence - proven by tapping two of
    three Mind Stones and asserting the third stays untapped.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Merchant's Dockhand", "Mind Stone", "Mind Stone", "Mind Stone"]
            + ["Island"] * 4,
            library=["Forest", "Mountain"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    dockhand = scenario.find("Merchant's Dockhand", Zone.BATTLEFIELD, "alice")
    stones = [c for c in scenario.game.battlefield if c.name == "Mind Stone"]
    chosen_stones = stones[:2]
    untouched_stone = stones[2]
    sources = scenario.untapped_sources(*(["Island"] * 4))

    ability = scenario.activate(
        dockhand,
        *sources,
        x_value=2,
        tapping_for_cost=chosen_stones,
    )
    assert isinstance(ability, AbilityOnStack)
    assert dockhand.tapped, "the {T} half of the cost taps the source itself"
    assert all(stone.tapped for stone in chosen_stones)
    assert not untouched_stone.tapped, (
        "only the two chosen Mind Stones pay the cost - the third is never touched"
    )
