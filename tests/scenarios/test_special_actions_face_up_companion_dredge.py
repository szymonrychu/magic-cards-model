"""Three special actions a seat outside the rules layer needs a reachable
entry point for, each with the engine's own refusal text: turning a face-down
permanent face up (CR 702.37e, CR 702.168d, CR 701.40b), bringing a chosen
companion into hand (CR 116.2g), and replacing a draw with dredge
(CR 702.52a).

Every CR number here was looked up with `mise run rules:find` in the session
that wrote this file:

- **CR 702.37b**: "Megamorph is a variant of the morph ability. ... 'As this
  permanent is turned face up, put a +1/+1 counter on it if its megamorph
  cost was paid to turn it face up.'"
- **CR 702.168d**: disguise's own turn-up procedure, identically shaped to
  morph's CR 702.37e but for a disguise cost - no counter.
- **CR 701.40a-b**: manifest's own face-down/turn-up pair - a manifested
  permanent is turned face up by paying the *card's own mana cost*, not a
  morph cost, and only when that card is a creature card with one.
- **CR 116.2g**: bringing a chosen companion into hand for {3} - already
  fully built and tested (`tests/scenarios/test_companion.py`); the tests
  here are a second, independent proof on an off-pool companion.
- **CR 702.52a-b**: dredge replaces an individual draw with a mill, "as long
  as you have at least N cards in your library" - `tests/scenarios/
  test_dredge.py` already covers the primitive (`machines/keywords.dredge`/
  `.why_cannot_dredge`) directly; the tests here are the missing half,
  `Game.draw_cards` actually offering it as the draw happens.
- **CR 616.1e**: "any of the applicable replacement ... effects may be
  chosen" - governs declining dredge as much as taking it.

Cards used and why: Marang River Skeleton (Megamorph {3}{B}, no other
turned-face-up trigger, so the counter is the whole story), Bolrac-Clan
Basher (Disguise {3}{R}{R}, likewise no rider), Elvish Warrior (a vanilla
{G}{G} 2/2 with no text at all, proving manifest's turn-up on a card that
never had morph or disguise to begin with), Obosh, the Preypiercer (a
companion this pool has not used elsewhere), Golgari Thug (Dredge 4), Life
from the Loam (Dredge 3, a sorcery - proving the mechanic is read off the
graveyard card's ability, not off being a creature) and Greater Mossdog
(Dredge 3, a plain vanilla creature with no other ability, used only to be
named as an *ineligible* pick alongside Golgari Thug). None of these is in
any existing scenario's deck pool.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import DecisionPending
from magic_cards_model.machines.keywords import why_cannot_dredge
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Type
from tests.scenarios.harness import PlayedScenario, Scenario

# ---------------------------------------------------------------------------
# Turning face up: morph/megamorph/disguise/manifest, and every refusal.
# ---------------------------------------------------------------------------


def face_up_board(
    *, hand: str | None = None, battlefield: list[str], bob: bool = True
) -> PlayedScenario:
    builder = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=[hand] if hand else [], battlefield=battlefield)
    )
    if bob:
        builder = builder.player("bob")
    return builder.build()


def cast_face_down(scenario: PlayedScenario, name: str, keyword: str, *mana: str):
    """Cast `name` face down for {3} using `keyword` (Megamorph or
    Disguise), paying with `mana` sources by name."""
    casting = scenario.cast(name)
    casting.use_keyword(keyword)
    assert str(casting.total_cost.mana) == "{3}"
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources(*mana))
    scenario.put_on_stack(casting)
    return scenario.resolve_top()


def test_a_megamorph_creature_pays_its_cost_and_gets_a_counter():
    """CR 702.37b: the counter half of megamorph, still absent before this
    change per `docs/engine-coverage.md`."""
    scenario = face_up_board(hand="Marang River Skeleton", battlefield=["Swamp"] * 8)
    scenario.start_at(Step.PRECOMBAT_MAIN)
    permanent = cast_face_down(
        scenario, "Marang River Skeleton", "Megamorph", "Swamp", "Swamp", "Swamp"
    )
    assert permanent.face_down
    assert permanent.counters.counts == {}

    turned = scenario.turn_face_up(
        permanent, *scenario.untapped_sources("Swamp", "Swamp", "Swamp", "Swamp")
    )

    assert turned.face_up
    assert turned.name == "Marang River Skeleton"
    assert turned.counters["+1/+1"] == 1
    # 1/1 printed, +1/+1 from the counter (CR 122.1a, layer 7c).
    assert (turned.power, turned.toughness) == (2, 2)


def test_a_disguise_creature_is_turned_face_up_with_no_counter():
    """CR 702.168d is morph's twin - no megamorph clause, so no counter."""
    scenario = face_up_board(hand="Bolrac-Clan Basher", battlefield=["Mountain"] * 8)
    scenario.start_at(Step.PRECOMBAT_MAIN)
    permanent = cast_face_down(
        scenario, "Bolrac-Clan Basher", "Disguise", "Mountain", "Mountain", "Mountain"
    )
    assert permanent.face_down

    turned = scenario.turn_face_up(
        permanent,
        *scenario.untapped_sources("Mountain", "Mountain", "Mountain", "Mountain", "Mountain"),
    )

    assert turned.face_up
    assert turned.name == "Bolrac-Clan Basher"
    assert turned.counters.counts == {}
    assert set(turned.keywords) >= {"Double strike", "Trample"}


def manifest_top_card(scenario: PlayedScenario, username: str = "alice"):
    """Manifest `username`'s own top library card through Mastery of the
    Unseen's real activated ability - `test_manifest.py`'s own pattern - so
    the manifested permanent gets a deterministic id the way a hand-built
    `CardState` constructed mid-test never would."""
    mastery = scenario.find("Mastery of the Unseen", Zone.BATTLEFIELD, username)
    scenario.activate(
        mastery,
        *scenario.untapped_sources("Plains", "Plains", "Plains", "Plains"),
        username=username,
    )
    scenario.pass_until_resolved()
    return next(state for state in scenario.game.battlefield if state.face_down)


def test_a_manifested_vanilla_creature_is_turned_face_up_for_its_mana_cost():
    """CR 701.40b: a manifested permanent's own turn-up, generalised past
    morph/disguise entirely - Elvish Warrior has neither."""
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Elvish Warrior"],
            battlefield=["Mastery of the Unseen", *["Plains"] * 4, "Forest", "Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    warrior = manifest_top_card(scenario)

    assert warrior.face_down
    assert warrior.manifested
    assert scenario.game.why_cannot_turn_face_up_as("alice", warrior) is None

    turned = scenario.turn_face_up(warrior, *scenario.untapped_sources("Forest", "Forest"))

    assert turned.face_up
    assert turned.name == "Elvish Warrior"
    assert not turned.manifested
    assert Type.CREATURE in turned.types


def test_a_manifested_noncreature_card_cannot_be_turned_face_up_this_way():
    """CR 701.40b's own parenthetical: not a creature card, no procedure."""
    scenario = (
        Scenario()
        .player("alice", library=["Forest"], battlefield=["Mastery of the Unseen", *["Plains"] * 4])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    manifested_forest = manifest_top_card(scenario)

    refusal = scenario.game.why_cannot_turn_face_up(manifested_forest)

    assert refusal is not None
    assert "not a creature card" in refusal


def test_refusal_the_permanent_is_already_face_up():
    scenario = face_up_board(battlefield=["Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears")

    refusal = scenario.game.why_cannot_turn_face_up_as("alice", bears)

    assert refusal is not None
    assert "already face up" in refusal


def test_refusal_not_its_controller():
    scenario = face_up_board(hand="Marang River Skeleton", battlefield=["Swamp"] * 8)
    scenario.start_at(Step.PRECOMBAT_MAIN)
    permanent = cast_face_down(
        scenario, "Marang River Skeleton", "Megamorph", "Swamp", "Swamp", "Swamp"
    )

    refusal = scenario.game.why_cannot_turn_face_up_as("bob", permanent)

    assert refusal is not None
    assert "bob does not control" in refusal
    assert "alice" in refusal
    # Alice herself still may.
    assert scenario.game.why_cannot_turn_face_up_as("alice", permanent) is None


def test_refusal_no_turn_up_cost_at_all():
    """A permanent turned face down directly - no morph, not manifested."""
    scenario = face_up_board(battlefield=["Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears")
    bears.turn_face_down()

    refusal = scenario.game.why_cannot_turn_face_up_as("alice", bears)

    assert refusal is not None
    assert "no morph cost" in refusal


def test_refusal_cannot_pay():
    """Enough mana to cast face down, none left over for the turn-up cost."""
    scenario = face_up_board(hand="Marang River Skeleton", battlefield=["Swamp", "Swamp", "Swamp"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    permanent = cast_face_down(
        scenario, "Marang River Skeleton", "Megamorph", "Swamp", "Swamp", "Swamp"
    )

    refusal = scenario.game.why_cannot_turn_face_up_as("alice", permanent)

    assert refusal is not None
    assert "cannot pay" in refusal
    with pytest.raises(ValueError):
        scenario.turn_face_up(permanent)


# ---------------------------------------------------------------------------
# Companion: pays and refuses (CR 116.2g) - full coverage already lives in
# test_companion.py; this is a second, independent proof.
# ---------------------------------------------------------------------------


def test_companion_to_hand_pays_and_is_once_per_game():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Island"] * 3, companion="Obosh, the Preypiercer")
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    assert scenario.game.why_cannot_bring_companion_to_hand("alice") is None
    companion = scenario.bring_companion_to_hand(
        *scenario.untapped_sources("Island", "Island", "Island")
    )

    assert companion.name == "Obosh, the Preypiercer"
    assert companion.zone is Zone.HAND

    refusal = scenario.game.why_cannot_bring_companion_to_hand("alice")
    assert refusal is not None
    assert "already brought their companion" in refusal


def test_companion_refuses_with_none_chosen():
    scenario = Scenario().manual_turn_based_actions().player("alice").player("bob").build()

    refusal = scenario.game.why_cannot_bring_companion_to_hand("alice")

    assert refusal is not None
    assert "has not chosen a companion" in refusal


# ---------------------------------------------------------------------------
# Dredge: offered on a draw, taken, declined, and refused for an
# ineligible pick (CR 702.52a-b, CR 616.1e).
# ---------------------------------------------------------------------------


def dredge_board(library: list[str], graveyard: list[str]) -> PlayedScenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", library=library, graveyard=graveyard)
        .player("bob")
        .build()
    )


def test_dredge_is_offered_and_taken_instead_of_drawing():
    scenario = dredge_board(library=["Mountain"] * 6, graveyard=["Golgari Thug", "Lightning Bolt"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_dredge("Golgari Thug", username="alice")

    drawn = scenario.draw(1, "alice")

    assert drawn == []  # the draw was replaced, not fulfilled (CR 603.2g)
    hand_names = [c.name for c in scenario.player("alice").hand]
    assert hand_names == ["Golgari Thug"]
    graveyard_names = sorted(c.name for c in scenario.player("alice").graveyard)
    assert graveyard_names == ["Lightning Bolt", "Mountain", "Mountain", "Mountain", "Mountain"]
    assert len(scenario.player("alice").library) == 2


def test_dredge_can_be_declined_to_draw_normally():
    scenario = dredge_board(library=["Mountain"] * 6, graveyard=["Golgari Thug"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_dredge(None, username="alice")

    drawn = scenario.draw(1, "alice")

    assert [c.name for c in drawn] == ["Mountain"]
    assert [c.name for c in scenario.player("alice").graveyard] == ["Golgari Thug"]
    assert len(scenario.player("alice").library) == 5


def test_declining_with_nobody_scripted_also_draws_normally():
    """`default_answer`'s own unscripted default: draw, do not dredge."""
    scenario = dredge_board(library=["Mountain"] * 6, graveyard=["Golgari Thug"])
    scenario.start_at(Step.PRECOMBAT_MAIN)

    drawn = scenario.draw(1, "alice")

    assert [c.name for c in drawn] == ["Mountain"]
    assert [c.name for c in scenario.player("alice").graveyard] == ["Golgari Thug"]


def test_dredge_is_not_offered_when_the_library_is_too_small():
    """CR 702.52b: "can't mill any of them this way" - not asked at all."""
    scenario = dredge_board(library=["Mountain"] * 3, graveyard=["Golgari Thug"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    thug = scenario.find("Golgari Thug", Zone.GRAVEYARD, "alice")
    assert "dredge 4 needs 4" in (why_cannot_dredge(scenario.game, thug, "alice") or "")

    drawn = scenario.draw(1, "alice")

    assert [c.name for c in drawn] == ["Mountain"]
    assert scenario.game.decisions.asked == []  # no DREDGE question was ever put


def test_dredge_refuses_an_ineligible_pick_with_the_engine_s_own_reason():
    """A scripted answer naming a dredge card this player cannot actually
    dredge with right now is refused with `why_cannot_dredge`'s own text,
    not silently honoured."""
    scenario = dredge_board(library=["Mountain"] * 3, graveyard=["Golgari Thug", "Greater Mossdog"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    thug = scenario.find("Golgari Thug", Zone.GRAVEYARD, "alice")
    # Dredge 3 (Greater Mossdog) is satisfiable with 3 cards in the library;
    # dredge 4 (Golgari Thug) is not (CR 702.52b) - so only Greater Mossdog is
    # actually offered.
    scenario.will_dredge(thug, username="alice")

    with pytest.raises(ValueError, match="dredge 4 needs 4"):
        scenario.draw(1, "alice")


def test_dredge_generality_on_a_sorcery_not_a_creature():
    """CR 702.52a reads the graveyard card's own ability, never its type -
    Life from the Loam is a sorcery, not a creature, and not the card the
    other tests here already exercised."""
    scenario = dredge_board(
        library=["Mountain"] * 6, graveyard=["Life from the Loam", "Forest", "Island"]
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_dredge("Life from the Loam", username="alice")

    drawn = scenario.draw(1, "alice")

    assert drawn == []
    assert [c.name for c in scenario.player("alice").hand] == ["Life from the Loam"]
    assert len(scenario.player("alice").library) == 3


def test_dredge_appears_in_a_pending_decision_s_legal_answers():
    """A paused game still tells a seat what it may answer with (`legal_
    actions` while a `DREDGE` decision is pending)."""
    from magic_cards_model.machines.decisions import DecisionKind
    from magic_cards_model.machines.legal_actions import legal_actions
    from magic_cards_model.models.action import ActionKind

    scenario = dredge_board(library=["Mountain"] * 6, graveyard=["Golgari Thug"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.decisions.pause_when_unanswered = True

    with pytest.raises(DecisionPending) as excinfo:
        scenario.draw(1, "alice")
    pending = excinfo.value.pending
    assert pending.decision.kind is DecisionKind.DREDGE
    assert pending.decision.cards == (card_or_none(scenario, "Golgari Thug").id,)

    answers = legal_actions(scenario.game, "alice", pending=pending)
    assert {a.kind for a in answers} == {ActionKind.ANSWER_DECISION}


def card_or_none(scenario: PlayedScenario, name: str):
    return scenario.find(name, Zone.GRAVEYARD, "alice")
