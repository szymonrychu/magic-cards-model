"""Whenever you discard a `<quality>` card, ... - a quality-filtered
CR 701.9a discard trigger, counted per CR 603.2c occurrence.

Card text, confirmed with `resolve_cards` in the session that wrote this
file:

Invasion of Kaldheim // Pyre of the World Tree (back face, an Enchantment):
    Discard a land card: This enchantment deals 2 damage to any target.
    Whenever you discard a land card, exile the top card of your library.
    You may play that card this turn.

Wharf Infiltrator (Creature, Modern/Pioneer legal):
    Whenever you discard a creature card, you may pay {2}. If you do,
    create a 3/2 colorless Eldrazi Horror creature token.

Before this session, `TriggerEvent.DISCARDS_A_CARD`'s own condition reader
(`machines/abilities._trigger_event`) recognised only "discards a card"/
"another card"/"one or more cards"/"this card" - "discards a `<quality>`
card" matched none of them, so the whole condition read `event=None` and the
trigger never fired at all, on either card (`support.py`'s own "triggered
(unread condition)" bucket, indistinguishable in the sweep from a genuinely
unreadable one). Widened generally (one bare type/subtype word,
`machines.effects._quality_matcher`) rather than to "land"/"creature" by
name - see `machines/triggers.py`'s own `_PER_CARD_DISCARD_CONDITION`
docstring.

Every rule below was looked up with `mise run rules:find` in the session
that wrote this file:

- **CR 701.9a** - discarding a card.
- **CR 603.2c** - "An ability triggers only once each time its trigger event
  occurs. However, it can trigger repeatedly if one event contains multiple
  occurrences" - Cathartic Reunion's own two-card discard is one CR 701.9a
  instruction with two occurrences, one per card, so a quality-filtered
  condition counts only the matching ones, not the whole batch.
- **CR 608.2d** - the exile is mandatory; the play permission is a "you may"
  made as the ability resolves.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

KALDHEIM = "Invasion of Kaldheim"
PYRE = "Pyre of the World Tree"


def _transform_kaldheim(scenario, siege):
    """Defeats Invasion of Kaldheim with two Lightning Bolts (CR 115.4/
    310.6, defense 4) so its own defeat trigger casts Pyre of the World
    Tree transformed - the only way this back face's own abilities are ever
    on the battlefield to test."""
    mountains = scenario.untapped_sources("Mountain", "Mountain", username="alice")
    scenario.cast_and_resolve("Lightning Bolt", mountains[0], username="alice", targets=[siege])
    scenario.cast_and_resolve("Lightning Bolt", mountains[1], username="alice", targets=[siege])
    scenario.game.check_state_based_actions()
    assert siege.counter_count("defense") == 0
    scenario.will_take_the_may(True, username="alice")
    scenario.pass_until_resolved()  # CR 310.12b's defeat trigger: exile, then cast
    scenario.pass_until_resolved()  # Pyre of the World Tree enters


def test_discarding_a_land_triggers_pyre_and_the_top_card_may_be_played():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Bolt", "Lightning Bolt", "Forest"],
            library=["Grizzly Bears"],
            battlefield=[KALDHEIM, "Mountain", "Mountain"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    siege = scenario.find(KALDHEIM, Zone.BATTLEFIELD, "alice")
    _transform_kaldheim(scenario, siege)
    assert siege.name == PYRE

    # A land in hand to discard as the activated ability's own cost.
    forest = scenario.find("Forest", Zone.HAND, "alice")
    bears = scenario.find("Grizzly Bears", Zone.LIBRARY, "alice")

    scenario.activate(siege, discarding=[forest], targets=["bob"], username="alice")
    scenario.pass_until_resolved()  # the damage ability
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()  # "whenever you discard a land card" trigger

    bob = scenario.player("bob")
    assert forest.zone is Zone.GRAVEYARD, "discarded to pay the activation's own cost"
    assert bob.life == 18, "the damage ability actually resolved"
    assert bears.zone is Zone.EXILE, "exiled off the top of the library"
    permission = scenario.game.play_permissions
    assert any(
        granted.card_id == bears.id and granted.action.value == "play" for granted in permission
    ), "granted play permission this turn"


def test_discarding_a_nonland_does_not_trigger_pyre():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[
                "Lightning Bolt",
                "Lightning Bolt",
                "Cathartic Reunion",
                "Grizzly Bears",
                "Llanowar Elves",
            ],
            library=["Forest", "Forest", "Forest", "Forest"],
            battlefield=[
                KALDHEIM,
                "Mountain",
                "Mountain",
                "Mountain",
                "Mountain",
                "Swamp",
                "Swamp",
            ],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    siege = scenario.find(KALDHEIM, Zone.BATTLEFIELD, "alice")
    _transform_kaldheim(scenario, siege)

    bears = scenario.find("Grizzly Bears", Zone.HAND, "alice")
    elves = scenario.find("Llanowar Elves", Zone.HAND, "alice")
    (mountain1, mountain2) = scenario.untapped_sources("Mountain", "Mountain", username="alice")

    scenario.cast_and_resolve(
        "Cathartic Reunion", mountain1, mountain2, username="alice", discarding=[bears, elves]
    )

    alice = scenario.player("alice")
    assert bears.zone is Zone.GRAVEYARD
    assert elves.zone is Zone.GRAVEYARD
    assert len(alice.hand) == 3, "drew three cards - Cathartic Reunion's own effect, nothing more"
    assert scenario.game.pending_triggers == [], (
        "no land was discarded - Pyre of the World Tree's own trigger never fires"
    )
    assert len(alice.library) == 1, "only the three drawn cards left the library - none exiled"


def test_wharf_infiltrator_counts_only_the_creature_card_of_a_two_card_discard():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Cathartic Reunion", "Grizzly Bears", "Forest"],
            library=["Island", "Island", "Island", "Island"],
            battlefield=["Wharf Infiltrator", "Mountain", "Mountain"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.creature("Wharf Infiltrator", "alice")
    bears = scenario.find("Grizzly Bears", Zone.HAND, "alice")
    forest = scenario.find("Forest", Zone.HAND, "alice")
    (mountain1, mountain2) = scenario.untapped_sources("Mountain", "Mountain", username="alice")

    scenario.cast_onto_stack(
        "Cathartic Reunion", mountain1, mountain2, username="alice", discarding=[bears, forest]
    )

    assert bears.zone is Zone.GRAVEYARD
    assert forest.zone is Zone.GRAVEYARD
    # CR 603.3: a triggered ability goes on the stack the next time a player
    # would receive priority - here, above the spell whose own cost caused
    # the discard (`cast_onto_stack`'s own pay-then-stack order).
    assert scenario.stack_names() == [
        "Cathartic Reunion",
        "Wharf Infiltrator's triggered ability",
    ], "one occurrence - only the creature card among the two discarded matched"
