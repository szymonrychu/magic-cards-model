"""Scenario: "`<source>` deals `<n>` damage to `<phrase1>` and `<m>` damage to
`<phrase2>`" where `<n>` != `<m>` - a single CR 608.2c instruction, split by
`_CLAUSE_SEPARATOR`'s bare "and" into two clauses, that names a *different*
amount for each of its two targets.

Every CR number here was looked up with `mise run rules:find <number>` in the
session that wrote this file:

- **CR 601.2c** - "if the spell uses the word 'target' in multiple places,
  the same object or player can be chosen once for each instance of the
  word 'target'" - Hungry Flames' two "target" phrases are two independent
  requirements, matched to two independently-typed targets.
- **CR 608.2b** - "Illegal targets, if any, won't be affected by parts of a
  resolving spell's effect for which they're illegal. Other parts of the
  effect for which those targets are not illegal may still affect them." -
  each requirement's own amount is paid only to that requirement's own
  target, and only if that target is still legal, independent of the other.
- **CR 608.2c** - "The controller of the spell or ability follows its
  instructions in the order written" - the 3-damage instruction and the
  2-damage instruction are followed as two separate payouts, not merged
  into a single shared amount.

`machines/effects._merge_split_damage_clauses` already handled this shape
when both halves named the identical amount (Way of the Warlord's granted
`[-4]`, `tests/scenarios/test_planeswalker_ability_grants.py`), by paying
every resolved target the one shared amount off `game.resolve_targets`
without needing to know which target came from which requirement. An
unequal pair needs exactly that correspondence, which nothing on
`AbilityOnStack`/`CardState` recorded - so this wave adds `target_amounts`,
one entry per resolved target, classified against each requirement's own
restriction (`TargetRequirement.rejects`) rather than assumed by position,
so the pairing is correct regardless of the order targets were chosen in.

**Hungry Flames** ("{2}{R} Instant - Hungry Flames deals 3 damage to target
creature and 2 damage to target player or planeswalker.") is the off-set
proof: a real Scryfall printing, not Way of the Warlord's own card, and not
in any deck pool this repo tests against, with two independently-typed
mandatory requirements (no "up to one" softening either side) so the
unequal amounts are the only thing this test can be proving.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_hungry_flames_deals_its_own_unequal_amount_to_each_target():
    """The creature takes 3, the player loses 2 life - not 2 and 2, not 3
    and 3, and not the two amounts swapped.

    Ancient Silverback (6/5), not a 2/2: CR 704.5g would put a 2/2 into the
    graveyard the moment 3 damage marks it (state-based actions, run right
    after this resolves), which would prove lethal damage, not that this
    clause marked exactly 3 - Ancient Silverback's own 5 toughness survives
    with the mark still readable, the same choice
    `test_planeswalker_ability_grants.py`'s own split-damage test makes."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Hungry Flames"],
            battlefield=["Mountain", "Mountain", "Mountain"],
        )
        .player("bob", battlefield=["Ancient Silverback"], life=20)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    silverback = scenario.creature("Ancient Silverback", "bob")

    sources = scenario.untapped_sources("Mountain", "Mountain", "Mountain")
    flames = scenario.cast_and_resolve(
        "Hungry Flames", *sources, username="alice", targets=[silverback, "bob"]
    )

    assert flames.zone is Zone.GRAVEYARD
    assert silverback.damage == 3, "the creature takes its own printed amount, not the player's"
    assert scenario.player("bob").life == 18, "the player loses their own printed amount"


def test_hungry_flames_pays_the_creature_even_when_the_player_target_is_reordered():
    """`targets=` reordered to player-then-creature - the pairing is judged by
    which requirement each target actually satisfies (CR 601.2c), not by
    position in the announced list, so the amounts still land correctly."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Hungry Flames"],
            battlefield=["Mountain", "Mountain", "Mountain"],
        )
        .player("bob", battlefield=["Ancient Silverback"], life=20)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    silverback = scenario.creature("Ancient Silverback", "bob")

    sources = scenario.untapped_sources("Mountain", "Mountain", "Mountain")
    flames = scenario.cast_and_resolve(
        "Hungry Flames", *sources, username="alice", targets=["bob", silverback]
    )

    assert flames.zone is Zone.GRAVEYARD
    assert silverback.damage == 3
    assert scenario.player("bob").life == 18
