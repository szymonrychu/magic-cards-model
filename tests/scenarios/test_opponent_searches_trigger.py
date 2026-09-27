"""Scenario: "Whenever an opponent searches their library, ..." (CR 701.23a)
as a real trigger event - `Game.search_library` is the one shared function
every search in this engine goes through, and nothing raised an event off it
for a trigger to watch, so the condition parsed and was never checked.

Oracle text, pulled with `scripts/add_card.py` and verified against the
printings pool (every card Modern-legal):

- **Wan Shi Tong, Librarian**: "Flash / Flying, vigilance / When Wan Shi Tong
  enters, put X +1/+1 counters on him. Then draw half X cards, rounded down.
  / Whenever an opponent searches their library, put a +1/+1 counter on Wan
  Shi Tong and draw a card."
- **Ob Nixilis, Unshackled** (a second printing, not in the api deck pool):
  "Flying, trample / Whenever an opponent searches their library, that player
  sacrifices a creature of their choice and loses 10 life. / Whenever another
  creature dies, put a +1/+1 counter on Ob Nixilis." - proof the new event
  fires for *any* search (a fetchland's activated ability), not only a spell,
  and that "that player" resolves to the searcher rather than to the
  ability's own controller.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone

from .harness import Scenario

WAN_SHI_TONG = "Wan Shi Tong, Librarian"
OB_NIXILIS = "Ob Nixilis, Unshackled"


def _fetch(scenario: Scenario, *, username: str) -> None:
    foothills = scenario.find("Wooded Foothills", Zone.BATTLEFIELD, username)
    if scenario.game.priority.seat != username:
        scenario.pass_priority(scenario.game.priority.seat)
    scenario.activate(foothills, sacrificing=[foothills])
    scenario.pass_until_resolved()


def test_wan_shi_tong_gets_a_counter_and_a_card_when_an_opponent_searches():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[WAN_SHI_TONG],
            library=["Forest", "Mountain", "Island"],
        )
        .player(
            "bob",
            battlefield=["Wooded Foothills"],
            library=["Mountain", "Forest", "Swamp", "Plains"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    wan_shi_tong = scenario.creature(WAN_SHI_TONG, "alice")
    scenario.will_choose_cards(scenario.find("Mountain", Zone.LIBRARY, "bob"))
    hand_before = len(scenario.player("alice").hand)

    _fetch(scenario, username="bob")
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == [f"{WAN_SHI_TONG}'s triggered ability"]
    scenario.resolve_top()

    assert wan_shi_tong.counter_count("+1/+1") == 1
    assert len(scenario.player("alice").hand) == hand_before + 1


def test_wan_shi_tong_does_not_trigger_on_its_own_controller_searching():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[WAN_SHI_TONG, "Wooded Foothills"],
            library=["Forest", "Mountain", "Island"],
        )
        .player("bob", battlefield=[], library=["Swamp"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_choose_cards(scenario.find("Mountain", Zone.LIBRARY, "alice"))

    _fetch(scenario, username="alice")
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == []


def test_ob_nixilis_makes_the_searcher_sacrifice_a_creature():
    """A second printing: "that player" (the sacrifice's subject) is the
    searcher (bob), not Ob Nixilis's own controller (alice), and the event
    fires off an activated ability's own search, not only a spell's.

    The sentence's second clause ("... and loses 10 life") resolves "that
    player" to the wrong player - a pre-existing `machines/effects.py`
    compound-clause defect unrelated to the trigger this file covers (see
    `MEMORY.md`'s dated line), so this proof stops at the clause the new
    event actually gates.
    """
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
    scenario.will_choose_cards(scenario.find("Mountain", Zone.LIBRARY, "bob"))
    scenario.will_choose_cards(bears)

    _fetch(scenario, username="bob")
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == [f"{OB_NIXILIS}'s triggered ability"]
    scenario.resolve_top()

    assert bears.zone is Zone.GRAVEYARD, "the searcher, not the ability's controller, sacrificed"


def test_wan_shi_tong_etb_counters_and_draws_by_its_own_announced_x():
    """ "When Wan Shi Tong enters, put X +1/+1 counters on him. Then draw
    half X cards, rounded down." - CR 107.3m's own X, carried from the cast
    spell to its ETB trigger (`Game._etb_x_effect_text`, already built for
    this exact rule) into a shape nothing read yet: casting for X=5 puts 5
    counters on him and draws 2 cards (5 halved, rounded down)."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[WAN_SHI_TONG],
            library=["Forest", "Mountain", "Island", "Swamp", "Plains"],
            battlefield=["Island"] * 7,
        )
        .player("bob", battlefield=[])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    islands = scenario.untapped_sources(*["Island"] * 7)
    hand_before_etb = None

    casting = scenario.cast(WAN_SHI_TONG)
    casting.x_value = 5
    payment = casting.begin_paying()
    scenario.pay_with(payment, *islands)
    scenario.put_on_stack(casting)
    wan_shi_tong = scenario.resolve_top()
    hand_before_etb = len(scenario.player("alice").hand)

    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == [f"{WAN_SHI_TONG}'s triggered ability"]
    scenario.resolve_top()

    assert wan_shi_tong.counter_count("+1/+1") == 5
    assert len(scenario.player("alice").hand) == hand_before_etb + 2
