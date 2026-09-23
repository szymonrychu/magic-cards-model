"""Scenario: a general "mill N cards. You may put [up to K] `<description>`
cards from among the milled cards into your hand[. You gain M life.]" reader
(`_mill_then_may_take_from_milled_runner`, `_MILL_THEN_MAY_TAKE_FROM_MILLED_RE`
- CR 701.17a's mill, CR 400.7's "from among the milled cards" anaphora),
widened to read an "and/or"-joined quality list.

Smuggler's Surprise's own first Spree mode - "Mill four cards. You may put
up to two creature and/or land cards from among the milled cards into your
hand." - names a *compound* quality: two card types joined by "and/or", which
the reader's old `(?P<group>[a-z]+)` capture (a single bare word) could never
match, so the whole mode fell through unread. Widening the capture and
normalizing "and/or" to "or" for `_parse_card_group_alternatives` (the same
normalization `_parse_mill_that_many_then_take_from_among_them` already uses
for Nashi, Searcher in the Dark's own "legendary and/or enchantment" list) is
all that was needed once the reader itself had a path from a *mode's* own
text at all - `_parse_mill_then_may_take_from_milled`/`_ability` were
reachable only from the whole-card dispatchers before this file, never from
`parse_mixed_effect_for_spell`/`parse_mixed_effect`, which is all
`parse_mode_effect` ever calls.

Every CR number below was looked up with `mise run rules:find` in the
session that wrote this file:

- **CR 701.17a** - "To mill a card, a player puts the top card of their
  library into their graveyard."
- **CR 400.7** - "from among the milled cards" is a narrower pool than "from
  your graveyard": a card already there before the mill is not a candidate.
- **CR 608.2d** - "you may put up to two ... cards" is optional; declining,
  or having none of the named quality among the milled cards, is a legal
  answer that moves nothing.
- **CR 119.3** - the trailing "you gain N life" (Seed of Hope's own third
  sentence).
- **CR 702.172a** - Spree: "Choose one or more modes. As an additional cost
  to cast this spell, pay the costs associated with those modes."

Seed of Hope (off-pool, confirmed with `scripts/add_card.py`, Modern- and
Pioneer-legal) is the proof this reads generally: a single-word quality
("permanent"), a fixed count of one rather than "up to two", and a trailing
life gain Smuggler's Surprise's own mode does not print at all.
"""

from magic_cards_model.machines import Step
from tests.scenarios.harness import Scenario


def test_smugglers_surprise_mode_one_alone_takes_a_creature_and_a_land_from_the_mill():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Smuggler's Surprise"],
            battlefield=["Forest"] * 3,
            library=["Mountain", "Grizzly Bears", "Lightning Bolt", "Opt"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources(*(["Forest"] * 3))
    alice = scenario.player("alice")
    mountain = next(state for state in alice.library if state.name == "Mountain")
    bears = next(state for state in alice.library if state.name == "Grizzly Bears")
    scenario.will_choose_cards(mountain, bears, username="alice", source="Smuggler's Surprise")

    casting = scenario.cast("Smuggler's Surprise")
    casting.choose_modes([1])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *sources)
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert len(alice.library) == 0, "CR 701.17a: all four milled"
    assert mountain in alice.hand, "a land qualifies for the and/or quality"
    assert bears in alice.hand, "a creature qualifies for the and/or quality"
    milled_leftovers = {
        state.name for state in alice.graveyard if state.name != "Smuggler's Surprise"
    }
    assert milled_leftovers == {"Lightning Bolt", "Opt"}, (
        "the two non-creature, non-land milled cards stayed behind"
    )


def test_smugglers_surprise_modes_one_and_three_together_still_mill_and_resolve():
    """Modes 1 and 3 chosen together (CR 700.2a): mode 1's own mill-and-take
    runs alongside mode 3's own power-filtered group grant, which affects no
    one here (nothing alice controls has power 4 or greater) - a legal "no
    candidates" resolution (CR 608.2d), not a notice.
    `test_group_grant_power_filter.py` is the file that proves the grant
    itself does something when there is a candidate.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Smuggler's Surprise"],
            battlefield=["Forest"] * 4,
            library=["Mountain", "Grizzly Bears", "Lightning Bolt", "Opt"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources(*(["Forest"] * 4))
    alice = scenario.player("alice")
    scenario.will_choose_cards(username="alice", source="Smuggler's Surprise")

    casting = scenario.cast("Smuggler's Surprise")
    casting.choose_modes([1, 3])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *sources)
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert len(alice.library) == 0
    milled_and_spell = len(alice.graveyard)
    assert milled_and_spell == 5, (
        "four milled cards plus the resolved instant itself; nothing taken from the mill "
        "(the choice was declined)"
    )
    assert not scenario.game.mode_notices, "both chosen modes read"


def test_seed_of_hope_takes_a_permanent_card_and_gains_life():
    """Off-pool, non-modal proof: a single "permanent" quality (not
    Smuggler's Surprise's own "creature and/or land"), a fixed count of one
    rather than "up to two", and a trailing "you gain 2 life" sentence the
    reader's own optional `life` group has to consume too - `_MILL_THEN_MAY_
    TAKE_FROM_MILLED_RE` has to match the whole three-sentence text, not
    only the first two, or the life gain is silently lost."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Seed of Hope"],
            battlefield=["Forest"],
            library=["Grizzly Bears", "Lightning Bolt"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    bears = next(state for state in alice.library if state.name == "Grizzly Bears")
    scenario.will_choose_cards(bears, username="alice", source="Seed of Hope")
    life_before = alice.life
    (forest,) = scenario.untapped_sources("Forest")

    scenario.cast_and_resolve("Seed of Hope", forest)

    assert bears in alice.hand
    graveyard_leftovers = {state.name for state in alice.graveyard if state.name != "Seed of Hope"}
    assert graveyard_leftovers == {"Lightning Bolt"}
    assert alice.life == life_before + 2
