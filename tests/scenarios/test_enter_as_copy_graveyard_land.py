"""Enter tapped as a copy of a land - from a graveyard, and from the battlefield.

Echoing Deeps (The Lost Caverns of Ixalan, legal in Modern, Pioneer and
Standard - verified against Scryfall this session): "You may have this land
enter tapped as a copy of any land card in a graveyard, except it's a Cave in
addition to its other types." / "{T}: Add {C}."

Vesuva (Modern-legal, not in any deck list) is the second printing for the
"enter tapped as a copy" reader: "You may have this land enter tapped as a copy
of any land on the battlefield."

The rules and rulings this file walks through:

- CR 614.1c - "[This permanent] enters as . . ." is a replacement effect;
  "tapped" is part of the same replacement, so it applies only when the copy
  choice is taken.
- Echoing Deeps ruling (2023-11-10): "If you choose to have Echoing Deeps not
  copy anything, it enters the battlefield untapped." Vesuva ruling
  (2021-03-19): "If you don't choose a land on the battlefield, Vesuva enters
  the battlefield untapped as itself".
- Echoing Deeps ruling: "Any enters-the-battlefield abilities of the copied
  land card will trigger when Echoing Deeps enters the battlefield."
- CR 400.1 - "a graveyard" is every player's graveyard, not only yours.
- CR 707.2 - the copy has the land card's printed characteristics; CR 205.1b's
  "in addition to its other types" keeps them and adds Cave.

No mocks: every card is a real printing from the pool.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import DecisionKind
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Type
from tests.cards import card
from tests.scenarios.harness import Scenario


def _copy_questions(scenario, source):
    return [
        decision
        for decision in scenario.questions_asked()
        if decision.kind is DecisionKind.CHOOSE_CARDS and decision.source == source
    ]


def test_echoing_deeps_enters_tapped_as_a_graveyard_forest_that_is_also_a_cave():
    scenario = (
        Scenario()
        .player("alice", hand=["Echoing Deeps"], graveyard=["Forest"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    forest = scenario.find("Forest", Zone.GRAVEYARD, "alice")

    deeps = scenario.play_land("Echoing Deeps")

    assert deeps.zone is Zone.BATTLEFIELD
    assert deeps.tapped is True
    characteristics = scenario.game.characteristics_of(deeps)
    assert characteristics.name == "Forest"
    assert "Forest" in card("Forest").type_line
    assert "Forest" in characteristics.subtypes and "Cave" in characteristics.subtypes
    # Copying does not move the card it copied (CR 707.2 reads it, nothing more).
    assert forest.zone is Zone.GRAVEYARD
    assert scenario.game.unreadable_copy_exception_notices == []


def test_echoing_deeps_reaches_an_opponents_graveyard():
    """ "a graveyard", not "your graveyard" - bob's Steam Vents is offered."""
    scenario = (
        Scenario()
        .player("alice", hand=["Echoing Deeps"])
        .player("bob", graveyard=["Steam Vents"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    vents = scenario.find("Steam Vents", Zone.GRAVEYARD, "bob")

    deeps = scenario.play_land("Echoing Deeps")

    (question,) = _copy_questions(scenario, "Echoing Deeps")
    assert vents.id in question.cards
    characteristics = scenario.game.characteristics_of(deeps)
    assert characteristics.name == "Steam Vents"
    assert set(characteristics.subtypes) >= {"Island", "Mountain", "Cave"}
    assert deeps.controller == "alice"
    assert deeps.tapped is True


def test_nonland_cards_in_graveyards_are_never_offered():
    scenario = (
        Scenario()
        .player("alice", hand=["Echoing Deeps"], graveyard=["Lightning Bolt", "Forest"])
        .player("bob", graveyard=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    forest = scenario.find("Forest", Zone.GRAVEYARD, "alice")

    scenario.play_land("Echoing Deeps")

    (question,) = _copy_questions(scenario, "Echoing Deeps")
    assert set(question.cards) == {forest.id}


def test_declining_the_copy_enters_untapped_as_a_colorless_cave():
    """The 2023-11-10 ruling: not copying anything, it enters untapped."""
    scenario = (
        Scenario()
        .player("alice", hand=["Echoing Deeps"], graveyard=["Forest"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_take_the_may(False, username="alice", source="Echoing Deeps")

    deeps = scenario.play_land("Echoing Deeps")

    assert deeps.tapped is False
    characteristics = scenario.game.characteristics_of(deeps)
    assert characteristics.name == "Echoing Deeps"
    assert characteristics.subtypes == ("Cave",)
    assert _copy_questions(scenario, "Echoing Deeps") == []


def test_with_no_land_card_in_any_graveyard_it_enters_untapped_as_itself():
    scenario = (
        Scenario()
        .player("alice", hand=["Echoing Deeps"], graveyard=["Lightning Bolt"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    deeps = scenario.play_land("Echoing Deeps")

    assert deeps.tapped is False
    assert scenario.game.characteristics_of(deeps).name == "Echoing Deeps"
    assert _copy_questions(scenario, "Echoing Deeps") == []


def test_a_copied_land_creature_is_a_one_one_cave_dryad():
    """Dryad Arbor's printed characteristics come along whole: a 1/1 Land
    Creature - Forest Dryad, with Cave added."""
    scenario = (
        Scenario()
        .player("alice", hand=["Echoing Deeps"], graveyard=["Dryad Arbor"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    deeps = scenario.play_land("Echoing Deeps")

    characteristics = scenario.game.characteristics_of(deeps)
    assert Type.CREATURE in characteristics.types and Type.LAND in characteristics.types
    assert (characteristics.power, characteristics.toughness) == (1, 1)
    assert set(characteristics.subtypes) == {"Forest", "Dryad", "Cave"}


def test_the_copied_lands_enters_trigger_fires():
    """The ruling: "Any enters-the-battlefield abilities of the copied land
    card will trigger". Echoing Deeps as a Bojuka Bog exiles bob's graveyard -
    and the Bojuka Bog card it copied stays in alice's."""
    scenario = (
        Scenario()
        .player("alice", hand=["Echoing Deeps"], graveyard=["Bojuka Bog"])
        .player("bob", graveyard=["Grizzly Bears", "Lightning Bolt"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "bob")
    bog = scenario.find("Bojuka Bog", Zone.GRAVEYARD, "alice")

    # The trigger is keyed by the permanent's own card - the Echoing Deeps
    # card - the same way Superior Spider-Man's copied trigger is.
    scenario.choose_trigger_targets("Echoing Deeps", ["bob"])
    deeps = scenario.play_land("Echoing Deeps")
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()

    assert scenario.game.characteristics_of(deeps).name == "Bojuka Bog"
    assert bears.zone is Zone.EXILE
    assert scenario.player("bob").graveyard == []
    assert bog.zone is Zone.GRAVEYARD


def test_vesuva_enters_tapped_as_a_copy_of_a_land_on_the_battlefield():
    """The second printing: the "enter tapped as a copy" reader on a
    battlefield candidate."""
    scenario = (
        Scenario()
        .player("alice", hand=["Vesuva"])
        .player("bob", battlefield=["Steam Vents"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    vesuva = scenario.play_land("Vesuva")

    assert vesuva.tapped is True
    characteristics = scenario.game.characteristics_of(vesuva)
    assert characteristics.name == "Steam Vents"
    # No "in addition to" exception here: the copy is exactly the land.
    assert "Cave" not in characteristics.subtypes


def test_vesuva_declined_enters_untapped_as_itself():
    """The 2021-03-19 ruling: "If you don't choose a land on the battlefield,
    Vesuva enters the battlefield untapped as itself"."""
    scenario = (
        Scenario().player("alice", hand=["Vesuva"]).player("bob", battlefield=["Forest"]).build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_take_the_may(False, username="alice", source="Vesuva")

    vesuva = scenario.play_land("Vesuva")

    assert vesuva.tapped is False
    assert scenario.game.characteristics_of(vesuva).name == "Vesuva"


def test_vesuva_does_not_reach_a_graveyard_land():
    """ "any land on the battlefield" - a land card in a graveyard is not a
    candidate, so there is nothing to copy and Vesuva enters untapped."""
    scenario = (
        Scenario().player("alice", hand=["Vesuva"], graveyard=["Forest"]).player("bob").build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    vesuva = scenario.play_land("Vesuva")

    assert vesuva.tapped is False
    assert _copy_questions(scenario, "Vesuva") == []
