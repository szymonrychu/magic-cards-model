"""CR 118.9: another permanent's static ability applies an alternative cost
to the spells its controller casts (EP-01 round 1, task T7).

    You may pay {W}{U}{B}{R}{G} rather than pay the mana cost for spells you cast.
    You may pay {0} rather than pay the mana cost for Zombie creature spells you cast.
    You may collect evidence 10 rather than pay the mana cost for spells you cast.
    Once each turn, you may pay {0} rather than pay the mana cost for a spell
    you cast with mana value X or less, where X is the number of time counters
    on this enchantment.

Each case reads the option list the engine offers for a real card in hand and
the cost that option makes of the cast; each has a spell the line does NOT name.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def _main(**players) -> Scenario:
    builder = Scenario().manual_turn_based_actions()
    for username, kwargs in players.items():
        builder = builder.player(username, **kwargs)
    scenario = builder.build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _static_options(scenario, name, username="alice", zone=Zone.HAND):
    card = scenario.find(name, zone, username)
    return [
        option
        for option in scenario.game.alternative_costs_for(card, username)
        if option.source.value == "static"
    ]


def _alt_cost(scenario, name, which, username="alice") -> str:
    casting = scenario.cast(name, username)
    casting.use_alternative_cost(which)
    scenario.game.determine_total_cost(casting)
    mana = str(casting.total_cost.mana)
    casting.cancel()
    return mana


def test_fist_of_suns_offers_five_colours_for_any_spell():
    scenario = _main(
        alice={
            "hand": ["Grizzly Bears", "Lightning Bolt"],
            "battlefield": ["Fist of Suns"],
        }
    )
    for name in ("Grizzly Bears", "Lightning Bolt"):
        (option,) = _static_options(scenario, name)
        assert option.available
        assert option.description == "{W}{U}{B}{R}{G}"
    assert _alt_cost(scenario, "Grizzly Bears", "Fist of Suns") == "{W}{U}{B}{R}{G}"


def test_no_alternative_cost_without_the_permanent():
    scenario = _main(alice={"hand": ["Grizzly Bears"]})
    assert _static_options(scenario, "Grizzly Bears") == []


def test_jodah_offers_the_same_five_colour_cost_to_its_controller_only():
    scenario = _main(
        alice={"hand": ["Grizzly Bears"], "battlefield": ["Jodah, Archmage Eternal"]},
        bob={"hand": ["Lightning Bolt"]},
    )
    assert len(_static_options(scenario, "Grizzly Bears")) == 1
    assert _static_options(scenario, "Lightning Bolt", "bob") == []


def test_rooftop_storm_makes_only_zombie_creature_spells_free():
    scenario = _main(
        alice={
            "hand": ["Walking Corpse", "Grizzly Bears"],
            "battlefield": ["Rooftop Storm"],
        }
    )
    (zombie,) = _static_options(scenario, "Walking Corpse")
    assert zombie.available
    assert _alt_cost(scenario, "Walking Corpse", "Rooftop Storm") == "{0}"
    (bears,) = _static_options(scenario, "Grizzly Bears")
    assert not bears.available


def test_runeforge_champion_charges_one_for_rune_spells_only():
    scenario = _main(
        alice={
            "hand": ["Rune of Might", "Grizzly Bears"],
            "battlefield": ["Runeforge Champion"],
        }
    )
    (rune,) = _static_options(scenario, "Rune of Might")
    assert rune.available and rune.description == "{1}"
    (bears,) = _static_options(scenario, "Grizzly Bears")
    assert not bears.available


def test_conspiracy_unraveler_needs_ten_mana_value_in_the_graveyard():
    short = _main(
        alice={
            "hand": ["Grizzly Bears"],
            "graveyard": ["Lightning Bolt"],
            "battlefield": ["Conspiracy Unraveler"],
        }
    )
    (option,) = _static_options(short, "Grizzly Bears")
    assert option.cost is not None and "collect evidence 10" in str(option.cost)


def test_as_foretold_caps_the_free_spell_by_its_time_counters():
    scenario = _main(
        alice={
            "hand": ["Grizzly Bears", "Serra Angel"],
            "battlefield": ["As Foretold"],
        }
    )
    foretold = scenario.find("As Foretold", Zone.BATTLEFIELD, "alice")
    foretold.add_counters(Counter.TIME, 2)
    (small,) = _static_options(scenario, "Grizzly Bears")
    assert small.available
    (big,) = _static_options(scenario, "Serra Angel")
    assert not big.available
    foretold.add_counters(Counter.TIME, 3)
    (big,) = _static_options(scenario, "Serra Angel")
    assert big.available


def test_charred_foyer_applies_only_to_spells_cast_from_exile():
    scenario = _main(
        alice={
            "hand": ["Grizzly Bears"],
            "exile": ["Lightning Bolt"],
            "battlefield": ["Charred Foyer // Warped Space"],
        }
    )
    room = next(
        s for s in scenario.game.permanents_controlled_by("alice") if "Foyer" in s.card.name
    )
    scenario.game.unlock_door(room, "Warped Space")
    (from_exile,) = [
        option
        for option in _static_options(scenario, "Lightning Bolt", zone=Zone.EXILE)
        if option.source_name.startswith("Charred")
    ]
    assert from_exile.available
    (from_hand,) = _static_options(scenario, "Grizzly Bears")
    assert not from_hand.available


def test_primal_prayers_charges_one_energy_for_small_creature_spells_only():
    scenario = _main(
        alice={
            "hand": ["Grizzly Bears", "Serra Angel", "Lightning Bolt"],
            "battlefield": ["Primal Prayers"],
        }
    )
    scenario.game.add_player_counters("alice", "energy", 2)
    (small,) = _static_options(scenario, "Grizzly Bears")
    assert small.available and small.description == "{E}"
    (big,) = _static_options(scenario, "Serra Angel")
    assert not big.available
    (bolt,) = _static_options(scenario, "Lightning Bolt")
    assert not bolt.available


def test_primal_prayers_pays_energy_and_grants_flash_only_with_that_cost():
    scenario = _main(
        alice={
            "hand": ["Grizzly Bears", "Grizzly Bears"],
            "battlefield": ["Primal Prayers", "Forest", "Forest"],
        },
        bob={},
    )
    scenario.game.add_player_counters("alice", "energy", 2)
    scenario.game.turn.active_index = 1  # bob's turn: only flash could allow it
    casting = scenario.cast("Grizzly Bears", "alice")
    casting.use_alternative_cost("Primal Prayers")
    scenario.game.determine_total_cost(casting)
    payment = casting.begin_paying()
    payment.pay()
    casting.cast()
    assert scenario.game.player("alice").energy == 1

    plain = scenario.cast("Grizzly Bears", "alice")
    scenario.game.determine_total_cost(plain)
    plain_payment = plain.begin_paying()
    plain_payment.auto_tap(scenario.game.permanents_controlled_by("alice"))
    plain_payment.pay()
    try:
        plain.cast()
    except ValueError as refusal:
        assert "flash" in str(refusal)
    else:
        raise AssertionError("a creature spell cast normally on the opponent's turn needs flash")


def test_kentaro_style_mana_value_cost_is_read_from_the_spell():
    from magic_cards_model.machines.casting import static_grant_option
    from magic_cards_model.machines.cost.text import static_free_cast_grant

    grant = static_free_cast_grant(
        "You may pay {X} rather than pay the mana cost for Samurai spells you cast, "
        "where X is that spell's mana value."
    )
    assert grant is not None and grant.cost_is_mana_value
    scenario = _main(alice={"hand": ["Serra Angel", "Grizzly Bears"]})
    angel = scenario.find("Serra Angel", Zone.HAND, "alice")
    option = static_grant_option(0, "Kentaro", grant, scenario.game, "alice", angel, Zone.HAND)
    assert not option.available  # Serra Angel is not a Samurai
    assert str(option.cost) == "{5}"


def test_thick_skinned_goblin_lets_echo_be_paid_with_zero():
    from magic_cards_model.machines.decisions import DecisionKind

    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Mountain"] * 4 + ["Thick-Skinned Goblin"],
            hand=["Flamecore Elemental"],
            library=["Mountain"] * 10,
        )
        .player("bob", library=["Mountain"] * 10)
        .build()
    )
    scenario.start_at(Step.UNTAP)
    flamecore = scenario.put_onto_battlefield("Flamecore Elemental")
    scenario.will_pay_the_mana_cost(True, username="alice", source="Flamecore Elemental")
    scenario.advance()
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()
    asked = [
        q
        for q in scenario.questions_asked()
        if q.kind is DecisionKind.PAY_MANA and q.source == "Flamecore Elemental"
    ]
    assert [q.amount for q in asked] == [0]
    assert flamecore.zone is Zone.BATTLEFIELD
    assert not any(p.tapped for p in scenario.game.battlefield if p.name == "Mountain")
