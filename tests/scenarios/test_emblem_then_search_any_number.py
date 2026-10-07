"""An emblem, then another instruction; and a search for "any number of" cards.

Nissa, Who Shakes the World's -8: "You get an emblem with "Lands you control
have indestructible." Search your library for any number of Forest cards, put
them onto the battlefield tapped, then shuffle." Two templates meet in one
ability, and each is proven on a second printing:

- **the emblem followed by more instructions** - Kiora, Master of the Depths'
  -8: "You get an emblem with "Whenever a creature you control enters, you
  may have it fight target creature." Then create three 8/8 blue Octopus
  creature tokens.";
- **"search your library for any number of <quality> cards"** - Iname,
  Death Aspect's enters trigger: "you may search your library for any number
  of Spirit cards, put them into your graveyard, then shuffle." (optional, a
  creature type rather than a land type, into the graveyard rather than onto
  the battlefield).

Rules, each read with `mise run rules:find` in the session that wrote this:

- **CR 114.2 / 114.4** - the emblem goes to the command zone, owned and
  controlled by its player, and its abilities function from there.
- **CR 107.1c** - "any number" is any positive number or zero.
- **CR 701.23b** - a search for a stated quality need not find every card
  that has it, or any.
- **CR 701.24a** - the library is shuffled afterwards.
- **CR 702.12b** - an indestructible permanent is not destroyed, by a destroy
  effect or by lethal damage.
- **CR 704.5i** - Nissa, left with 0 loyalty by the -8, goes to the
  graveyard; the emblem stays.
- **CR 305.6** - a nonbasic land with the Forest land type (Breeding Pool) is
  a Forest card.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def _nissa_minus_eight(library: list[str], *, bob_hand: list[str] | None = None):
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Nissa, Who Shakes the World", "Forest"],
            library=library,
        )
        .player(
            "bob",
            hand=bob_hand or [],
            battlefield=["Mountain", "Forest", "Forest"],
            library=["Island"] * 5,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    nissa = scenario.find("Nissa, Who Shakes the World", Zone.BATTLEFIELD, "alice")
    nissa.add_counters(Counter.LOYALTY, 8 - nissa.counters[Counter.LOYALTY])
    return scenario, nissa


def _library_cards(scenario, name: str) -> list:
    return [card for card in scenario.player("alice").library if card.name == name]


def _resolve(scenario) -> None:
    while scenario.game.stack:
        scenario.resolve_top()


def test_minus_eight_gives_alice_the_lands_indestructible_emblem():
    scenario, nissa = _nissa_minus_eight(["Forest", "Island"])
    scenario.will_choose_cards()
    scenario.activate(nissa, index=1)
    _resolve(scenario)

    (emblem,) = scenario.game.emblems_of("alice")
    assert emblem.zone is Zone.COMMAND
    assert emblem.owner == "alice" and emblem.controller == "alice"
    assert "Lands you control have indestructible" in emblem.card.oracle_text
    assert scenario.game.emblems_of("bob") == []


def test_every_forest_card_chosen_enters_tapped_and_the_rest_stays():
    scenario, nissa = _nissa_minus_eight(["Forest", "Island", "Forest", "Forest", "Island"])
    forests = _library_cards(scenario, "Forest")
    scenario.will_choose_cards(*forests)
    scenario.activate(nissa, index=1)
    _resolve(scenario)

    for forest in forests:
        assert forest.zone is Zone.BATTLEFIELD
        assert forest.tapped, "put them onto the battlefield tapped"
        assert forest.controller == "alice"
    assert sorted(card.name for card in scenario.player("alice").library) == ["Island", "Island"]


def test_any_number_includes_only_some_of_them():
    """CR 107.1c / CR 701.23b: alice may leave Forests behind."""
    scenario, nissa = _nissa_minus_eight(["Forest", "Forest", "Forest"])
    first, *_rest = _library_cards(scenario, "Forest")
    scenario.will_choose_cards(first)
    scenario.activate(nissa, index=1)
    _resolve(scenario)

    assert first.zone is Zone.BATTLEFIELD and first.tapped
    assert [card.name for card in scenario.player("alice").library] == ["Forest", "Forest"]


def test_any_number_includes_zero_and_the_emblem_still_arrives():
    scenario, nissa = _nissa_minus_eight(["Forest", "Forest"])
    scenario.will_choose_cards()
    scenario.activate(nissa, index=1)
    _resolve(scenario)

    assert len(scenario.player("alice").library) == 2
    assert len(scenario.game.emblems_of("alice")) == 1


def test_the_search_offers_every_forest_card_and_nothing_else():
    """CR 305.6: Breeding Pool is a Forest card; an Island is not."""
    scenario, nissa = _nissa_minus_eight(["Breeding Pool", "Island", "Forest"])
    scenario.activate(nissa, index=1)
    _resolve(scenario)

    (question,) = [q for q in scenario.questions_asked() if q.source == nissa.name]
    offered = {scenario.game.find_by_id(card_id).name for card_id in question.cards}
    assert offered == {"Breeding Pool", "Forest"}


def test_nissa_goes_to_the_graveyard_but_the_emblem_stays():
    """CR 704.5i: 8 - 8 = 0 loyalty. CR 114.4: the emblem does not care."""
    scenario, nissa = _nissa_minus_eight(["Forest"])
    scenario.will_choose_cards()
    scenario.activate(nissa, index=1)
    _resolve(scenario)
    scenario.game.check_state_based_actions()

    assert nissa.zone is Zone.GRAVEYARD
    assert len(scenario.game.emblems_of("alice")) == 1


def test_with_the_emblem_alices_lands_survive_a_destroy_effect():
    """CR 702.12b, from an emblem's static ability (CR 114.4)."""
    scenario, nissa = _nissa_minus_eight(["Forest"])
    scenario.will_choose_cards()
    scenario.activate(nissa, index=1)
    _resolve(scenario)

    forest = scenario.find("Forest", Zone.BATTLEFIELD, "alice")
    assert scenario.game.computed_board().of(forest).has_ability("Indestructible")
    scenario.game.destroy(forest)
    assert forest.zone is Zone.BATTLEFIELD


def test_the_emblem_does_not_protect_the_opponents_lands():
    scenario, nissa = _nissa_minus_eight(["Forest"])
    scenario.will_choose_cards()
    scenario.activate(nissa, index=1)
    _resolve(scenario)

    bobs_forest = scenario.find("Forest", Zone.BATTLEFIELD, "bob")
    assert not scenario.game.computed_board().of(bobs_forest).has_ability("Indestructible")
    scenario.game.destroy(bobs_forest)
    assert bobs_forest.zone is Zone.GRAVEYARD


def test_a_land_that_enters_later_is_indestructible_too():
    """The emblem's ability is static (CR 604.2): it reads the board as it is,
    not as it was when the emblem was made."""
    scenario, nissa = _nissa_minus_eight(["Forest", "Forest"])
    first, second = _library_cards(scenario, "Forest")
    scenario.will_choose_cards(first)
    scenario.activate(nissa, index=1)
    _resolve(scenario)

    assert scenario.game.computed_board().of(first).has_ability("Indestructible")


def test_an_animated_land_under_the_emblem_survives_lethal_damage():
    """CR 702.12b: indestructible ignores CR 704.5g's lethal-damage check."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Nissa, Who Shakes the World", "Forest", "Island"],
            library=["Forest"] * 3,
        )
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain"], library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    nissa = scenario.find("Nissa, Who Shakes the World", Zone.BATTLEFIELD, "alice")
    forest = scenario.find("Forest", Zone.BATTLEFIELD, "alice")
    nissa.add_counters(Counter.LOYALTY, 9 - nissa.counters[Counter.LOYALTY])
    scenario.will_choose_cards()
    scenario.activate(nissa, index=1)
    _resolve(scenario)
    # a second Nissa-free way to make the land a creature is not needed: the
    # emblem is what this is about, so animate it with the +1 next turn.
    while scenario.game.turn.active_player == "alice":
        scenario.advance()
    while scenario.game.turn.active_player == "bob":
        scenario.advance()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.activate(nissa, index=0, targets=[forest])
    _resolve(scenario)
    assert scenario.game.computed_board().of(forest).is_creature

    scenario.pass_priority("alice")
    scenario.cast_and_resolve(
        "Lightning Bolt",
        *scenario.untapped_sources("Mountain", username="bob"),
        username="bob",
        targets=[forest],
    )
    assert forest.zone is Zone.BATTLEFIELD
    assert forest.damage == 3


# -- Kiora, Master of the Depths: emblem, then more ---------------------------


def test_kioras_minus_eight_gives_the_emblem_and_then_three_octopuses():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Kiora, Master of the Depths"], library=["Island"] * 3)
        .player("bob", library=["Island"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    kiora = scenario.find("Kiora, Master of the Depths", Zone.BATTLEFIELD, "alice")
    kiora.add_counters(Counter.LOYALTY, 8 - kiora.counters[Counter.LOYALTY])

    scenario.activate(kiora, index=2)
    scenario.resolve_top()
    # The emblem exists before the tokens are created, so each Octopus
    # entering triggers it (CR 603.2). Alice declines every fight (CR 608.2d)
    # so the three tokens stay to be counted.
    triggers = [o for o in scenario.game.stack if o.source_name.endswith("emblem")]
    assert len(triggers) == 3
    scenario.will_take_the_may(False, times=None)
    _resolve(scenario)

    (emblem,) = scenario.game.emblems_of("alice")
    assert "fight target creature" in emblem.card.oracle_text
    assert "Then create" not in emblem.card.oracle_text, "the emblem holds only its quote"
    octopuses = [p for p in scenario.game.battlefield if p.name.startswith("Octopus")]
    assert len(octopuses) == 3
    for octopus in octopuses:
        computed = scenario.game.computed_board().of(octopus)
        assert (computed.power, computed.toughness) == (8, 8)
        assert octopus.controller == "alice"


# -- Iname, Death Aspect: "any number of Spirit cards", into the graveyard ---


def _iname(library: list[str]):
    scenario = (
        Scenario()
        .player("alice", hand=["Iname, Death Aspect"], library=library)
        .player("bob", library=["Island"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _enter_iname(scenario, *, take: bool = True) -> None:
    scenario.will_take_the_may(take, source="Iname, Death Aspect")
    scenario.put_onto_battlefield("Iname, Death Aspect", "alice")
    scenario.game.put_triggers_on_stack()
    _resolve(scenario)


def test_iname_puts_every_chosen_spirit_card_into_the_graveyard():
    scenario = _iname(["Bloodghast", "Island", "Dark Revenant", "Grizzly Bears"])
    spirits = [
        card
        for card in scenario.player("alice").library
        if card.name in ("Bloodghast", "Dark Revenant")
    ]
    scenario.will_choose_cards(*spirits)
    _enter_iname(scenario)

    for spirit in spirits:
        assert spirit.zone is Zone.GRAVEYARD
    assert sorted(card.name for card in scenario.player("alice").library) == [
        "Grizzly Bears",
        "Island",
    ]


def test_inames_search_offers_only_spirit_cards():
    scenario = _iname(["Bloodghast", "Grizzly Bears", "Island"])
    _enter_iname(scenario)

    (question,) = [q for q in scenario.questions_asked() if q.cards]
    offered = {scenario.game.find_by_id(card_id).name for card_id in question.cards}
    assert offered == {"Bloodghast"}


def test_iname_may_find_some_of_the_spirits_and_leave_the_rest():
    """CR 107.1c / CR 701.23b."""
    scenario = _iname(["Bloodghast", "Dark Revenant"])
    first = scenario.player("alice").library[0]
    scenario.will_choose_cards(first)
    _enter_iname(scenario)

    assert first.zone is Zone.GRAVEYARD
    assert [card.name for card in scenario.player("alice").library] == ["Dark Revenant"]


def test_iname_declined_searches_nothing():
    """The printed "you may" (CR 608.2d): no search, no shuffle question."""
    scenario = _iname(["Bloodghast", "Island"])
    _enter_iname(scenario, take=False)

    assert sorted(card.name for card in scenario.player("alice").library) == [
        "Bloodghast",
        "Island",
    ]
    assert not [q for q in scenario.questions_asked() if q.cards]
