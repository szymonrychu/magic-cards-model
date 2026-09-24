""" "Return this card from your graveyard to the battlefield attached to
target creature you control[ with power `<n>` or less]. Activate only as a
sorcery." (CR 113.6m's graveyard-zone activated ability, CR 701.3a's attach)

Eagle's Rescue: "{2}{W/U}{W/U}: Return this card from your graveyard to the
battlefield attached to target creature you control with power 1 or less.
Activate only as a sorcery."
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_eagles_rescue_returns_from_the_graveyard_attached_to_a_small_creature():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            graveyard=["Eagle's Rescue"],
            battlefield=["Raging Goblin", "Plains", "Plains", "Island", "Island"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    goblin = scenario.creature("Raging Goblin", "alice")
    rescue = scenario.find("Eagle's Rescue", Zone.GRAVEYARD, "alice")

    activation = scenario.activate(rescue, targets=[goblin], auto=True, username="alice")
    scenario.pass_until_resolved()

    aura = scenario.find("Eagle's Rescue", Zone.BATTLEFIELD, "alice")
    assert aura.attached_to == goblin.id
    assert activation is not None


def test_eagles_rescue_cannot_target_a_creature_with_power_over_one():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            graveyard=["Eagle's Rescue"],
            battlefield=["Grizzly Bears", "Plains", "Plains", "Island", "Island"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    rescue = scenario.find("Eagle's Rescue", Zone.GRAVEYARD, "alice")

    import pytest

    with pytest.raises(ValueError):
        scenario.activate(rescue, targets=[bears], auto=True, username="alice")


def test_gryffs_boon_returns_from_the_graveyard_attached_to_target_creature():
    """Realms Uncharted's own printing of the same "return this card from
    your graveyard to the battlefield attached to target creature[...].
    Activate only as a sorcery." shape - proof the reader is not fitted to
    Eagle's Rescue's own power restriction."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            graveyard=["Gryff's Boon"],
            battlefield=["Grizzly Bears", "Plains", "Plains", "Plains", "Plains"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    boon = scenario.find("Gryff's Boon", Zone.GRAVEYARD, "alice")

    scenario.activate(boon, targets=[bears], auto=True, username="alice")
    scenario.pass_until_resolved()

    aura = scenario.find("Gryff's Boon", Zone.BATTLEFIELD, "alice")
    assert aura.attached_to == bears.id
