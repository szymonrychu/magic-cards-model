"""Scenario: CR 508.4 - a creature put onto the battlefield already attacking,
off a library reveal and off a combat-damage reanimation from the damaged
player's own graveyard.

Raph & Mikey, Troublemakers: "Whenever Raph & Mikey attack, reveal cards from
the top of your library until you reveal a creature card. Put that card onto
the battlefield tapped and attacking and the rest on the bottom of your
library in a random order."

Shark Shredder, Killer Clone: "Whenever Shark Shredder deals combat damage to
a player, put up to one target creature card from that player's graveyard
onto the battlefield under your control. It enters tapped and attacking that
player."

- **CR 701.20a** - revealing a card does not move it; every card seen along
  the way stays on top of the library until dealt with.
- **CR 508.4** - "If a creature is put onto the battlefield attacking, its
  controller chooses which defending player, planeswalker a defending player
  controls, or battle a defending player protects it's attacking as it
  enters the battlefield" - for Raph & Mikey, whichever player/planeswalker
  they are already attacking; for Shark Shredder, the very player its
  combat damage was just dealt to (CR 120.2a), read off the trigger event
  rather than the current combat.
- **CR 109.4/CR 108.4a** - a graveyard card's owner, not a controller, is
  what "that player's graveyard" restricts a target by; `models.game._that_
  player_of` and `machines.targeting._ZONE_CLAUSE` are both extended to
  recognise the phrase (they already recognised "that player controls" for a
  permanent).
- **CR 701.24a** - the cards Raph & Mikey's reveal did not keep are shuffled
  to the bottom of the library, not the top and not in revealed order.

No second legal printing carries either combined template (dated MEMORY.md
lines); the CR 508.4 primitives themselves (`_defender_of_controllers_
attack`/`_put_onto_the_battlefield_attacking`) are the same ones Ilharg, the
Raze-Boar's own attack trigger and Grim Reaper, Lethal Legionnaire's own
graveyard-reanimation trigger already prove.

Every CR number here was looked up with `mise run rules:find` in the session
that wrote this file.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_raph_and_mikey_reveal_until_a_creature_and_attack_with_it():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Raph & Mikey, Troublemakers"],
            library=["Lightning Bolt", "Grizzly Bears", "Forest", "Forest"],
        )
        .player("bob", library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    raph_mikey = scenario.creature("Raph & Mikey, Troublemakers", "alice")
    bolt = scenario.find("Lightning Bolt", Zone.LIBRARY, "alice")

    scenario.attack_with(raph_mikey, defending="bob")
    assert scenario.stack_names() == ["Raph & Mikey, Troublemakers's triggered ability"]
    scenario.pass_until_resolved()

    bears = scenario.creature("Grizzly Bears", "alice")
    assert bears.zone is Zone.BATTLEFIELD
    assert bears.tapped
    assert bears in scenario.attackers()
    # CR 701.20a: revealed, never moved out of the library, until the reveal
    # sorted it to the bottom.
    assert bolt.zone is Zone.LIBRARY
    assert scenario.player("alice").library[-1] is bolt
    # The two Forests underneath were never touched by the reveal at all.
    assert [state.name for state in scenario.player("alice").library[:2]] == ["Forest", "Forest"]


def test_a_library_with_no_creature_reveals_everything_and_puts_nothing_down():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Raph & Mikey, Troublemakers"],
            library=["Lightning Bolt", "Opt"],
        )
        .player("bob", library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    raph_mikey = scenario.creature("Raph & Mikey, Troublemakers", "alice")

    scenario.attack_with(raph_mikey, defending="bob")
    scenario.pass_until_resolved()

    assert scenario.battlefield_names().count("Grizzly Bears") == 0
    assert len(scenario.player("alice").library) == 2


def test_shark_shredder_reanimates_from_the_damaged_players_own_graveyard():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Shark Shredder, Killer Clone"], library=["Island"] * 5)
        .player("bob", graveyard=["Grizzly Bears"], library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    shredder = scenario.creature("Shark Shredder, Killer Clone", "alice")
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "bob")

    scenario.attack_with(shredder, defending="bob")
    scenario.advance()  # declare blockers
    scenario.no_blocks()
    scenario.will_choose_targets(bears, username="alice", source="Shark Shredder, Killer Clone")
    scenario.combat_damage()

    assert scenario.stack_names() == ["Shark Shredder, Killer Clone's triggered ability"]
    scenario.pass_until_resolved()

    assert bears.zone is Zone.BATTLEFIELD
    assert bears.controller == "alice"
    assert bears.tapped
    assert bears in scenario.attackers()


def test_shark_shredder_declining_the_up_to_one_target_reanimates_nothing():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Shark Shredder, Killer Clone"], library=["Island"] * 5)
        .player("bob", graveyard=["Grizzly Bears"], library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    shredder = scenario.creature("Shark Shredder, Killer Clone", "alice")

    scenario.attack_with(shredder, defending="bob")
    scenario.advance()
    scenario.no_blocks()
    scenario.will_choose_targets(username="alice", source="Shark Shredder, Killer Clone")
    scenario.combat_damage()
    scenario.pass_until_resolved()

    assert scenario.find("Grizzly Bears", Zone.GRAVEYARD, "bob").zone is Zone.GRAVEYARD
