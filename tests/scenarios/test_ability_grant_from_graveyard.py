"""Scenario: "<this> has all activated abilities of all <quality> cards in
<your graveyard | all graveyards>."

A layer 6 ability-adding effect (CR 613.1f), rebuilt with the board (CR
613.5): a card arriving in the graveyard grants its abilities at once, one
leaving takes them away. The pile is the graveyard named - "your graveyard"
is the controller's alone - and the quality is a card type or a creature
subtype. The copied abilities are the host's own now: "this creature" in
them is the host. A static ability of a permanent functions on the
battlefield (CR 113.6), which is all Necrotic Ooze's "As long as this
creature is on the battlefield" says.

This widens C00-T1's linked-exile grant reader (`machines/layers.
all_activated_abilities_grant`) from an exile pile to a graveyard pile.
Printings: Thranduil, the Elvenking (a subtype, "your graveyard", its own
name), off-set Necrotic Ooze (a card type, "all graveyards", "As long as
... it has") - a different pile, quality and subject.

CR numbers verified with `mise run rules:find`: 613.1f, 613.5, 113.6, 302.6.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Color
from magic_cards_model.support import card_support
from tests.cards import card

from .harness import PlayedScenario, Scenario

THRANDUIL = "Thranduil, the Elvenking"
OOZE = "Necrotic Ooze"
ELVES_TAP = "{T}: Add {G}."
GUARDIAN_TRAMPLE = "{G}: Target creature gains trample until end of turn."
ROOTWALLA_PUMP = "{1}{G}: This creature gets +2/+2 until end of turn. Activate only once each turn."


def test_both_printings_are_handled():
    for name in (THRANDUIL, OOZE):
        statics = [c for c in card_support(card(name)).clauses if c.kind == "static"]
        assert [c.outcome for c in statics] == ["handled"], name


def board(alice: list[str], *, alice_graveyard=(), bob_graveyard=()) -> PlayedScenario:
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=alice,
            graveyard=list(alice_graveyard),
            library=["Forest"] * 5,
        )
        .player("bob", graveyard=list(bob_graveyard), library=["Forest"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def texts(scenario: PlayedScenario, permanent) -> list[str]:
    return [ability.raw for ability in scenario.game.activated_abilities(permanent)]


def test_thranduil_has_the_mana_ability_of_an_elf_in_your_graveyard():
    scenario = board([THRANDUIL], alice_graveyard=["Llanowar Elves"])
    thranduil = scenario.creature(THRANDUIL)
    assert ELVES_TAP in texts(scenario, thranduil)
    scenario.activate(thranduil, index=texts(scenario, thranduil).index(ELVES_TAP))
    assert thranduil.tapped
    assert scenario.player("alice").mana_pool.floating.get(Color.GREEN) == 1


def test_thranduil_activates_a_targeted_elf_ability():
    scenario = board([THRANDUIL, "Forest", "Grizzly Bears"], alice_graveyard=["Greenbelt Guardian"])
    thranduil = scenario.creature(THRANDUIL)
    bears = scenario.creature("Grizzly Bears")
    index = texts(scenario, thranduil).index(GUARDIAN_TRAMPLE)
    scenario.activate(thranduil, *scenario.untapped_sources("Forest"), index=index, targets=[bears])
    scenario.pass_until_resolved()
    from magic_cards_model.machines.combat import Keyword, has_keyword

    assert has_keyword(bears, Keyword.TRAMPLE, scenario.game)


def test_a_non_elf_card_in_your_graveyard_grants_nothing():
    scenario = board([THRANDUIL], alice_graveyard=["Basking Rootwalla"])
    assert texts(scenario, scenario.creature(THRANDUIL)) == []


def test_an_elf_in_an_opponents_graveyard_grants_nothing():
    scenario = board([THRANDUIL], bob_graveyard=["Llanowar Elves"])
    assert texts(scenario, scenario.creature(THRANDUIL)) == []


def test_the_grant_follows_the_graveyard_as_cards_arrive_and_leave():
    scenario = board([THRANDUIL], alice_graveyard=["Llanowar Elves"])
    thranduil = scenario.creature(THRANDUIL)
    elves = scenario.find("Llanowar Elves", Zone.GRAVEYARD, "alice")
    assert ELVES_TAP in texts(scenario, thranduil)
    scenario.game.exile_permanent(elves)
    assert ELVES_TAP not in texts(scenario, thranduil)


def test_an_elf_dying_on_the_battlefield_grants_its_ability_from_the_graveyard():
    scenario = board([THRANDUIL, "Llanowar Elves"])
    thranduil = scenario.creature(THRANDUIL)
    assert ELVES_TAP not in texts(scenario, thranduil)
    scenario.game.destroy(scenario.creature("Llanowar Elves"))
    assert ELVES_TAP in texts(scenario, thranduil)


def test_two_copies_of_one_ability_are_granted_once():
    scenario = board([THRANDUIL], alice_graveyard=["Llanowar Elves", "Llanowar Elves"])
    assert texts(scenario, scenario.creature(THRANDUIL)).count(ELVES_TAP) == 1


# -- Necrotic Ooze: creature cards in all graveyards -------------------------


def test_necrotic_ooze_has_abilities_from_every_graveyard():
    scenario = board(
        [OOZE, "Forest", "Forest"],
        alice_graveyard=["Llanowar Elves"],
        bob_graveyard=["Basking Rootwalla"],
    )
    ooze = scenario.creature(OOZE)
    assert {ELVES_TAP, ROOTWALLA_PUMP} <= set(texts(scenario, ooze))
    scenario.activate(
        ooze,
        *scenario.untapped_sources("Forest", "Forest"),
        index=texts(scenario, ooze).index(ROOTWALLA_PUMP),
    )
    scenario.pass_until_resolved()
    chars = scenario.game.characteristics_of(ooze)
    assert (chars.power, chars.toughness) == (6, 5)


def test_necrotic_ooze_ignores_noncreature_cards():
    scenario = board([OOZE], alice_graveyard=["Mind Stone"])
    assert texts(scenario, scenario.creature(OOZE)) == []


def test_a_granted_tap_ability_still_needs_the_host_to_have_been_under_control_since_the_turn_began():
    """CR 302.6: a creature's {T} ability can't be activated unless it has
    been under its controller's control continuously since their most recent
    turn began - granted abilities included."""
    scenario = (
        Scenario()
        .player("alice", hand=[THRANDUIL], graveyard=["Llanowar Elves"], library=["Forest"] * 3)
        .player("bob", library=["Forest"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    thranduil = scenario.put_onto_battlefield(THRANDUIL)
    index = texts(scenario, thranduil).index(ELVES_TAP)
    assert scenario.why_cannot_activate(thranduil, index=index) is not None
