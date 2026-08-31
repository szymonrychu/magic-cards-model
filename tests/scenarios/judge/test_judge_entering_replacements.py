"""Judge scenario: two lands entering together, each with its own replacement.

From DDR#969 "Lakeside Shack + Breeding Pool". Amy is at 14 life and puts both
lands onto the battlefield at once with Kamahl's Druidic Vow, then pays 2 life
for Breeding Pool. Does Lakeside Shack - "This land enters tapped unless a
player has 13 or less life" - see 14 or 12?

It sees 14, and enters tapped. The reason is the *scope* of CR 616.1 rather
than any ordering rule:

- **CR 614.1c** - "Effects that read '[This permanent] enters with ...,' 'As
  [this permanent] enters ...,' or '[This permanent] enters as ...' are
  replacement effects", and **CR 614.1d** covers the plain "[This permanent]
  enters ..." wording. Both lands' text is one of these, so neither uses the
  stack; both apply as the lands are entering.
- **CR 614.12a** - "If a replacement effect that modifies how a permanent
  enters the battlefield requires a choice, that choice is made before the
  permanent enters the battlefield." Breeding Pool's "you may pay 2 life" is
  that choice.
- **CR 616.1** - the choose-one-then-recheck loop applies only when two or more
  effects "are attempting to modify the way an event affects **an object or
  player**", singular. Here each effect modifies how the event affects *its
  own* land, so there is no ordering to choose: both apply at once, and
  Lakeside Shack's life check is made against the life total before Breeding
  Pool's payment.

The engine models Breeding Pool exactly (both branches of its choice). It does
not model Lakeside Shack's conditional "enters tapped unless a player has 13 or
less life" at all - the land enters untapped at every life total - so the
episode's actual question is `xfail`.

Every CR number in this file was verified with `knowledge_search(q="...",
type="rules")` in the session that wrote it: CR 119.3, CR 614.1c, CR 614.1d,
CR 614.12, CR 614.12a, CR 616.1.
"""

import pytest

from magic_cards_model.machines import Step
from tests.scenarios.harness import Scenario


def board(life: int = 14) -> Scenario:
    return (
        Scenario()
        .player("alice", life=life, hand=["Breeding Pool", "Lakeside Shack"])
        .player("bob", life=20)
    )


def test_breeding_pool_pays_two_life_and_enters_untapped():
    """CR 614.1c's "As this land enters, you may pay 2 life", taken.

    The choice is made before the land is on the battlefield (CR 614.12a), and
    paying it is what stops the "it enters tapped" half.
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_pay_the_life(True)

    pool = scenario.play_land("Breeding Pool")

    assert not pool.tapped
    assert scenario.player("alice").life == 12


def test_declining_the_payment_taps_breeding_pool_instead():
    """The other branch of the same replacement: "If you don't, it enters
    tapped."

    Both branches matter to the episode, because the whole question is what
    Amy's life total is at the moment Lakeside Shack looks at it - which is
    only interesting if paying really does move it.
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_pay_the_life(False)

    pool = scenario.play_land("Breeding Pool")

    assert pool.tapped
    assert scenario.player("alice").life == 14


@pytest.mark.xfail(
    reason=(
        "Lakeside Shack's 'This land enters tapped unless a player has 13 or "
        "less life' is not modelled: nothing compiles it into a replacement "
        "effect, so the land enters untapped at 14 life and at 10 life alike. "
        "Without it there is nothing for DDR#969's simultaneous-entry question "
        "to be about."
    ),
    strict=True,
)
def test_lakeside_shack_enters_tapped_when_nobody_is_low_enough():
    """CR 614.1d, on its own, before any second land is involved.

    At 14 and 20 life no player has 13 or less, so the land enters tapped. This
    is the plain case; the episode's Kamahl's Druidic Vow board is a harder one
    the engine cannot reach until this works.
    """
    scenario = board(life=14).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    shack = scenario.play_land("Lakeside Shack")

    assert shack.tapped


@pytest.mark.xfail(
    reason=(
        "Same gap, stated as the episode's own question: Lakeside Shack has no "
        "replacement effect, so it cannot be shown reading the life total from "
        "before Breeding Pool's payment. Recorded separately because it is the "
        "ruling, not the missing card behaviour."
    ),
    strict=True,
)
def test_the_shack_reads_the_life_total_from_before_the_pools_payment():
    """DDR#969's answer: both replacements apply at once (CR 616.1 does not
    engage), so 14 is what Lakeside Shack sees even though Amy ends on 12.

    Driven here as two separate entries rather than one simultaneous one - the
    engine has no way to put two permanents onto the battlefield as a single
    event - which makes this test *weaker* than the episode, and it still
    fails.
    """
    scenario = board(life=14).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_pay_the_life(True)

    shack = scenario.play_land("Lakeside Shack")
    assert scenario.player("alice").life == 14
    assert shack.tapped
