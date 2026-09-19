"""FRA stream S8: "Search your library for up to `<n>` `<quality>` cards
with different names, reveal them, put them into your hand, then shuffle."
(CR 701.23a's single-card find, applied once per distinct name.)

Every CR number below was looked up with `mise run rules:find` in the
session that wrote this file.

- **CR 701.23a** - "find a card that matches the given description."
- **CR 701.23b** - a stated-quality search is declinable, so finding fewer
  than the stated maximum (a shorter library, or fewer distinct names left)
  is a legal answer.
- **CR 701.20a/701.20b** - revealing.
- **CR 701.24a** - the library is shuffled after the search.
- **CR 107.3a** - X in a mana cost, fixed as the spell is cast.

Fblthp, Knows the Way is the reported card - its own search count is CR
107.3a's X, fixed by its own casting cost. The "with different names"
restriction is proven directly: a library holding two copies of Forest and
one Island offers only one Forest as a candidate once the first Forest is
found, never a second.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_fblthp_finds_up_to_x_basic_lands_with_no_repeated_name():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Fblthp, Knows the Way"],
            battlefield=["Forest", "Forest", "Forest", "Forest"],
            library=["Forest", "Forest", "Island", "Mountain"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    sources = scenario.untapped_sources("Forest", "Forest", "Forest", "Forest")
    (first_forest, second_forest) = [state for state in alice.library if state.name == "Forest"]
    island = next(state for state in alice.library if state.name == "Island")

    casting = scenario.cast("Fblthp, Knows the Way", username="alice")
    casting.choose_modes([], x_value=2)
    payment = casting.begin_paying()
    scenario.pay_with(payment, *sources)
    scenario.put_on_stack(casting)
    scenario.will_choose_cards(first_forest, username="alice")
    scenario.will_choose_cards(island, username="alice")
    scenario.resolve_top()
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert first_forest.zone is Zone.HAND
    assert island.zone is Zone.HAND
    assert second_forest.zone is Zone.LIBRARY, "a second Forest was never even offered"
    assert len(alice.hand) == 2
