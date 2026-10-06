"""CR 406.1 / CR 701.13a: "Exile the top N cards of your library", then put
cards of a quality from among them onto the battlefield (CR 110.2: under the
control of the player who put them there) - the rest stay in exile.

Two quantifiers on the put, read off the same sentence shape:

- "You may put any number of <quality> cards from among them onto the
  battlefield." - Xenagos, the Reveler's `-6` (CR 107.1c: "any number"
  includes zero). The player chooses which.
- "Put all <quality> cards from among them onto the battlefield." -
  Tezzeret, Master of the Bridge's `-8`, no choice at all.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def _ability_index(scenario, permanent, starts_with: str) -> int:
    for index, ability in enumerate(scenario.game.activated_abilities(permanent)):
        if ability.effect.startswith(starts_with):
            return index
    raise AssertionError(f"{permanent.name} has no ability starting {starts_with!r}")


_XENAGOS_LIBRARY = [
    "Grizzly Bears",
    "Lightning Bolt",
    "Forest",
    "Llanowar Elves",
    "Mountain",
    "Shock",
    "Fog Bank",
    "Island",  # the eighth card: not among the top seven
]


def test_xenagos_minus_six_puts_the_chosen_creatures_and_lands_and_exiles_the_rest():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Xenagos, the Reveler"], library=_XENAGOS_LIBRARY)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    xenagos = scenario.find("Xenagos, the Reveler", Zone.BATTLEFIELD)
    xenagos.counters.set(Counter.LOYALTY, 7)
    index = _ability_index(scenario, xenagos, "Exile the top seven")
    top = scenario.top_of_library(7, username="alice")
    by_name = {state.name: state for state in top}
    scenario.will_choose_cards(
        by_name["Grizzly Bears"],
        by_name["Forest"],
        by_name["Mountain"],
        username="alice",
        source="Xenagos, the Reveler",
    )

    scenario.activate(xenagos, index=index)
    scenario.pass_until_resolved()

    assert xenagos.counter_count(Counter.LOYALTY) == 1
    for name in ("Grizzly Bears", "Forest", "Mountain"):
        assert by_name[name].zone is Zone.BATTLEFIELD, name
        assert by_name[name].controller == "alice"
    for name in ("Lightning Bolt", "Llanowar Elves", "Shock", "Fog Bank"):
        assert by_name[name].zone is Zone.EXILE, name
    library = scenario.game.player("alice").library
    assert [state.name for state in library] == ["Island"]


def test_xenagos_offers_only_creature_and_land_cards_and_any_number_includes_none():
    """CR 107.1c: "any number" includes zero - choosing none exiles all seven.
    The question offers only creature and land cards."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Xenagos, the Reveler"], library=_XENAGOS_LIBRARY)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    xenagos = scenario.find("Xenagos, the Reveler", Zone.BATTLEFIELD)
    xenagos.counters.set(Counter.LOYALTY, 6)
    index = _ability_index(scenario, xenagos, "Exile the top seven")
    top = scenario.top_of_library(7, username="alice")
    scenario.will_choose_cards(username="alice", source="Xenagos, the Reveler")

    scenario.activate(xenagos, index=index)
    scenario.pass_until_resolved()

    assert all(state.zone is Zone.EXILE for state in top)
    (asked,) = [
        decision
        for decision in scenario.questions_asked()
        if decision.source == "Xenagos, the Reveler"
    ]
    offered = {state.name for state in top if state.id in set(asked.cards)}
    assert offered == {"Grizzly Bears", "Forest", "Llanowar Elves", "Mountain", "Fog Bank"}


def test_xenagos_with_a_short_library_exiles_what_there_is():
    """CR 609.3: as much as possible - three cards is all there is to exile."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Xenagos, the Reveler"],
            library=["Grizzly Bears", "Shock", "Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    xenagos = scenario.find("Xenagos, the Reveler", Zone.BATTLEFIELD)
    xenagos.counters.set(Counter.LOYALTY, 6)
    index = _ability_index(scenario, xenagos, "Exile the top seven")
    bears, shock, forest = scenario.top_of_library(3, username="alice")
    scenario.will_choose_cards(bears, username="alice", source="Xenagos, the Reveler")

    scenario.activate(xenagos, index=index)
    scenario.pass_until_resolved()

    assert bears.zone is Zone.BATTLEFIELD
    assert shock.zone is Zone.EXILE
    assert forest.zone is Zone.EXILE
    assert scenario.game.player("alice").library == []


def test_tezzeret_minus_eight_puts_every_artifact_card_and_asks_nothing():
    """Tezzeret, Master of the Bridge: "-8: Exile the top ten cards of your
    library. Put all artifact cards from among them onto the battlefield." -
    the mandatory "all" twin of Xenagos's "you may put any number"."""
    library = [
        "Sol Ring",
        "Lightning Bolt",
        "Ornithopter",
        "Forest",
        "Mind Stone",
        "Grizzly Bears",
        "Shock",
        "Island",
        "Mountain",
        "Fog Bank",
        "Swamp",  # the eleventh card stays
    ]
    scenario = (
        Scenario()
        .player("alice", battlefield=["Tezzeret, Master of the Bridge"], library=library)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    tezzeret = scenario.find("Tezzeret, Master of the Bridge", Zone.BATTLEFIELD)
    tezzeret.counters.set(Counter.LOYALTY, 9)
    index = _ability_index(scenario, tezzeret, "Exile the top ten")
    top = scenario.top_of_library(10, username="alice")

    scenario.activate(tezzeret, index=index)
    scenario.pass_until_resolved()

    artifacts = {"Sol Ring", "Ornithopter", "Mind Stone"}
    for state in top:
        expected = Zone.BATTLEFIELD if state.name in artifacts else Zone.EXILE
        assert state.zone is expected, state.name
    assert [state.name for state in scenario.game.player("alice").library] == ["Swamp"]
    assert not [
        decision
        for decision in scenario.questions_asked()
        if decision.source == "Tezzeret, Master of the Bridge"
    ]
