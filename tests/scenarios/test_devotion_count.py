"""CR 700.5's devotion, read as a resolving trigger's magnitude -
`_devotion_count` in `machines/effects.py`, consumed by Gray Merchant of
Asphodel's own "each opponent loses X life, where X is your devotion to
black. You gain life equal to the life lost this way."

Every CR number below was looked up with `knowledge_search(q="...",
type="rules")` in the session that wrote this file:

- **CR 700.5** - "A player's devotion to [color] is equal to the number of
  mana symbols of that color among the mana costs of permanents that player
  controls."
- **CR 107.4e** - "A hybrid mana symbol is also a colored mana symbol" of
  each color it names, so a `{B/R}` pip counts toward black devotion the
  same as a plain `{B}`.
- **CR 119.3** - losing life and gaining life, what the drain actually does
  once the magnitude is known.

`ManaSymbol.colors` (`models/mana.py`) already carries every symbol kind's
colors uniformly, so `_devotion_count` reads that field directly rather than
special-casing hybrid mana - Footlight Fiend's `{B/R}` is the hybrid corner
case below.
"""

from magic_cards_model.machines import Step
from tests.scenarios.harness import Scenario


def test_gray_merchant_drains_life_equal_to_its_controllers_devotion_to_black():
    """Gray Merchant itself ({3}{B}{B}, two black pips) plus Footlight Fiend
    ({B/R}, one hybrid black pip) is a devotion of three - Grizzly Bears
    ({1}{G}) contributes nothing, proving the color qualifier is actually
    checked and not just "how many permanents"."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Gray Merchant of Asphodel"],
            battlefield=["Swamp"] * 5 + ["Footlight Fiend", "Grizzly Bears"],
            life=20,
        )
        .player("bob", life=20)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources(*["Swamp"] * 5)

    scenario.cast_and_resolve("Gray Merchant of Asphodel", *sources)
    scenario.pass_until_resolved()

    assert scenario.player("bob").life == 17
    assert scenario.player("alice").life == 23


def test_the_merchant_counts_its_own_mana_cost_toward_its_own_devotion():
    """CR 700.5 counts "permanents that player controls" - by the time this
    ETB trigger asks, Gray Merchant is already one of them, so its own two
    black pips ({3}{B}{B}) are the floor even with nothing else black on the
    board. A "genuinely zero" devotion is not reachable through Gray
    Merchant's own trigger for exactly this reason."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Gray Merchant of Asphodel"],
            battlefield=["Swamp"] * 5,
            life=20,
        )
        .player("bob", life=20)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources(*["Swamp"] * 5)

    scenario.cast_and_resolve("Gray Merchant of Asphodel", *sources)
    scenario.pass_until_resolved()

    assert scenario.player("bob").life == 18
    assert scenario.player("alice").life == 22


def test_devotion_only_counts_permanents_the_controller_controls():
    """Bob's own black permanents do not count toward alice's devotion (CR
    700.5's "permanents that player controls")."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Gray Merchant of Asphodel"],
            battlefield=["Swamp"] * 5,
            life=20,
        )
        .player("bob", battlefield=["Footlight Fiend"], life=20)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources(*["Swamp"] * 5)

    scenario.cast_and_resolve("Gray Merchant of Asphodel", *sources)
    scenario.pass_until_resolved()

    # Only Gray Merchant's own two black pips count; bob's Footlight Fiend is
    # his, not alice's.
    assert scenario.player("bob").life == 18
    assert scenario.player("alice").life == 22
