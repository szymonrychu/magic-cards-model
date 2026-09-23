"""Scenario: "`<instruction on target card>`. If it was a `<type>` card, `<A>`.
Otherwise, `<B>`." - one CR 608.2c instruction whose middle sentence looks
back at the card the first sentence moved.

CR 608.2h: "if it's no longer in that zone, or if the effect has moved it
from a public zone to a hidden zone, the effect uses the object's last known
information" - the card's type is read as it was in the graveyard, before
the exile, and exactly one of the two branches runs.

Cling to Dust (instant, and its escape cast from the graveyard, CR 702.138a)
is the listed card. Klothys, God of Destiny's first-main-phase trigger prints
the same template with a different type word ("land"), a mana branch and a
two-instruction "Otherwise" branch - the second printing proving the reader
is the template, not Cling to Dust's sentence.

With its only target gone before it resolves, the spell or ability does not
resolve at all (CR 608.2b), so neither branch runs.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Color, Zone
from tests.scenarios.harness import Scenario


def _cling_board(*, alice_graveyard=None, bob_graveyard=None) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=["Cling to Dust"],
            graveyard=list(alice_graveyard or []),
            battlefield=["Swamp", "Swamp", "Swamp", "Swamp"],
            library=["Swamp"] * 3,
        )
        .player("bob", graveyard=list(bob_graveyard or []), library=["Island"] * 3)
        .build()
    )


def _cast_cling(scenario: Scenario, target) -> None:
    (swamp,) = scenario.untapped_sources("Swamp", username="alice")[:1]
    scenario.cast_and_resolve("Cling to Dust", swamp, username="alice", targets=[target])


def test_a_creature_card_gains_three_life_and_draws_nothing():
    scenario = _cling_board(bob_graveyard=["Grizzly Bears"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "bob")

    _cast_cling(scenario, bears)

    assert bears.zone is Zone.EXILE
    assert scenario.player("alice").life == 23
    assert len(scenario.player("alice").hand) == 0


def test_a_noncreature_card_draws_and_gains_nothing():
    scenario = _cling_board(bob_graveyard=["Lightning Bolt"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bolt = scenario.find("Lightning Bolt", Zone.GRAVEYARD, "bob")

    _cast_cling(scenario, bolt)

    assert bolt.zone is Zone.EXILE
    assert scenario.player("alice").life == 20
    assert len(scenario.player("alice").hand) == 1


def test_a_land_card_is_not_a_creature_card():
    scenario = _cling_board(bob_graveyard=["Island"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    island = scenario.find("Island", Zone.GRAVEYARD, "bob")

    _cast_cling(scenario, island)

    assert scenario.player("alice").life == 20
    assert len(scenario.player("alice").hand) == 1


def test_an_artifact_creature_card_is_a_creature_card():
    """A card with several types is a creature card if creature is one of
    them - Ornithopter is an artifact creature."""
    scenario = _cling_board(alice_graveyard=["Ornithopter"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    thopter = scenario.find("Ornithopter", Zone.GRAVEYARD, "alice")

    _cast_cling(scenario, thopter)

    assert scenario.player("alice").life == 23
    assert len(scenario.player("alice").hand) == 0


def test_the_type_is_read_from_the_card_that_was_exiled_not_its_new_zone():
    """CR 608.2h: the exile moves the card before the second sentence reads
    it; the answer is the card as it last existed in the graveyard. The card
    in exile is still a creature card too, so this also pins down that the
    branch is decided once, not re-run per zone."""
    scenario = _cling_board(alice_graveyard=["Grizzly Bears"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")

    _cast_cling(scenario, bears)

    assert bears.zone is Zone.EXILE
    assert scenario.player("alice").life == 23


def test_a_target_gone_before_resolution_means_neither_branch():
    """CR 608.2b: its only target is illegal, so the spell does not resolve -
    no life, no card."""
    scenario = _cling_board(bob_graveyard=["Grizzly Bears"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "bob")
    (swamp,) = scenario.untapped_sources("Swamp", username="alice")[:1]
    scenario.cast_onto_stack("Cling to Dust", swamp, username="alice", targets=[bears])
    scenario.game.exile_cards([bears])

    scenario.resolve_top()

    assert scenario.player("alice").life == 20
    assert len(scenario.player("alice").hand) == 0


def test_escape_cast_from_the_graveyard_resolves_the_same_branches():
    """CR 702.138a: escape only changes how the spell is cast - the escaped
    Cling to Dust reads its target exactly as the hand-cast one does."""
    scenario = (
        Scenario()
        .player(
            "alice",
            graveyard=["Cling to Dust", *["Mishra's Bauble"] * 5],
            battlefield=["Swamp", "Swamp", "Swamp", "Swamp"],
            library=["Swamp"] * 3,
        )
        .player("bob", graveyard=["Grizzly Bears"], library=["Island"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    fuel = [c for c in scenario.player("alice").graveyard if c.name == "Mishra's Bauble"]
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "bob")

    casting = scenario.cast("Cling to Dust", from_zone=Zone.GRAVEYARD)
    casting.use_keyword("Escape", choosing=fuel)
    casting.choose_targets([bears])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Swamp", "Swamp", "Swamp", "Swamp"))
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert bears.zone is Zone.EXILE
    assert all(bauble.zone is Zone.EXILE for bauble in fuel)
    assert scenario.player("alice").life == 23
    assert len(scenario.player("alice").hand) == 0


def test_escape_cast_on_a_noncreature_card_draws():
    scenario = (
        Scenario()
        .player(
            "alice",
            graveyard=["Cling to Dust", *["Mishra's Bauble"] * 6],
            battlefield=["Swamp", "Swamp", "Swamp", "Swamp"],
            library=["Swamp"] * 3,
        )
        .player("bob", library=["Island"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    baubles = [c for c in scenario.player("alice").graveyard if c.name == "Mishra's Bauble"]
    fuel, target = baubles[:5], baubles[5]

    casting = scenario.cast("Cling to Dust", from_zone=Zone.GRAVEYARD)
    casting.use_keyword("Escape", choosing=fuel)
    casting.choose_targets([target])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Swamp", "Swamp", "Swamp", "Swamp"))
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert target.zone is Zone.EXILE
    assert scenario.player("alice").life == 20
    assert len(scenario.player("alice").hand) == 1


# -- Klothys, God of Destiny: "If it was a land card, ... Otherwise, ..." ----


def _walk_to(scenario, step: Step) -> None:
    """CR 500.6's "a step began" event is emitted by `Game.advance`, not by
    `start_at` - so a "beginning of your first main phase" trigger can only
    be proven by walking there."""
    while scenario.step is not step:
        scenario.advance()


def _klothys_board(*, bob_graveyard: list[str], bob_life: int = 20) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            battlefield=["Klothys, God of Destiny"],
            library=["Forest"] * 3,
        )
        .player("bob", life=bob_life, graveyard=bob_graveyard, library=["Island"] * 3)
        .build()
    )


def _klothys_resolves_on(scenario: Scenario, target_name: str):
    scenario.start_at(Step.UPKEEP)
    target = scenario.find(target_name, Zone.GRAVEYARD, "bob")
    scenario.choose_trigger_targets("Klothys, God of Destiny", [target])
    _walk_to(scenario, Step.PRECOMBAT_MAIN)
    assert scenario.stack_names() == ["Klothys, God of Destiny's triggered ability"]
    scenario.resolve_top()
    return target


def test_klothys_exiling_a_land_card_adds_red_or_green():
    scenario = _klothys_board(bob_graveyard=["Island"])
    scenario.will_choose(Color.GREEN.value, source="Klothys, God of Destiny")

    island = _klothys_resolves_on(scenario, "Island")

    assert island.zone is Zone.EXILE
    assert scenario.player("alice").mana_pool.floating == {Color.GREEN: 1}
    assert scenario.player("alice").life == 20
    assert scenario.player("bob").life == 20


def test_klothys_the_mana_choice_offers_only_red_and_green():
    scenario = _klothys_board(bob_graveyard=["Island"])
    scenario.will_choose(Color.RED.value, source="Klothys, God of Destiny")

    _klothys_resolves_on(scenario, "Island")

    assert scenario.player("alice").mana_pool.floating == {Color.RED: 1}
    (question,) = [
        decision
        for decision in scenario.questions_asked()
        if decision.source == "Klothys, God of Destiny"
    ]
    assert set(question.options) == {Color.RED.value, Color.GREEN.value}


def test_klothys_exiling_a_nonland_card_drains_instead():
    scenario = _klothys_board(bob_graveyard=["Grizzly Bears"])

    bears = _klothys_resolves_on(scenario, "Grizzly Bears")

    assert bears.zone is Zone.EXILE
    assert scenario.player("alice").life == 22
    assert scenario.player("bob").life == 18
    assert scenario.player("alice").mana_pool.floating == {}


def test_klothys_with_its_target_gone_does_neither():
    scenario = _klothys_board(bob_graveyard=["Grizzly Bears"])
    scenario.start_at(Step.UPKEEP)
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "bob")
    scenario.choose_trigger_targets("Klothys, God of Destiny", [bears])
    _walk_to(scenario, Step.PRECOMBAT_MAIN)
    scenario.game.exile_cards([bears])

    scenario.resolve_top()

    assert scenario.player("alice").life == 20
    assert scenario.player("bob").life == 20
    assert scenario.player("alice").mana_pool.floating == {}
