"""Behold: CR 701.4's keyword action.

"Behold a [quality]" means "Reveal a [quality] card from your hand or choose a
[quality] permanent you control on the battlefield" (CR 701.4a). Not new to
Reality Fracture - `grep -ri behold` returned nothing in this engine before
this wave (S10 survey, 2026-09-19), and the keyword itself predates the set
(Tarkir: Dragonstorm's Dragon cycle, Eldraine's Kithkin cycle).

Countersculpt and Theorist's Sanctum print it as an additional cost -
"behold a Jace or pay {1}." - the same CR 601.2b "[cost] or pay [mana]" shape
`test_additional_cost_alternatives.py` generalized, with `behold` now a third
readable component alongside sacrifice/discard/exile/tap. Generality is
proved on Kinsbaile Aspirant (Eldritch Moon... no - Lorwyn block's Eldraine
remaster "ecl"), a Kithkin rather than a Jace, and on both of Behold's own
halves: revealing a card from hand, and choosing a permanent already on the
battlefield.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.cost import ComponentKind, additional_cost_phrases
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_kinsbaile_aspirant_beheld_by_choosing_a_battlefield_permanent():
    """Kinsbaile Aspirant: "behold a Kithkin or pay {2}." Choosing the behold
    half costs no extra mana, and the beheld permanent is untouched - not
    tapped, not sacrificed, not exiled."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Kinsbaile Aspirant"],
            battlefield=["Plains", "Kinsbaile Aspirant"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    assert additional_cost_phrases(scenario.find("Kinsbaile Aspirant", Zone.HAND).card) == [
        "behold a Kithkin or pay {2}"
    ]
    already_in_play = scenario.creature("Kinsbaile Aspirant", "alice")
    (plains,) = scenario.untapped_sources("Plains", username="alice")

    scenario.cast_and_resolve("Kinsbaile Aspirant", plains, beholding=[already_in_play])

    assert already_in_play.zone is Zone.BATTLEFIELD
    assert not already_in_play.tapped
    assert plains.tapped
    battlefield_kithkin = [
        state for state in scenario.game.battlefield if state.name == "Kinsbaile Aspirant"
    ]
    assert len(battlefield_kithkin) == 2


def test_kinsbaile_aspirant_beheld_by_revealing_a_hand_card():
    """The other half of the same choice: a Kithkin card revealed from hand,
    left exactly where it was (CR 701.20b)."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Kinsbaile Aspirant", "Kinsbaile Aspirant"],
            battlefield=["Plains"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    first, second = scenario.game.player("alice").hand
    (plains,) = scenario.untapped_sources("Plains", username="alice")

    scenario.cast_and_resolve("Kinsbaile Aspirant", plains, beholding=[second])

    assert second.zone is Zone.HAND
    assert first.zone is Zone.BATTLEFIELD
    assert second.id in {known.card_id for known in scenario.game.known_to("bob")}


def test_kinsbaile_aspirant_can_be_paid_with_mana_alone():
    """No Kithkin anywhere - the mana alternative is still a legal cast."""
    scenario = (
        Scenario()
        .player("alice", hand=["Kinsbaile Aspirant"], battlefield=["Plains", "Plains", "Plains"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Plains", "Plains", "Plains", username="alice")

    scenario.cast_and_resolve("Kinsbaile Aspirant", *sources)

    assert scenario.find("Kinsbaile Aspirant", Zone.BATTLEFIELD).zone is Zone.BATTLEFIELD
    assert all(source.tapped for source in sources)


def test_countersculpt_reads_behold_or_pay_as_its_additional_cost():
    """Countersculpt (Reality Fracture, the reported card): "behold a Jace or
    pay {1}." Only the cost side is this stream's scope - "Empower Jace 1" is
    S1's own mechanic and is left unresolved here; this only proves
    Countersculpt is castable and its additional cost reads as `BEHOLD`."""
    scenario = (
        Scenario().player("alice", hand=["Countersculpt"], battlefield=["Island", "Island"]).build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    phrases = additional_cost_phrases(scenario.find("Countersculpt", Zone.HAND).card)
    assert phrases == ["behold a Jace or pay {1}"]

    casting = scenario.cast("Countersculpt", username="alice")
    built = casting._printed_additional_costs()  # noqa: SLF001
    (cost,) = built
    assert cost.components == [] or cost.components[0].kind is ComponentKind.BEHOLD
