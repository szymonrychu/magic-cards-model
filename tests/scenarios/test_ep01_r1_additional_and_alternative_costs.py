"""CR 118.8 additional costs and CR 118.9 alternative costs read off a spell's
own printed line (EP-01 round 1, task T7): "tap N untapped artifacts,
creatures, and/or lands you control", "discard a card or sacrifice a
permanent", "you may collect evidence 6", "You may pay {1} and return a basic
land you control to its owner's hand rather than pay this spell's mana cost".

Rules read whole with `mise run rules:find 118.8` and `mise run rules:find
118.9` this session: an additional cost is paid on top of the mana or
alternative cost (CR 118.8, CR 601.2f); only one alternative cost may be
applied to a spell (CR 118.9a); a cost is paid in full or not at all (CR 118.3).
"""

import pytest

from magic_cards_model.machines import Step, payability
from magic_cards_model.machines.casting.options import (
    optional_additional_costs,
    or_additional_cost_alternatives,
    reads_optional_additional_cost_line,
)
from magic_cards_model.models import Color, Zone
from magic_cards_model.models.token import create_predefined_tokens
from tests.scenarios.harness import Scenario


def _main(**players) -> Scenario:
    builder = Scenario()
    for username, kwargs in players.items():
        builder = builder.player(username, **kwargs)
    scenario = builder.build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _kinds(casting) -> list[tuple[str, int]]:
    scenario_game = casting.game
    scenario_game.determine_total_cost(casting)
    return [(c.kind.value, c.required) for c in casting.total_cost.components]


# -- mandatory "tap N untapped <qualities>" -----------------------------------


@pytest.mark.parametrize(
    ("spell", "count", "fodder"),
    [
        ("Fear of Exposure", 2, ["Grizzly Bears", "Forest"]),
        ("Warlord's Elite", 2, ["Grizzly Bears", "Sol Ring"]),
        ("Guardian of the Great Door", 4, ["Grizzly Bears", "Sol Ring", "Plains", "Plains"]),
    ],
)
def test_and_or_tap_costs_are_charged_with_the_chosen_permanents(spell, count, fodder):
    scenario = _main(alice={"hand": [spell], "battlefield": fodder})
    chosen = scenario.game.permanents_controlled_by("alice")[:count]
    casting = scenario.cast(spell, "alice", tapping=chosen)
    assert _kinds(casting) == [("tap", count)]
    assert len(casting.total_cost.components[0].cards) == count


def test_a_tap_cost_refuses_fewer_permanents_than_it_demands():
    scenario = _main(alice={"hand": ["Fear of Exposure"], "battlefield": ["Forest"]})
    forest = scenario.find("Forest", Zone.BATTLEFIELD, "alice")
    casting = scenario.cast("Fear of Exposure", "alice", tapping=[forest])
    scenario.game.determine_total_cost(casting)
    (component,) = casting.total_cost.components
    assert component.required == 2
    assert len(component.cards) == 1, "one permanent cannot pay for two (CR 118.3)"


# -- "discard a card or sacrifice a permanent" ----------------------------------


def test_souls_of_the_lost_is_paid_by_discarding_a_card():
    scenario = _main(
        alice={"hand": ["Souls of the Lost", "Grizzly Bears"], "battlefield": ["Sol Ring"]}
    )
    bears = scenario.find("Grizzly Bears", Zone.HAND, "alice")
    casting = scenario.cast("Souls of the Lost", "alice", discarding=[bears])
    assert _kinds(casting) == [("discard", 1)]


def test_souls_of_the_lost_is_paid_by_sacrificing_a_permanent():
    scenario = _main(alice={"hand": ["Souls of the Lost"], "battlefield": ["Sol Ring"]})
    ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "alice")
    casting = scenario.cast("Souls of the Lost", "alice", sacrificing=[ring])
    assert _kinds(casting) == [("sacrifice", 1)]


def test_the_two_halves_are_both_readable_alternatives():
    assert or_additional_cost_alternatives("discard a card or sacrifice a permanent") == [
        "discard a card",
        "sacrifice a permanent",
    ]


# -- optional additional costs ---------------------------------------------------


@pytest.mark.parametrize(
    ("spell", "keyword"),
    [
        ("Crimestopper Sprite", "collect evidence"),
        ("Vitu-Ghazi Inspector", "collect evidence"),
        ("Orator of Ojutai", "reveal"),
    ],
)
def test_optional_additional_costs_are_offered_and_understood(spell, keyword):
    scenario = _main(alice={"hand": [spell]})
    (card,) = scenario.game.player("alice").hand
    (offer,) = optional_additional_costs(card.card)
    assert offer.keyword == keyword
    assert offer.understood
    assert reads_optional_additional_cost_line(
        f"As an additional cost to cast this spell, {offer.cost}."
    )


# -- alternative costs: "pay {M} and <object cost>" ---------------------------------


@pytest.mark.parametrize("post", ["Fieldmist Borderpost", "Firewild Borderpost"])
def test_borderposts_offer_pay_one_and_return_a_basic_land(post):
    scenario = _main(alice={"hand": [post], "battlefield": ["Plains", "Island", "Mountain"]})
    casting = scenario.cast(post, "alice")
    (option,) = casting.alternative_costs
    assert "return a basic land" in option.description.lower() or option.cost is not None
    land = scenario.find("Plains", Zone.BATTLEFIELD, "alice")
    casting.use_alternative_cost(choosing=[land])
    scenario.game.determine_total_cost(casting)
    assert str(casting.total_cost.mana) == "{1}"
    assert [c.kind.value for c in casting.total_cost.components] == ["return_to_hand"]


def test_stalwart_valkyrie_exiles_a_creature_card_from_the_graveyard():
    scenario = _main(
        alice={
            "hand": ["Stalwart Valkyrie"],
            "graveyard": ["Grizzly Bears"],
            "battlefield": ["Plains", "Plains"],
        }
    )
    casting = scenario.cast("Stalwart Valkyrie", "alice")
    (option,) = casting.alternative_costs
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")
    casting.use_alternative_cost(choosing=[bears])
    scenario.game.determine_total_cost(casting)
    assert str(casting.total_cost.mana) == "{1}{W}"
    assert [c.kind.value for c in casting.total_cost.components] == ["exile"]
    assert option is not None


def test_zahid_taps_an_untapped_artifact():
    scenario = _main(
        alice={"hand": ["Zahid, Djinn of the Lamp"], "battlefield": ["Sol Ring", "Island"]}
    )
    casting = scenario.cast("Zahid, Djinn of the Lamp", "alice")
    (option,) = casting.alternative_costs
    ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "alice")
    casting.use_alternative_cost(choosing=[ring])
    scenario.game.determine_total_cost(casting)
    assert str(casting.total_cost.mana) == "{3}{U}"
    assert [c.kind.value for c in casting.total_cost.components] == ["tap"]
    assert option is not None


# -- casting this card from the graveyard (CR 601.3, 118.9, 601.2f) --------------


def _graveyard_cast_cost(scenario, name):
    from magic_cards_model.machines.casting import castable_from
    from tests.cards import card as printing

    options = castable_from(printing(name), Zone.GRAVEYARD)
    assert options, f"{name} should be castable from the graveyard"
    return options[0]


def test_raffines_guidance_is_castable_from_the_graveyard_for_its_own_cost():
    scenario = _main(alice={"graveyard": ["Raffine's Guidance"]})
    option = _graveyard_cast_cost(scenario, "Raffine's Guidance")
    assert not option.pays_mana_cost
    assert str(option.cost.mana) == "{2}{W}"


def test_squee_needs_four_other_graveyard_cards_as_well():
    scenario = _main(alice={"graveyard": ["Squee, Dubious Monarch"]})
    option = _graveyard_cast_cost(scenario, "Squee, Dubious Monarch")
    assert str(option.cost.mana) == "{3}{R}"
    (component,) = option.cost.components
    assert component.required == 4


def test_demilich_pays_its_mana_cost_and_exiles_four_instants_or_sorceries():
    scenario = _main(alice={"graveyard": ["Demilich"]})
    option = _graveyard_cast_cost(scenario, "Demilich")
    assert option.pays_mana_cost
    (component,) = option.additional_cost.components
    assert component.required == 4


def _force_of_virtue_board() -> Scenario:
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Grizzly Bears"])
        .player("bob", hand=["Force of Virtue", "Savannah Lions", "Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)  # alice is active, so it is not bob's turn
    return scenario


def test_force_of_virtue_is_cast_on_an_opponents_turn_by_exiling_a_white_card():
    """CR 118.9: "If it's not your turn, you may exile a white card from your
    hand rather than pay this spell's mana cost." - the printed line the
    sweep reads as a permanent card's alternative cost."""
    scenario = _force_of_virtue_board()
    white = scenario.find("Savannah Lions", Zone.HAND, "bob")
    scenario.pass_priority("alice")

    casting = scenario.cast("Force of Virtue", username="bob")
    (option,) = [found for found in casting.alternative_costs if found.available]
    casting.use_alternative_cost(option.index, choosing=[white])
    payment = casting.begin_paying()
    payment.pay()
    scenario.put_on_stack(casting)
    scenario.pass_until_resolved()

    assert white.zone is Zone.EXILE
    assert scenario.find("Force of Virtue", Zone.BATTLEFIELD, "bob").zone is Zone.BATTLEFIELD


def test_force_of_virtue_offers_nothing_on_its_controllers_own_turn():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Force of Virtue", "Savannah Lions"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    casting = scenario.cast("Force of Virtue", username="alice")
    assert not [found for found in casting.alternative_costs if found.available]
    casting.cancel()


def test_force_of_virtue_needs_a_white_card_to_exile():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice")
        .player("bob", hand=["Force of Virtue", "Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.pass_priority("alice")
    assert not payability(
        scenario.game, "bob", scenario.find("Force of Virtue", Zone.HAND, "bob")
    ).payable


def test_sephara_taps_four_untapped_flyers_instead_of_paying_its_mana_cost():
    """CR 118.9 + 118.3: "You may pay {W} and tap four untapped creatures you
    control with flying rather than pay this spell's mana cost." - a creature
    without flying cannot be chosen for the tap."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Sephara, Sky's Blade"],
            battlefield=["Plains", "Wind Drake", "Wind Drake", "Wind Drake", "Wind Drake", "Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    flyers = [s for s in scenario.game.battlefield if s.name == "Wind Drake"]
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice")

    casting = scenario.cast("Sephara, Sky's Blade")
    (option,) = [found for found in casting.alternative_costs if found.available]
    plains = scenario.find("Plains", Zone.BATTLEFIELD, "alice")
    casting.use_alternative_cost(option.index, choosing=[*flyers[:3], bears])
    payment = casting.begin_paying()
    payment.tap_for_mana(plains, [Color.WHITE])
    with pytest.raises(ValueError, match="does not have flying"):
        payment.pay()
    casting.cancel()

    casting = scenario.cast("Sephara, Sky's Blade")
    casting.use_alternative_cost(option.index, choosing=flyers)
    payment = casting.begin_paying()
    payment.tap_for_mana(plains, [Color.WHITE])
    payment.pay()
    scenario.put_on_stack(casting)
    scenario.pass_until_resolved()

    assert scenario.find("Sephara, Sky's Blade", Zone.BATTLEFIELD, "alice").zone is Zone.BATTLEFIELD
    assert all(flyer.tapped for flyer in flyers)
    assert not bears.tapped


def test_sephara_gives_other_flyers_indestructible_and_only_them():
    """CR 613.1f: "Other creatures you control with flying have indestructible."
    selects by the keyword the creature has when layer 6 is applied, and
    leaves Sephara herself and any creature without flying out."""
    from magic_cards_model.machines.combat import has_keyword

    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Sephara, Sky's Blade", "Wind Drake", "Grizzly Bears"])
        .player("bob", battlefield=["Wind Drake"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    game = scenario.game
    drake = scenario.find("Wind Drake", Zone.BATTLEFIELD, "alice")
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice")
    sephara = scenario.find("Sephara, Sky's Blade", Zone.BATTLEFIELD, "alice")
    enemy = scenario.find("Wind Drake", Zone.BATTLEFIELD, "bob")

    assert has_keyword(drake, "indestructible", game)
    assert not has_keyword(bears, "indestructible", game)
    assert not has_keyword(sephara, "indestructible", game)
    assert not has_keyword(enemy, "indestructible", game)


# -- "Spend only mana produced by Treasures to cast it this way." ------------------


def _rhox_board() -> Scenario:
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Security Rhox"],
            battlefield=["Mountain", "Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    create_predefined_tokens(scenario.game, "Treasure", "alice", 2)
    scenario.game.put_triggers_on_stack()
    return scenario


def _treasure_ability_index(scenario, treasure) -> int:
    for index, ability in enumerate(scenario.game.activated_abilities(treasure)):
        if ability.mana is not None:
            return index
    raise AssertionError("no mana ability")


def _rhox_alternative(scenario):
    casting = scenario.cast("Security Rhox")
    (option,) = [found for found in casting.alternative_costs if found.available]
    assert option.treasure_only
    casting.use_alternative_cost(option.index)
    return casting


def test_security_rhox_is_cast_for_rg_paid_with_treasure_mana_only():
    scenario = _rhox_board()
    treasures = [s for s in scenario.game.battlefield if "Treasure" in s.subtypes]
    casting = _rhox_alternative(scenario)
    payment = casting.begin_paying()
    for treasure, color in zip(treasures, (Color.RED, Color.GREEN), strict=True):
        payment.activate_mana_ability(
            treasure, _treasure_ability_index(scenario, treasure), color=[color]
        )
    payment.pay()
    scenario.put_on_stack(casting)
    scenario.pass_until_resolved()

    rhox = scenario.find("Security Rhox", Zone.BATTLEFIELD, "alice")
    assert rhox.zone is Zone.BATTLEFIELD
    assert all(t.zone is Zone.GRAVEYARD or t not in scenario.game.battlefield for t in treasures)
    assert not any(land.tapped for land in scenario.game.battlefield if land.name in {"Mountain", "Forest"})


def test_security_rhox_refuses_mana_from_lands():
    scenario = _rhox_board()
    casting = _rhox_alternative(scenario)
    payment = casting.begin_paying()
    mountain, forest = scenario.untapped_sources("Mountain", "Forest")
    with pytest.raises(ValueError, match="Treasure"):
        payment.tap_for_mana(mountain, [Color.RED])
    with pytest.raises(ValueError, match="Treasure"):
        payment.tap_for_mana(forest, [Color.GREEN])


def test_security_rhox_refuses_floating_mana_that_no_treasure_made():
    scenario = _rhox_board()
    casting = _rhox_alternative(scenario)
    payment = casting.begin_paying()
    payment.add_mana(Color.RED)
    payment.add_mana(Color.GREEN)
    with pytest.raises(ValueError, match="cannot pay"):
        payment.pay()


def test_security_rhox_hard_cast_is_unrestricted():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Security Rhox"], battlefield=["Mountain", "Forest", "Forest", "Forest", "Forest"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    casting = scenario.cast("Security Rhox")
    payment = casting.begin_paying()
    payment.auto_tap(scenario.untapped_sources("Mountain", "Forest", "Forest", "Forest", "Forest"))
    payment.pay()
    scenario.put_on_stack(casting)
    scenario.pass_until_resolved()
    assert scenario.find("Security Rhox", Zone.BATTLEFIELD, "alice").zone is Zone.BATTLEFIELD
