"""Cast triggers that copy the spell once an optional cost is paid.

- Aziza, Mage Tower Captain: "Whenever you cast an instant or sorcery spell,
  you may tap three untapped creatures you control. If you do, copy that
  spell. You may choose new targets for the copy."
- Mica, Reader of Ruins: "Whenever you cast an instant or sorcery spell, you
  may sacrifice an artifact. If you do, copy that spell and you may choose
  new targets for the copy."
- Mirari (off-pool proof, a mana cost instead): "Whenever you cast an
  instant or sorcery spell, you may pay {3}. If you do, copy that spell. You
  may choose new targets for the copy."
- Raff, Weatherlight Stalwart (off-pool proof of the tap cost, a different
  count and consequence): "Whenever you cast an instant or sorcery spell, you
  may tap two untapped creatures you control. If you do, draw a card."

CR 118.12's "[Do something]. If [a player] does, [effect]" - the cost is paid
while the trigger resolves, and the effect only follows a payment. CR
707.10, read whole with `mise run rules:find` in the session that wrote this
file: "To copy a spell ... means to put a copy of it onto the stack; a copy
of a spell isn't cast"; CR 707.10c: the controller "may leave any number of
the targets unchanged ... If the player chooses to change some or all of the
targets, the new targets must be legal." CR 701.26a is tapping.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import PlayedScenario, Scenario

AZIZA = "Aziza, Mage Tower Captain"
MICA = "Mica, Reader of Ruins"
RAFF = "Raff, Weatherlight Stalwart"


def board(*battlefield: str, hand: tuple[str, ...] = ("Lightning Bolt",)) -> PlayedScenario:
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=list(hand),
            library=["Island"] * 5,
            battlefield=[*battlefield, "Mountain", "Mountain", "Mountain", "Mountain"],
        )
        .player("bob", life=20, battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def bolt_bob(scenario: PlayedScenario):
    (mountain,) = scenario.untapped_sources("Mountain")
    return scenario.cast_onto_stack("Lightning Bolt", mountain, targets=["bob"])


def resolve_everything(scenario: PlayedScenario) -> None:
    while scenario.game.stack:
        scenario.resolve_top()


def bolts_on_stack(scenario: PlayedScenario) -> list:
    return [
        state for state in scenario.game.stack if getattr(state, "name", "") == "Lightning Bolt"
    ]


# -- Aziza: tap three untapped creatures -----------------------------------------------


def test_aziza_taps_three_creatures_and_copies_the_bolt():
    scenario = board(AZIZA, "Savannah Lions", "Goblin Guide")
    creatures = [
        scenario.creature(AZIZA, "alice"),
        scenario.creature("Savannah Lions", "alice"),
        scenario.creature("Goblin Guide", "alice"),
    ]
    scenario.will_take_the_may(True, username="alice", source=AZIZA)
    scenario.will_choose_cards(*creatures, username="alice", source=AZIZA)
    scenario.will_take_the_may(False, username="alice", source=AZIZA)
    bolt_bob(scenario)

    scenario.resolve_top()  # Aziza's trigger

    assert all(creature.tapped for creature in creatures)
    assert len(bolts_on_stack(scenario)) == 2
    resolve_everything(scenario)
    assert scenario.player("bob").life == 14


def test_the_copy_may_choose_new_targets():
    scenario = board(AZIZA, "Savannah Lions", "Goblin Guide")
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.will_take_the_may(True, username="alice", source=AZIZA, times=2)
    scenario.will_choose_targets(bears, username="alice", source=AZIZA)
    bolt_bob(scenario)
    resolve_everything(scenario)
    assert bears.zone is Zone.GRAVEYARD
    assert scenario.player("bob").life == 17


def test_too_few_untapped_creatures_cannot_pay():
    """Aziza and one more creature are two, not three: "yes" is illegal (CR
    118.3), so an unscripted player declines and nothing is copied."""
    scenario = board(AZIZA, "Savannah Lions")
    bolt_bob(scenario)
    scenario.resolve_top()
    assert len(bolts_on_stack(scenario)) == 1
    assert not scenario.creature(AZIZA, "alice").tapped


def test_a_tapped_creature_is_not_an_untapped_creature():
    scenario = board(AZIZA, "Savannah Lions", "Goblin Guide")
    scenario.creature("Goblin Guide", "alice").tap()
    bolt_bob(scenario)
    scenario.resolve_top()
    assert len(bolts_on_stack(scenario)) == 1


def test_declining_taps_nothing_and_copies_nothing():
    scenario = board(AZIZA, "Savannah Lions", "Goblin Guide")
    scenario.will_take_the_may(False, username="alice", source=AZIZA)
    bolt_bob(scenario)
    scenario.resolve_top()
    assert len(bolts_on_stack(scenario)) == 1
    assert not any(
        permanent.tapped
        for permanent in scenario.game.battlefield
        if permanent.controller == "alice" and permanent.is_creature
    )


def test_a_creature_spell_does_not_trigger_aziza():
    scenario = board(AZIZA, "Savannah Lions", "Goblin Guide", hand=("Grizzly Bears", "Forest"))
    scenario.play_land("Forest")
    casting = scenario.cast("Grizzly Bears")
    scenario.auto_pay(casting.begin_paying())
    scenario.put_on_stack(casting)
    assert [item.name for item in scenario.game.stack] == ["Grizzly Bears"]


def test_the_copy_is_not_cast_so_aziza_does_not_trigger_again():
    scenario = board(AZIZA, "Savannah Lions", "Goblin Guide", "Grizzly Bears")
    scenario.will_take_the_may(True, username="alice", source=AZIZA)
    scenario.will_choose_cards(
        scenario.creature(AZIZA, "alice"),
        scenario.creature("Savannah Lions", "alice"),
        scenario.creature("Goblin Guide", "alice"),
        username="alice",
        source=AZIZA,
    )
    scenario.will_take_the_may(False, username="alice", source=AZIZA)
    bolt_bob(scenario)
    scenario.resolve_top()
    assert all(not getattr(item, "is_ability", False) for item in scenario.game.stack)
    assert scenario.game.pending_triggers == []


# -- Raff: the tap cost with a different count and consequence -------------------------


def test_raff_taps_two_creatures_to_draw_a_card():
    scenario = board(RAFF, "Savannah Lions")
    hand_before = len(scenario.player("alice").hand)
    scenario.will_take_the_may(True, username="alice", source=RAFF)
    scenario.will_choose_cards(
        scenario.creature(RAFF, "alice"),
        scenario.creature("Savannah Lions", "alice"),
        username="alice",
        source=RAFF,
    )
    bolt_bob(scenario)
    scenario.resolve_top()
    assert len(scenario.player("alice").hand) == hand_before  # Bolt left, a card came
    assert scenario.creature(RAFF, "alice").tapped


def test_raff_with_one_creature_draws_nothing():
    scenario = board(RAFF)
    hand_before = len(scenario.player("alice").hand)
    bolt_bob(scenario)
    scenario.resolve_top()
    assert len(scenario.player("alice").hand) == hand_before - 1


# -- Mica: sacrifice an artifact -----------------------------------------------------


def test_mica_sacrifices_an_artifact_and_copies_the_bolt():
    scenario = board(MICA, "Ornithopter")
    ornithopter = scenario.creature("Ornithopter", "alice")
    scenario.will_take_the_may(True, username="alice", source=MICA)
    scenario.will_take_the_may(False, username="alice", source=MICA)
    bolt_bob(scenario)
    scenario.resolve_top()
    assert ornithopter.zone is Zone.GRAVEYARD
    assert len(bolts_on_stack(scenario)) == 2
    resolve_everything(scenario)
    assert scenario.player("bob").life == 14


def test_micas_copy_may_choose_new_targets():
    scenario = board(MICA, "Ornithopter")
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.will_take_the_may(True, username="alice", source=MICA, times=2)
    scenario.will_choose_targets(bears, username="alice", source=MICA)
    bolt_bob(scenario)
    resolve_everything(scenario)
    assert bears.zone is Zone.GRAVEYARD
    assert scenario.player("bob").life == 17


def test_mica_with_no_artifact_copies_nothing():
    scenario = board(MICA, "Savannah Lions")
    bolt_bob(scenario)
    scenario.resolve_top()
    assert len(bolts_on_stack(scenario)) == 1
    assert scenario.creature("Savannah Lions", "alice").zone is Zone.BATTLEFIELD


def test_declining_micas_sacrifice_keeps_the_artifact():
    scenario = board(MICA, "Ornithopter")
    scenario.will_take_the_may(False, username="alice", source=MICA)
    bolt_bob(scenario)
    scenario.resolve_top()
    assert scenario.creature("Ornithopter", "alice").zone is Zone.BATTLEFIELD
    assert len(bolts_on_stack(scenario)) == 1


# -- Mirari: a mana cost ----------------------------------------------------------------


def test_mirari_pays_three_and_copies_the_bolt():
    scenario = board("Mirari")
    scenario.will_take_the_may(True, username="alice", source="Mirari")
    scenario.will_take_the_may(False, username="alice", source="Mirari")
    bolt_bob(scenario)
    scenario.resolve_top()
    assert len(bolts_on_stack(scenario)) == 2
    resolve_everything(scenario)
    assert scenario.player("bob").life == 14


def test_mirari_without_the_mana_copies_nothing():
    scenario = board("Mirari")
    for mountain in scenario.untapped_sources("Mountain", "Mountain"):
        mountain.tap()
    bolt_bob(scenario)
    scenario.resolve_top()
    assert len(bolts_on_stack(scenario)) == 1
