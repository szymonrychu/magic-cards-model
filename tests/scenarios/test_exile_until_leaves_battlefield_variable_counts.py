"""`_EXILE_UNTIL_THIS_LEAVES_BATTLEFIELD_RE`/
`_parse_exile_until_leaves_battlefield_clause` beyond Static Prison's own
single mandatory target ("exile target nonland permanent an opponent
controls until this enchantment leaves the battlefield" -
`test_exile_until_leaves_the_battlefield.py`).

Real printings with an "up to one" count on the same shape (per the number
sweep):

- **Prayer of Binding**: "When this enchantment enters, exile up to one
  target nonland permanent an opponent controls until this enchantment
  leaves the battlefield. You gain 2 life." Before this fix,
  `_targets_understood(match.group("phrase"))` was not `count_agnostic`, so
  "up to one" (a 0-or-1 requirement, not exactly-one) refused the whole
  match outright - silent, per the sweep.
- **Touch the Spirit Realm**: "When this enchantment enters, exile up to one
  target artifact or creature until this enchantment leaves the
  battlefield." The same shape with no life-gain tail.

Both are read the same way Lagrella's own "any number of other target
creatures" sibling parser (`_parse_exile_targets_until_leaves_then_counters`)
already reads its own count-agnostic phrase: loop over every legal target,
each with its own CR 610.3 departure watch and return.

CR numbers verified this session with `mise run rules:find`:

- **CR 115.6** - "up to one" still requires targets, but zero may be chosen.
- **CR 608.2b** - an illegal target is skipped, not a reason to fail the
  whole spell/ability.
- **CR 610.2/610.3/610.3c** - the delayed-trigger return, and that it
  returns under the owner's control (already proven for Static Prison in
  `test_exile_until_leaves_the_battlefield.py`; not re-derived here).
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone

from .harness import Scenario


def _board(hand_card: str) -> Scenario:
    return (
        Scenario()
        .player("alice", hand=[hand_card], battlefield=["Plains", "Plains", "Plains", "Plains"])
        .player("bob", battlefield=["Grizzly Bears"])
    )


def test_prayer_of_binding_up_to_one_exiles_the_chosen_target_and_gains_life():
    scenario = _board("Prayer of Binding").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    alice = scenario.game.player("alice")
    life_before = alice.life

    sources = scenario.untapped_sources("Plains", "Plains", "Plains", "Plains")
    scenario.choose_trigger_targets("Prayer of Binding", [bears])
    prayer = scenario.cast_and_resolve("Prayer of Binding", *sources)
    scenario.pass_until_resolved()  # the ETB trigger: exile Grizzly Bears, gain 2 life

    assert bears.zone is Zone.EXILE
    assert alice.life == life_before + 2

    scenario.game.destroy(prayer)
    scenario.pass_until_resolved()  # the delayed trigger returns Grizzly Bears

    assert bears.zone is Zone.BATTLEFIELD
    assert scenario.game.controller_of(bears).username == "bob"


def test_prayer_of_binding_up_to_one_may_choose_zero_targets():
    """CR 115.6/107.1c: "up to one" legally chooses nothing at all - the
    trigger still resolves, exiling nothing, and Prayer of Binding's
    controller still gains the life."""
    scenario = _board("Prayer of Binding").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    alice = scenario.game.player("alice")
    life_before = alice.life

    sources = scenario.untapped_sources("Plains", "Plains", "Plains", "Plains")
    scenario.choose_trigger_targets("Prayer of Binding", [])
    scenario.cast_and_resolve("Prayer of Binding", *sources)
    scenario.pass_until_resolved()

    assert bears.zone is Zone.BATTLEFIELD
    assert alice.life == life_before + 2


def test_touch_the_spirit_realm_up_to_one_exiles_and_returns_on_departure():
    scenario = (
        Scenario()
        .player(
            "alice", hand=["Touch the Spirit Realm"], battlefield=["Plains", "Plains", "Plains"]
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")

    sources = scenario.untapped_sources("Plains", "Plains", "Plains")
    scenario.choose_trigger_targets("Touch the Spirit Realm", [bears])
    realm = scenario.cast_and_resolve("Touch the Spirit Realm", *sources)
    scenario.pass_until_resolved()

    assert bears.zone is Zone.EXILE

    scenario.game.sacrifice(realm)
    scenario.pass_until_resolved()

    assert bears.zone is Zone.BATTLEFIELD
    assert scenario.game.controller_of(bears).username == "bob"
