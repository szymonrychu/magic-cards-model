"""Scenario: "When [this permanent] dies, return it to the battlefield
[tapped][ and][ transformed] under its owner's control[ with N `<kind>`
counters on it]." - the Ojer cycle's own death trigger (Kamigawa: Neon
Dynasty), read generally by `machines/effects.py` rather than pinned to one
printing.

Both cards' oracle text was pulled with `scripts/add_card.py` and verified
against `src/magic_cards_model/data/printings/`:

- **Ojer Taq, Deepest Foundation // Temple of Civilization** (the pool card
  this follow-up names): "When Ojer Taq dies, return it to the battlefield
  tapped and transformed under its owner's control." No trailing counters.
- **Ojer Pakpatiq, Deepest Epoch // Temple of Cyclical Time** (off-pool,
  added here to prove the parser generalises rather than reading Ojer Taq's
  exact sentence): "When Ojer Pakpatiq dies, return it to the battlefield
  tapped and transformed under its owner's control with three time counters
  on it." Same template, an extra trailing counters clause the first card
  does not print, and a different back face ({T}: Add {U} rather than {W}).

Rules verified with `mise run rules:find` in this session:

- **CR 700.11** is unrelated (descend); not used here.
- **CR 701.27a** - "To transform a permanent, turn it over so that its other
  face is up."
- **CR 712.14a** - a permanent put onto the battlefield "transformed" enters
  with its back face up (`.rules/MagicCompRules.txt`, section 712).
- **CR 400.7** - a card that changes zones becomes a new object; the dying
  Ojer and the Ojer that returns are not the same permanent, so no state
  (tapped, damage, counters other than what the trigger itself grants)
  carries over except what the sentence names.
- **CR 122.6** - counters put on an object as it enters the battlefield are
  "counters being put on that object", read the same way
  `enter_the_battlefield`'s own docstring already cites it.
- **CR 603.6b** - a "dies" trigger looks back at the game state before the
  event for whether it applies; both cards are simple unconditional death
  triggers, so this is only the general backing for the trigger firing at
  all.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter

from .harness import Scenario


def test_ojer_taq_returns_itself_tapped_and_transformed_when_it_dies():
    scenario = Scenario().player("alice", battlefield=["Ojer Taq, Deepest Foundation"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ojer = scenario.creature("Ojer Taq, Deepest Foundation", "alice")

    scenario.game.destroy(ojer)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert ojer.zone is Zone.BATTLEFIELD
    assert ojer.controller == "alice"
    assert ojer.transformed is True
    assert ojer.name == "Temple of Civilization"
    assert ojer.tapped is True


def test_ojer_taq_does_not_return_if_it_left_the_graveyard_first():
    """CR 113.7a: the trigger exists independently of its source, and
    CR 608.2's ordinary "the object is gone" case - bob exiles alice's
    graveyard with Tormod's Crypt in response to the death trigger, so when
    that trigger resolves Ojer Taq is in exile, not in a graveyard, and
    nothing returns."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Ojer Taq, Deepest Foundation"])
        .player("bob", battlefield=["Tormod's Crypt"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ojer = scenario.creature("Ojer Taq, Deepest Foundation", "alice")

    scenario.game.destroy(ojer)
    scenario.game.put_triggers_on_stack()
    scenario.pass_priority("alice")

    crypt = scenario.find("Tormod's Crypt", Zone.BATTLEFIELD, "bob")
    scenario.activate(crypt, username="bob", targets=["alice"])
    scenario.resolve_top()  # the Crypt exiles alice's graveyard

    assert ojer.zone is Zone.EXILE

    scenario.resolve_top()  # Ojer Taq's own death trigger, nothing to return

    assert ojer.zone is Zone.EXILE, "an ability whose card has moved on does nothing"
    assert "Ojer Taq, Deepest Foundation" not in scenario.battlefield_names()


def test_off_pool_ojer_pakpatiq_returns_transformed_with_its_own_time_counters():
    """Off-pool proof card: same death-trigger template as Ojer Taq, plus a
    trailing "with three time counters on it" the first card does not print.
    """
    scenario = Scenario().player("alice", battlefield=["Ojer Pakpatiq, Deepest Epoch"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ojer = scenario.creature("Ojer Pakpatiq, Deepest Epoch", "alice")

    scenario.game.destroy(ojer)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert ojer.zone is Zone.BATTLEFIELD
    assert ojer.transformed is True
    assert ojer.name == "Temple of Cyclical Time"
    assert ojer.tapped is True
    assert ojer.counters[Counter.TIME] == 3
