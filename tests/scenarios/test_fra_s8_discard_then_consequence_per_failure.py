"""FRA stream S8: "Each `<player|opponent>` discards `<n>` cards. [Then] for
each `<player|opponent>` who didn't discard `<n>` `<quality>` cards this way,
`<consequence>`." - a group discard whose own CR 701.9b choice feeds a
per-member consequence.

Every CR number below was looked up with `mise run rules:find` in the
session that wrote this file.

- **CR 701.9a/701.9b** - discarding, chosen by the discarding player.
- **CR 608.2c** - "this way" is anaphora onto exactly the discard the first
  sentence just performed, read off what was actually discarded rather than
  reasked.
- **CR 119.3** - losing life.

Garruk, Veiled Butcher's `−3` ("Each opponent discards two cards. For each
opponent who didn't discard two nonland cards this way, you draw a card.")
is the reported card - a count of the *failing* opponents, applied once as a
draw to this ability's own controller. Strongarm Tactics is the off-set
proof: a real, non-FRA, non-pool sorcery naming "each player" rather than
"each opponent", a different quality ("creature" rather than "nonland"), a
single-card discard rather than two, and a consequence that lands on each
*failing member themselves* (a life loss) rather than on the ability's
controller - genuinely exercising both the subject-group and the
consequence-shape generalisation, not re-confirming Garruk's one sentence.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_garruks_minus_three_draws_once_per_opponent_who_kept_a_nonland_short():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Garruk, Veiled Butcher"], library=["Forest"] * 5)
        .player("bob", hand=["Grizzly Bears", "Mountain", "Forest"])
        .player("carol", hand=["Goblin Guide", "Elvish Mystic"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    garruk = scenario.find("Garruk, Veiled Butcher", Zone.BATTLEFIELD, "alice")
    alice = scenario.player("alice")
    bob_bears = scenario.find("Grizzly Bears", Zone.HAND, "bob")
    bob_mountain = scenario.find("Mountain", Zone.HAND, "bob")
    carol_guide = scenario.find("Goblin Guide", Zone.HAND, "carol")
    carol_mystic = scenario.find("Elvish Mystic", Zone.HAND, "carol")

    # Bob discards a nonland and a land - only one nonland card, short of the
    # printed "two nonland cards" threshold.
    scenario.will_choose_cards(bob_bears, bob_mountain, username="bob")
    # Carol discards two nonland cards - meets the threshold.
    scenario.will_choose_cards(carol_guide, carol_mystic, username="carol")

    hand_before = len(alice.hand)
    scenario.activate(garruk, index=2)
    scenario.pass_until_resolved()

    assert bob_bears.zone is Zone.GRAVEYARD
    assert bob_mountain.zone is Zone.GRAVEYARD
    assert carol_guide.zone is Zone.GRAVEYARD
    assert carol_mystic.zone is Zone.GRAVEYARD
    assert len(alice.hand) == hand_before + 1, "only bob fell short, so alice draws exactly once"


def test_strongarm_tactics_each_failing_player_loses_life_not_the_caster():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Strongarm Tactics", "Lightning Bolt"],
            battlefield=["Swamp", "Mountain"],
        )
        .player("bob", hand=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    bob = scenario.player("bob")
    sources = scenario.untapped_sources("Swamp", "Mountain")
    alice_bolt = scenario.find("Lightning Bolt", Zone.HAND, "alice")
    bob_bears = scenario.find("Grizzly Bears", Zone.HAND, "bob")

    # Alice discards Lightning Bolt (not a creature card) - falls short.
    scenario.will_choose_cards(alice_bolt, username="alice")
    # Bob discards Grizzly Bears (a creature card) - meets the threshold.
    scenario.will_choose_cards(bob_bears, username="bob")

    alice_life_before = alice.life
    bob_life_before = bob.life
    scenario.cast_and_resolve("Strongarm Tactics", *sources)

    assert alice_bolt.zone is Zone.GRAVEYARD
    assert bob_bears.zone is Zone.GRAVEYARD
    assert alice.life == alice_life_before - 4, "alice's own discard wasn't a creature card"
    assert bob.life == bob_life_before, "bob's discard met the quality, so bob loses nothing"
