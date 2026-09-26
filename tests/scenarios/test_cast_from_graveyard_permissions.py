"""A permanent's static permission to cast spells of a quality from its
controller's graveyard, with the "enters with a counter" rider some print.

- **Leonardo, Sewer Samurai** - "During your turn, you may cast creature
  spells with power or toughness 1 or less from your graveyard. If you cast a
  spell this way, that creature enters with a finality counter on it."
- **Noctis, Prince of Lucis** (second printing - legal in Modern, Pioneer and
  Standard, in no deck list) - "You may cast artifact spells from your
  graveyard by paying 3 life in addition to paying their other costs. If you
  cast a spell this way, that artifact enters with a finality counter on it."
  A card type instead of a power/toughness bound, no "during your turn", and
  an additional cost.

Rules, each read with `mise run rules:find` in the session that wrote this file:

- **CR 601.3** - a spell can be cast only if a rule or effect allows it; the
  permission is the permanent's static ability (CR 611.3d).
- **CR 614.1c** - "enters with ..." is a replacement effect, so the counter
  is on the permanent as it enters.
- **CR 122.1h** - a finality counter: "If this permanent would be put into a
  graveyard from the battlefield, exile it instead."
- **CR 601.2f** - the 3 life is an additional cost, added to the total cost.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.legal_actions import legal_actions
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario

CAST_PERMISSION = "Cast permission"


def _resolve_everything(scenario: Scenario) -> None:
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()


def _cast(scenario, card, caster="alice", keyword=CAST_PERMISSION):
    return scenario.game.cast(
        card,
        caster,
        keyword=keyword,
        mana_sources=scenario.game.permanents_controlled_by(caster),
    )


def _leonardo(graveyard, *, bob_graveyard=(), mana=("Forest", "Forest", "Swamp", "Swamp")):
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Leonardo, Sewer Samurai", *mana],
            graveyard=list(graveyard),
            library=["Forest"] * 6,
        )
        .player("bob", graveyard=list(bob_graveyard), library=["Island"] * 6)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


# -- Leonardo: power or toughness 1 or less, during your turn ----------------


def test_a_one_one_creature_is_cast_from_the_graveyard_and_enters_with_finality():
    scenario = _leonardo(["Llanowar Elves"])
    elves = scenario.find("Llanowar Elves", Zone.GRAVEYARD, "alice")
    _cast(scenario, elves)
    _resolve_everything(scenario)
    elves = scenario.find("Llanowar Elves", Zone.BATTLEFIELD, "alice")
    assert elves.counter_count(Counter.FINALITY) == 1


def test_the_finality_counter_exiles_it_instead_of_the_graveyard():
    scenario = _leonardo(["Llanowar Elves"])
    elves = scenario.find("Llanowar Elves", Zone.GRAVEYARD, "alice")
    _cast(scenario, elves)
    _resolve_everything(scenario)
    elves = scenario.find("Llanowar Elves", Zone.BATTLEFIELD, "alice")
    scenario.game.destroy(elves)
    assert elves.zone is Zone.EXILE


def test_toughness_one_is_enough_even_with_power_two():
    """ "power or toughness 1 or less": Bloodghast is 2/1."""
    scenario = _leonardo(["Bloodghast"])
    ghast = scenario.find("Bloodghast", Zone.GRAVEYARD, "alice")
    _cast(scenario, ghast)
    _resolve_everything(scenario)
    assert scenario.find("Bloodghast", Zone.BATTLEFIELD, "alice").counter_count(Counter.FINALITY)


def test_power_zero_counts_as_one_or_less():
    scenario = _leonardo(["Ornithopter"])
    thopter = scenario.find("Ornithopter", Zone.GRAVEYARD, "alice")
    _cast(scenario, thopter)
    _resolve_everything(scenario)
    assert scenario.find("Ornithopter", Zone.BATTLEFIELD, "alice").zone is Zone.BATTLEFIELD


def test_a_two_two_is_not_covered():
    scenario = _leonardo(["Grizzly Bears"])
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")
    with pytest.raises(ValueError):
        _cast(scenario, bears)
    assert bears.zone is Zone.GRAVEYARD


def test_a_noncreature_spell_is_not_covered():
    scenario = _leonardo(["Shock"])
    shock = scenario.find("Shock", Zone.GRAVEYARD, "alice")
    with pytest.raises(ValueError):
        _cast(scenario, shock)


def test_not_during_an_opponents_turn_even_with_flash():
    """Spectral Sailor (1/1, flash) could be cast at instant speed, but the
    permission is "during your turn" only."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Leonardo, Sewer Samurai", "Island", "Island"],
            graveyard=["Spectral Sailor"],
            library=["Island"] * 6,
        )
        .player("bob", library=["Island"] * 6)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    while scenario.game.turn.active_player == "alice":
        scenario.advance()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sailor = scenario.find("Spectral Sailor", Zone.GRAVEYARD, "alice")
    with pytest.raises(ValueError, match="no Cast permission"):
        _cast(scenario, sailor)


def test_flash_creature_is_cast_at_instant_speed_during_your_own_turn():
    """The permission changes where from, not when: Spectral Sailor keeps its
    flash, so it is castable in alice's own combat."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Leonardo, Sewer Samurai", "Island", "Island"],
            graveyard=["Spectral Sailor"],
            library=["Island"] * 6,
        )
        .player("bob", library=["Island"] * 6)
        .build()
    )
    scenario.start_at(Step.BEGINNING_OF_COMBAT)
    sailor = scenario.find("Spectral Sailor", Zone.GRAVEYARD, "alice")
    _cast(scenario, sailor)
    _resolve_everything(scenario)
    assert scenario.find("Spectral Sailor", Zone.BATTLEFIELD, "alice").counter_count(
        Counter.FINALITY
    )


def test_a_creature_without_flash_still_waits_for_the_main_phase():
    scenario = _leonardo(["Llanowar Elves"])
    scenario.start_at(Step.BEGINNING_OF_COMBAT)
    elves = scenario.find("Llanowar Elves", Zone.GRAVEYARD, "alice")
    with pytest.raises(ValueError):
        _cast(scenario, elves)


def test_an_opponents_graveyard_is_not_yours():
    scenario = _leonardo([], bob_graveyard=["Llanowar Elves"])
    elves = scenario.find("Llanowar Elves", Zone.GRAVEYARD, "bob")
    with pytest.raises(ValueError):
        _cast(scenario, elves)


def test_the_same_creature_cast_from_hand_gets_no_counter():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Leonardo, Sewer Samurai", "Forest"],
            hand=["Llanowar Elves"],
            library=["Forest"] * 6,
        )
        .player("bob", library=["Island"] * 6)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    elves = scenario.find("Llanowar Elves", Zone.HAND, "alice")
    scenario.game.cast(elves, "alice", mana_sources=scenario.game.permanents_controlled_by("alice"))
    _resolve_everything(scenario)
    assert (
        scenario.find("Llanowar Elves", Zone.BATTLEFIELD, "alice").counter_count(Counter.FINALITY)
        == 0
    )


def test_every_qualifying_card_may_be_cast_not_just_one():
    scenario = _leonardo(["Llanowar Elves", "Mogg Fanatic"], mana=("Forest", "Mountain"))
    for name in ("Llanowar Elves", "Mogg Fanatic"):
        _cast(scenario, scenario.find(name, Zone.GRAVEYARD, "alice"))
        _resolve_everything(scenario)
    assert {"Llanowar Elves", "Mogg Fanatic"} <= set(scenario.battlefield_names())


def test_legal_actions_offer_the_qualifying_card_and_not_the_other():
    scenario = _leonardo(["Llanowar Elves", "Grizzly Bears"])
    elves = scenario.find("Llanowar Elves", Zone.GRAVEYARD, "alice")
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")
    offered = {getattr(action, "card_id", None) for action in legal_actions(scenario.game, "alice")}
    assert elves.id in offered
    assert bears.id not in offered


def test_without_leonardo_the_graveyard_is_closed():
    scenario = _leonardo(["Llanowar Elves"])
    scenario.game.destroy(scenario.find("Leonardo, Sewer Samurai", Zone.BATTLEFIELD, "alice"))
    elves = scenario.find("Llanowar Elves", Zone.GRAVEYARD, "alice")
    with pytest.raises(ValueError):
        _cast(scenario, elves)


# -- Noctis: artifact spells, 3 life on top of the other costs --------------


def _noctis(graveyard, *, life=20):
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Noctis, Prince of Lucis", "Plains", "Island", "Swamp"],
            graveyard=list(graveyard),
            library=["Plains"] * 6,
            life=life,
        )
        .player("bob", library=["Island"] * 6)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_noctis_casts_an_artifact_for_its_cost_plus_three_life_with_finality():
    scenario = _noctis(["Mind Stone"])
    stone = scenario.find("Mind Stone", Zone.GRAVEYARD, "alice")
    _cast(scenario, stone)
    assert scenario.player("alice").life == 17
    _resolve_everything(scenario)
    stone = scenario.find("Mind Stone", Zone.BATTLEFIELD, "alice")
    assert stone.counter_count(Counter.FINALITY) == 1
    scenario.game.destroy(stone)
    assert stone.zone is Zone.EXILE


def test_noctis_does_not_cover_a_nonartifact_creature():
    scenario = _noctis(["Llanowar Elves"])
    elves = scenario.find("Llanowar Elves", Zone.GRAVEYARD, "alice")
    with pytest.raises(ValueError):
        _cast(scenario, elves)
    assert scenario.player("alice").life == 20


def test_noctis_covers_an_artifact_creature_too():
    """ "artifact spells" is CR 205.2b's any-of-its-types: Memnite is an
    artifact creature, so it qualifies, and still casts at its own creature
    timing (CR 117.1a)."""
    scenario = _noctis(["Memnite"])
    memnite = scenario.find("Memnite", Zone.GRAVEYARD, "alice")
    _cast(scenario, memnite)
    _resolve_everything(scenario)
    assert scenario.find("Memnite", Zone.BATTLEFIELD, "alice").counter_count(Counter.FINALITY)
    assert scenario.player("alice").life == 17


def test_noctis_cannot_be_used_without_the_life_to_pay():
    """CR 119.4: a player can pay life only if their life total is at least
    that much."""
    scenario = _noctis(["Memnite"], life=2)
    memnite = scenario.find("Memnite", Zone.GRAVEYARD, "alice")
    with pytest.raises(ValueError):
        _cast(scenario, memnite)
    assert memnite.zone is Zone.GRAVEYARD
