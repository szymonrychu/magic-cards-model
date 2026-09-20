"""FRA stream S8b: "return target `<X>` card with mana value N or less from
your graveyard to the battlefield, where N is `<expr>`." - CR 107.3c's own
"where X is" definition, printed *after* the destination it modifies rather
than immediately after "mana value X or less"
(`_RETURN_FROM_YOUR_GRAVEYARD_TO_BATTLEFIELD_RE` in `machines/effects.py`).

Every CR number below was looked up with `mise run rules:find` in the
session that wrote this file.

- **CR 107.3c** - "Some effects state a value for X (or another variable)
  that applies to a spell or ability. ... If the variable is defined by the
  spell or ability's own text, that definition applies." Nothing in the rule
  requires the definition to sit immediately after the comparison it
  defines.
- **CR 207.2c** - an ability word ("Healing Tears") is unofficial, has no
  rules meaning of its own, and groups abilities that share a common theme -
  it is not part of the triggered ability's own condition or effect text.
- **CR 603.10a** - a leaves-the-battlefield-adjacent reanimation still reads
  the graveyard as it is when the ability resolves (no LKI needed here: the
  card stays in the graveyard, visible, until this ability itself moves it).

Celestine, the Living Saint's own "Healing Tears" ability is the reported
card: "At the beginning of your end step, return target creature card with
mana value X or less from your graveyard to the battlefield, where X is the
amount of life you gained this turn." `_RETURN_FROM_YOUR_GRAVEYARD_TO_
BATTLEFIELD_RE` already read a *fixed* "mana value N or less" (Unearth) and
`_SEARCH_MV_LTE_COUNT_RE` already read a board-count "where X is ..." bound
for a search; this is the first card in the pool whose *targeted*
graveyard-to-battlefield return carries one, and it is also the first where
the "where X is" clause sits after the destination rather than right next
to the comparison it defines - `machines/targeting.profile_for_text` already
read that shape correctly (verified directly against it before this file
existed), so the actual gap was only the effects.py regex's own end-of-line
anchor ending the match before it ever reached that far.

Germinate Recruits (real, non-FRA, non-pool) is the off-set proof for the
"amount of life gained this turn" expression itself - a spell rather than a
triggered ability, and a fixed count-of-permanents-you-control effect rather
than a search or a return, proving `_AMOUNT_OF_LIFE_GAINED_THIS_TURN_RE` is
one shared reader (`count_expression`) rather than a table entry re-read per
card; that card's own test already exists elsewhere; this file's own proof
is the regex/phrase widening itself, exercised on the one real card that
needs it.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_celestine_returns_a_creature_bounded_by_life_gained_this_turn():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Celestine, the Living Saint"],
            graveyard=["Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")
    assert bears.mana_value == 2

    alice.gain_life(2)
    while scenario.step is not Step.END_STEP:
        scenario.advance()
    scenario.will_choose_targets(bears, username="alice")
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert bears.zone is Zone.BATTLEFIELD
    assert bears.controller == "alice"


def test_celestine_offers_no_legal_target_below_the_life_gained_this_turn():
    """Gaining only 1 life leaves Grizzly Bears (mana value 2) with no legal
    target to name at all (CR 601.2c/603.3d: a mandatory target with nothing
    that qualifies never goes on the stack), so the graveyard is untouched."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Celestine, the Living Saint"],
            graveyard=["Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")

    alice.gain_life(1)
    while scenario.step is not Step.END_STEP:
        scenario.advance()
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == []
    assert bears.zone is Zone.GRAVEYARD
