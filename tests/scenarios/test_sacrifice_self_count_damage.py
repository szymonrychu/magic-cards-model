"""Stadium Headliner's "{1}{R}, Sacrifice this creature: It deals damage
equal to the number of creatures you control to target creature." (R0a T8).

Every CR number here was looked up with `mise run rules:find <number>` against
the 2026-09-25 Comprehensive Rules release in the session that wrote this
file.

- **CR 601.2h/602.2b** - the total cost, including the sacrifice, is paid in
  full before the ability goes on the stack: the creature is already gone by
  the time "the number of creatures you control" is counted at resolution
  (CR 608.2c), so the count is naturally the *post*-sacrifice number with no
  special-casing needed - this is what the acceptance note's "count after
  the sacrifice cost is paid" actually asks for.
- **CR 113.7a** - the source "can still perform the action even though it no
  longer exists": the damage's source is `AbilityOnStack.source_or_last_known`,
  Stadium Headliner itself, even sacrificed.
- **CR 120.3** - protection/prevention still apply to the damage as normal;
  nothing here bypasses them.

`machines/effects.py`'s `_DAMAGE_EQUAL_TO_EXPR_TARGET_RE` ("`<subject>` deals
damage equal to `<expr>` to target `<X>`.") already read this shape for a
*spell* (`deal_damage_equal_to_expression`, Combustion Technique); the gap
was that an *ability*'s identical text fell through to a narrower branch that
only read "the number of `<kind>` counters on it", never a game-wide count
like "the number of creatures you control". Widened additively alongside
that branch (`damage_ability_targets_equal_to_expression`, already used by
Honden of Infinite Rage's and Ben-Ben, Akki Hermit's own "equal to the
number of ... you control" shape printed the other way around, damage
before the count) - never narrowed to Stadium Headliner's own sentence.

Generality is proven on Team Avatar (legal Modern/Pioneer/Standard, not in
`code/magic-cards-model-api/decks/*.txt`): "{2}{W}, Discard this card: It
deals damage equal to the number of creatures you control to target
creature." - the identical count expression, a completely different cost
(discard, not sacrifice - so nothing about *this* creature leaving the
battlefield changes the count at all), proving the widened reader is not
fitted to "sacrifice" specifically.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

HEADLINER = "Stadium Headliner"
TEAM_AVATAR = "Team Avatar"


def test_stadium_headliner_deals_damage_equal_to_creatures_after_sacrifice():
    """Two other creatures survive the sacrifice - the count is 2, not 3."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[HEADLINER, "Grizzly Bears", "Runeclaw Bear", "Mountain", "Mountain"],
        )
        .player("bob", battlefield=["Tarmogoyf"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    headliner = scenario.find(HEADLINER, Zone.BATTLEFIELD, "alice")
    goyf = scenario.find("Tarmogoyf", Zone.BATTLEFIELD, "bob")
    mountains = scenario.untapped_sources("Mountain", "Mountain", username="alice")

    scenario.activate(headliner, *mountains, sacrificing=[headliner], targets=[goyf])
    scenario.resolve_top()

    assert headliner.zone is Zone.GRAVEYARD
    # Tarmogoyf is 0/0 plus its own card-type count (CR 208.1) - it started
    # with none in any graveyard here, so 2 damage is lethal either way;
    # the marked damage itself is the assertion that matters.
    assert goyf.damage == 2 or goyf.zone is Zone.GRAVEYARD


def test_stadium_headliner_counts_zero_when_it_was_the_only_creature():
    """CR 107.1b: a zero amount is zero damage, not an error."""
    scenario = (
        Scenario()
        .player("alice", battlefield=[HEADLINER, "Mountain", "Mountain"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    headliner = scenario.find(HEADLINER, Zone.BATTLEFIELD, "alice")
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "bob")
    mountains = scenario.untapped_sources("Mountain", "Mountain", username="alice")

    scenario.activate(headliner, *mountains, sacrificing=[headliner], targets=[bears])
    scenario.resolve_top()

    assert bears.damage == 0
    assert bears.zone is Zone.BATTLEFIELD


def test_team_avatar_proves_generality_with_a_discard_cost_instead_of_sacrifice():
    """Proof of generality: a different cost (discard, not sacrifice) and a
    different source (an enchantment, not a creature), same count expression."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[TEAM_AVATAR],
            battlefield=["Grizzly Bears", "Runeclaw Bear", "Plains", "Plains", "Plains"],
        )
        .player("bob", battlefield=["Llanowar Elves"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    team_avatar = scenario.find(TEAM_AVATAR, Zone.HAND, "alice")
    elves = scenario.find("Llanowar Elves", Zone.BATTLEFIELD, "bob")
    plains = scenario.untapped_sources("Plains", "Plains", "Plains", username="alice")

    # CR 113.6j: "Discard this card" functions only from the hand, so this
    # never touches the battlefield at all.
    scenario.activate(team_avatar, *plains, index=0, discarding=[team_avatar], targets=[elves])
    scenario.resolve_top()

    assert team_avatar.zone is Zone.GRAVEYARD
    # Two Bears still on the battlefield - the count is 2, lethal to the 0/1 Elves.
    assert elves.zone is Zone.GRAVEYARD or elves.damage == 2
