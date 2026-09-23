"""Exile a card from your graveyard, then create a token that's a copy of it.

    Exile target <filter> card [with mana value <X|less than <self>'s
    loyalty>] from your graveyard. Create a token that's a copy of <it|that
    card>[, except <exception>]. [<rider>]

"It"/"that card" is CR 608.2c anaphora back to the card the first
sentence just exiled - never the ability's own source. Before this reader
existed, `parse_mixed_effect` split the two sentences apart and read the
second one's bare "it" as the *source*, so Nahiri, the Unforgiving's 0 made
a token copy of Nahiri herself.

Every CR number here was read in full with `mise run rules:find` in the
session that wrote this file:

- **CR 707.2** - a copy acquires the copiable values of the original's
  characteristics; counters and other effects are not copied.
- **CR 707.9b** - "except it's 1/1" is a characteristic change made as part
  of the copying process.
- **CR 608.2b** - a target that left the zone it was in is illegal, and any
  part of the effect that needs information about it does not happen.
- **CR 606.4** / **CR 107.3a** - a -X loyalty cost removes X loyalty counters
  as the ability is activated, and X is announced then.
- **CR 603.7c** - the delayed exile does not reach an object that already
  left the battlefield.

Offspring's Revenge is the proof printing: legal in Modern and Pioneer
(Scryfall legalities, 2026-09-23), in no deck under
`magic-cards-model-api/decks/`, a triggered ability rather than a loyalty
one, with a CR 707.9b exception and an "until your next turn" haste rider
instead of an end-step exile.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import has_keyword
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _walk_to(scenario, step: Step) -> None:
    while scenario.step is not step:
        scenario.advance()
        while not scenario.game.stack_is_empty:
            scenario.resolve_top()


def _resolve_stack(scenario) -> None:
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()


def _has_haste(scenario, permanent) -> bool:
    return has_keyword(permanent, "Haste", scenario.game)


def _tokens(scenario) -> list:
    return [state for state in scenario.game.battlefield if state.token]


# --------------------------------------------------------------------------
# Nahiri, the Unforgiving's 0
# --------------------------------------------------------------------------


def _nahiri_board(graveyard: list[str]):
    scenario = (
        Scenario()
        .player("alice", hand=["Nahiri, the Unforgiving"], graveyard=graveyard)
        .player("bob", library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    nahiri = scenario.put_onto_battlefield("Nahiri, the Unforgiving")
    assert nahiri.loyalty == 5
    return scenario, nahiri


def test_nahiri_zero_exiles_the_card_and_copies_it_not_herself():
    scenario, nahiri = _nahiri_board(["Hill Giant"])
    giant = scenario.find("Hill Giant", Zone.GRAVEYARD, "alice")

    scenario.activate(nahiri, index=2, targets=[giant])
    _resolve_stack(scenario)

    assert giant.zone is Zone.EXILE
    (token,) = _tokens(scenario)
    assert token.name == "Hill Giant", "the copy is of the exiled card, never of Nahiri"
    assert _has_haste(scenario, token)
    assert scenario.can_attack(token)


def test_nahiri_zero_token_is_exiled_at_the_next_end_step():
    scenario, nahiri = _nahiri_board(["Hill Giant"])
    giant = scenario.find("Hill Giant", Zone.GRAVEYARD, "alice")
    scenario.activate(nahiri, index=2, targets=[giant])
    _resolve_stack(scenario)

    _walk_to(scenario, Step.END_STEP)

    assert _tokens(scenario) == []
    assert giant.zone is Zone.EXILE, "the exiled card stays exiled"
    assert nahiri.zone is Zone.BATTLEFIELD


def test_nahiri_zero_bound_is_her_current_loyalty():
    """The mana value is compared to the loyalty Nahiri has now: at 5, a mana
    value 4 creature card is a legal target."""
    scenario, nahiri = _nahiri_board(["Serra Angel", "Hill Giant"])
    angel = scenario.find("Serra Angel", Zone.GRAVEYARD, "alice")

    try:
        scenario.activate(nahiri, index=2, targets=[angel])
        refused = None
    except ValueError as error:
        refused = error
    assert refused is not None, "Serra Angel is mana value 5, not less than 5"

    giant = scenario.find("Hill Giant", Zone.GRAVEYARD, "alice")
    scenario.activate(nahiri, index=2, targets=[giant])
    _resolve_stack(scenario)
    assert [t.name for t in _tokens(scenario)] == ["Hill Giant"]


def test_nahiri_zero_does_nothing_if_the_target_left_the_graveyard():
    """CR 608.2b: the target is illegal, so the ability does not resolve and
    no token is made."""
    scenario, nahiri = _nahiri_board(["Hill Giant"])
    giant = scenario.find("Hill Giant", Zone.GRAVEYARD, "alice")
    scenario.activate(nahiri, index=2, targets=[giant])

    scenario.game.exile_permanent(giant)
    _resolve_stack(scenario)

    assert _tokens(scenario) == []
    assert scenario.game.delayed_triggers.triggers == []


def test_nahiri_zero_exile_skips_a_token_that_already_died():
    scenario, nahiri = _nahiri_board(["Hill Giant"])
    giant = scenario.find("Hill Giant", Zone.GRAVEYARD, "alice")
    scenario.activate(nahiri, index=2, targets=[giant])
    _resolve_stack(scenario)
    (token,) = _tokens(scenario)

    scenario.game.destroy(token)
    _walk_to(scenario, Step.END_STEP)

    assert _tokens(scenario) == []
    assert nahiri.zone is Zone.BATTLEFIELD


# --------------------------------------------------------------------------
# Tamiyo, Compleated Sage's -X
# --------------------------------------------------------------------------


def _tamiyo_board(graveyard: list[str]):
    scenario = (
        Scenario()
        .player("alice", hand=["Tamiyo, Compleated Sage"], graveyard=graveyard)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    tamiyo = scenario.put_onto_battlefield("Tamiyo, Compleated Sage")
    assert tamiyo.loyalty == 5
    return scenario, tamiyo


def test_tamiyo_minus_x_takes_x_loyalty_at_activation():
    scenario, tamiyo = _tamiyo_board(["Mind Stone"])
    stone = scenario.find("Mind Stone", Zone.GRAVEYARD, "alice")

    scenario.activate(tamiyo, index=1, targets=[stone], x_value=2)

    assert tamiyo.loyalty == 3, "CR 606.4: the cost is paid as it is activated"
    _resolve_stack(scenario)

    assert stone.zone is Zone.EXILE
    (token,) = _tokens(scenario)
    assert token.name == "Mind Stone"


def test_tamiyo_copy_stays_there_is_no_end_step_removal():
    scenario, tamiyo = _tamiyo_board(["Mind Stone"])
    stone = scenario.find("Mind Stone", Zone.GRAVEYARD, "alice")
    scenario.activate(tamiyo, index=1, targets=[stone], x_value=2)
    _resolve_stack(scenario)

    _walk_to(scenario, Step.END_STEP)

    assert [t.name for t in _tokens(scenario)] == ["Mind Stone"]


def test_tamiyo_minus_x_cannot_target_a_card_whose_mana_value_is_not_x():
    scenario, tamiyo = _tamiyo_board(["Hill Giant"])
    giant = scenario.find("Hill Giant", Zone.GRAVEYARD, "alice")

    try:
        scenario.activate(tamiyo, index=1, targets=[giant], x_value=2)
        refused = False
    except ValueError:
        refused = True

    assert refused, "Hill Giant is mana value 4, not X = 2"


def test_tamiyo_copy_of_a_creature_card():
    scenario, tamiyo = _tamiyo_board(["Hill Giant"])
    giant = scenario.find("Hill Giant", Zone.GRAVEYARD, "alice")

    scenario.activate(tamiyo, index=1, targets=[giant], x_value=4)
    _resolve_stack(scenario)

    assert tamiyo.loyalty == 1
    (token,) = _tokens(scenario)
    assert (token.power, token.toughness) == (3, 3)


# --------------------------------------------------------------------------
# Offspring's Revenge - the proof printing
# --------------------------------------------------------------------------


def _revenge_board(graveyard: list[str]):
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Offspring's Revenge"],
            graveyard=graveyard,
            library=["Plains"] * 5,
        )
        .player("bob", library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_offspring_revenge_copies_the_exiled_card_as_a_hasty_one_one():
    scenario = _revenge_board(["Hill Giant"])
    giant = scenario.find("Hill Giant", Zone.GRAVEYARD, "alice")
    scenario.will_choose_targets(giant)

    _walk_to(scenario, Step.BEGINNING_OF_COMBAT)

    assert giant.zone is Zone.EXILE
    (token,) = _tokens(scenario)
    assert token.name == "Hill Giant"
    assert (token.power, token.toughness) == (1, 1), "CR 707.9b"
    assert _has_haste(scenario, token)


def test_offspring_revenge_haste_lasts_until_its_controllers_next_turn():
    scenario = _revenge_board(["Hill Giant"])
    giant = scenario.find("Hill Giant", Zone.GRAVEYARD, "alice")
    scenario.will_choose_targets(giant)
    _walk_to(scenario, Step.BEGINNING_OF_COMBAT)
    (token,) = _tokens(scenario)

    _walk_to(scenario, Step.END_STEP)
    assert _has_haste(scenario, token), "still there through the end of this turn"
    while scenario.turn.active_player == "alice":
        scenario.advance()
    while scenario.turn.active_player == "bob":
        scenario.advance()

    assert not _has_haste(scenario, token), "gone once alice's next turn began"
    assert token.zone is Zone.BATTLEFIELD, "the token itself stays"


def test_offspring_revenge_with_an_empty_graveyard_makes_nothing():
    scenario = _revenge_board([])

    _walk_to(scenario, Step.BEGINNING_OF_COMBAT)

    assert _tokens(scenario) == []


def test_every_listed_clause_is_handled_by_the_sweep():
    from magic_cards_model.support import HANDLED, card_support
    from tests.cards import card

    for name in ("Nahiri, the Unforgiving", "Tamiyo, Compleated Sage", "Offspring's Revenge"):
        for clause in card_support(card(name)).clauses:
            if clause.kind == "keyword":
                continue
            assert clause.outcome == HANDLED, (name, clause.text, clause.outcome)
