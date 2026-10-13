"""EP-02 R2 T8 follow-up: the eight neighbours of the chosen-amount cards.

    Sacrifice any number of other permanents, then draw that many cards.
    Sacrifice any number of artifacts, enchantments, and/or tokens. Return
    that many creature cards from your graveyard to the battlefield.
    Pay any amount of life. Target opponent reveals that many cards from
    their hand. You choose one of them and exile it.
    You get {E}{E}{E}, then you may pay any amount of {E}. Each player may
    exile their hand and draw that many cards.
    Counter that spell unless its controller pays {1} for each {E} paid.
    You may pay {1}{G} any number of times. When you pay this cost one or
    more times, ... then up to that many target lands become 3/3 Wolves.

Rules, each read in full with `mise run rules:find` in this session:

- CR 107.1c - "any number" may be any positive number or zero.
- CR 608.2c - a later "that many" reads what the earlier instruction did.
- CR 608.2d - an illegal option can't be chosen.
- CR 701.21a - only a permanent its controller controls can be sacrificed.
- CR 701.20a - revealing shows a card; it stays where it is.
- CR 107.14 / CR 118.3 - energy paid is limited to what the player has.
- CR 118.12a - "unless" is "may pay; if not, the effect".
- CR 603.12 - "when you pay this cost one or more times" is reflexive.
- CR 205.1b / CR 613 - "still lands": the type is added, not replaced.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.casting.permissions import play_permissions_on
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from magic_cards_model.support import card_support
from tests.cards import card

from .harness import Scenario

NEIGHBOURS = [
    "Primal Adversary",
    "Bloodthirsty Adversary",
    "God-Eternal Bontu",
    "Malevolent Witchkite",
    "Lich-Knights' Conquest",
    "Vizkopa Confessor",
    "Wheel of Potential",
    "Aether Spike",
]


@pytest.mark.parametrize("name", NEIGHBOURS)
def test_every_neighbour_reads_handled(name):
    support = card_support(card(name))
    assert support.status == "handled", name
    assert all(clause.outcome == "handled" for clause in support.clauses), name


def _board(
    *,
    alice_hand=(),
    alice_battlefield=(),
    alice_lands=("Plains", "Swamp", "Mountain", "Forest", "Island"),
    alice_library=("Forest",) * 10,
    alice_graveyard=(),
    bob_hand=(),
    bob_battlefield=(),
    bob_lands=("Island", "Island"),
    bob_library=("Island",) * 10,
    start=Step.PRECOMBAT_MAIN,
):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=list(alice_hand),
            battlefield=[*alice_lands, *alice_lands, *alice_battlefield],
            library=list(alice_library),
            graveyard=list(alice_graveyard),
        )
        .player(
            "bob",
            hand=list(bob_hand),
            battlefield=[*bob_lands, *bob_battlefield],
            library=list(bob_library),
        )
        .build()
    )
    scenario.start_at(start)
    return scenario


def _cast(scenario, name, targets=None, username="alice"):
    return scenario.cast_and_resolve(name, username=username, targets=targets, auto=True)


def _resolve_all(scenario):
    while scenario.stack_names() or scenario.pending_triggers:
        scenario.game.put_triggers_on_stack()
        scenario.pass_until_resolved()


def _on_battlefield(scenario, name, username="alice"):
    return [
        state
        for state in scenario.game.battlefield
        if state.name == name and state.controller == username
    ]


def _question(scenario, source):
    return [q for q in scenario.questions_asked() if q.source == source]


# --------------------------------------------------------------------------
# God-Eternal Bontu: "sacrifice any number of other permanents, then draw
# that many cards"
# --------------------------------------------------------------------------


@pytest.mark.parametrize("sacrificed", [0, 1, 3])
def test_bontu_draws_one_card_per_other_permanent_really_sacrificed(sacrificed):
    scenario = _board(
        alice_hand=["God-Eternal Bontu"],
        alice_battlefield=["Grizzly Bears", "Grizzly Bears", "Grizzly Bears"],
        alice_library=["Island"] * 10,
    )
    bears = _on_battlefield(scenario, "Grizzly Bears")
    scenario.will_choose_cards(*bears[:sacrificed], source="God-Eternal Bontu")
    scenario.put_onto_battlefield("God-Eternal Bontu")
    _resolve_all(scenario)
    assert len(scenario.player("alice").hand) == sacrificed
    assert len(_on_battlefield(scenario, "Grizzly Bears")) == 3 - sacrificed


def test_bontu_never_offers_itself_or_the_opponents_permanents():
    scenario = _board(
        alice_hand=["God-Eternal Bontu"],
        alice_lands=("Swamp", "Swamp"),
        alice_battlefield=["Grizzly Bears"],
        bob_battlefield=["Grizzly Bears"],
    )
    scenario.will_choose_cards(source="God-Eternal Bontu")
    bontu = scenario.put_onto_battlefield("God-Eternal Bontu")
    _resolve_all(scenario)
    (question,) = _question(scenario, "God-Eternal Bontu")
    bob_bear = scenario.creature("Grizzly Bears", "bob")
    assert bontu.id not in question.cards
    assert bob_bear.id not in question.cards
    assert len(question.cards) == 5
    assert question.amount == 5 and not question.exact


def test_bontu_dying_may_go_third_from_the_top_of_its_owners_library():
    scenario = _board(
        alice_battlefield=["God-Eternal Bontu"],
        alice_library=["Island", "Swamp", "Forest", "Plains", "Mountain"],
    )
    bontu = scenario.find("God-Eternal Bontu", Zone.BATTLEFIELD, "alice")
    scenario.will_take_the_may(True, source="God-Eternal Bontu")
    scenario.game.destroy(bontu)
    _resolve_all(scenario)
    library = scenario.player("alice").library
    assert library[2].id == bontu.id
    assert bontu.zone is Zone.LIBRARY


def test_bontu_declining_leaves_it_in_the_graveyard():
    scenario = _board(alice_battlefield=["God-Eternal Bontu"])
    bontu = scenario.find("God-Eternal Bontu", Zone.BATTLEFIELD, "alice")
    scenario.will_take_the_may(False, source="God-Eternal Bontu")
    scenario.game.destroy(bontu)
    _resolve_all(scenario)
    assert bontu.zone is Zone.GRAVEYARD


# --------------------------------------------------------------------------
# Malevolent Witchkite / Lich-Knights' Conquest: "artifacts, enchantments,
# and/or tokens"
# --------------------------------------------------------------------------


def _witch_board(**extra):
    return _board(
        alice_lands=("Plains",),
        alice_battlefield=["Sol Ring", "Ghostly Prison", "Grizzly Bears", "Glorious Anthem"],
        **extra,
    )


def test_witchkite_offers_artifacts_enchantments_and_tokens_only():
    scenario = _witch_board(alice_hand=["Malevolent Witchkite"])
    scenario.will_choose_cards(source="Malevolent Witchkite")
    scenario.put_onto_battlefield("Malevolent Witchkite")
    _resolve_all(scenario)
    (question,) = _question(scenario, "Malevolent Witchkite")
    names = sorted(scenario.game.find_by_id(cid).name for cid in question.cards)
    assert names == ["Ghostly Prison", "Glorious Anthem", "Sol Ring"]


def test_witchkite_offers_tokens_too_even_when_they_are_creatures():
    scenario = _witch_board(alice_hand=["Malevolent Witchkite", "Raise the Alarm"])
    _cast(scenario, "Raise the Alarm")
    soldiers = [s for s in scenario.game.battlefield if s.token and s.controller == "alice"]
    assert len(soldiers) == 2
    scenario.will_choose_cards(*soldiers, source="Malevolent Witchkite")
    scenario.put_onto_battlefield("Malevolent Witchkite")
    _resolve_all(scenario)
    (question,) = _question(scenario, "Malevolent Witchkite")
    assert {s.id for s in soldiers} <= set(question.cards)
    bear = scenario.creature("Grizzly Bears", "alice")
    assert bear.id not in question.cards
    assert all(s.zone is not Zone.BATTLEFIELD for s in soldiers)


def test_witchkite_draws_one_per_permanent_sacrificed():
    scenario = _witch_board(alice_hand=["Malevolent Witchkite"], alice_library=["Island"] * 10)
    ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "alice")
    anthem = scenario.find("Glorious Anthem", Zone.BATTLEFIELD, "alice")
    scenario.will_choose_cards(ring, anthem, source="Malevolent Witchkite")
    scenario.put_onto_battlefield("Malevolent Witchkite")
    _resolve_all(scenario)
    assert len(scenario.player("alice").hand) == 2
    assert ring.zone is Zone.GRAVEYARD and anthem.zone is Zone.GRAVEYARD


@pytest.mark.parametrize("sacrificed", [0, 2])
def test_lich_knights_conquest_returns_that_many_creatures_from_the_graveyard(sacrificed):
    scenario = _board(
        alice_hand=["Lich-Knights' Conquest"],
        alice_lands=("Swamp",) * 5,
        alice_battlefield=["Sol Ring", "Ghostly Prison", "Glorious Anthem"],
        alice_graveyard=["Grizzly Bears", "Serra Angel", "Elvish Mystic"],
    )
    ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "alice")
    prison = scenario.find("Ghostly Prison", Zone.BATTLEFIELD, "alice")
    back = [
        s for s in scenario.player("alice").graveyard if s.name in ("Serra Angel", "Elvish Mystic")
    ]
    scenario.will_choose_cards(*[ring, prison][:sacrificed], source="Lich-Knights' Conquest")
    scenario.will_choose_cards(*back[:sacrificed], source="Lich-Knights' Conquest")
    _cast(scenario, "Lich-Knights' Conquest")
    returned = [s for s in back if s.zone is Zone.BATTLEFIELD]
    assert len(returned) == sacrificed


def test_lich_knights_conquest_returns_as_many_as_it_can_when_the_graveyard_is_short():
    scenario = _board(
        alice_hand=["Lich-Knights' Conquest"],
        alice_lands=("Swamp",) * 5,
        alice_battlefield=["Sol Ring", "Ghostly Prison"],
        alice_graveyard=["Grizzly Bears"],
    )
    ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "alice")
    prison = scenario.find("Ghostly Prison", Zone.BATTLEFIELD, "alice")
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")
    scenario.will_choose_cards(ring, prison, source="Lich-Knights' Conquest")
    scenario.will_choose_cards(bears, source="Lich-Knights' Conquest")
    _cast(scenario, "Lich-Knights' Conquest")
    assert bears.zone is Zone.BATTLEFIELD


# --------------------------------------------------------------------------
# Vizkopa Confessor: "pay any amount of life. Target opponent reveals that
# many cards from their hand. You choose one of them and exile it."
# --------------------------------------------------------------------------

_BOB_HAND = ["Lightning Bolt", "Opt", "Divination"]


@pytest.mark.parametrize("paid", [0, 2])
def test_vizkopa_confessor_reveals_that_many_and_exiles_the_one_chosen(paid):
    scenario = _board(alice_hand=["Vizkopa Confessor"], bob_hand=_BOB_HAND)
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "bob")
    opt = scenario.find("Opt", Zone.HAND, "bob")
    scenario.will_pay_life_amount(paid, username="alice", source="Vizkopa Confessor")
    scenario.will_choose_cards(bolt, opt, username="bob", source="Vizkopa Confessor")
    scenario.will_choose_cards(opt, username="alice", source="Vizkopa Confessor")
    scenario.choose_trigger_targets("Vizkopa Confessor", [scenario.player("bob")])
    scenario.put_onto_battlefield("Vizkopa Confessor")
    _resolve_all(scenario)
    assert scenario.player("alice").life == 20 - paid
    if paid:
        assert opt.zone is Zone.EXILE
        assert bolt.zone is Zone.HAND
    else:
        assert len(scenario.player("bob").hand) == 3


def test_vizkopa_confessor_reveals_the_whole_hand_when_it_is_short():
    scenario = _board(alice_hand=["Vizkopa Confessor"], bob_hand=["Opt"])
    opt = scenario.find("Opt", Zone.HAND, "bob")
    scenario.will_pay_life_amount(3, username="alice", source="Vizkopa Confessor")
    scenario.will_choose_cards(opt, username="alice", source="Vizkopa Confessor")
    scenario.choose_trigger_targets("Vizkopa Confessor", [scenario.player("bob")])
    scenario.put_onto_battlefield("Vizkopa Confessor")
    _resolve_all(scenario)
    assert opt.zone is Zone.EXILE


def test_vizkopa_confessor_refuses_paying_more_life_than_held():
    scenario = _board(alice_hand=["Vizkopa Confessor"], bob_hand=_BOB_HAND)
    scenario.will_pay_life_amount(21, username="alice", source="Vizkopa Confessor")
    scenario.choose_trigger_targets("Vizkopa Confessor", [scenario.player("bob")])
    scenario.put_onto_battlefield("Vizkopa Confessor")
    with pytest.raises(ValueError):
        _resolve_all(scenario)


# --------------------------------------------------------------------------
# Wheel of Potential / Aether Spike: energy
# --------------------------------------------------------------------------


@pytest.mark.parametrize("paid", [0, 3])
def test_wheel_of_potential_each_player_who_agrees_exiles_their_hand_and_draws_the_energy_paid(
    paid,
):
    scenario = _board(
        alice_hand=["Wheel of Potential", "Opt"],
        alice_lands=("Mountain",) * 3,
        bob_hand=["Lightning Bolt", "Shock"],
        alice_library=["Island"] * 10,
    )
    scenario.will_pay_energy_amount(paid, source="Wheel of Potential")
    scenario.will_take_the_may(True, username="alice", source="Wheel of Potential")
    scenario.will_take_the_may(True, username="bob", source="Wheel of Potential")
    _cast(scenario, "Wheel of Potential")
    assert scenario.player("alice").energy == 3 - paid
    assert len(scenario.player("alice").hand) == paid
    assert len(scenario.player("bob").hand) == paid
    exiled = [s for s in scenario.game.exile if s.name in ("Opt", "Lightning Bolt", "Shock")]
    assert len(exiled) == 3


def test_wheel_of_potential_a_player_may_keep_their_hand():
    scenario = _board(
        alice_hand=["Wheel of Potential", "Opt"],
        alice_lands=("Mountain",) * 3,
        bob_hand=["Lightning Bolt"],
    )
    scenario.will_pay_energy_amount(3, source="Wheel of Potential")
    scenario.will_take_the_may(True, username="alice", source="Wheel of Potential")
    scenario.will_take_the_may(False, username="bob", source="Wheel of Potential")
    _cast(scenario, "Wheel of Potential")
    assert [s.name for s in scenario.player("bob").hand] == ["Lightning Bolt"]


def test_wheel_of_potential_seven_energy_lets_you_play_what_you_exiled_next_turn():
    scenario = _board(
        alice_hand=["Wheel of Potential", "Grizzly Bears"],
        alice_lands=("Mountain",) * 3,
        alice_library=["Island"] * 10,
    )
    scenario.player("alice").add_counters(Counter.ENERGY, 4)
    scenario.will_pay_energy_amount(7, source="Wheel of Potential")
    scenario.will_take_the_may(True, username="alice", source="Wheel of Potential")
    scenario.will_take_the_may(True, username="bob", source="Wheel of Potential")
    _cast(scenario, "Wheel of Potential")
    bears = scenario.find("Grizzly Bears", Zone.EXILE, "alice")
    assert play_permissions_on(scenario.game, bears)


def test_wheel_of_potential_six_energy_gives_no_permission_to_play():
    scenario = _board(
        alice_hand=["Wheel of Potential", "Grizzly Bears"],
        alice_lands=("Mountain",) * 3,
        alice_library=["Island"] * 10,
    )
    scenario.player("alice").add_counters(Counter.ENERGY, 3)
    scenario.will_pay_energy_amount(6, source="Wheel of Potential")
    scenario.will_take_the_may(True, username="alice", source="Wheel of Potential")
    scenario.will_take_the_may(True, username="bob", source="Wheel of Potential")
    _cast(scenario, "Wheel of Potential")
    bears = scenario.find("Grizzly Bears", Zone.EXILE, "alice")
    assert not play_permissions_on(scenario.game, bears)


def _spike_board(alice_extra=()):
    scenario = Scenario().manual_turn_based_actions()
    scenario.player(
        "alice",
        hand=["Opt"],
        battlefield=["Island", *alice_extra],
        library=["Island"] * 5,
    ).player("bob", hand=["Aether Spike"], battlefield=["Island", "Island"], library=["Island"] * 5)
    built = scenario.build()
    built.start_at(Step.PRECOMBAT_MAIN)
    return built


def _opt_into_spike(scenario):
    first_island = scenario.find("Island", Zone.BATTLEFIELD, "alice")
    opt = scenario.cast_onto_stack("Opt", first_island, username="alice")
    scenario.pass_priority("alice")
    bob_islands = scenario.untapped_sources("Island", "Island", username="bob")
    scenario.cast_and_resolve("Aether Spike", *bob_islands, username="bob", targets=[opt])
    _resolve_all(scenario)
    return opt


def test_aether_spike_counters_unless_its_controller_pays_one_per_energy_paid():
    scenario = _spike_board()
    scenario.will_pay_energy_amount(2, username="bob", source="Aether Spike")
    scenario.will_pay_the_mana_cost(False, username="alice", source="Aether Spike")
    opt = _opt_into_spike(scenario)
    assert len(scenario.player("alice").hand) == 0, "Opt was countered before it drew"
    assert scenario.player("bob").energy == 0


def test_aether_spike_does_nothing_when_the_controller_pays():
    scenario = _spike_board(alice_extra=["Island", "Island"])
    scenario.will_pay_energy_amount(2, username="bob", source="Aether Spike")
    scenario.will_pay_the_mana_cost(True, username="alice", source="Aether Spike")
    opt = _opt_into_spike(scenario)
    assert len(scenario.player("alice").hand) == 1, "Opt resolved and drew"
    assert scenario.player("bob").energy == 0
    assert all(s.tapped for s in scenario.game.battlefield if s.controller == "alice")


def test_aether_spike_paying_no_energy_counters_nothing_to_pay():
    scenario = _spike_board()
    scenario.will_pay_energy_amount(0, username="bob", source="Aether Spike")
    opt = _opt_into_spike(scenario)
    assert scenario.player("bob").energy == 2
    assert len(scenario.player("alice").hand) == 1, "paying {0} owes nothing, so Opt resolved"


def test_aether_spike_refuses_more_energy_than_held():
    scenario = _spike_board()
    scenario.will_pay_energy_amount(3, username="bob", source="Aether Spike")
    with pytest.raises(ValueError, match="only 2 available"):
        _opt_into_spike(scenario)


# --------------------------------------------------------------------------
# Primal Adversary / Bloodthirsty Adversary: "pay {cost} any number of times"
# then a multi-part payoff
# --------------------------------------------------------------------------


def test_primal_adversary_animates_up_to_that_many_lands_into_haste_wolves():
    scenario = _board(
        alice_hand=["Primal Adversary"], alice_lands=("Forest",) * 5, alice_battlefield=[]
    )
    forests = _on_battlefield(scenario, "Forest")
    scenario.will_choose_an_amount(2, source="Primal Adversary")
    scenario.will_choose_targets(forests[8], forests[9], source="Primal Adversary")
    adversary = scenario.put_onto_battlefield("Primal Adversary")
    _resolve_all(scenario)
    assert adversary.counters["+1/+1"] == 2
    for land in (forests[8], forests[9]):
        chars = scenario.game.characteristics_of(land)
        assert (chars.power, chars.toughness) == (3, 3)
        type_line = str(chars.type_line)
        assert "Land" in type_line and "Creature" in type_line and "Wolf" in type_line
        assert "haste" in {k.lower() for k in chars.keywords}


def test_primal_adversary_one_payment_animates_at_most_one_land():
    scenario = _board(alice_hand=["Primal Adversary"], alice_lands=("Forest",) * 5)
    forests = _on_battlefield(scenario, "Forest")
    scenario.will_choose_an_amount(1, source="Primal Adversary")
    scenario.will_choose_targets(forests[0], source="Primal Adversary")
    adversary = scenario.put_onto_battlefield("Primal Adversary")
    _resolve_all(scenario)
    assert adversary.counters["+1/+1"] == 1
    assert scenario.game.characteristics_of(forests[0]).power == 3
    assert scenario.game.characteristics_of(forests[1]).power in (None, 0)


def test_primal_adversary_paying_nothing_does_nothing():
    scenario = _board(alice_hand=["Primal Adversary"], alice_lands=("Forest",) * 5)
    scenario.will_choose_an_amount(0, source="Primal Adversary")
    adversary = scenario.put_onto_battlefield("Primal Adversary")
    _resolve_all(scenario)
    assert adversary.counters["+1/+1"] == 0


def _gy_board(**extra):
    return _board(
        alice_hand=["Bloodthirsty Adversary"],
        alice_lands=("Mountain",) * 5,
        alice_graveyard=["Lightning Bolt", "Opt", "Divination", "Brainstorm"],
        **extra,
    )


def test_bloodthirsty_adversary_exiles_that_many_cards_and_casts_the_copies_free():
    scenario = _gy_board(alice_library=["Island"] * 10)
    opt = scenario.find("Opt", Zone.GRAVEYARD, "alice")
    divination = scenario.find("Divination", Zone.GRAVEYARD, "alice")
    scenario.will_choose_an_amount(2, source="Bloodthirsty Adversary")
    scenario.will_choose_targets(opt, divination, source="Bloodthirsty Adversary")
    scenario.will_take_the_may(True, username="alice", source="Bloodthirsty Adversary", times=None)
    adversary = scenario.put_onto_battlefield("Bloodthirsty Adversary")
    _resolve_all(scenario)
    assert adversary.counters["+1/+1"] == 2
    assert opt.zone is Zone.EXILE and divination.zone is Zone.EXILE
    # Opt draws one, Divination two: the copies were cast and resolved.
    assert len(scenario.player("alice").hand) == 3


def test_bloodthirsty_adversary_may_decline_to_cast_the_copies():
    scenario = _gy_board(alice_library=["Island"] * 10)
    opt = scenario.find("Opt", Zone.GRAVEYARD, "alice")
    scenario.will_choose_an_amount(1, source="Bloodthirsty Adversary")
    scenario.will_choose_targets(opt, source="Bloodthirsty Adversary")
    scenario.will_take_the_may(False, username="alice", source="Bloodthirsty Adversary", times=None)
    scenario.put_onto_battlefield("Bloodthirsty Adversary")
    _resolve_all(scenario)
    assert opt.zone is Zone.EXILE
    assert len(scenario.player("alice").hand) == 0


def test_bloodthirsty_adversary_will_not_target_a_spell_worth_more_than_three():
    scenario = _board(
        alice_hand=["Bloodthirsty Adversary"],
        alice_lands=("Mountain",) * 5,
        alice_graveyard=["Day of Judgment"],
    )
    scenario.will_choose_an_amount(1, source="Bloodthirsty Adversary")
    scenario.put_onto_battlefield("Bloodthirsty Adversary")
    _resolve_all(scenario)
    judgment = scenario.find("Day of Judgment", Zone.GRAVEYARD, "alice")
    assert judgment.zone is Zone.GRAVEYARD
