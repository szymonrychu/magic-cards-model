"""Scenario: Frontline Heroism's own cast trigger (CR 603.2, 707.10).

"Whenever you cast a spell that targets only a single creature you control,
create a 1/1 red Soldier creature token with haste, then copy that spell. The
copy targets that token."

Two things had to be built for real, both read off the card's own printed
text rather than a name-keyed table:

- **The condition.** "that targets only a single creature you control" is not
  a fact about the cast spell's own printed characteristics (colour, card
  type, mana value) the way every other `CAST_SPELL` condition in the pool
  is - it is a fact about *what the spell targets*, read off `CardState.
  targets` (CR 601.2c's announcement, already made by the time the spell
  goes on the stack and the trigger checks it). `machines/triggers.py`'s
  `condition_matches` reads it directly: exactly one target, not a player,
  a creature (CR 300.1), on the battlefield, controlled by the same player
  casting the spell. The clause also happens to contain the word "creature",
  which `_types_match`'s ordinary type-word scan used to misread as "cast a
  creature spell" - Lightning Bolt (an instant) aimed at your own creature
  would have wrongly failed to trigger. `_TARGETS_ONLY_SINGLE_CREATURE_CLAUSE`
  strips the clause out of the copy handed to the type/colour/subtype checks,
  which have nothing to do with what the spell targets.
- **The effect.** "create `<token>`, then copy that spell. The copy targets
  that token." is `_parse_create_token_then_copy_spell_retargeted_clause` in
  `machines/effects.py`: `_TOKEN_CLAUSE_RE`'s ordinary token descriptor for
  the first half, `Game.copy_spell` (CR 707.10) for the second, and a forced
  `copy.targets` overwrite for the third - CR 707.10c's "you may choose new
  targets" is an optional permission (Alania, Divergent Storm's own shape,
  `_parse_target_opponent_draw_then_copy_that_spell_clause`); "the copy
  targets that token" is not optional and does not offer a choice.

Every CR number here was looked up with `knowledge_search(q="...",
type="rules")` in the session that wrote this file:

- **CR 603.2** - a triggered ability triggers when its condition is met.
- **CR 601.2c** - a spell's targets are announced as part of casting it.
- **CR 707.10, 707.10c** - copying a spell, and choosing new targets for a
  copy.
- **CR 111.2** - a token's creator is its owner and controller.
- **CR 702.9c** (haste's own printed keyword) is not re-verified here; the
  token's haste is asserted by it being able to act the turn it entered.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _board(alice_battlefield: list[str], alice_hand: list[str]) -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=alice_hand,
            battlefield=["Frontline Heroism", "Mountain", "Mountain", *alice_battlefield],
        )
        .player("bob", battlefield=["Grizzly Bears"])
    )


def test_targeting_your_own_creature_creates_a_token_and_copies_the_spell():
    """The trigger fires, a 1/1 red Soldier with haste appears, and the copy
    kills it while the original still resolves against the original target."""
    scenario = _board(["Grizzly Bears"], ["Lightning Bolt"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice_bears = scenario.creature("Grizzly Bears", "alice")
    sources = scenario.untapped_sources("Mountain", "Mountain")

    scenario.cast_onto_stack("Lightning Bolt", sources[0], targets=[alice_bears])
    assert scenario.stack_names() == [
        "Lightning Bolt",
        "Frontline Heroism's triggered ability",
    ]

    scenario.pass_until_resolved()  # the trigger resolves: token + copy appear
    (token,) = [state for state in scenario.game.battlefield if state.token]
    assert "Soldier" in token.subtypes
    assert token.power == 1 and token.toughness == 1
    assert token.controller == "alice"
    assert "Haste" in token.keywords

    assert scenario.stack_names() == ["Lightning Bolt", "Lightning Bolt"], (
        "the copy sits above the original spell it copied"
    )

    scenario.pass_until_resolved()  # the copy resolves first (CR 608), at the token
    assert token.zone is Zone.GRAVEYARD, "3 damage killed the 1-toughness token"
    assert alice_bears.zone is Zone.BATTLEFIELD, "the original spell has not resolved yet"

    scenario.pass_until_resolved()  # the original Lightning Bolt resolves, at the bears
    assert alice_bears.zone is Zone.GRAVEYARD, "3 damage killed the 2-toughness bears too"


def test_targeting_an_opponents_creature_does_not_trigger_it():
    """ "... a single creature *you* control" - Bob's Grizzly Bears is not
    Alice's, so casting Lightning Bolt at it never fires the trigger."""
    scenario = _board([], ["Lightning Bolt"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bob_bears = scenario.creature("Grizzly Bears", "bob")
    sources = scenario.untapped_sources("Mountain", "Mountain")

    scenario.cast_onto_stack("Lightning Bolt", sources[0], targets=[bob_bears])
    assert scenario.stack_names() == ["Lightning Bolt"], "no trigger - not Alice's creature"

    scenario.pass_until_resolved()
    assert bob_bears.zone is Zone.GRAVEYARD
    assert not any(state.token for state in scenario.game.battlefield)


def test_targeting_a_player_does_not_trigger_it():
    """ "a single creature you control" is not "any target" - a spell aimed
    at a player's face never satisfies the condition at all."""
    scenario = _board([], ["Lightning Bolt"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Mountain", "Mountain")

    scenario.cast_onto_stack("Lightning Bolt", sources[0], targets=["bob"])
    assert scenario.stack_names() == ["Lightning Bolt"], "no trigger - the target is a player"


def test_a_spell_with_no_targets_does_not_trigger_it():
    """No target announced at all - the condition needs "only a single"
    target, and zero is not one. Opt's own "Scry 1. Draw a card." names no
    target of any kind."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Opt"],
            battlefield=["Frontline Heroism", "Island", "Grizzly Bears"],
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (island,) = scenario.untapped_sources("Island")

    scenario.cast_onto_stack("Opt", island)
    assert scenario.stack_names() == ["Opt"], "Opt targets nothing at all"
