"""Scenario: a counterspell whose legal targets are bounded by mana value.

Two shapes, both a restriction on the *target* rather than on what the spell
does when it resolves, so both are settled at announcement (CR 601.2c: "the
player announces their choice of an appropriate object or player for each
target the spell requires") and rechecked on resolution (CR 608.2b).

- **Spell Snare** - "Counter target spell with mana value 2." A fixed number
  (CR 202.3: "the mana value of an object is a number equal to the total
  amount of mana in its mana cost, regardless of color").
- **Drown in the Loch** - "Counter target spell with mana value less than or
  equal to the number of cards in its controller's graveyard." The same
  restriction with the bound *computed* off the game state instead of printed:
  CR 404.1's discard pile, counted right now. It is knowable at CR 601.2c, so
  unlike Prismatic Ending's converge count (which is not fixed until CR 601.2h
  pays the cost, after targets are announced) it genuinely restricts what may
  be targeted.

Every CR number here was looked up with `knowledge_search(q="...",
type="rules")` in the session that wrote this file: CR 115.1 (targets are
declared as part of putting the spell on the stack), CR 601.2c, CR 601.2h,
CR 608.2b, CR 202.3, CR 404.1, CR 404.2, CR 108.4a.

- **Spellstutter Sprite** - off-pool: "counter target spell with mana value X
  or less, where X is the number of Faeries you control." A triggered
  ability, and the bound is defined by the text (CR 107.3c), counted for the
  ability's controller at CR 603.3d's announcement and again at CR 608.2b.

Both halves are covered: the restriction (`machines/targeting.py`) and the
counter itself (CR 701.6a, `machines/effects.py`'s counterspell predicate,
which accepts exactly the comparisons the targeting reader enforces).
CR 107.3c, 603.3d, 701.6a and 117.3b were looked up with `mise run rules:find`
in the session that added the resolution tests.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone

from .harness import Scenario


def _snare_board(graveyard: list[str] | None = None) -> Scenario:
    """Bob is the active player casting creatures in his own main phase
    (CR 117.1a); alice holds the counterspells and answers at instant speed."""
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "bob",
            hand=["Grizzly Bears", "Hill Giant"],
            battlefield=["Forest", "Forest", "Forest", "Mountain"],
            graveyard=graveyard,
        )
        .player(
            "alice",
            hand=["Spell Snare", "Drown in the Loch"],
            battlefield=["Island", "Island", "Swamp"],
        )
    )


# -- Spell Snare: a printed number ------------------------------------------


def test_spell_snare_accepts_a_mana_value_2_spell():
    """CR 202.3: Grizzly Bears' {1}{G} is a mana value of exactly 2."""
    scenario = _snare_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    forests = scenario.untapped_sources("Forest", "Forest", username="bob")
    bears = scenario.cast_onto_stack("Grizzly Bears", *forests, username="bob")
    assert bears.zone is Zone.STACK
    scenario.pass_priority("bob")

    (island,) = scenario.untapped_sources("Island", username="alice")
    snare = scenario.cast_onto_stack("Spell Snare", island, username="alice", targets=[bears])

    assert snare.zone is Zone.STACK


def test_spell_snare_refuses_a_mana_value_3_spell_at_announcement():
    """Hill Giant is {3}{R}, mana value 4 - not 2, so CR 601.2c refuses it."""
    scenario = _snare_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    sources = scenario.untapped_sources("Forest", "Forest", "Forest", "Mountain", username="bob")
    giant = scenario.cast_onto_stack("Hill Giant", *sources, username="bob")
    scenario.pass_priority("bob")

    with pytest.raises(ValueError, match="mana value"):
        scenario.cast("Spell Snare", username="alice", targets=[giant])


# -- Drown in the Loch: a bound computed from the graveyard ------------------


def test_drown_in_the_loch_refuses_a_spell_the_graveyard_cannot_cover():
    """ "mana value less than or equal to the number of cards in its
    controller's graveyard" - bob's graveyard holds one card, so a mana value
    2 spell is out of reach and the announcement is refused (CR 601.2c).

    "Its controller" is the *target's* controller, not the caster's: CR 108.4a
    only redirects to the owner for a card with no controller at all, and a
    spell on the stack has one.
    """
    scenario = _snare_board(graveyard=["Lightning Bolt"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    assert len(scenario.player("bob").graveyard) == 1

    forests = scenario.untapped_sources("Forest", "Forest", username="bob")
    bears = scenario.cast_onto_stack("Grizzly Bears", *forests, username="bob")
    scenario.pass_priority("bob")

    casting = scenario.cast("Drown in the Loch", username="alice")
    casting.choose_modes([1])
    with pytest.raises(ValueError, match="mana value"):
        casting.choose_targets([bears])


def test_drown_in_the_loch_accepts_a_spell_the_graveyard_covers():
    """Two cards in bob's graveyard is exactly enough for a mana value 2 spell."""
    scenario = _snare_board(graveyard=["Lightning Bolt", "Grizzly Bears"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    assert len(scenario.player("bob").graveyard) == 2

    forests = scenario.untapped_sources("Forest", "Forest", username="bob")
    bears = scenario.cast_onto_stack("Grizzly Bears", *forests, username="bob")
    scenario.pass_priority("bob")

    casting = scenario.cast("Drown in the Loch", username="alice")
    casting.choose_modes([1])
    casting.choose_targets([bears])  # no refusal


def test_drown_in_the_loch_creature_mode_is_bounded_by_the_same_count():
    """The second mode restricts a creature on the battlefield the same way,
    and the count is read off *that* creature's controller's graveyard."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Drown in the Loch"], battlefield=["Island", "Swamp"])
        .player("bob", battlefield=["Hill Giant"], graveyard=["Lightning Bolt"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    giant = scenario.creature("Hill Giant", "bob")

    casting = scenario.cast("Drown in the Loch", username="alice")
    casting.choose_modes([2])
    with pytest.raises(ValueError, match="mana value"):
        casting.choose_targets([giant])


def test_drown_in_the_loch_creature_mode_accepts_a_creature_within_the_count():
    """Four cards in the graveyard reach Hill Giant's mana value of 4."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Drown in the Loch"], battlefield=["Island", "Swamp"])
        .player(
            "bob",
            battlefield=["Hill Giant"],
            graveyard=["Lightning Bolt", "Grizzly Bears", "Forest", "Mountain"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    giant = scenario.creature("Hill Giant", "bob")

    casting = scenario.cast("Drown in the Loch", username="alice")
    casting.choose_modes([2])
    casting.choose_targets([giant])  # no refusal


def test_spell_snare_actually_counters_the_spell_it_legally_targeted():
    """CR 701.6a's counter: the targeted spell leaves the stack unresolved.

    Written as a strict xfail when the targeting half landed - the effect half
    was measured as `None` at the time, and named as the counter-qualifier
    family's job. That family landed in the same wave, so the marker came off
    rather than the test: both halves are real now, and Spell Snare needed
    both to do anything at all.
    """
    scenario = _snare_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    forests = scenario.untapped_sources("Forest", "Forest", username="bob")
    bears = scenario.cast_onto_stack("Grizzly Bears", *forests, username="bob")
    scenario.pass_priority("bob")
    (island,) = scenario.untapped_sources("Island", username="alice")
    scenario.cast_onto_stack("Spell Snare", island, username="alice", targets=[bears])

    scenario.resolve_top()

    assert bears.zone is Zone.GRAVEYARD


# -- Drown in the Loch's counter mode, resolved -------------------------------


def _cast_drown_at(scenario, target) -> None:
    """Alice casts Drown in the Loch's first mode at `target`, onto the stack."""
    casting = scenario.cast("Drown in the Loch", username="alice")
    casting.choose_modes([1])
    casting.choose_targets([target])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Island", "Swamp", username="alice"))
    scenario.put_on_stack(casting)


def test_drown_in_the_loch_counters_a_spell_whose_mana_value_equals_the_count():
    """Bound equal passes: two cards in bob's graveyard, a mana value 2 spell.
    CR 701.6a: the countered spell goes to its owner's graveyard, and the mode
    is read, so no mode notice is left behind (CR 700.2a)."""
    scenario = _snare_board(graveyard=["Lightning Bolt", "Grizzly Bears"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    forests = scenario.untapped_sources("Forest", "Forest", username="bob")
    bears = scenario.cast_onto_stack("Grizzly Bears", *forests, username="bob")
    scenario.pass_priority("bob")

    _cast_drown_at(scenario, bears)
    scenario.resolve_top()

    assert bears.zone is Zone.GRAVEYARD
    assert scenario.game.mode_notices == []


def test_drown_in_the_loch_counts_the_targets_controllers_graveyard_not_the_casters():
    """Alice's own full graveyard does not help: "its controller" is bob, whose
    graveyard is empty, so a mana value 2 spell exceeds the bound (CR 601.2c)."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("bob", hand=["Grizzly Bears"], battlefield=["Forest", "Forest"])
        .player(
            "alice",
            hand=["Drown in the Loch"],
            battlefield=["Island", "Swamp"],
            graveyard=["Lightning Bolt", "Hill Giant", "Forest", "Mountain"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    forests = scenario.untapped_sources("Forest", "Forest", username="bob")
    bears = scenario.cast_onto_stack("Grizzly Bears", *forests, username="bob")
    scenario.pass_priority("bob")

    casting = scenario.cast("Drown in the Loch", username="alice")
    casting.choose_modes([1])
    with pytest.raises(ValueError, match="mana value"):
        casting.choose_targets([bears])


def test_drown_in_the_loch_rechecks_the_count_on_resolution():
    """CR 608.2b: legal at announcement with two cards in bob's graveyard, then
    Nihil Spellbomb exiles that graveyard in response. The bound is now 0, the
    only target is illegal, so Drown does not resolve and Grizzly Bears does."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "bob",
            hand=["Grizzly Bears"],
            battlefield=["Forest", "Forest"],
            graveyard=["Lightning Bolt", "Hill Giant"],
        )
        .player(
            "alice",
            hand=["Drown in the Loch"],
            battlefield=["Island", "Swamp", "Nihil Spellbomb"],
            library=["Island", "Island"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    forests = scenario.untapped_sources("Forest", "Forest", username="bob")
    bears = scenario.cast_onto_stack("Grizzly Bears", *forests, username="bob")
    scenario.pass_priority("bob")
    _cast_drown_at(scenario, bears)
    drown = scenario.find("Drown in the Loch", Zone.STACK, "alice")

    spellbomb = scenario.find("Nihil Spellbomb", Zone.BATTLEFIELD, "alice")
    scenario.activate(spellbomb, targets=["bob"], username="alice")
    for _ in range(3):
        if not scenario.player("bob").graveyard:
            break
        scenario.pass_until_resolved()
    assert scenario.player("bob").graveyard == []
    assert drown.zone is Zone.STACK

    while drown.zone is Zone.STACK:
        scenario.pass_until_resolved()

    assert drown.zone is Zone.GRAVEYARD
    assert scenario.game.mode_notices == [], "it did not resolve, so no mode was performed at all"
    assert bears.zone is Zone.STACK, "the counter did not resolve, so bears is still waiting"
    scenario.pass_until_resolved()
    assert bears.zone is Zone.BATTLEFIELD


# -- Spellstutter Sprite: the bound defined by "where X is ..." ----------------
#
# Off-pool, and worded differently from Drown in the Loch: "counter target
# spell with mana value X or less, where X is the number of Faeries you
# control." CR 107.3c: X is defined by the text, the controller does not choose
# it, and "the value of X may change while that spell or ability is on the
# stack" - so it is counted at CR 603.3d's announcement and again at the
# CR 608.2b recheck. CR 107.3c was looked up with `mise run rules:find` in the
# session that added these tests, as were CR 603.3d and CR 608.2b.

SPRITE = "Spellstutter Sprite"


def _sprite_board(*alice_battlefield: str) -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "bob",
            hand=["Grizzly Bears", "Lightning Bolt"],
            battlefield=["Forest", "Forest", "Mountain"],
        )
        .player("alice", hand=[SPRITE], battlefield=["Island", "Island", *alice_battlefield])
    )


def _flash_in_sprite_over_bears(scenario):
    scenario.start_at(Step.PRECOMBAT_MAIN)
    forests = scenario.untapped_sources("Forest", "Forest", username="bob")
    bears = scenario.cast_onto_stack("Grizzly Bears", *forests, username="bob")
    scenario.pass_priority("bob")
    islands = scenario.untapped_sources("Island", "Island", username="alice")
    sprite = scenario.cast_onto_stack(SPRITE, *islands, username="alice")
    scenario.will_choose_targets(bears, username="alice", source=SPRITE)
    scenario.pass_until_resolved()  # Sprite resolves; its enters trigger goes on the stack
    assert sprite.zone is Zone.BATTLEFIELD
    return bears


def test_spellstutter_sprite_counters_a_spell_within_its_faerie_count():
    """Sprite plus Faerie Macabre is two Faeries, so X is 2 and Grizzly Bears'
    mana value of 2 is in reach."""
    scenario = _sprite_board("Faerie Macabre").build()
    bears = _flash_in_sprite_over_bears(scenario)

    scenario.pass_until_resolved()

    assert bears.zone is Zone.GRAVEYARD


def test_spellstutter_sprite_alone_has_no_legal_target_above_its_count():
    """Sprite alone makes X 1: Grizzly Bears is no legal target, so CR 603.3d
    removes the trigger and the bears resolve."""
    scenario = _sprite_board().build()
    bears = _flash_in_sprite_over_bears(scenario)

    while bears.zone is Zone.STACK:
        scenario.pass_until_resolved()

    assert bears.zone is Zone.BATTLEFIELD


def test_spellstutter_sprite_rechecks_x_when_a_faerie_leaves_in_response():
    """X was 2 at announcement; bob bolts Faerie Macabre in response, X is 1
    at the CR 608.2b recheck, the only target is illegal, and the trigger does
    not resolve."""
    scenario = _sprite_board("Faerie Macabre").build()
    bears = _flash_in_sprite_over_bears(scenario)
    macabre = scenario.creature("Faerie Macabre", "alice")

    # CR 117.3b: the active player receives priority after the Sprite resolved.
    assert scenario.priority_holder == "bob"
    (mountain,) = scenario.untapped_sources("Mountain", username="bob")
    scenario.cast_onto_stack("Lightning Bolt", mountain, username="bob", targets=[macabre])
    scenario.pass_until_resolved()  # the Bolt
    assert macabre.zone is Zone.GRAVEYARD

    scenario.pass_until_resolved()  # the trigger, rechecked
    assert bears.zone is Zone.STACK
    scenario.pass_until_resolved()
    assert bears.zone is Zone.BATTLEFIELD
