"""The monarch (CR 725), through Grave Venerations:

    When this enchantment enters, you become the monarch.
    At the beginning of your end step, if you're the monarch, return up to
    one target creature card from your graveyard to your hand.
    Whenever a creature you control dies, each opponent loses 1 life and you
    gain 1 life.

Every rule cited here was looked up with `mise run rules:find` in the session
that wrote this file, against the 2026-09-25 Comprehensive Rules:

- **CR 725.1** - "The monarch is a designation a player can have. There is no
  monarch in a game until an effect instructs a player to become the
  monarch."
- **CR 725.2** - "There are two inherent triggered abilities associated with
  being the monarch. These triggered abilities have no source and are
  controlled by the player who was the monarch at the time the abilities
  triggered. This is an exception to rule 113.8. The full texts of these
  abilities are 'At the beginning of the monarch's end step, that player
  draws a card' and 'Whenever a creature deals combat damage to the monarch,
  its controller becomes the monarch.'"
- **CR 725.3** - "Only one player can be the monarch at a time. As a player
  becomes the monarch, the current monarch ceases to be the monarch."
- **CR 725.4** - "If the monarch leaves the game, the active player becomes
  the monarch at the same time as that player leaves the game. If the active
  player is leaving the game or if there is no active player, the next player
  in turn order who can become the monarch becomes the monarch. If no player
  still in the game can become the monarch, the game continues with no
  monarch."
- **CR 603.4 / CR 608.2a** - the intervening *if* ("if you're the monarch")
  that gates Grave Venerations' own end-step return.
- **CR 104.3a** - conceding leaves the game immediately.

Generality is proven on two cards that are not Grave Venerations and are not
otherwise in the deck pool this round: Palace Sentinels ("When this creature
enters, you become the monarch.", a creature ETB rather than an enchantment
ETB) and Denethor, Stone Seer ("{3}{R}, {T}, Sacrifice Denethor: Target player
becomes the monarch. Denethor deals 3 damage to any target.", an activated
ability whose *target* becomes the monarch, rather than the controller).

No Modern/Pioneer/Standard-legal card carries the monarch designation at all
(verified via `scryfall.com/docs/reference` search for
`o:"monarch" (f:modern or f:pioneer or f:standard)`, zero results) - the
mechanic has only ever been printed in Commander-only products. Palace
Sentinels and Denethor are both legacy/vintage/commander-legal, the same
legality class Grave Venerations itself is in.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.targeting import TargetRef
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

# --------------------------------------------------------------------------
# CR 725.1 / CR 725.3: becoming the monarch, and only one at a time
# --------------------------------------------------------------------------


def test_you_become_the_monarch_on_etb():
    """Grave Venerations' own "When this enchantment enters, you become the
    monarch." (CR 725.1)."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Grave Venerations"], battlefield=["Swamp"] * 4)
        .player("bob")
        .build()
    )
    assert scenario.game.monarch is None
    scenario.start_at(Step.PRECOMBAT_MAIN)
    swamps = scenario.untapped_sources("Swamp", "Swamp", "Swamp", "Swamp")
    scenario.cast_and_resolve("Grave Venerations", *swamps)
    while scenario.game.stack:
        scenario.resolve_top()

    assert scenario.game.monarch == "alice"


def test_only_one_monarch_at_a_time():
    """CR 725.3: becoming the monarch ousts whoever held it."""
    scenario = Scenario().player("alice").player("bob").build()
    scenario.game.become_monarch("alice")
    assert scenario.game.monarch == "alice"
    scenario.game.become_monarch("bob")
    assert scenario.game.monarch == "bob"


# --------------------------------------------------------------------------
# CR 725.2: the monarch's own end-step draw
# --------------------------------------------------------------------------


def test_monarch_end_step_draws_a_card():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", library=["Plains"])
        .player("bob")
        .build()
    )
    scenario.game.become_monarch("alice")
    before = len(scenario.player("alice").hand)

    scenario.start_at(Step.POSTCOMBAT_MAIN)
    scenario.advance()  # alice's end step begins
    while scenario.game.stack:
        scenario.resolve_top()

    assert len(scenario.player("alice").hand) == before + 1


def test_non_monarchs_end_step_does_not_draw_for_the_monarch():
    """The ability is "the monarch's end step", not "your end step" - bob
    holding the monarch changes nothing about alice's own turn."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", library=["Plains"])
        .player("bob", library=["Island"])
        .build()
    )
    scenario.game.become_monarch("bob")
    bob_hand_before = len(scenario.player("bob").hand)

    scenario.start_at(Step.POSTCOMBAT_MAIN)
    scenario.advance()  # alice's end step begins (alice is active, not bob)
    while scenario.game.stack:
        scenario.resolve_top()

    assert len(scenario.player("bob").hand) == bob_hand_before
    assert scenario.game.monarch == "bob"


# --------------------------------------------------------------------------
# CR 725.2: combat damage to the monarch steals it
# --------------------------------------------------------------------------


def test_creature_dealing_combat_damage_to_the_monarch_becomes_its_controllers():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.game.become_monarch("bob")

    scenario.start_at(Step.DECLARE_ATTACKERS)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.attack_with(bears, defending="bob")
    scenario.no_blocks()
    scenario.combat_damage()
    while scenario.game.stack:
        scenario.resolve_top()

    assert scenario.game.monarch == "alice"


def test_noncombat_damage_to_the_monarch_does_not_steal_it():
    """CR 725.2's own ability names combat damage specifically - a bolt to
    the face is a different event."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice")
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.game.become_monarch("alice")
    bears = scenario.creature("Grizzly Bears", "bob")

    scenario.game.deal_damage(scenario.player("alice"), 2, source=bears)

    assert scenario.game.monarch == "alice"


def test_combat_damage_to_a_non_monarch_does_nothing():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Grizzly Bears"])
        .player("bob")
        .build()
    )
    assert scenario.game.monarch is None

    scenario.start_at(Step.DECLARE_ATTACKERS)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.attack_with(bears, defending="bob")
    scenario.no_blocks()
    scenario.combat_damage()
    while scenario.game.stack:
        scenario.resolve_top()

    assert scenario.game.monarch is None


# --------------------------------------------------------------------------
# Grave Venerations' own end-step return - the intervening "if you're the
# monarch" (CR 603.4, CR 608.2a)
# --------------------------------------------------------------------------


def test_grave_venerations_returns_a_creature_while_monarch():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Grave Venerations"],
            battlefield=["Swamp"] * 4,
            graveyard=["Grizzly Bears"],
            library=["Plains"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    swamps = scenario.untapped_sources("Swamp", "Swamp", "Swamp", "Swamp")
    scenario.cast_and_resolve("Grave Venerations", *swamps)
    while scenario.game.stack:
        scenario.resolve_top()
    assert scenario.game.monarch == "alice"

    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")
    scenario.start_at(Step.POSTCOMBAT_MAIN)
    scenario.choose_trigger_targets("Grave Venerations", [TargetRef.coerce(bears)])
    scenario.advance()  # alice's end step begins
    while scenario.game.stack:
        scenario.resolve_top()

    assert bears.zone is Zone.HAND


def test_grave_venerations_does_nothing_when_not_the_monarch():
    """Placed directly on the battlefield (never cast), so its own ETB never
    fired and alice never became the monarch - the intervening *if* is false
    at her end step, and CR 603.4 says the ability does not trigger at all."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=["Grave Venerations", "Swamp"],
            graveyard=["Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    assert scenario.game.monarch is None

    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")
    scenario.start_at(Step.POSTCOMBAT_MAIN)
    scenario.advance()  # alice's end step begins
    while scenario.game.stack:
        scenario.resolve_top()

    assert bears.zone is Zone.GRAVEYARD
    assert scenario.game.intervening_if_notices == []


# --------------------------------------------------------------------------
# CR 725.4: leaving the game passes the monarchy
# --------------------------------------------------------------------------


def test_monarch_conceding_passes_it_to_the_active_player():
    scenario = Scenario().player("alice").player("bob").build()
    scenario.game.become_monarch("bob")
    assert scenario.turn.active_player == "alice"

    scenario.game.concede("bob")

    assert scenario.game.monarch == "alice"


def test_active_monarch_conceding_passes_it_to_the_next_player_in_turn_order():
    """A third player keeps the game (and a monarch) alive once the departing
    player was both active and the monarch."""
    scenario = Scenario().player("alice").player("bob").player("carol").build()
    scenario.game.become_monarch("alice")
    assert scenario.turn.active_player == "alice"

    scenario.game.concede("alice")

    assert scenario.game.monarch == "bob"


# --------------------------------------------------------------------------
# Generality: Palace Sentinels (a creature ETB, not an enchantment's) and
# Denethor, Stone Seer (an activated ability whose *target* becomes the
# monarch, not its controller) - neither is Grave Venerations and neither
# is in this round's deck pool.
# --------------------------------------------------------------------------


def test_palace_sentinels_etb_grants_the_monarch():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Palace Sentinels"], battlefield=["Plains"] * 4)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    plains = scenario.untapped_sources("Plains", "Plains", "Plains", "Plains")
    scenario.cast_and_resolve("Palace Sentinels", *plains)
    while scenario.game.stack:
        scenario.resolve_top()

    assert scenario.game.monarch == "alice"


def test_denethor_makes_its_target_the_monarch():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Denethor, Stone Seer"] + ["Mountain"] * 4)
        .player("bob")
        .build()
    )
    scenario.game.become_monarch("alice")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    denethor = scenario.creature("Denethor, Stone Seer", "alice")
    mountains = scenario.untapped_sources("Mountain", "Mountain", "Mountain", "Mountain")

    scenario.activate(
        denethor,
        *mountains,
        sacrificing=[denethor],
        targets=[
            TargetRef.coerce(scenario.player("bob")),
            TargetRef.coerce(scenario.player("bob")),
        ],
    )
    while scenario.game.stack:
        scenario.resolve_top()

    assert scenario.game.monarch == "bob"
