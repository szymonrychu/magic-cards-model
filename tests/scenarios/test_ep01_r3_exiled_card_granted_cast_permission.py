"""An exiled card granted its own cast-from-exile permission (EP-01 round 3, T4).

Monk Class, level 3: "At the beginning of your upkeep, exile the top card of
your library. For as long as it remains exiled, it has "You may cast this card
from exile as long as you've cast another spell this turn."" The quoted line is
an ability of the exiled card itself, read by the same reader as a printed
"You may cast this card from exile ..." line (Misthollow Griffin), with its
condition checked whenever the card would be cast. No other printing legal in
Modern, Pioneer or Standard carries the "for as long as it remains exiled, it
has" grant (MEMORY.md, 2026-10-12).

Rules read with `mise run rules:find` in the session that wrote this:

- **CR 601.3** - a player may begin to cast a spell only if a rule or effect
  allows it from the zone it is in.
- **CR 604.6** - some static abilities function from a zone other than the
  battlefield; the granted line functions from exile.
- **CR 400.7** - a card that leaves exile is a new object; the grant does not
  follow it.
- **CR 716.2a** - a Class's level-3 ability exists only at level 3.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.casting import why_cannot_cast_from
from magic_cards_model.machines.casting.permissions import CAST_PERMISSION
from magic_cards_model.models import Zone
from tests.scenarios.harness import PlayedScenario, Scenario

LANDS = ["Mountain", "Mountain", "Island", "Island", "Plains"]


def _board(*, level: int = 3, library=None, hand=()) -> PlayedScenario:
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Monk Class", *LANDS],
            hand=list(hand),
            library=list(library or ["Lightning Bolt", "Island", "Island", "Island"]),
        )
        .player("bob", library=["Island"] * 6)
        .build()
    )
    scenario.find("Monk Class", Zone.BATTLEFIELD, "alice").class_level = level
    scenario.start_at(Step.UNTAP)
    return scenario


def _to_main_phase(scenario: PlayedScenario) -> None:
    while scenario.step is not Step.PRECOMBAT_MAIN:
        scenario.advance()
        scenario.game.put_triggers_on_stack()
        while scenario.game.stack:
            scenario.resolve_top()
            scenario.game.put_triggers_on_stack()


def _resolve_everything(scenario: PlayedScenario) -> None:
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()


def _refusal(scenario: PlayedScenario, name: str) -> str | None:
    card = scenario.find(name, Zone.EXILE, None)
    return why_cannot_cast_from(card, "alice", Zone.EXILE, scenario.game)


def _cast_from_exile(scenario: PlayedScenario, name: str, targets) -> None:
    casting = scenario.cast(name, username="alice", from_zone=Zone.EXILE)
    casting.use_keyword(CAST_PERMISSION)
    casting.choose_targets(targets)
    scenario.auto_pay(casting.begin_paying(), username="alice")
    scenario.put_on_stack(casting)
    _resolve_everything(scenario)


def test_the_upkeep_exiles_the_top_card_and_grants_it_the_permission():
    scenario = _board()
    _to_main_phase(scenario)

    bolt = scenario.find("Lightning Bolt", Zone.EXILE, None)
    assert bolt.zone is Zone.EXILE
    assert any("cast this card from exile" in line for line in bolt.granted_ability_texts)


def test_the_exiled_card_cannot_be_cast_before_another_spell_this_turn():
    scenario = _board()
    _to_main_phase(scenario)

    assert _refusal(scenario, "Lightning Bolt") is not None


def test_after_another_spell_the_exiled_card_is_cast_from_exile():
    scenario = _board(hand=["Opt"])
    _to_main_phase(scenario)
    scenario.cast_onto_stack("Opt", username="alice", auto=True)
    _resolve_everything(scenario)

    assert _refusal(scenario, "Lightning Bolt") is None
    _cast_from_exile(scenario, "Lightning Bolt", ["bob"])

    assert scenario.player("bob").life == 17
    bolt = scenario.find("Lightning Bolt", Zone.GRAVEYARD, "alice")
    assert not bolt.granted_ability_texts, "CR 400.7: the grant stays behind in exile"


def test_a_level_two_monk_class_exiles_nothing():
    scenario = _board(level=2)
    _to_main_phase(scenario)

    assert scenario.player("alice").library[0].name == "Lightning Bolt"
    assert not scenario.game.exile
