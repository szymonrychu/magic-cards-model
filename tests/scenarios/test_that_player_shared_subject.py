"""Scenario: a triggered ability's "that player `<verb>` ... and `<verb>` ..."
- one subject, the player the trigger event named, carried to every verb of
the list, and a restated subject ("and you ...") taking over from there.

CR 608.2c: the instructions are followed in the order written, reading the
whole text by the rules of English - "that player sacrifices a creature of
their choice and loses 10 life" is one subject with two verbs, so the life
is lost by the same player who sacrificed, never by the ability's own
controller.

The engine used to split such a sentence at its "and" and run the orphaned
"loses 10 life" against the ability's controller (the `MEMORY.md` line of
2026-09-27 R0a-T6). The sweep's search-trigger driver found it pinned into
Ob Nixilis, Unshackled's golden.

Oracle text (the printings pool):

- **Ob Nixilis, Unshackled**: "Whenever an opponent searches their library,
  that player sacrifices a creature of their choice and loses 10 life."
- **Sword of Feast and Famine** (a second shape, not in any deck pool):
  "Whenever equipped creature deals combat damage to a player, that player
  discards a card and you untap all lands you control." - "that player"
  leads, then "you" is restated for the second verb.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.keywords import equip_activation
from magic_cards_model.models import Zone

from .harness import Scenario, mana_from

OB_NIXILIS = "Ob Nixilis, Unshackled"
SWORD = "Sword of Feast and Famine"


def test_ob_nixilis_makes_the_searcher_lose_the_life_too():
    scenario = (
        Scenario()
        .player("alice", battlefield=[OB_NIXILIS], library=["Forest"])
        .player(
            "bob",
            battlefield=["Wooded Foothills", "Grizzly Bears"],
            library=["Mountain", "Forest"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    foothills = scenario.find("Wooded Foothills", Zone.BATTLEFIELD, "bob")
    scenario.will_choose_cards(scenario.find("Mountain", Zone.LIBRARY, "bob"))
    scenario.will_choose_cards(bears)

    scenario.pass_priority("alice")
    scenario.activate(foothills, sacrificing=[foothills])
    scenario.pass_until_resolved()
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == [f"{OB_NIXILIS}'s triggered ability"]
    bob_life = scenario.player("bob").life
    scenario.resolve_top()

    assert bears.zone is Zone.GRAVEYARD
    assert scenario.player("bob").life == bob_life - 10
    assert scenario.player("alice").life == 20


def test_sword_of_feast_and_famine_the_damaged_player_discards_and_you_untap():
    scenario = (
        Scenario()
        .player("alice", battlefield=[SWORD, "Grizzly Bears", "Forest", "Forest"])
        .player("bob", hand=["Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    sword = scenario.find(SWORD, Zone.BATTLEFIELD, "alice")
    activation = equip_activation(scenario.game, sword, bears, "alice")
    payment = activation.begin_paying()
    forests = scenario.untapped_sources("Forest", "Forest", username="alice")
    for source in forests:
        payment.tap_for_mana(source, mana_from(source))
    payment.pay()
    activation.activate()
    activation.resolve()
    assert all(forest.tapped for forest in forests)
    alice_hand = len(scenario.player("alice").hand)

    scenario.turn.advance_to(Step.DECLARE_ATTACKERS)
    scenario.game.sync_priority_with_step()
    scenario.attack_with(bears)
    scenario.no_blocks()
    scenario.combat_damage()
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == [f"{SWORD}'s triggered ability"]
    scenario.resolve_top()

    assert scenario.player("bob").hand == []
    assert len(scenario.player("alice").hand) == alice_hand
    assert not any(forest.tapped for forest in forests)
