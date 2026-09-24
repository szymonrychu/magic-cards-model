"""A permanent already on the battlefield becoming a copy of another object
(CR 707.4), with CR 707.9b's exceptions ("except his name is ..., he's a
legendary ... creature ...") written into the copiable values, and a stated
duration (CR 611.2a).

- Absorbing Man: "At the beginning of your first main phase, until your next
  turn, Absorbing Man becomes a copy of up to one target artifact, non-Aura
  enchantment, or land, except his name is Absorbing Man, he's a legendary
  4/4 Human Villain creature in addition to his other types, and he has
  vigilance."
- Taskmaster, Mercenary Mimic: "... until your next turn, Taskmaster becomes
  a copy of up to one target creature on the battlefield or creature card in
  a graveyard, except his name is Taskmaster, Mercenary Mimic and he's a
  legendary Human Mercenary Villain creature." - with no "in addition to",
  the type line is exactly that (CR 707.9b; CR 205.1a).
- Shuri, Wakandan Inventor: "{1}, {T}: Target artifact you control becomes a
  copy of a second target artifact you control until end of turn, except it
  isn't legendary. Activate only as a sorcery."
- Secret Invasion: "When this Aura enters, exile up to one target creature
  other than enchanted creature until this Aura leaves the battlefield.
  Enchanted creature becomes a copy of that creature until this Aura leaves
  the battlefield."

Off-set proofs (legal, in no deck list):

- Lazav, the Multifarious: "{X}: Lazav becomes a copy of target creature
  card in your graveyard with mana value X, except its name is Lazav, the
  Multifarious, it's legendary in addition to its other types, and it has
  this ability." - a graveyard card, no duration, and "this ability" kept.
- Saheeli, Sublime Artificer: "-2: Target artifact you control becomes a copy
  of another target artifact or creature you control until end of turn,
  except it's an artifact in addition to its other types." - the two-target
  shape with a different exception.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Type, Zone
from magic_cards_model.models.card import Supertype

from .harness import Scenario

ABSORBING = "Absorbing Man"
TASKMASTER = "Taskmaster, Mercenary Mimic"
SHURI = "Shuri, Wakandan Inventor"
INVASION = "Secret Invasion"


def _chars(scenario, permanent):
    return scenario.game.computed_board().of(permanent)


def _into_first_main(scenario, name, targets):
    scenario.start_at(Step.DRAW)
    scenario.choose_trigger_targets(name, list(targets))
    scenario.advance()  # precombat main: the trigger
    while scenario.game.stack or scenario.game.pending_triggers:
        scenario.pass_until_resolved()


def _next_turn(scenario):
    turns = scenario.turn.turns_taken
    while scenario.turn.turns_taken == turns:
        scenario.advance()
        while not scenario.game.stack_is_empty:
            scenario.resolve_top()


# -- Absorbing Man -----------------------------------------------------------------------


def _absorbing_board(*, alice=(), bob=()):
    return (
        Scenario()
        .player("alice", battlefield=[ABSORBING, *alice], library=["Island"] * 8)
        .player("bob", battlefield=list(bob), library=["Forest"] * 8)
        .build()
    )


def test_absorbing_man_becomes_a_copy_of_an_artifact_with_his_exceptions():
    scenario = _absorbing_board(bob=["Mind Stone"])
    man = scenario.creature(ABSORBING, "alice")
    stone = scenario.find("Mind Stone", Zone.BATTLEFIELD, "bob")

    _into_first_main(scenario, ABSORBING, [stone])

    chars = _chars(scenario, man)
    assert chars.name == ABSORBING
    assert Supertype.LEGENDARY in chars.supertypes
    assert set(chars.types) == {Type.ARTIFACT, Type.CREATURE}
    assert set(chars.subtypes) >= {"Human", "Villain"}
    assert chars.power_toughness == (4, 4)
    assert any("Draw a card" in line for line in chars.abilities)  # Mind Stone's
    assert any(line.startswith("Vigilance") for line in chars.abilities)
    assert chars.mana_value == 2  # the copied value


def test_absorbing_man_can_copy_a_land():
    scenario = _absorbing_board(bob=["Forest"])
    man = scenario.creature(ABSORBING, "alice")
    forest = scenario.find("Forest", Zone.BATTLEFIELD, "bob")

    _into_first_main(scenario, ABSORBING, [forest])

    chars = _chars(scenario, man)
    assert Type.LAND in chars.types and Type.CREATURE in chars.types
    assert "Forest" in chars.subtypes
    assert chars.power_toughness == (4, 4)


def test_absorbing_man_with_no_target_stays_himself():
    scenario = _absorbing_board(bob=["Mind Stone"])
    man = scenario.creature(ABSORBING, "alice")

    _into_first_main(scenario, ABSORBING, [])

    chars = _chars(scenario, man)
    assert chars.types == (Type.CREATURE,)
    assert any(line.startswith("At the beginning") for line in chars.abilities)


def test_absorbing_man_stays_a_copy_until_his_controllers_next_turn():
    scenario = _absorbing_board(bob=["Mind Stone"])
    man = scenario.creature(ABSORBING, "alice")
    stone = scenario.find("Mind Stone", Zone.BATTLEFIELD, "bob")
    _into_first_main(scenario, ABSORBING, [stone])

    _next_turn(scenario)  # bob's turn
    assert Type.ARTIFACT in _chars(scenario, man).types

    scenario.choose_trigger_targets(ABSORBING, [])
    _next_turn(scenario)  # alice's next turn: the copy has ended
    assert Type.ARTIFACT not in _chars(scenario, man).types
    assert _chars(scenario, man).name == ABSORBING


def test_absorbing_man_cannot_target_an_aura():
    scenario = _absorbing_board(alice=["Grizzly Bears"], bob=["Claustrophobia"])
    bears = scenario.creature("Grizzly Bears", "alice")
    aura = scenario.find("Claustrophobia", Zone.BATTLEFIELD, "bob")
    aura.attach_to(bears)

    with pytest.raises(ValueError):
        _into_first_main(scenario, ABSORBING, [aura])


# -- Taskmaster, Mercenary Mimic ---------------------------------------------------------


def _taskmaster_board(*, bob=(), bob_graveyard=()):
    return (
        Scenario()
        .player("alice", battlefield=[TASKMASTER], library=["Island"] * 8)
        .player(
            "bob",
            battlefield=list(bob),
            graveyard=list(bob_graveyard),
            library=["Forest"] * 8,
        )
        .build()
    )


def test_taskmaster_copies_a_creature_and_has_exactly_his_own_type_line():
    scenario = _taskmaster_board(bob=["Serra Angel"])
    taskmaster = scenario.creature(TASKMASTER, "alice")
    angel = scenario.creature("Serra Angel", "bob")

    _into_first_main(scenario, TASKMASTER, [angel])

    chars = _chars(scenario, taskmaster)
    assert chars.name == TASKMASTER
    assert chars.supertypes == (Supertype.LEGENDARY,)
    assert chars.types == (Type.CREATURE,)
    assert set(chars.subtypes) == {"Human", "Mercenary", "Villain"}  # no Angel
    assert chars.power_toughness == (4, 4)
    assert "Flying" in chars.abilities


def test_taskmaster_copies_a_creature_card_in_a_graveyard():
    scenario = _taskmaster_board(bob_graveyard=["Hill Giant"])
    taskmaster = scenario.creature(TASKMASTER, "alice")
    giant = scenario.find("Hill Giant", Zone.GRAVEYARD, "bob")

    _into_first_main(scenario, TASKMASTER, [giant])

    chars = _chars(scenario, taskmaster)
    assert chars.power_toughness == (3, 3)
    assert chars.name == TASKMASTER
    assert giant.zone is Zone.GRAVEYARD


def test_taskmaster_copying_an_artifact_creature_is_no_longer_an_artifact():
    """The exception sets the whole type line (CR 707.9b)."""
    scenario = _taskmaster_board(bob=["Ornithopter"])
    taskmaster = scenario.creature(TASKMASTER, "alice")
    thopter = scenario.creature("Ornithopter", "bob")

    _into_first_main(scenario, TASKMASTER, [thopter])

    chars = _chars(scenario, taskmaster)
    assert chars.types == (Type.CREATURE,)
    assert chars.power_toughness == (0, 2)
    assert "Flying" in chars.abilities


# -- Shuri, Wakandan Inventor ------------------------------------------------------------


def test_shuri_turns_an_artifact_into_a_nonlegendary_copy_until_end_of_turn():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[SHURI, "Mind Stone", "Mox Opal", "Island"],
            library=["Island"] * 5,
        )
        .player("bob", library=["Forest"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    shuri = scenario.creature(SHURI, "alice")
    shuri.summoning_sick = False
    stone = scenario.find("Mind Stone", Zone.BATTLEFIELD, "alice")
    mox = scenario.find("Mox Opal", Zone.BATTLEFIELD, "alice")

    scenario.activate(shuri, *scenario.untapped_sources("Island"), index=0, targets=[stone, mox])
    scenario.pass_until_resolved()
    scenario.state_based_actions()

    chars = _chars(scenario, stone)
    assert chars.name == "Mox Opal"
    assert Supertype.LEGENDARY not in chars.supertypes
    assert stone.zone is Zone.BATTLEFIELD and mox.zone is Zone.BATTLEFIELD  # no legend rule
    scenario.start_at(Step.END_STEP)
    scenario.advance()
    assert _chars(scenario, stone).name == "Mind Stone"


def test_shuri_is_sorcery_speed():
    scenario = (
        Scenario()
        .player("bob", library=["Forest"] * 5)
        .player("alice", battlefield=[SHURI, "Mind Stone", "Mox Opal", "Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    shuri = scenario.creature(SHURI, "alice")

    assert scenario.why_cannot_activate(shuri, 0, "alice") is not None


# -- Secret Invasion ----------------------------------------------------------------------


def _invasion(scenario, enchanted, target):
    scenario.choose_trigger_targets(INVASION, [target] if target else [])
    scenario.cast_and_resolve(
        INVASION, *scenario.untapped_sources("Island", "Island", "Island"), targets=[enchanted]
    )
    while scenario.game.stack or scenario.game.pending_triggers:
        scenario.pass_until_resolved()
    return scenario.find(INVASION, Zone.BATTLEFIELD, "alice")


def _invasion_board():
    return (
        Scenario()
        .player(
            "alice",
            hand=[INVASION],
            battlefield=["Grizzly Bears", "Island", "Island", "Island"],
            library=["Island"] * 5,
        )
        .player("bob", battlefield=["Serra Angel"], library=["Forest"] * 5)
        .build()
    )


def test_secret_invasion_exiles_a_creature_and_the_enchanted_one_becomes_it():
    scenario = _invasion_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    angel = scenario.creature("Serra Angel", "bob")

    _invasion(scenario, bears, angel)

    assert angel.zone is Zone.EXILE
    chars = _chars(scenario, bears)
    assert chars.name == "Serra Angel"
    assert chars.power_toughness == (4, 4)
    assert "Flying" in chars.abilities
    assert any(line.lower().startswith("ward") for line in chars.abilities)  # the Aura's


def test_secret_invasion_leaving_returns_the_creature_and_ends_the_copy():
    scenario = _invasion_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    angel = scenario.creature("Serra Angel", "bob")
    aura = _invasion(scenario, bears, angel)

    scenario.game.destroy(aura)
    while scenario.game.stack or scenario.game.pending_triggers:
        scenario.pass_until_resolved()

    assert angel.zone is Zone.BATTLEFIELD
    assert scenario.game.controller_of(angel).username == "bob"
    assert _chars(scenario, bears).name == "Grizzly Bears"


def test_secret_invasion_with_no_target_changes_nothing():
    scenario = _invasion_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")

    _invasion(scenario, bears, None)

    assert _chars(scenario, bears).name == "Grizzly Bears"


# -- Lazav, the Multifarious (off-set proof) -------------------------------------------------


def test_lazav_becomes_a_graveyard_creature_keeping_his_name_and_ability():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Lazav, the Multifarious"] + ["Island"] * 4,
            graveyard=["Hill Giant"],
            library=["Island"] * 5,
        )
        .player("bob", library=["Forest"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    lazav = scenario.creature("Lazav, the Multifarious", "alice")
    giant = scenario.find("Hill Giant", Zone.GRAVEYARD, "alice")

    scenario.activate(
        lazav, *scenario.untapped_sources(*["Island"] * 4), x_value=4, targets=[giant]
    )
    scenario.pass_until_resolved()

    chars = _chars(scenario, lazav)
    assert chars.name == "Lazav, the Multifarious"
    assert Supertype.LEGENDARY in chars.supertypes
    assert chars.power_toughness == (3, 3)
    assert "Giant" in chars.subtypes
    assert any(line.startswith("{X}: Lazav becomes a copy") for line in chars.abilities)
    scenario.start_at(Step.END_STEP)
    scenario.advance()
    assert _chars(scenario, lazav).power_toughness == (3, 3)  # no duration


# -- Saheeli, Sublime Artificer (off-set proof) --------------------------------------------


def test_saheeli_makes_an_artifact_a_copy_of_a_creature_that_is_also_an_artifact():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Saheeli, Sublime Artificer", "Mind Stone", "Serra Angel"],
            library=["Island"] * 5,
        )
        .player("bob", library=["Forest"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    saheeli = scenario.find("Saheeli, Sublime Artificer", Zone.BATTLEFIELD, "alice")
    stone = scenario.find("Mind Stone", Zone.BATTLEFIELD, "alice")
    angel = scenario.creature("Serra Angel", "alice")

    scenario.activate(saheeli, index=0, targets=[stone, angel])
    scenario.pass_until_resolved()

    chars = _chars(scenario, stone)
    assert chars.name == "Serra Angel"
    assert Type.ARTIFACT in chars.types and Type.CREATURE in chars.types
    assert chars.power_toughness == (4, 4)
    scenario.start_at(Step.END_STEP)
    scenario.advance()
    assert _chars(scenario, stone).name == "Mind Stone"
