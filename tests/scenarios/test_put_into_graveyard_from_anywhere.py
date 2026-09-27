"""Scenario: "When `<name>` is put into a graveyard from anywhere, ..." as a
real self-referential trigger - distinct from `TriggerEvent.DIES` (CR
700.4's battlefield-only move): this condition watches the card's own
arrival at a graveyard from *any* zone, library milled or hand discarded
included, not only a death. Not one of CR 603.10a's own enumerated look-back
exceptions (CR 603.6c: "an ability that triggers when a card is put into a
certain zone 'from anywhere' is never treated as a leaves-the-battlefield
ability") - CR 603.10's own default answers it instead: the object is
checked as it exists immediately after the event, which is exactly the
graveyard card as it now sits (CR 113.6k lets the ability function from
whichever zone it can actually trigger from).

`ExtraTriggerEvent.PUT_INTO_GRAVEYARD` already exists for the batched "one or
more `<type>` cards are put into your graveyard from anywhere" shape
(Robot Domination); this file is the missing *self*-referential singular
form of the identical event.

Oracle text, pulled with `scripts/add_card.py` and verified against the
printings pool (every card Modern-legal):

- **Emrakul, the Aeons Torn**: "... / When Emrakul is put into a graveyard
  from anywhere, its owner shuffles their graveyard into their library."
- **Purity** (a second printing, not in the api deck pool): "Flying / If
  noncombat damage would be dealt to you, prevent that damage. You gain life
  equal to the damage prevented this way. / When Purity is put into a
  graveyard from anywhere, shuffle it into its owner's library." - proof
  that the same condition composes with the already-generic "shuffle it
  into its owner's library" self reader (`machines/effects.
  _DEAD_OBJECT_TO_LIBRARY_RE`), and that it fires from a milled library card,
  not only a death on the battlefield.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone

from .harness import Scenario

EMRAKUL = "Emrakul, the Aeons Torn"
PURITY = "Purity"


def test_emrakul_shuffles_its_owners_graveyard_into_their_library_on_death():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[EMRAKUL],
            graveyard=["Mountain", "Forest", "Island"],
            library=["Swamp"],
        )
        .player("bob", battlefield=["Lightning Bolt"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    emrakul = scenario.creature(EMRAKUL, "alice")
    library_size_before = len(scenario.player("alice").library)
    graveyard_size_before = len(scenario.player("alice").graveyard)

    scenario.game.destroy(emrakul)
    scenario.state_based_actions()
    assert emrakul.zone is Zone.GRAVEYARD
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == [f"{EMRAKUL}'s triggered ability"]
    scenario.resolve_top()

    assert scenario.player("alice").graveyard == []
    assert len(scenario.player("alice").library) == library_size_before + graveyard_size_before + 1


def test_emrakul_triggers_from_the_library_too_not_only_the_battlefield():
    """CR 603.10a's "from anywhere": milled straight from the library, never
    having been on the battlefield at all, still triggers."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[EMRAKUL],
            library=["Mountain", EMRAKUL, "Forest"],
            graveyard=["Swamp"],
        )
        .player("bob", battlefield=[])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    milled_emrakul = scenario.find(EMRAKUL, Zone.LIBRARY, "alice")

    for state in list(scenario.player("alice").library):
        scenario.game.put_into_graveyard(state)
    scenario.game.announce_batched_events()
    scenario.game.put_triggers_on_stack()

    assert milled_emrakul.zone is Zone.GRAVEYARD
    names = scenario.stack_names()
    assert names.count(f"{EMRAKUL}'s triggered ability") == 1


def test_purity_shuffles_itself_into_its_owners_library():
    scenario = (
        Scenario()
        .player("alice", battlefield=[PURITY], library=["Mountain"])
        .player("bob", battlefield=["Lightning Bolt"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    purity = scenario.creature(PURITY, "alice")

    scenario.game.destroy(purity)
    scenario.state_based_actions()
    assert purity.zone is Zone.GRAVEYARD
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == [f"{PURITY}'s triggered ability"]
    scenario.resolve_top()

    assert purity.zone is Zone.LIBRARY
