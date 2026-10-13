"""EP-02 R2 T8: chosen or paid amounts, and damage or life as X.

    Tap any number of untapped creatures you control. Create a 4/4 ... token
    for each creature tapped this way.
    You may pay {1}{W} any number of times. When you pay this cost one or
    more times, put that many valor counters on this creature.
    ... draw cards equal to the damage dealt to target opponent this turn.

Rules, each read in full with `mise run rules:find` in this session:

- CR 107.1c - "any number" may be any positive number or zero.
- CR 608.2c - instructions are followed in order; a later "this way" / "that
  many" reads what the earlier instruction really did.
- CR 608.2d - a choice an effect offers is made as the effect is applied, and
  an illegal or impossible option can't be chosen.
- CR 701.26a - only an untapped permanent can be tapped.
- CR 701.20a - revealing shows a card; it stays where it is.
- CR 118.3 / CR 119.4 / CR 107.14 - a player can't pay more than they have:
  life, energy, mana.
- CR 603.12 - "when you pay this cost one or more times" is a reflexive
  trigger, a separate object put on the stack after the payment.
- CR 120.3a / CR 119.3 - damage to a player is life lost; gaining or losing
  life adjusts the total.
- CR 603.2c - a trigger's amount is its one event's.
- CR 605.3b - a mana ability resolves immediately, off the stack.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.keywords import equip_activation
from magic_cards_model.models import Color, Zone
from magic_cards_model.support import card_support
from tests.cards import card

from .harness import Scenario, mana_from

LISTED = [
    "Barrel Down Sokenzan",
    "Devout Invocation",
    "Hew the Entwood",
    "Ledev Champion",
    "Nahiri's Lithoforming",
    "Orphans of the Wheat",
    "Plow Through Reito",
    "Plunge into Darkness",
    "Quintorius Kand",
    "Sacellum Godspeaker",
    "Siege Striker",
    "Sink into Takenuma",
    "The Hunger Tide Rises",
    "Die Young",
    "Plague of Vermin",
    "Phosphorescent Feast",
    "Karn, Living Legacy",
    "Intrepid Adversary",
    "Tainted Adversary",
    "Cradle of Vitality",
    "Knollspine Dragon",
    "Kotis, the Fangkeeper",
    "Jagged Poppet",
    "Notorious Throng",
    "Shanna, Purifying Blade",
    "Florian, Voldaren Scion",
    "Buster Sword",
    "Covert Technician",
    "Ziatora's Envoy",
    "Blood Tribute",
]

#: Second printings, legal and outside every deck list, each proving a reader
#: with different wording from the listed card it was built for.
PROOFS = [
    "Jaddi Lifestrider",
    "Charge Across the Araba",
    "Rosheen, Roaring Prophet",
]


@pytest.mark.parametrize("name", LISTED + PROOFS)
def test_every_listed_and_proof_card_reads_handled(name):
    support = card_support(card(name))
    # A mana ability is not an effect clause (CR 605.3b) - its verdict is the
    # card's own status - so only the clauses present are checked.
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
            battlefield=["Swamp", "Swamp", *bob_battlefield],
            library=list(bob_library),
        )
        .build()
    )
    scenario.start_at(start)
    return scenario


def _cast(scenario, name, targets=None):
    return scenario.cast_and_resolve(name, username="alice", targets=targets, auto=True)


def _resolve_all(scenario):
    while scenario.stack_names() or scenario.pending_triggers:
        scenario.game.put_triggers_on_stack()
        scenario.pass_until_resolved()


def _advance_to(scenario, step):
    """Walk the turn through `Game.advance`, so beginning-of-step triggers
    fire (CR 503.1a-style "at the beginning of"), then resolve them."""
    while scenario.turn.step is not step:
        scenario.advance()
    _resolve_all(scenario)


def _on_battlefield(scenario, name, username="alice"):
    return [
        state
        for state in scenario.game.battlefield
        if state.name == name and state.controller == username
    ]


def _question(scenario, source):
    return [q for q in scenario.questions_asked() if q.source == source]


# --------------------------------------------------------------------------
# "Tap any number of untapped creatures you control" + "for each ... tapped
# this way"
# --------------------------------------------------------------------------


@pytest.mark.parametrize("tapped", [0, 1, 3])
def test_devout_invocation_makes_an_angel_per_creature_really_tapped(tapped):
    scenario = _board(
        alice_hand=["Devout Invocation"],
        alice_battlefield=["Grizzly Bears"] * 3,
        alice_lands=("Plains", "Plains", "Plains", "Plains"),
    )
    bears = _on_battlefield(scenario, "Grizzly Bears")
    scenario.will_choose_cards(*bears[:tapped], source="Devout Invocation")
    _cast(scenario, "Devout Invocation")
    assert sum(1 for b in bears if b.tapped) == tapped
    angels = [s for s in scenario.game.battlefield if "Angel" in str(s.card.type_line)]
    assert len(angels) == tapped


def test_devout_invocation_offers_only_untapped_creatures_and_names_the_limit():
    scenario = _board(
        alice_hand=["Devout Invocation"],
        alice_battlefield=["Grizzly Bears"] * 2,
        alice_lands=("Plains", "Plains", "Plains", "Plains"),
    )
    first, second = _on_battlefield(scenario, "Grizzly Bears")
    first.tap()
    scenario.will_choose_cards(second, source="Devout Invocation")
    _cast(scenario, "Devout Invocation")
    (question,) = _question(scenario, "Devout Invocation")
    assert question.cards == (second.id,)
    assert question.amount == 1 and not question.exact


def test_tapping_more_than_the_untapped_creatures_is_refused_with_the_limit():
    scenario = _board(
        alice_hand=["Devout Invocation"],
        alice_battlefield=["Grizzly Bears"],
        alice_lands=("Plains", "Plains", "Plains", "Plains"),
    )
    (bear,) = _on_battlefield(scenario, "Grizzly Bears")
    plains = _on_battlefield(scenario, "Plains")
    scenario.will_choose_cards(bear, plains[0], source="Devout Invocation")
    with pytest.raises(ValueError, match="cannot choose a card that was not offered"):
        _cast(scenario, "Devout Invocation")


@pytest.mark.parametrize("attacker", ["Ledev Champion", "Siege Striker", "Orphans of the Wheat"])
@pytest.mark.parametrize("tapped", [0, 2])
def test_attack_trigger_pumps_once_per_creature_tapped(attacker, tapped):
    scenario = _board(
        alice_battlefield=[attacker, "Grizzly Bears", "Grizzly Bears"],
    )
    champion = scenario.creature(attacker, "alice")
    for state in scenario.game.battlefield:
        state.summoning_sick = False
    bears = _on_battlefield(scenario, "Grizzly Bears")
    base = scenario.game.characteristics_of(champion).power
    scenario.will_choose_cards(*bears[:tapped], source=attacker)
    scenario.turn.advance_to(Step.DECLARE_ATTACKERS)
    scenario.attack_with(champion)
    _resolve_all(scenario)
    assert scenario.game.characteristics_of(champion).power == base + tapped
    assert sum(1 for b in bears if b.tapped) == tapped


def test_jaddi_lifestrider_gains_two_life_per_creature_tapped():
    scenario = _board(
        alice_hand=["Jaddi Lifestrider"], alice_battlefield=["Grizzly Bears", "Llanowar Elves"]
    )
    creatures = [
        *_on_battlefield(scenario, "Grizzly Bears"),
        *_on_battlefield(scenario, "Llanowar Elves"),
    ]
    scenario.will_choose_cards(*creatures, source="Jaddi Lifestrider")
    scenario.put_onto_battlefield("Jaddi Lifestrider")
    _resolve_all(scenario)
    assert scenario.player("alice").life == 24


# --------------------------------------------------------------------------
# Sweep: "Return any number of <basic> you control to their owner's hand"
# --------------------------------------------------------------------------


@pytest.mark.parametrize("returned", [0, 1, 2])
def test_barrel_down_sokenzan_deals_twice_the_mountains_returned(returned):
    scenario = _board(
        alice_hand=["Barrel Down Sokenzan"],
        alice_lands=("Mountain", "Mountain", "Mountain"),
        bob_battlefield=["Colossal Dreadmaw"],
    )
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")
    mountains = _on_battlefield(scenario, "Mountain")
    chosen = mountains[-returned:] if returned else []
    scenario.will_choose_cards(*chosen, source="Barrel Down Sokenzan")
    _cast(scenario, "Barrel Down Sokenzan", targets=[dreadmaw])
    assert dreadmaw.damage == 2 * returned
    assert sum(1 for s in scenario.player("alice").hand if s.name == "Mountain") == returned


def test_plow_through_reito_pumps_target_per_plains_returned():
    scenario = _board(
        alice_hand=["Plow Through Reito"],
        alice_lands=("Plains", "Plains", "Plains"),
        alice_battlefield=["Grizzly Bears"],
    )
    bear = scenario.creature("Grizzly Bears", "alice")
    plains = _on_battlefield(scenario, "Plains")
    scenario.will_choose_cards(*plains[-2:], source="Plow Through Reito")
    _cast(scenario, "Plow Through Reito", targets=[bear])
    assert scenario.game.characteristics_of(bear).power == 4


def test_sink_into_takenuma_discards_one_per_swamp_returned():
    scenario = _board(
        alice_hand=["Sink into Takenuma"],
        alice_lands=("Swamp", "Swamp", "Swamp", "Swamp"),
        bob_hand=["Island", "Island", "Island"],
    )
    swamps = _on_battlefield(scenario, "Swamp")
    scenario.will_choose_cards(*swamps[-2:], source="Sink into Takenuma")
    _cast(scenario, "Sink into Takenuma", targets=[scenario.player("bob")])
    assert len(scenario.player("bob").hand) == 1


def test_charge_across_the_araba_pumps_each_creature_per_plains_returned():
    scenario = _board(
        alice_hand=["Charge Across the Araba"],
        alice_lands=("Plains", "Plains", "Plains", "Plains", "Plains"),
        alice_battlefield=["Grizzly Bears", "Llanowar Elves"],
    )
    plains = _on_battlefield(scenario, "Plains")
    scenario.will_choose_cards(*plains[-3:], source="Charge Across the Araba")
    _cast(scenario, "Charge Across the Araba")
    assert scenario.game.characteristics_of(scenario.creature("Grizzly Bears")).power == 5
    assert scenario.game.characteristics_of(scenario.creature("Llanowar Elves")).power == 4


# --------------------------------------------------------------------------
# "Reveal any number of <cards> from your hand. Add {M} for each card revealed
# this way." - a mana ability (CR 605.3b)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("revealed", [0, 1, 2])
def test_sacellum_godspeaker_adds_green_per_big_creature_revealed(revealed):
    scenario = _board(
        alice_hand=["Colossal Dreadmaw", "Craterhoof Behemoth", "Grizzly Bears"],
        alice_battlefield=["Sacellum Godspeaker"],
    )
    godspeaker = scenario.creature("Sacellum Godspeaker", "alice")
    godspeaker.summoning_sick = False
    big = [s for s in scenario.player("alice").hand if s.name != "Grizzly Bears"]
    scenario.will_choose_cards(*big[:revealed], source="Sacellum Godspeaker")
    scenario.activate(godspeaker, username="alice")
    assert scenario.player("alice").mana_pool.floating.get(Color.GREEN, 0) == revealed
    assert len(scenario.player("alice").hand) == 3


def test_sacellum_godspeaker_does_not_offer_a_small_creature():
    scenario = _board(
        alice_hand=["Colossal Dreadmaw", "Grizzly Bears"],
        alice_battlefield=["Sacellum Godspeaker"],
    )
    godspeaker = scenario.creature("Sacellum Godspeaker", "alice")
    godspeaker.summoning_sick = False
    bears = scenario.find("Grizzly Bears", Zone.HAND, "alice")
    scenario.will_choose_cards(bears, source="Sacellum Godspeaker")
    with pytest.raises(ValueError, match="not offered"):
        scenario.activate(godspeaker, username="alice")


def test_rosheen_adds_two_colorless_per_x_card_revealed():
    scenario = _board(
        alice_hand=["Hew the Entwood", "Nahiri's Lithoforming", "Grizzly Bears"],
        alice_battlefield=["Rosheen, Roaring Prophet"],
    )
    rosheen = scenario.creature("Rosheen, Roaring Prophet", "alice")
    rosheen.summoning_sick = False
    x_card = scenario.find("Nahiri's Lithoforming", Zone.HAND, "alice")
    scenario.will_choose_cards(x_card, source="Rosheen, Roaring Prophet")
    scenario.activate(rosheen, username="alice")
    assert scenario.player("alice").mana_pool.floating.get(Color.COLORLESS, 0) == 2


# --------------------------------------------------------------------------
# "Sacrifice any number of <things>" / "Sacrifice X lands" + payoffs
# --------------------------------------------------------------------------


def test_nahiris_lithoforming_draws_per_land_sacrificed_and_grants_land_plays():
    scenario = _board(
        alice_hand=["Nahiri's Lithoforming"],
        alice_lands=("Mountain", "Mountain", "Mountain", "Mountain"),
    )
    hand_before = len(scenario.player("alice").hand) - 1
    mountains = _on_battlefield(scenario, "Mountain")
    scenario.will_choose_cards(*mountains[:2], source="Nahiri's Lithoforming")
    scenario.game.cast_x = 2  # announced X, read off the cast record
    scenario.cast_and_resolve("Nahiri's Lithoforming", username="alice", auto=True)
    assert len(_on_battlefield(scenario, "Mountain")) == 6
    assert len(scenario.player("alice").hand) == hand_before + 2


def test_hunger_tide_rises_chapter_four_searches_up_to_creatures_sacrificed():
    scenario = _board(
        alice_battlefield=["Grizzly Bears", "Llanowar Elves"],
        alice_library=["Colossal Dreadmaw", "Grizzly Bears", "Forest", "Forest"],
    )
    saga = scenario.put_onto_battlefield("The Hunger Tide Rises", from_zone=Zone.LIBRARY)
    creatures = [
        *_on_battlefield(scenario, "Grizzly Bears"),
        *_on_battlefield(scenario, "Llanowar Elves"),
    ]
    scenario.will_choose_cards(*creatures, source="The Hunger Tide Rises")
    bears = scenario.find("Grizzly Bears", Zone.LIBRARY, "alice")
    scenario.will_choose_cards(bears, source="The Hunger Tide Rises")
    for _ in range(3):
        scenario.game.add_counters(saga, "lore", 1)
        _resolve_all(scenario)
    assert any(s.name == "Grizzly Bears" for s in scenario.game.battlefield)


def test_hew_the_entwood_reveals_one_card_per_land_sacrificed():
    scenario = _board(
        alice_hand=["Hew the Entwood"],
        alice_lands=("Mountain", "Mountain", "Mountain"),
        alice_library=["Forest", "Sol Ring", "Grizzly Bears", "Island", "Island"],
    )
    mountains = _on_battlefield(scenario, "Mountain")
    scenario.will_choose_cards(*mountains[:3], source="Hew the Entwood")
    top = scenario.top_of_library(3, "alice")
    scenario.will_choose_cards(top[0], top[1], source="Hew the Entwood")
    _cast(scenario, "Hew the Entwood")
    forest = [s for s in scenario.game.battlefield if s.id == top[0].id]
    ring = [s for s in scenario.game.battlefield if s.id == top[1].id]
    assert forest and forest[0].tapped
    assert ring and not ring[0].tapped
    assert scenario.player("alice").library[-1].name == "Grizzly Bears"


@pytest.mark.parametrize("sacrificed", [0, 2])
def test_plunge_into_darkness_first_mode_gains_three_per_creature(sacrificed):
    scenario = _board(
        alice_hand=["Plunge into Darkness"],
        alice_battlefield=["Grizzly Bears", "Grizzly Bears"],
    )
    bears = _on_battlefield(scenario, "Grizzly Bears")
    scenario.will_choose_mode(
        "Sacrifice any number of creatures. You gain 3 life for each creature sacrificed this way."
    )
    scenario.will_choose_cards(*bears[:sacrificed], source="Plunge into Darkness")
    _cast(scenario, "Plunge into Darkness")
    assert scenario.player("alice").life == 20 + 3 * sacrificed


def test_plunge_into_darkness_second_mode_looks_at_life_paid_cards():
    scenario = _board(
        alice_hand=["Plunge into Darkness"],
        alice_library=["Sol Ring", "Island", "Forest", "Forest"],
    )
    scenario.will_choose_mode(
        "Pay any amount of life, then look at that many cards from the top of your library. "
        "Put one of those cards into your hand and exile the rest."
    )
    scenario.will_pay_life_amount(3, source="Plunge into Darkness")
    ring = scenario.find("Sol Ring", Zone.LIBRARY, "alice")
    scenario.will_choose_cards(ring, source="Plunge into Darkness")
    _cast(scenario, "Plunge into Darkness")
    assert scenario.player("alice").life == 17
    assert ring.zone is Zone.HAND
    assert len(scenario.game.exile) == 2


def test_quintorius_ultimate_exiles_chosen_cards_and_adds_red_per_card():
    scenario = _board(
        alice_battlefield=["Quintorius Kand"],
        alice_graveyard=["Grizzly Bears", "Lightning Bolt", "Forest"],
    )
    quintorius = scenario.find("Quintorius Kand", Zone.BATTLEFIELD, "alice")
    quintorius.counters.add("loyalty", 2)
    graveyard = list(scenario.player("alice").graveyard)
    scenario.activate(quintorius, index=3, targets=graveyard[:2], username="alice")
    _resolve_all(scenario)
    assert scenario.player("alice").mana_pool.floating.get(Color.RED, 0) == 2
    assert all(state.zone is Zone.EXILE for state in graveyard[:2])


# --------------------------------------------------------------------------
# "Pay any amount of {E} / life / mana", "pay {cost} any number of times"
# --------------------------------------------------------------------------


@pytest.mark.parametrize("paid", [0, 2])
def test_die_young_shrinks_target_once_per_energy_paid(paid):
    scenario = _board(alice_hand=["Die Young"], bob_battlefield=["Colossal Dreadmaw"])
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")
    scenario.will_pay_energy_amount(paid, source="Die Young")
    _cast(scenario, "Die Young", targets=[dreadmaw])
    assert scenario.game.characteristics_of(dreadmaw).power == 6 - paid
    assert scenario.player("alice").energy == 2 - paid


def test_die_young_refuses_more_energy_than_held():
    scenario = _board(alice_hand=["Die Young"], bob_battlefield=["Colossal Dreadmaw"])
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")
    scenario.will_pay_energy_amount(3, source="Die Young")
    with pytest.raises(ValueError, match="only 2 available"):
        _cast(scenario, "Die Young", targets=[dreadmaw])


def test_plague_of_vermin_repeats_until_nobody_pays_and_makes_rats_per_life():
    scenario = _board(alice_hand=["Plague of Vermin"], alice_lands=("Swamp",) * 4)
    scenario.will_pay_life_amount(2, username="alice", source="Plague of Vermin")
    scenario.will_pay_life_amount(1, username="bob", source="Plague of Vermin")
    scenario.will_pay_life_amount(1, username="alice", source="Plague of Vermin")
    scenario.will_pay_life_amount(0, username="bob", source="Plague of Vermin")
    scenario.will_pay_life_amount(0, username="alice", source="Plague of Vermin")
    _cast(scenario, "Plague of Vermin")
    rats = lambda user: [s for s in scenario.game.battlefield if s.token and s.controller == user]  # noqa: E731
    assert len(rats("alice")) == 3 and len(rats("bob")) == 1
    assert scenario.player("alice").life == 17 and scenario.player("bob").life == 19


def test_phosphorescent_feast_gains_two_per_green_symbol_revealed():
    scenario = _board(
        alice_hand=["Phosphorescent Feast", "Llanowar Elves", "Grizzly Bears", "Lightning Bolt"],
        alice_lands=("Forest", "Forest", "Forest", "Forest", "Forest"),
    )
    elves = scenario.find("Llanowar Elves", Zone.HAND, "alice")
    bears = scenario.find("Grizzly Bears", Zone.HAND, "alice")
    scenario.will_choose_cards(elves, bears, source="Phosphorescent Feast")
    _cast(scenario, "Phosphorescent Feast")
    assert scenario.player("alice").life == 24


def test_karn_minus_one_pays_any_amount_of_mana_and_looks_at_that_many():
    scenario = _board(
        alice_battlefield=["Karn, Living Legacy"],
        alice_library=["Sol Ring", "Island", "Forest", "Forest"],
    )
    karn = scenario.find("Karn, Living Legacy", Zone.BATTLEFIELD, "alice")
    scenario.will_choose_an_amount(3, source="Karn, Living Legacy")
    ring = scenario.find("Sol Ring", Zone.LIBRARY, "alice")
    scenario.will_choose_cards(ring, source="Karn, Living Legacy")
    scenario.activate(karn, index=1, username="alice")
    _resolve_all(scenario)
    assert ring.zone is Zone.HAND
    assert sum(1 for s in scenario.game.battlefield if s.controller == "alice" and s.tapped) == 3


def test_karn_minus_one_refuses_more_mana_than_can_be_paid():
    scenario = _board(alice_battlefield=["Karn, Living Legacy"], alice_lands=("Forest",))
    karn = scenario.find("Karn, Living Legacy", Zone.BATTLEFIELD, "alice")
    scenario.will_choose_an_amount(5, source="Karn, Living Legacy")
    with pytest.raises(ValueError, match="at most 2"):
        scenario.activate(karn, index=1, username="alice")
        _resolve_all(scenario)


@pytest.mark.parametrize("times", [0, 2])
def test_intrepid_adversary_puts_a_valor_counter_per_payment(times):
    scenario = _board(alice_hand=["Intrepid Adversary"], alice_lands=("Plains", "Plains", "Plains"))
    scenario.will_choose_an_amount(times, source="Intrepid Adversary")
    adversary = scenario.put_onto_battlefield("Intrepid Adversary")
    _resolve_all(scenario)
    assert adversary.counters["valor"] == times


def test_tainted_adversary_counters_and_twice_that_many_zombies():
    scenario = _board(alice_hand=["Tainted Adversary"], alice_lands=("Swamp", "Swamp", "Swamp"))
    scenario.will_choose_an_amount(2, source="Tainted Adversary")
    adversary = scenario.put_onto_battlefield("Tainted Adversary")
    _resolve_all(scenario)
    assert adversary.counters["+1/+1"] == 2
    zombies = [
        s for s in scenario.game.battlefield if s.token and "Zombie" in str(s.card.type_line)
    ]
    assert len(zombies) == 4


# --------------------------------------------------------------------------
# damage-or-life-amount-as-x
# --------------------------------------------------------------------------


def test_cradle_of_vitality_puts_a_counter_per_life_gained():
    scenario = _board(
        alice_battlefield=["Cradle of Vitality", "Grizzly Bears"], alice_lands=("Plains", "Plains")
    )
    bear = scenario.creature("Grizzly Bears", "alice")
    scenario.will_pay_the_mana_cost(True, source="Cradle of Vitality")
    scenario.game.gain_life(scenario.player("alice"), 3)
    scenario.choose_trigger_targets("Cradle of Vitality", [bear])
    _resolve_all(scenario)
    assert bear.counters["+1/+1"] == 3


def test_knollspine_dragon_draws_the_damage_dealt_to_target_opponent_this_turn():
    scenario = _board(alice_hand=["Knollspine Dragon"], alice_library=["Forest"] * 10)
    scenario.game.deal_damage(scenario.player("bob"), 4, source=None)
    scenario.will_take_the_may(True, source="Knollspine Dragon")
    scenario.put_onto_battlefield("Knollspine Dragon")
    scenario.choose_trigger_targets("Knollspine Dragon", [scenario.player("bob")])
    _resolve_all(scenario)
    assert len(scenario.player("alice").hand) == 4


def test_notorious_throng_makes_a_faerie_per_damage_dealt_to_opponents():
    scenario = _board(alice_hand=["Notorious Throng"], alice_lands=("Island",) * 4)
    scenario.game.deal_damage(scenario.player("bob"), 3, source=None)
    _cast(scenario, "Notorious Throng")
    faeries = [
        s for s in scenario.game.battlefield if s.token and "Faerie" in str(s.card.type_line)
    ]
    assert len(faeries) == 3


def _hit(scenario, attacker_name):
    attacker = scenario.creature(attacker_name, "alice")
    attacker.summoning_sick = False
    scenario.turn.advance_to(Step.DECLARE_ATTACKERS)
    scenario.attack_with(attacker)
    _resolve_all(scenario)
    scenario.no_blocks()
    scenario.combat_damage()
    _resolve_all(scenario)
    return attacker


def test_jagged_poppet_hellbent_discards_equal_to_the_damage():
    scenario = _board(alice_battlefield=["Jagged Poppet"], bob_hand=["Island"] * 5)
    _hit(scenario, "Jagged Poppet")
    assert len(scenario.player("bob").hand) == 2


def test_kotis_exiles_top_x_where_x_is_the_damage():
    scenario = _board(alice_battlefield=["Kotis, the Fangkeeper"], bob_library=["Island"] * 6)
    _hit(scenario, "Kotis, the Fangkeeper")
    assert len(scenario.player("bob").library) == 4


def test_covert_technician_puts_an_artifact_with_mana_value_up_to_the_damage():
    scenario = _board(
        alice_battlefield=["Covert Technician"], alice_hand=["Sol Ring", "Buster Sword"]
    )
    ring = scenario.find("Sol Ring", Zone.HAND, "alice")
    scenario.will_choose_cards(ring, source="Covert Technician")
    _hit(scenario, "Covert Technician")
    assert ring.zone is Zone.BATTLEFIELD


def test_shanna_draws_x_capped_by_life_gained_this_turn():
    scenario = _board(alice_battlefield=["Shanna, Purifying Blade"], start=Step.PRECOMBAT_MAIN)
    scenario.game.gain_life(scenario.player("alice"), 2)
    hand = len(scenario.player("alice").hand)
    scenario.will_choose_an_amount(2, source="Shanna, Purifying Blade")
    _advance_to(scenario, Step.END_STEP)
    assert len(scenario.player("alice").hand) == hand + 2


def test_shanna_refuses_x_above_life_gained():
    scenario = _board(alice_battlefield=["Shanna, Purifying Blade"])
    scenario.game.gain_life(scenario.player("alice"), 1)
    scenario.will_choose_an_amount(3, source="Shanna, Purifying Blade")
    with pytest.raises(ValueError, match="at most 1"):
        _advance_to(scenario, Step.END_STEP)


def test_florian_looks_at_the_life_opponents_lost_this_turn():
    scenario = _board(
        alice_battlefield=["Florian, Voldaren Scion"],
        alice_library=["Sol Ring", "Forest", "Forest"],
    )
    scenario.game.lose_life(scenario.player("bob"), 2)
    ring = scenario.find("Sol Ring", Zone.LIBRARY, "alice")
    scenario.will_choose_cards(ring, source="Florian, Voldaren Scion")
    _advance_to(scenario, Step.POSTCOMBAT_MAIN)
    assert ring.zone is Zone.EXILE


def test_blood_tribute_kicked_gains_the_life_lost_this_way():
    scenario = _board(alice_hand=["Blood Tribute"], alice_battlefield=["Florian, Voldaren Scion"])
    vampire = scenario.creature("Florian, Voldaren Scion", "alice")
    scenario.cast_and_resolve(
        "Blood Tribute",
        username="alice",
        targets=[scenario.player("bob")],
        auto=True,
        tapping=[vampire],
    )
    assert scenario.player("bob").life == 10
    assert scenario.player("alice").life == 30


def test_buster_sword_draws_then_casts_a_spell_up_to_the_damage_free():
    scenario = _board(
        alice_battlefield=["Buster Sword", "Grizzly Bears"],
        alice_hand=["Colossal Dreadmaw", "Llanowar Elves"],
        alice_library=["Forest"] * 5,
    )
    sword = scenario.find("Buster Sword", Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    activation = equip_activation(scenario.game, sword, bears, "alice")
    payment = activation.begin_paying()
    for source in scenario.untapped_sources("Plains", "Plains", username="alice"):
        payment.tap_for_mana(source, mana_from(source))
    payment.pay()
    activation.activate()
    scenario.pass_until_resolved()
    elves = scenario.find("Llanowar Elves", Zone.HAND, "alice")
    dreadmaw = scenario.find("Colossal Dreadmaw", Zone.HAND, "alice")
    hand = len(scenario.player("alice").hand)
    scenario.will_take_the_may(True, source="Buster Sword")
    scenario.will_choose_cards(elves, source="Buster Sword")
    _hit(scenario, "Grizzly Bears")
    _resolve_all(scenario)
    # 5 damage: the 6-mana Dreadmaw is never offered, the Elves are cast free.
    assert elves.zone is Zone.BATTLEFIELD or any(
        s.name == "Llanowar Elves" for s in scenario.game.battlefield
    )
    assert dreadmaw.zone is Zone.HAND
    assert len(scenario.player("alice").hand) == hand  # drew one, cast one


@pytest.mark.parametrize(
    ("top", "where"), [("Grizzly Bears", Zone.BATTLEFIELD), ("Colossal Dreadmaw", Zone.HAND)]
)
def test_ziatoras_envoy_casts_the_top_card_up_to_the_damage_else_takes_it(top, where):
    scenario = _board(alice_battlefield=["Ziatora's Envoy"], alice_library=[top, "Forest"])
    card_on_top = scenario.find(top, Zone.LIBRARY, "alice")
    if where is Zone.BATTLEFIELD:
        scenario.will_take_the_may(True, source="Ziatora's Envoy")
    _hit(scenario, "Ziatora's Envoy")
    landed = [s for s in scenario.game.battlefield if s.name == top]
    if where is Zone.BATTLEFIELD:
        assert landed
    else:
        assert card_on_top.zone is Zone.HAND and not landed
