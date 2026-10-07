"""Sacrifice branches: "If you can't, ..." and "If you do, ..." riders (NW-06, T3).

- Liege of the Pit / Lord of the Pit / Demonic Taskmaster: "sacrifice a creature
  other than this creature" - CR 701.21a (a player sacrifices only permanents
  they control, and the source is not "other than this creature"); with nothing
  else to sacrifice "If you can't" runs (CR 608.2c).
- Ravenous Demon's back face and Rust Elemental: "If you can't, tap this
  creature and <it deals N damage to you | you lose N life>" - a two-action rider.
- Flame-Kin War Scout: "sacrifice this creature. If you do, this creature deals
  4 damage to that creature." - the entering creature stays the referent across
  the pair and the source deals the damage from its last known information
  (CR 113.7a). Booby Trap's pair, with the drawing player, is read the same way.

CR numbers checked with `mise run rules:find` (rules effective 2026-09-25).
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.abilities import TriggerEvent
from magic_cards_model.machines.effects.registries import trigger_effect_for
from magic_cards_model.models import Zone
from magic_cards_model.support import card_support
from tests.cards import card

from .harness import Scenario


def _drain(scenario) -> None:
    scenario.game.put_triggers_on_stack()
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()


def _notices(scenario) -> list[object]:
    game = scenario.game
    found: list[object] = list(game.continuous_effects.layer_notices)
    for name in type(game).model_fields:
        if name.endswith("_notices"):
            found.extend(getattr(game, name))
    return found


def _outcomes(name: str) -> list[str]:
    return [c.outcome for c in card_support(card(name)).clauses if c.kind != "keyword"]


def _upkeep(alice=(), bob=(), *, setup=None):
    """alice's upkeep with her trigger resolved; returns the scenario."""
    scenario = (
        Scenario().player("alice", battlefield=list(alice)).player("bob", battlefield=list(bob))
    ).build()
    if setup is not None:
        setup(scenario)
    scenario.advance()
    assert scenario.step is Step.UPKEEP
    _drain(scenario)
    return scenario


def test_every_listed_and_proof_card_reads_handled():
    for name in (
        "Liege of the Pit",
        "Lord of the Pit",
        "Ravenous Demon // Archdemon of Greed",
        "Flame-Kin War Scout",
        "Rust Elemental",
        "Demonic Taskmaster",
    ):
        assert set(_outcomes(name)) == {"handled"}, name


# -- "sacrifice a creature other than this creature. If you can't, ..." -------


@pytest.mark.parametrize("demon", ["Liege of the Pit", "Lord of the Pit"])
def test_another_creature_is_sacrificed_and_the_demon_deals_nothing(demon):
    scenario = _upkeep([demon, "Grizzly Bears"])
    assert scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")
    assert scenario.creature(demon, "alice").zone is Zone.BATTLEFIELD
    assert scenario.player("alice").life == 20
    assert _notices(scenario) == []


@pytest.mark.parametrize("demon", ["Liege of the Pit", "Lord of the Pit"])
def test_alone_the_demon_is_not_sacrificed_and_deals_seven_to_its_controller(demon):
    scenario = _upkeep([demon])
    assert scenario.creature(demon, "alice").zone is Zone.BATTLEFIELD
    assert scenario.player("alice").life == 13
    assert scenario.player("bob").life == 20
    assert _notices(scenario) == []


def test_other_than_this_creature_ignores_non_creatures_and_opponents_creatures():
    scenario = _upkeep(["Liege of the Pit", "Mountain"], bob=["Grizzly Bears"])
    assert scenario.player("alice").life == 13
    assert scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "bob")
    assert scenario.find("Mountain", Zone.BATTLEFIELD, "alice")


def test_with_several_candidates_the_controller_chooses_which_one_goes():
    holder = {}

    def setup(scenario):
        holder["keep"] = scenario.creature("Grizzly Bears", "alice")
        holder["lose"] = scenario.creature("Hill Giant", "alice")
        scenario.will_choose_cards(holder["lose"], username="alice")

    scenario = _upkeep(["Liege of the Pit", "Grizzly Bears", "Hill Giant"], setup=setup)
    assert holder["lose"].zone is Zone.GRAVEYARD
    assert holder["keep"].zone is Zone.BATTLEFIELD
    assert scenario.player("alice").life == 20


def test_only_one_creature_is_sacrificed_even_with_two_candidates():
    scenario = _upkeep(["Lord of the Pit", "Grizzly Bears", "Hill Giant"])
    graveyard = [c.name for c in scenario.player("alice").graveyard]
    assert len(graveyard) == 1


def test_it_is_alice_s_upkeep_only():
    scenario = (
        Scenario()
        .player("bob", battlefield=["Grizzly Bears"])
        .player("alice", battlefield=["Liege of the Pit"])
        .build()
    )
    scenario.advance()
    _drain(scenario)
    assert scenario.player("alice").life == 20


def test_the_bare_sacrifice_other_than_this_reads_without_a_rider():
    """Demonic Taskmaster: no "If you can't" sentence at all."""
    scenario = _upkeep(["Demonic Taskmaster", "Grizzly Bears"])
    assert scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")
    assert scenario.creature("Demonic Taskmaster", "alice").zone is Zone.BATTLEFIELD
    assert scenario.player("alice").life == 20


def test_the_bare_sacrifice_other_than_this_never_sacrifices_the_source():
    scenario = _upkeep(["Demonic Taskmaster"])
    assert scenario.creature("Demonic Taskmaster", "alice").zone is Zone.BATTLEFIELD


# -- "sacrifice another artifact. If you can't, tap this creature and you lose 4 life" --


def test_rust_elemental_sacrifices_another_artifact():
    scenario = _upkeep(["Rust Elemental", "Mind Stone"])
    assert scenario.find("Mind Stone", Zone.GRAVEYARD, "alice")
    elemental = scenario.creature("Rust Elemental", "alice")
    assert elemental.zone is Zone.BATTLEFIELD and not elemental.tapped
    assert scenario.player("alice").life == 20


def test_rust_elemental_never_sacrifices_itself_it_taps_and_loses_four_life():
    scenario = _upkeep(["Rust Elemental"])
    elemental = scenario.creature("Rust Elemental", "alice")
    assert elemental.zone is Zone.BATTLEFIELD
    assert elemental.tapped
    assert scenario.player("alice").life == 16
    assert _notices(scenario) == []


def test_rust_elemental_ignores_an_opponents_artifact():
    scenario = _upkeep(["Rust Elemental"], bob=["Mind Stone"])
    assert scenario.creature("Rust Elemental", "alice").tapped
    assert scenario.player("alice").life == 16
    assert scenario.find("Mind Stone", Zone.BATTLEFIELD, "bob")


# -- Ravenous Demon // Archdemon of Greed: "tap this creature and it deals 9 damage to you" --


def _archdemon_upkeep(alice=()):
    def setup(scenario):
        scenario.creature("Ravenous Demon", "alice").transform()

    return _upkeep(["Ravenous Demon", *alice], setup=setup)


def test_archdemon_sacrifices_a_human_when_it_has_one():
    scenario = _archdemon_upkeep(["Elite Vanguard"])
    assert scenario.find("Elite Vanguard", Zone.GRAVEYARD, "alice")
    assert scenario.player("alice").life == 20


def test_archdemon_without_a_human_taps_and_deals_nine_to_its_controller():
    scenario = _archdemon_upkeep(["Grizzly Bears"])
    archdemon = scenario.creature("Archdemon of Greed", "alice")
    assert archdemon.tapped
    assert scenario.player("alice").life == 11
    assert scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice")
    assert _notices(scenario) == []


def test_archdemon_alone_taps_and_deals_nine():
    scenario = _archdemon_upkeep()
    assert scenario.creature("Archdemon of Greed", "alice").tapped
    assert scenario.player("alice").life == 11


def test_archdemon_is_not_its_own_human_sacrifice():
    """Archdemon of Greed is a Demon, not a Human (CR 205.3m: creature types),
    so with no Human of its own to give it taps and takes the damage."""
    scenario = _archdemon_upkeep()
    assert scenario.creature("Archdemon of Greed", "alice").zone is Zone.BATTLEFIELD


# -- Flame-Kin War Scout: "sacrifice this creature. If you do, ... damage to that creature" --


def _scout_board(enter="Colossal Dreadmaw", *, bob=()):
    scenario = (
        Scenario()
        .player("alice", battlefield=["Flame-Kin War Scout"], hand=[enter])
        .player("bob", battlefield=list(bob), hand=[] if enter != "Colossal Dreadmaw" else [])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_the_scout_is_sacrificed_and_deals_four_to_the_creature_that_entered():
    scenario = _scout_board()
    giant = scenario.put_onto_battlefield("Colossal Dreadmaw", "alice")
    _drain(scenario)
    scout = scenario.find("Flame-Kin War Scout", Zone.GRAVEYARD, "alice")
    assert scout.zone is Zone.GRAVEYARD
    assert giant.damage == 4
    assert _notices(scenario) == []


def test_the_scout_kills_a_small_creature_with_its_last_known_power():
    scenario = _scout_board("Grizzly Bears")
    bears = scenario.put_onto_battlefield("Grizzly Bears", "alice")
    _drain(scenario)
    assert bears.zone is Zone.GRAVEYARD
    assert scenario.find("Flame-Kin War Scout", Zone.GRAVEYARD, "alice")


def test_an_opponents_creature_entering_is_the_referent_too():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Flame-Kin War Scout"])
        .player("bob", hand=["Colossal Dreadmaw"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    giant = scenario.put_onto_battlefield("Colossal Dreadmaw", "bob")
    _drain(scenario)
    assert giant.damage == 4
    assert scenario.find("Flame-Kin War Scout", Zone.GRAVEYARD, "alice")


def test_the_scout_does_not_trigger_on_itself_or_on_a_noncreature():
    scenario = (
        Scenario().player("alice", hand=["Flame-Kin War Scout", "Mountain"]).player("bob").build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scout = scenario.put_onto_battlefield("Flame-Kin War Scout", "alice")
    scenario.put_onto_battlefield("Mountain", "alice")
    _drain(scenario)
    assert scout.zone is Zone.BATTLEFIELD
    assert scenario.player("alice").life == 20


def test_when_the_scout_is_gone_in_response_nothing_deals_the_damage():
    """CR 608.2c: the "If you do" damage needs the sacrifice to have happened;
    a source removed in response is not sacrificed, so no damage follows."""
    scenario = _scout_board()
    giant = scenario.put_onto_battlefield("Colossal Dreadmaw", "alice")
    scenario.game.put_triggers_on_stack()
    scout = scenario.creature("Flame-Kin War Scout", "alice")
    scenario.game.sacrifice(scout)
    scenario.resolve_top()
    assert giant.damage == 0
    assert giant.zone is Zone.BATTLEFIELD


# -- the pair is also readable as a trigger effect text (cross-task clauses) ----


def _reads(event, text):
    effect = trigger_effect_for("Some Card", event, text)
    assert effect is not None, text
    assert "notice_only" not in getattr(effect, "__qualname__", ""), text


def test_booby_traps_pair_reads_with_the_drawing_player_as_recipient():
    _reads(
        TriggerEvent.DRAWS_A_CARD,
        "sacrifice this artifact. If you do, this artifact deals 10 damage to that player.",
    )


@pytest.mark.parametrize(
    "text",
    [
        "sacrifice this creature. If you do, this creature deals 4 damage to that creature.",
        "sacrifice this creature. If you do, this creature deals 3 damage to that player.",
    ],
)
def test_the_self_sacrifice_pair_reads_on_enters_and_damage_events(text):
    _reads(TriggerEvent.ENTERS_THE_BATTLEFIELD, text)


@pytest.mark.parametrize(
    "text",
    [
        "sacrifice a creature other than this creature. If you can't, this creature deals 7 damage "
        "to you if the moon is full.",
        "sacrifice this creature. If you do, this creature deals 4 damage to that creature "
        "unless you control a Dragon.",
    ],
)
def test_a_trailing_condition_is_never_dropped(text):
    effect = trigger_effect_for("Some Card", TriggerEvent.BEGINNING_OF_STEP, text)
    assert effect is None or "notice_only" in effect.__qualname__
