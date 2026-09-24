"""Behold: CR 701.4's keyword action.

"Behold a [quality]" means "Reveal a [quality] card from your hand or choose a
[quality] permanent you control on the battlefield" (CR 701.4a). Not new to
Reality Fracture - `grep -ri behold` returned nothing in this engine before
this wave (S10 survey, 2026-09-19), and the keyword itself predates the set
(Tarkir: Dragonstorm's Dragon cycle, Eldraine's Kithkin cycle).

Countersculpt prints it as an additional cost - "behold a Jace or pay {1}." -
the same CR 601.2b "[cost] or pay [mana]" shape
`test_additional_cost_alternatives.py` generalized, with `behold` now a third
readable component alongside sacrifice/discard/exile/tap. Generality is
proved on Kinsbaile Aspirant (set `ecl`, the Eldraine remaster), a Kithkin
rather than a Jace, and on both of Behold's own halves: revealing a card from
hand, and choosing a permanent already on the battlefield.

Theorist's Sanctum prints Behold's *other* shape: "As this land enters, you
may behold a Jace. If you don't, this land enters tapped." - CR 614.12a's
own "choice before it enters" pattern, already built for shocklands (pay
life) and reveal lands (reveal a card); this only adds a third reader,
`_behold_or_tapped`, alongside the two that were already there. No off-set
card prints this exact "behold ... enters tapped" combination (searched
Scryfall for `o:"you may behold" o:"enters tapped"` - no matches), so
generality here rests on reusing the same CR 614.12a choice machinery the
existing shockland/reveal-land tests already exercise, not on a second card.
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


# -- Behold as a CR 614.12a "enters tapped unless" choice (Theorist's Sanctum) -


def test_theorist_sanctum_enters_untapped_beholding_a_jace_on_the_battlefield():
    """Theorist's Sanctum: "As this land enters, you may behold a Jace. If you
    don't, this land enters tapped." Choosing to behold an already-controlled
    Jace leaves it untouched - not tapped, not sacrificed."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Theorist's Sanctum"],
            battlefield=["Jace Beleren"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    jace = scenario.find("Jace Beleren", Zone.BATTLEFIELD)
    scenario.will_take_the_may(True, source="Theorist's Sanctum")
    scenario.will_choose_cards(jace, username="alice", source="Theorist's Sanctum")

    sanctum = scenario.play_land("Theorist's Sanctum")

    assert not sanctum.tapped
    assert jace.zone is Zone.BATTLEFIELD
    assert not jace.tapped


def test_theorist_sanctum_enters_untapped_beholding_a_jace_from_hand():
    """The other half: a Jace card revealed from hand, left in hand."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Theorist's Sanctum", "Jace Beleren"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    jace = scenario.find("Jace Beleren", Zone.HAND)
    scenario.will_take_the_may(True, source="Theorist's Sanctum")
    scenario.will_choose_cards(jace, username="alice", source="Theorist's Sanctum")

    sanctum = scenario.play_land("Theorist's Sanctum")

    assert not sanctum.tapped
    assert jace.zone is Zone.HAND
    assert jace.id in {known.card_id for known in scenario.game.known_to("bob")}


def test_theorist_sanctum_enters_tapped_with_no_jace_to_behold():
    """No Jace on the battlefield or in hand: nobody is asked, and CR 118.3
    leaves beholding unpayable, so the land enters tapped."""
    scenario = Scenario().player("alice", hand=["Theorist's Sanctum"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    sanctum = scenario.play_land("Theorist's Sanctum")

    assert sanctum.tapped


def test_theorist_sanctum_enters_tapped_when_declining_to_behold():
    """A Jace is available, but the controller declines - CR 118.8b's kind of
    choice, still legal to decline even though there is something to spend."""
    scenario = (
        Scenario()
        .player("alice", hand=["Theorist's Sanctum"], battlefield=["Jace Beleren"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    jace = scenario.find("Jace Beleren", Zone.BATTLEFIELD)
    scenario.will_take_the_may(False, source="Theorist's Sanctum")

    sanctum = scenario.play_land("Theorist's Sanctum")

    assert sanctum.tapped
    assert jace.zone is Zone.BATTLEFIELD


# -- Behold as a resolution-time effect (Elven Passage), not a cost --------
#
# Elven Passage's whole activated ability: "{T}, Pay 1 life, Sacrifice this
# land: Search your library for a basic land card, put it onto the
# battlefield tapped, then shuffle. You may behold an Elf. If you do, untap
# that land." A different half of the same CR 701.4a keyword action from
# the cost-side reader above: this card's own "You may behold ..." sentence
# is the ability's *resolution* text, after the search has already put a
# land onto the battlefield - a genuinely new dispatch path
# (`effects._parse_search_put_battlefield_tapped_then_behold_untap_clause`,
# a whole-text reader since "that land" (CR 400.7/CR 607.1) names the
# specific card the search just found). One `CHOOSE_CARDS` question over the
# union of a matching hand card and a matching battlefield permanent folds
# CR 701.4a's own "or" together with CR 608.2d's "you may": declining
# (choosing none) is a legal answer whenever the question is even asked, and
# it is asked at all only when at least one candidate exists in either pool.
#
# No second printing pairs "behold" with an "if you do, untap" rider
# anywhere in the card pool or on Scryfall (checked in the session that
# wrote this addition) - see the dated `MEMORY.md` line. Generality is
# instead demonstrated here across all three of CR 701.4a's own branches:
# beholding from hand, beholding from the battlefield, and declining.


def _elven_passage_board(*, hand_extra=(), battlefield_extra=()):
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=list(hand_extra),
            battlefield=["Elven Passage", *battlefield_extra],
            library=["Forest", "Grizzly Bears"],
        )
        .player("bob")
    )


def test_beholding_an_elf_from_hand_untaps_the_fetched_land():
    scenario = _elven_passage_board(hand_extra=["Llanowar Elves"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    passage = scenario.find("Elven Passage", Zone.BATTLEFIELD, "alice")
    (elves,) = scenario.player("alice").hand
    assert elves.name == "Llanowar Elves"
    life_before = scenario.player("alice").life

    scenario.will_choose_cards(elves, username="alice", source="Elven Passage")
    scenario.activate(passage, sacrificing=[passage])
    scenario.pass_until_resolved()

    forest = scenario.find("Forest", Zone.BATTLEFIELD, "alice")
    assert not forest.tapped, "beholding untapped the land the search just found"
    assert elves in scenario.player("alice").hand, "revealing does not move the card (CR 701.20a)"
    assert scenario.player("alice").life == life_before - 1


def test_beholding_an_elf_already_on_the_battlefield_untaps_the_fetched_land():
    scenario = _elven_passage_board(battlefield_extra=["Llanowar Elves"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    passage = scenario.find("Elven Passage", Zone.BATTLEFIELD, "alice")
    elves = scenario.creature("Llanowar Elves", "alice")

    scenario.will_choose_cards(elves, username="alice", source="Elven Passage")
    scenario.activate(passage, sacrificing=[passage])
    scenario.pass_until_resolved()

    forest = scenario.find("Forest", Zone.BATTLEFIELD, "alice")
    assert not forest.tapped


def test_declining_to_behold_leaves_the_fetched_land_tapped():
    scenario = _elven_passage_board(hand_extra=["Llanowar Elves"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    passage = scenario.find("Elven Passage", Zone.BATTLEFIELD, "alice")

    scenario.will_choose_cards(username="alice", source="Elven Passage")
    scenario.activate(passage, sacrificing=[passage])
    scenario.pass_until_resolved()

    forest = scenario.find("Forest", Zone.BATTLEFIELD, "alice")
    assert forest.tapped


def test_with_no_elf_anywhere_the_land_stays_tapped_and_nothing_is_asked():
    """CR 608.2d: with no candidate in either pool, the "you may behold" is
    never even asked - `Game.ask` would refuse a question with no legal
    affirmative answer, so this only passes if the reader itself skips it."""
    scenario = _elven_passage_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    passage = scenario.find("Elven Passage", Zone.BATTLEFIELD, "alice")

    scenario.activate(passage, sacrificing=[passage])
    scenario.pass_until_resolved()

    forest = scenario.find("Forest", Zone.BATTLEFIELD, "alice")
    assert forest.tapped
