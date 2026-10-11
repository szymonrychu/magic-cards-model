"""EP-01 round 2, task T7: static cast and play permissions and prohibitions
(CR 305.2, 305.1, 601.3, 611.3d, 701.20).

    Ghirapur Orrery / Rites of Flourishing - Each player may play an additional land.
    Aggressive Mining       - You can't play lands.
    Experimental Frenzy     - You can't play lands or cast spells from your hand.
    Lens of Clarity         - look at the top card and at face-down creatures you don't control.

The pool carries no second printing of any of these four shapes (the two
"each player" lands are the only ones, and the two prohibitions are the only
"you can't play lands" lines), so the listed cards are the proof.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.casting import PlayAction, why_cannot_cast_restriction
from magic_cards_model.machines.legal_actions import legal_actions
from magic_cards_model.models import Zone
from magic_cards_model.models.action import ActionKind, Affordability
from magic_cards_model.support import HANDLED, classify_clauses
from tests.cards import card
from tests.scenarios.harness import Scenario


def _handled(name: str, containing: str) -> None:
    outcomes = [o for o in classify_clauses(card(name)) if containing in o.text]
    assert outcomes, f"{name}: no clause containing {containing!r}"
    assert {o.category for o in outcomes} == {HANDLED}, outcomes


def _main(**players) -> Scenario:
    builder = Scenario().manual_turn_based_actions()
    for username, kwargs in players.items():
        builder = builder.player(username, **kwargs)
    scenario = builder.build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _offered(scenario, card_state, kind, username="alice") -> bool:
    return any(
        action.kind is kind and getattr(action, "card_id", None) == card_state.id
        for action in legal_actions(scenario.game, username)
    )


# -- Each player may play an additional land ------------------------------


@pytest.mark.parametrize("source", ["Ghirapur Orrery", "Rites of Flourishing"])
def test_each_player_may_play_an_additional_land(source):
    scenario = _main(
        alice={"hand": ["Forest", "Forest", "Forest"], "battlefield": [source]},
        bob={"library": ["Island"] * 4},
    )
    assert scenario.game.land_allowance("alice") == 2
    assert scenario.game.land_allowance("bob") == 2, (
        "CR 611.3d: each player, not only the controller"
    )
    scenario.play_land("Forest")
    scenario.play_land("Forest")
    with pytest.raises(ValueError, match="already used"):
        scenario.play_land("Forest")


@pytest.mark.parametrize("source", ["Ghirapur Orrery", "Rites of Flourishing"])
def test_an_opponents_each_player_grant_reaches_me_too(source):
    scenario = _main(
        alice={"hand": ["Forest", "Forest"]},
        bob={"battlefield": [source]},
    )
    assert scenario.game.land_allowance("alice") == 2
    scenario.play_land("Forest")
    scenario.play_land("Forest")


def test_without_the_grant_a_second_land_is_refused_and_the_grant_leaves_with_its_source():
    scenario = _main(
        alice={"hand": ["Forest", "Forest"], "battlefield": ["Ghirapur Orrery"]},
        bob={},
    )
    assert scenario.game.land_allowance("alice") == 2
    orrery = scenario.find("Ghirapur Orrery", Zone.BATTLEFIELD, "alice")
    scenario.game.destroy(orrery)
    assert scenario.game.land_allowance("alice") == 1
    scenario.play_land("Forest")
    with pytest.raises(ValueError, match="already used"):
        scenario.play_land("Forest")


def test_the_each_player_grants_stack_with_a_personal_one():
    scenario = _main(
        alice={
            "battlefield": ["Ghirapur Orrery", "Rites of Flourishing", "Azusa, Lost but Seeking"]
        },
        bob={},
    )
    assert scenario.game.land_allowance("alice") == 5
    assert scenario.game.land_allowance("bob") == 3


def test_each_player_land_grants_are_credited():
    _handled("Ghirapur Orrery", "Each player may play an additional land")
    _handled("Rites of Flourishing", "Each player may play an additional land")


# -- You can't play lands (Aggressive Mining) -----------------------------


def test_aggressive_mining_refuses_every_land_play_of_its_controller():
    scenario = _main(
        alice={"hand": ["Forest"], "battlefield": ["Aggressive Mining"]},
        bob={},
    )
    land = scenario.find("Forest", Zone.HAND, "alice")
    reason = scenario.game.why_cannot_play_land("alice")
    assert reason is not None and "Aggressive Mining" in reason
    with pytest.raises(ValueError, match="Aggressive Mining"):
        scenario.play_land("Forest")
    assert land.zone is Zone.HAND
    assert not _offered(scenario, land, ActionKind.PLAY_LAND)


def test_aggressive_mining_does_not_stop_an_opponents_land_play():
    scenario = _main(
        alice={"hand": ["Forest"]},
        bob={"battlefield": ["Aggressive Mining"]},
    )
    assert scenario.game.why_cannot_play_land("alice") is None
    scenario.play_land("Forest")


def test_aggressive_mining_still_lets_a_spell_put_a_land_onto_the_battlefield():
    scenario = _main(
        alice={"hand": ["Forest"], "battlefield": ["Aggressive Mining"]},
        bob={},
    )
    land = scenario.put_onto_battlefield("Forest")
    assert land.zone is Zone.BATTLEFIELD, (
        "CR 305.4: putting a land onto the battlefield is not playing it"
    )


def test_aggressive_mining_is_credited():
    _handled("Aggressive Mining", "You can't play lands")


# -- Experimental Frenzy: no lands or spells from hand ---------------------


def _frenzy():
    return _main(
        alice={
            "hand": ["Forest", "Lightning Bolt"],
            "battlefield": ["Experimental Frenzy", "Mountain"],
            "library": ["Mountain", "Lightning Bolt"],
        },
        bob={},
    )


def test_frenzy_refuses_a_land_and_a_spell_from_hand():
    scenario = _frenzy()
    land = scenario.find("Forest", Zone.HAND, "alice")
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "alice")
    with pytest.raises(ValueError, match="Experimental Frenzy"):
        scenario.play_land("Forest")
    assert not _offered(scenario, land, ActionKind.PLAY_LAND)
    reason = why_cannot_cast_restriction(bolt, "alice", scenario.game)
    assert reason is not None and "Experimental Frenzy" in reason
    assert not _offered(scenario, bolt, ActionKind.CAST)


def test_frenzy_still_allows_the_top_of_the_library():
    scenario = _frenzy()
    top = scenario.player("alice").library[0]
    assert _offered(scenario, top, ActionKind.PLAY_LAND)
    scenario.play_land("Mountain", from_zone=Zone.LIBRARY)
    assert top.zone is Zone.BATTLEFIELD


def test_frenzy_allows_casting_a_spell_from_the_top_of_the_library():
    scenario = _main(
        alice={
            "hand": ["Lightning Bolt"],
            "battlefield": ["Experimental Frenzy", "Mountain"],
            "library": ["Lightning Bolt", "Mountain"],
        },
        bob={},
    )
    top = scenario.player("alice").library[0]
    assert why_cannot_cast_restriction(top, "alice", scenario.game) is None
    assert _offered(scenario, top, ActionKind.CAST)


def test_frenzy_does_not_bind_an_opponent_and_ends_when_it_leaves():
    scenario = _main(
        alice={"hand": ["Forest"], "battlefield": ["Experimental Frenzy", "Mountain"]},
        bob={"hand": ["Lightning Bolt"]},
    )
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "bob")
    assert why_cannot_cast_restriction(bolt, "bob", scenario.game) is None
    frenzy = scenario.find("Experimental Frenzy", Zone.BATTLEFIELD, "alice")
    scenario.game.destroy(frenzy)
    scenario.play_land("Forest")


def test_frenzy_can_destroy_itself_for_3r():
    scenario = _main(
        alice={
            "battlefield": ["Experimental Frenzy", "Mountain", "Mountain", "Mountain", "Mountain"]
        },
        bob={},
    )
    frenzy = scenario.find("Experimental Frenzy", Zone.BATTLEFIELD, "alice")
    scenario.activate(
        frenzy, *scenario.untapped_sources("Mountain", "Mountain", "Mountain", "Mountain"), index=0
    )
    scenario.pass_until_resolved()
    assert frenzy.zone is Zone.GRAVEYARD


def test_frenzy_is_credited():
    _handled("Experimental Frenzy", "You can't play lands or cast spells from your hand")
    _handled("Experimental Frenzy", "Destroy this enchantment")


# -- Lens of Clarity: the top card and face-down creatures you don't control --


def _known_ids(scenario, viewer):
    return {known.card_id for known in scenario.game.known_to(viewer)}


def test_lens_of_clarity_shows_the_top_card_and_opposing_face_down_creatures():
    scenario = _main(
        alice={"battlefield": ["Lens of Clarity"], "library": ["Island", "Forest"]},
        bob={"battlefield": ["Grizzly Bears"], "library": ["Island"]},
    )
    morph = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "bob")
    morph.turn_face_down()
    assert morph.face_down
    top = scenario.player("alice").library[0]
    known = _known_ids(scenario, "alice")
    assert top.id in known
    assert morph.id in known


def test_lens_of_clarity_does_not_show_my_own_hidden_cards_to_the_opponent():
    scenario = _main(
        alice={"battlefield": ["Lens of Clarity", "Grizzly Bears"], "library": ["Island"]},
        bob={"library": ["Island"]},
    )
    mine = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice")
    mine.turn_face_down()
    assert mine.id not in _known_ids(scenario, "bob")
    assert scenario.player("alice").library[0].id not in _known_ids(scenario, "bob")
    assert mine.id not in _known_ids(scenario, "alice"), (
        "my own face-down creature is not 'I don't control'"
    )


def test_without_lens_an_opposing_face_down_creature_is_unknown():
    scenario = _main(
        alice={"library": ["Island"]},
        bob={"battlefield": ["Grizzly Bears"], "library": ["Island"]},
    )
    morph = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "bob")
    morph.turn_face_down()
    assert morph.id not in _known_ids(scenario, "alice")


def test_lens_of_clarity_stops_when_it_leaves():
    scenario = _main(
        alice={"battlefield": ["Lens of Clarity"], "library": ["Island"]},
        bob={"battlefield": ["Grizzly Bears"], "library": ["Island"]},
    )
    morph = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "bob")
    morph.turn_face_down()
    scenario.game.destroy(scenario.find("Lens of Clarity", Zone.BATTLEFIELD, "alice"))
    assert morph.id not in _known_ids(scenario, "alice")


def test_lens_of_clarity_is_credited():
    _handled("Lens of Clarity", "face-down creatures")


# -- Linked-exile piles: Valgavoth, Shared Fate, Uba Mask -------------------

CAST_PERMISSION = "Cast permission"


def _cast_from_exile(scenario, name, username="alice", targets=None):
    casting = scenario.cast(name, username, from_zone=Zone.EXILE)
    casting.use_keyword(CAST_PERMISSION)
    if targets:
        casting.choose_targets(targets)
    payment = casting.begin_paying()
    scenario.auto_pay(payment, username=username)
    scenario.put_on_stack(casting)
    return scenario.resolve_top()


def test_valgavoth_exiles_an_opponents_dying_creature_and_i_cast_it_for_life():
    scenario = _main(
        alice={"battlefield": ["Valgavoth, Terror Eater"]},
        bob={"battlefield": ["Grizzly Bears"]},
    )
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "bob")
    scenario.game.destroy(bears)
    assert bears.zone is Zone.EXILE
    assert _offered(scenario, bears, ActionKind.CAST)
    life = scenario.player("alice").life
    _cast_from_exile(scenario, "Grizzly Bears")
    assert scenario.player("alice").life == life - 2, "life equal to its mana value, no mana"
    assert scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice")


def test_valgavoth_life_payment_must_be_affordable():
    scenario = _main(
        alice={"battlefield": ["Valgavoth, Terror Eater"]},
        bob={"battlefield": ["Grizzly Bears"]},
    )
    scenario.player("alice").life = 1
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "bob")
    scenario.game.destroy(bears)
    assert not any(
        action.kind is ActionKind.CAST
        and action.card_id == bears.id
        and action.affordable is Affordability.YES
        for action in legal_actions(scenario.game, "alice")
    ), "one life cannot pay 2"


def test_valgavoth_leaves_my_own_dying_creature_in_my_graveyard():
    scenario = _main(
        alice={"battlefield": ["Valgavoth, Terror Eater", "Grizzly Bears"]},
        bob={},
    )
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice")
    scenario.game.destroy(bears)
    assert bears.zone is Zone.GRAVEYARD


def test_valgavoth_pile_is_only_playable_during_its_controllers_turn():
    scenario = _main(
        alice={"battlefield": ["Grizzly Bears"]},
        bob={"battlefield": ["Valgavoth, Terror Eater"]},
    )
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice")
    scenario.game.destroy(bears)
    assert bears.zone is Zone.EXILE, "bob's Valgavoth exiled alice's dying creature"
    assert not _offered(scenario, bears, ActionKind.CAST, username="bob"), "it is alice's turn"


def test_valgavoth_lets_me_play_an_opponents_discarded_land():
    scenario = _main(
        alice={"battlefield": ["Valgavoth, Terror Eater"]},
        bob={"hand": ["Forest"]},
    )
    forest = scenario.find("Forest", Zone.HAND, "bob")
    scenario.game.discard_cards("bob", [forest])
    assert forest.zone is Zone.EXILE
    scenario.play_land("Forest", "alice", from_zone=Zone.EXILE)
    assert forest.zone is Zone.BATTLEFIELD


def test_valgavoth_is_credited():
    _handled("Valgavoth, Terror Eater", "During your turn, you may play cards exiled with")


def test_shared_fate_exiles_an_opponents_top_card_for_me_to_look_at_and_cast():
    scenario = _main(
        alice={"battlefield": ["Shared Fate", "Mountain"], "library": ["Island"] * 3},
        bob={"library": ["Lightning Bolt", "Island", "Island"]},
    )
    bolt = scenario.player("bob").library[0]
    hand = len(scenario.player("alice").hand)
    scenario.draw(1, "alice")
    assert len(scenario.player("alice").hand) == hand, "the draw was replaced"
    assert bolt.zone is Zone.EXILE
    assert bolt.id in _known_ids(scenario, "alice"), "alice may look at the card she exiled"
    assert bolt.id not in _known_ids(scenario, "bob")
    assert _offered(scenario, bolt, ActionKind.CAST)
    assert not _offered(scenario, bolt, ActionKind.CAST, username="bob"), "bob did not exile it"
    life = scenario.player("bob").life
    _cast_from_exile(scenario, "Lightning Bolt", targets=["bob"])
    assert scenario.player("bob").life == life - 3


def test_shared_fate_lets_me_play_a_land_i_exiled():
    scenario = _main(
        alice={"battlefield": ["Shared Fate"], "library": ["Island"] * 3},
        bob={"library": ["Forest", "Island", "Island"]},
    )
    forest = scenario.player("bob").library[0]
    scenario.draw(1, "alice")
    scenario.play_land("Forest", "alice", from_zone=Zone.EXILE)
    assert forest.zone is Zone.BATTLEFIELD
    assert scenario.game.controller_of(forest).username == "alice"


def test_shared_fate_works_for_the_opponent_too_and_only_for_their_own_exile():
    scenario = _main(
        alice={"battlefield": ["Shared Fate"], "library": ["Lightning Bolt", "Island", "Island"]},
        bob={"battlefield": ["Mountain"], "library": ["Island"] * 3},
    )
    bolt = scenario.player("alice").library[0]
    scenario.draw(1, "bob")
    assert bolt.zone is Zone.EXILE
    assert bolt.id in _known_ids(scenario, "bob")
    assert bolt.id not in _known_ids(scenario, "alice")
    assert not _offered(scenario, bolt, ActionKind.CAST, username="alice")
    assert _offered(scenario, bolt, ActionKind.CAST, username="bob")


def test_without_shared_fate_the_draw_is_a_draw():
    scenario = _main(alice={"library": ["Island"] * 3}, bob={"library": ["Lightning Bolt"] * 3})
    hand = len(scenario.player("alice").hand)
    scenario.draw(1, "alice")
    assert len(scenario.player("alice").hand) == hand + 1


def test_uba_mask_exiles_my_draw_face_up_and_i_may_play_it_this_turn():
    scenario = _main(
        alice={"battlefield": ["Uba Mask", "Mountain"], "library": ["Lightning Bolt", "Island"]},
        bob={"library": ["Island"] * 3},
    )
    bolt = scenario.player("alice").library[0]
    hand = len(scenario.player("alice").hand)
    scenario.draw(1, "alice")
    assert len(scenario.player("alice").hand) == hand
    assert bolt.zone is Zone.EXILE and bolt.face_up
    assert _offered(scenario, bolt, ActionKind.CAST)
    assert not _offered(scenario, bolt, ActionKind.CAST, username="bob")
    life = scenario.player("bob").life
    _cast_from_exile(scenario, "Lightning Bolt", targets=["bob"])
    assert scenario.player("bob").life == life - 3


def test_uba_mask_land_is_playable_this_turn_only():
    scenario = _main(
        alice={"battlefield": ["Uba Mask"], "library": ["Forest", "Island", "Island", "Island"]},
        bob={"library": ["Island"] * 6},
    )
    forest = scenario.player("alice").library[0]
    scenario.draw(1, "alice")
    assert _offered(scenario, forest, ActionKind.PLAY_LAND)
    turns = scenario.turn.turns_taken
    while scenario.turn.turns_taken == turns:
        scenario.advance()
    while scenario.turn.active_player != "alice":
        scenario.advance()
    assert forest.zone is Zone.EXILE
    assert not _offered(scenario, forest, ActionKind.PLAY_LAND), "'this turn' has ended"


def test_uba_mask_each_player_includes_the_opponent():
    scenario = _main(
        alice={"battlefield": ["Uba Mask"]},
        bob={"battlefield": ["Mountain"], "library": ["Lightning Bolt", "Island"]},
    )
    bolt = scenario.player("bob").library[0]
    scenario.draw(1, "bob")
    assert bolt.zone is Zone.EXILE and bolt.face_up
    assert _offered(scenario, bolt, ActionKind.CAST, username="bob")
    assert not _offered(scenario, bolt, ActionKind.CAST, username="alice")


def test_shared_fate_and_uba_mask_are_credited():
    _handled("Shared Fate", "Each player may look at cards they exiled")
    _handled("Uba Mask", "Each player may play lands and cast spells")


# -- Skyclave Shade: a landfall trigger from the graveyard ------------------


def _shade_board(*, hand=("Swamp",), graveyard=("Skyclave Shade",), bob_hand=()):
    return _main(
        alice={
            "hand": list(hand),
            "graveyard": list(graveyard),
            "battlefield": ["Swamp", "Swamp"],
        },
        bob={"hand": list(bob_hand), "battlefield": ["Forest"]},
    )


def test_skyclave_shade_can_be_cast_from_the_graveyard_after_a_land_enters_on_my_turn():
    scenario = _shade_board()
    shade = scenario.find("Skyclave Shade", Zone.GRAVEYARD, "alice")
    assert not _offered(scenario, shade, ActionKind.CAST), "no landfall yet"
    scenario.play_land("Swamp")
    scenario.pass_until_resolved()
    assert _offered(scenario, shade, ActionKind.CAST)
    casting = scenario.cast("Skyclave Shade", "alice", from_zone=Zone.GRAVEYARD)
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Swamp", "Swamp"))
    scenario.put_on_stack(casting)
    scenario.resolve_top()
    assert shade.zone is Zone.BATTLEFIELD


def test_skyclave_shade_stays_put_when_the_land_is_an_opponents():
    scenario = _shade_board(hand=(), bob_hand=("Forest",))
    scenario.game.put_onto_battlefield(scenario.find("Forest", Zone.HAND, "bob"), "bob")
    scenario.pass_until_resolved()
    shade = scenario.find("Skyclave Shade", Zone.GRAVEYARD, "alice")
    assert not _offered(scenario, shade, ActionKind.CAST), "'a land you control' only"


def test_skyclave_shade_permission_ends_with_the_turn():
    scenario = _shade_board()
    shade = scenario.find("Skyclave Shade", Zone.GRAVEYARD, "alice")
    scenario.play_land("Swamp")
    scenario.pass_until_resolved()
    assert _offered(scenario, shade, ActionKind.CAST)
    turns = scenario.turn.turns_taken
    while scenario.turn.turns_taken == turns:
        scenario.advance()
    assert not _offered(scenario, shade, ActionKind.CAST, username="alice")


def test_skyclave_shade_needs_it_to_be_my_turn():
    scenario = _shade_board(hand=("Swamp",))
    while not (scenario.turn.active_player == "bob" and scenario.step is Step.PRECOMBAT_MAIN):
        scenario.advance()
    scenario.game.put_onto_battlefield(scenario.find("Swamp", Zone.HAND, "alice"), "alice")
    scenario.pass_until_resolved()
    shade = scenario.find("Skyclave Shade", Zone.GRAVEYARD, "alice")
    assert scenario.game.play_permission_for(shade, "alice") is None, "it is bob's turn"


def test_skyclave_shade_is_credited():
    _handled("Skyclave Shade", "Landfall")


# -- d20 result tables: Wizard's Spellbook and Chaos Channeler -------------------


def _force_roll(scenario, low, high):
    """Pick the game's shuffle seed so the next d20 lands in `low`..`high`
    (`Game.roll_dice` seeds each die from the seed and its count of random
    outcomes so far)."""
    from random import Random

    game = scenario.game
    for seed in range(5000):
        if low <= Random(f"{seed}:{game.coin_flips_performed}:die").randint(1, 20) <= high:
            game.shuffle_seed = seed
            return
    raise AssertionError("no seed found")


def _spellbook_board(*, islands=3):
    scenario = _main(
        alice={
            "battlefield": ["Wizard's Spellbook", *(["Island"] * islands)],
            "library": ["Island"] * 6,
        },
        bob={"graveyard": ["Divination", "Opt"], "library": ["Island"] * 3},
    )
    return scenario


def _activate_spellbook(scenario, target):
    book = scenario.find("Wizard's Spellbook", Zone.BATTLEFIELD, "alice")
    scenario.activate(book, targets=[target])
    scenario.pass_until_resolved()
    while scenario.game.stack:
        scenario.pass_until_resolved()


def _hand(scenario, username="alice"):
    return len(scenario.player(username).hand)


def test_spellbook_low_roll_exiles_the_card_and_lets_me_cast_a_copy_at_full_cost():
    scenario = _spellbook_board()
    divination = scenario.find("Divination", Zone.GRAVEYARD, "bob")
    _force_roll(scenario, 1, 9)
    scenario.will_take_the_may(True)
    hand = _hand(scenario)
    _activate_spellbook(scenario, divination)
    assert divination.zone is Zone.EXILE, "the original is exiled with the book"
    assert _hand(scenario) == hand + 2, "the copy of Divination was cast and resolved"
    islands = [c for c in scenario.game.battlefield if c.name == "Island"]
    assert islands and all(c.tapped for c in islands), "{2}{U} was paid"


def test_spellbook_middle_roll_casts_the_copy_for_one_generic():
    scenario = _spellbook_board(islands=1)
    divination = scenario.find("Divination", Zone.GRAVEYARD, "bob")
    _force_roll(scenario, 10, 19)
    scenario.will_take_the_may(True)
    hand = _hand(scenario)
    _activate_spellbook(scenario, divination)
    assert _hand(scenario) == hand + 2
    assert divination.zone is Zone.EXILE


def test_spellbook_low_roll_with_too_little_mana_casts_nothing():
    scenario = _spellbook_board(islands=1)
    divination = scenario.find("Divination", Zone.GRAVEYARD, "bob")
    _force_roll(scenario, 1, 9)
    hand = _hand(scenario)
    _activate_spellbook(scenario, divination)
    assert _hand(scenario) == hand, "{2}{U} is not payable with one Island"
    assert divination.zone is Zone.EXILE
    assert not [c for c in scenario.game.exile if c.is_copy], "an uncast copy ceases to exist"


def test_spellbook_declining_the_copy_leaves_nothing_behind():
    scenario = _spellbook_board()
    divination = scenario.find("Divination", Zone.GRAVEYARD, "bob")
    _force_roll(scenario, 1, 9)
    scenario.will_take_the_may(False)
    hand = _hand(scenario)
    _activate_spellbook(scenario, divination)
    assert _hand(scenario) == hand
    assert not [c for c in scenario.game.exile if c.is_copy]


def test_spellbook_natural_twenty_copies_every_card_exiled_with_it_for_free():
    scenario = _spellbook_board(islands=0)
    divination = scenario.find("Divination", Zone.GRAVEYARD, "bob")
    book = scenario.find("Wizard's Spellbook", Zone.BATTLEFIELD, "alice")
    # a card exiled with the book on an earlier activation
    counterspell = scenario.find("Opt", Zone.GRAVEYARD, "bob")
    scenario.game.exile_cards([counterspell])
    from magic_cards_model.models.card_state import ExileAnnotation, ExileMarker

    counterspell.exile_annotation = ExileAnnotation(
        marker=ExileMarker.LINKED,
        owner="bob",
        turn_exiled=0,
        linked_permanent_id=book.id,
        linked_permanent_stamp=book.zone_change_stamp,
    )
    _force_roll(scenario, 20, 20)
    scenario.will_take_the_may(False)  # Opt's copy, the older exile
    scenario.will_take_the_may(True)  # Divination's copy
    hand = _hand(scenario)
    _activate_spellbook(scenario, divination)
    assert _hand(scenario) == hand + 2, "Divination's copy was cast without paying {2}{U}"


def test_spellbook_cannot_target_a_land_or_a_creature_card():
    scenario = _spellbook_board()
    bob_island = scenario.player("bob").library[0]
    with pytest.raises(ValueError):
        _activate_spellbook(scenario, bob_island)


def test_spellbook_is_sorcery_speed():
    scenario = _spellbook_board()
    book = scenario.find("Wizard's Spellbook", Zone.BATTLEFIELD, "alice")
    scenario.advance()  # past the main phase into combat
    while scenario.step is not Step.BEGINNING_OF_COMBAT:
        scenario.advance()
    assert scenario.why_cannot_activate(book) is not None


def _channeler_attack(top, *, low, high, library_extra=()):
    scenario = _main(
        alice={
            "battlefield": ["Chaos Channeler"],
            "library": [*top, *library_extra, "Island", "Island", "Island"],
        },
        bob={"library": ["Island"] * 3},
    )
    channeler = scenario.find("Chaos Channeler", Zone.BATTLEFIELD, "alice")
    channeler.summoning_sick = False
    _force_roll(scenario, low, high)
    return scenario, channeler


@pytest.mark.parametrize(
    ("low", "high", "count"), [(1, 9, 1), (10, 19, 2), (20, 20, 3)], ids=["1-9", "10-19", "20"]
)
def test_chaos_channeler_exiles_as_many_cards_as_the_row_says_and_they_are_playable(
    low, high, count
):
    scenario, channeler = _channeler_attack(["Forest", "Mountain", "Swamp"], low=low, high=high)
    top = list(scenario.player("alice").library[:3])
    scenario.attack_with(channeler)
    scenario.pass_until_resolved()
    exiled = [c for c in top if c.zone is Zone.EXILE]
    assert len(exiled) == count
    assert exiled == top[:count], "the top cards, in order"
    for card_state in exiled:
        assert scenario.game.play_permission_for(card_state, "alice", PlayAction.PLAY) is not None


def test_chaos_channeler_does_nothing_unless_it_attacks():
    scenario, channeler = _channeler_attack(["Forest", "Mountain"], low=20, high=20)
    top = scenario.player("alice").library[0]
    scenario.pass_until_resolved()
    assert top.zone is Zone.LIBRARY


def test_roll_tables_are_credited():
    _handled("Wizard's Spellbook", "Roll a d20")
    _handled("Wizard's Spellbook", "Copy that card")
    _handled("Wizard's Spellbook", "Copy each card exiled")
    _handled("Chaos Channeler", "roll a d20")


# -- Weftwalking: shuffle hand and graveyard away, draw seven, if cast ---------


def _weftwalking_board():
    return _main(
        alice={
            "hand": ["Weftwalking", "Grizzly Bears", "Lightning Bolt"],
            "graveyard": ["Llanowar Elves"],
            "battlefield": ["Island"] * 6,
            "library": ["Forest"] * 12,
        },
        bob={"library": ["Island"] * 6},
    )


def test_weftwalking_cast_shuffles_hand_and_graveyard_into_the_library_and_draws_seven():
    scenario = _weftwalking_board()
    scenario.cast_and_resolve("Weftwalking", *scenario.untapped_sources(*["Island"] * 6))
    scenario.pass_until_resolved()
    alice = scenario.player("alice")
    assert len(alice.hand) == 7
    assert not alice.graveyard
    assert len(alice.library) == 12 + 2 + 1 - 7, "hand (2 left) and graveyard went into the library"


def test_weftwalking_put_onto_the_battlefield_does_not_shuffle():
    scenario = _weftwalking_board()
    scenario.put_onto_battlefield("Weftwalking")
    scenario.pass_until_resolved()
    alice = scenario.player("alice")
    assert len(alice.hand) == 2
    assert [c.name for c in alice.graveyard] == ["Llanowar Elves"]


def _affordable_casts(scenario, username="alice"):
    return [
        action
        for action in legal_actions(scenario.game, username)
        if action.kind is ActionKind.CAST and action.affordable is Affordability.YES
    ]


def test_weftwalking_makes_the_first_spell_each_turn_free_but_not_the_second():
    scenario = _main(
        alice={"hand": ["Grizzly Bears", "Grizzly Bears"], "battlefield": ["Weftwalking"]},
        bob={},
    )
    assert _affordable_casts(scenario), "the first spell may be cast without paying its mana cost"
    casting = scenario.cast("Grizzly Bears", "alice")
    casting.use_alternative_cost("Weftwalking")
    scenario.pay_with(casting.begin_paying())
    scenario.put_on_stack(casting)
    scenario.resolve_top()
    assert len(scenario.game.spells_cast_this_turn["alice"]) == 1
    assert not _affordable_casts(scenario), "the second spell this turn is not free"


def test_weftwalking_grants_the_free_first_spell_to_the_opponent_on_their_own_turn_only():
    scenario = _main(
        alice={"battlefield": ["Weftwalking"]},
        bob={"hand": ["Grizzly Bears"]},
    )
    assert not _affordable_casts(scenario, "bob"), "it is not bob's turn"


def test_weftwalking_is_credited():
    _handled("Weftwalking", "shuffle your hand and graveyard into your library")
