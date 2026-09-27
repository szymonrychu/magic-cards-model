"""A resolved effect that gives the next spell of a quality its controller
casts this turn a cost keyword.

- **Don & Raph, Hard Science** - "Whenever Don & Raph attack, the next
  noncreature spell you cast this turn has affinity for artifacts. (It costs
  {1} less to cast for each artifact you control.)"
- **Archway of Innovation** (second printing - Modern legal, in no deck
  list) - "{U}, {T}: The next spell you cast this turn has improvise." No
  quality at all, a different keyword, and an activated ability rather than
  a trigger.

Rules, each read with `mise run rules:find` in the session that wrote this file:

- **CR 702.41a** - affinity: "This spell costs {1} less to cast for each
  [text] you control."
- **CR 702.126a** - improvise: each artifact tapped pays for {1} of the
  generic cost.
- **CR 601.2f** - the reduction applies while the total cost is determined.
- **CR 601.2i** - the spell "becomes cast" there, which is what makes it the
  "next" one and uses the grant up.
- **CR 514.2** - "this turn" ends with the turn.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _resolve_everything(scenario: Scenario) -> None:
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()


def _don_and_raph(*, hand, lands=(), attack=True):
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Don & Raph, Hard Science", "Ornithopter", "Memnite", *lands],
            hand=list(hand),
            library=["Island"] * 8,
        )
        .player("bob", library=["Island"] * 8)
        .build()
    )
    if attack:
        scenario.start_at(Step.DECLARE_ATTACKERS)
        scenario.attack_with(scenario.creature("Don & Raph, Hard Science", "alice"))
        _resolve_everything(scenario)
    scenario.start_at(Step.POSTCOMBAT_MAIN)
    return scenario


def _cast(scenario, name, caster="alice", **kwargs):
    card = scenario.find(name, Zone.HAND, caster)
    spell = scenario.game.cast(
        card,
        caster,
        mana_sources=[
            permanent
            for permanent in scenario.game.permanents_controlled_by(caster)
            if permanent.card.is_land
        ],
        **kwargs,
    )
    _resolve_everything(scenario)
    return spell


def _tapped_lands(scenario):
    return [
        permanent
        for permanent in scenario.game.permanents_controlled_by("alice")
        if permanent.card.is_land and permanent.tapped
    ]


# -- Don & Raph: the next noncreature spell has affinity for artifacts ----


def test_the_next_noncreature_spell_costs_one_less_per_artifact():
    """Two artifacts (Ornithopter, Memnite): Mind Stone's {2} is paid in full
    by affinity, with no land at all."""
    scenario = _don_and_raph(hand=["Mind Stone"])
    _cast(scenario, "Mind Stone")
    assert "Mind Stone" in scenario.battlefield_names()


def test_without_the_attack_the_spell_costs_its_full_price():
    scenario = _don_and_raph(hand=["Mind Stone"], attack=False)
    with pytest.raises(ValueError):
        _cast(scenario, "Mind Stone")


def test_only_the_next_one_is_cheaper():
    """Mind Stone is the next noncreature spell; Sol Ring after it pays {1}."""
    scenario = _don_and_raph(hand=["Mind Stone", "Sol Ring"], lands=["Plains"])
    _cast(scenario, "Mind Stone")
    assert not _tapped_lands(scenario)
    _cast(scenario, "Sol Ring")
    assert len(_tapped_lands(scenario)) == 1


def test_a_creature_spell_in_between_neither_benefits_nor_uses_it_up():
    """Signal Pest ({1}, an artifact creature) is not noncreature: it pays its
    {1}, and Mind Stone after it is still the next noncreature spell."""
    scenario = _don_and_raph(hand=["Signal Pest", "Mind Stone"], lands=["Plains"])
    _cast(scenario, "Signal Pest")
    assert len(_tapped_lands(scenario)) == 1
    _cast(scenario, "Mind Stone")
    assert "Mind Stone" in scenario.battlefield_names()
    assert len(_tapped_lands(scenario)) == 1


def test_the_reduction_counts_artifacts_as_the_cost_is_determined():
    """CR 601.2f: a third artifact (Signal Pest) cast first makes Mind Stone's
    reduction 3 - still capped at the {2} it costs, never below {0}."""
    scenario = _don_and_raph(hand=["Signal Pest", "Mind Stone"], lands=["Plains"])
    _cast(scenario, "Signal Pest")
    _cast(scenario, "Mind Stone")
    assert "Mind Stone" in scenario.battlefield_names()


def test_it_lasts_only_this_turn():
    scenario = _don_and_raph(hand=["Mind Stone"])
    while scenario.game.turn.active_player == "alice":
        scenario.advance()
    while scenario.game.turn.active_player != "alice":
        scenario.advance()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    with pytest.raises(ValueError):
        _cast(scenario, "Mind Stone")


def test_the_grant_is_recorded_for_its_controller_only():
    scenario = _don_and_raph(hand=["Mind Stone"])
    (grant,) = scenario.game.next_spell_keyword_grants
    assert grant.controller == "alice"
    assert grant.line == "Affinity for artifacts"


# -- Archway of Innovation: the next spell has improvise -------------------


def _archway(hand):
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Archway of Innovation", "Island", "Forest", "Ornithopter", "Memnite"],
            hand=list(hand),
            library=["Island"] * 8,
        )
        .player("bob", library=["Island"] * 8)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    archway = scenario.find("Archway of Innovation", Zone.BATTLEFIELD, "alice")
    island = scenario.find("Island", Zone.BATTLEFIELD, "alice")
    scenario.activate(archway, island, index=1)
    _resolve_everything(scenario)
    return scenario


def _artifacts(scenario):
    return [
        permanent
        for permanent in scenario.game.permanents_controlled_by("alice")
        if permanent.name in ("Ornithopter", "Memnite")
    ]


def test_archway_gives_the_next_spell_improvise_even_a_creature():
    """Grizzly Bears ({1}{G}): the Forest pays {G}, an artifact tapped for
    improvise pays the {1}."""
    scenario = _archway(["Grizzly Bears"])
    bears = scenario.find("Grizzly Bears", Zone.HAND, "alice")
    ornithopter = scenario.find("Ornithopter", Zone.BATTLEFIELD, "alice")
    forest = scenario.find("Forest", Zone.BATTLEFIELD, "alice")
    scenario.game.cast(bears, "alice", mana_sources=[forest], improvise=[ornithopter])
    _resolve_everything(scenario)
    assert "Grizzly Bears" in scenario.battlefield_names()
    assert ornithopter.tapped


def test_archway_improvise_is_gone_after_the_next_spell():
    scenario = _archway(["Memnite", "Signal Pest"])
    memnite = scenario.find("Memnite", Zone.HAND, "alice")
    scenario.game.cast(memnite, "alice", mana_sources=[])
    _resolve_everything(scenario)
    pest = scenario.find("Signal Pest", Zone.HAND, "alice")
    with pytest.raises(ValueError):
        scenario.game.cast(pest, "alice", mana_sources=[], improvise=_artifacts(scenario)[:1])
    assert pest.zone is Zone.HAND


def test_without_archway_no_improvise():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Forest", "Ornithopter"],
            hand=["Grizzly Bears"],
            library=["Island"] * 4,
        )
        .player("bob", library=["Island"] * 4)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.HAND, "alice")
    with pytest.raises(ValueError):
        scenario.game.cast(
            bears,
            "alice",
            mana_sources=[scenario.find("Forest", Zone.BATTLEFIELD, "alice")],
            improvise=[scenario.find("Ornithopter", Zone.BATTLEFIELD, "alice")],
        )
