"""EP-01 round 2, task T7: cost modification and mana-spending statics left over
from round 1 (CR 601.2f, 118.7, 106.6, 609.4b).

    Arachne, Psionic Weaver  - Spells of the chosen type cost {1} more to cast.
    Anointed Peacekeeper     - Spells your opponents cast with the chosen name cost {2} more.
    Bard Class               - Legendary spells you cast cost {R}{G} less ... only coloured mana.
    The Balrog, Durin's Bane - costs {1} less for each permanent sacrificed this turn.
    Wildvine Pummeler        - Vivid: costs {1} less for each colour among your permanents.
    Vizier of the Menagerie  - You can spend mana of any type to cast creature spells.
    Imperiosaur / Myr Superion - Spend only mana produced by basic lands / creatures.

Every case is a real cast through the engine; each has a spell, a player or a
source the line does NOT reach.
"""

import pytest

from magic_cards_model.machines import Step, payability
from magic_cards_model.models import Color, Zone
from magic_cards_model.models.card_state import Choice, ChoiceKind
from magic_cards_model.models.mana import ManaCost, ManaPool, ManaSpend, SpendPurpose
from tests.scenarios.harness import Scenario


def _main(**players) -> Scenario:
    builder = Scenario().manual_turn_based_actions()
    for username, kwargs in players.items():
        builder = builder.player(username, **kwargs)
    scenario = builder.build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _cost(scenario, name, *, targets=None, username="alice", from_zone=Zone.HAND) -> str:
    casting = scenario.cast(name, username, from_zone=from_zone, targets=targets)
    scenario.game.determine_total_cost(casting)
    mana = str(casting.total_cost.mana)
    casting.cancel()
    return mana


def _can_pay(scenario, name, username="alice") -> bool:
    return payability(scenario.game, username, scenario.find(name, Zone.HAND, username)).payable


def _choose(scenario, name, owner, kind, value) -> None:
    scenario.find(name, Zone.BATTLEFIELD, owner).choice = Choice(kind=kind, value=value)


# -- Arachne: spells of the chosen card type cost {1} more (all players) --------


def test_arachne_taxes_every_players_spell_of_the_chosen_type():
    scenario = _main(
        alice={"hand": ["Lightning Bolt"], "battlefield": ["Arachne, Psionic Weaver"]},
        bob={"hand": ["Lightning Helix"]},
    )
    _choose(scenario, "Arachne, Psionic Weaver", "alice", ChoiceKind.CARD_TYPE, "instant")
    assert _cost(scenario, "Lightning Bolt", targets=["bob"]) == "{1}{R}"
    assert _cost(scenario, "Lightning Helix", username="bob", targets=["alice"]) == "{1}{R}{W}"


def test_arachne_does_not_tax_a_spell_of_another_type():
    scenario = _main(
        alice={"hand": ["Grizzly Bears", "Divination"], "battlefield": ["Arachne, Psionic Weaver"]},
    )
    _choose(scenario, "Arachne, Psionic Weaver", "alice", ChoiceKind.CARD_TYPE, "instant")
    assert _cost(scenario, "Grizzly Bears") == "{1}{G}"
    assert _cost(scenario, "Divination") == "{2}{U}"


def test_arachne_taxes_nothing_before_a_type_is_chosen():
    scenario = _main(
        alice={"hand": ["Lightning Bolt"], "battlefield": ["Arachne, Psionic Weaver"]},
    )
    assert _cost(scenario, "Lightning Bolt", targets=["alice"]) == "{R}"


# -- Anointed Peacekeeper: opponents' spells with the chosen name cost {2} more ---


def test_anointed_peacekeeper_taxes_an_opponents_spell_with_the_chosen_name():
    scenario = _main(
        alice={"hand": ["Lightning Bolt"]},
        bob={"battlefield": ["Anointed Peacekeeper"]},
    )
    _choose(scenario, "Anointed Peacekeeper", "bob", ChoiceKind.CARD_NAME, "Lightning Bolt")
    assert _cost(scenario, "Lightning Bolt", targets=["bob"]) == "{2}{R}"


def test_anointed_peacekeeper_does_not_tax_its_controllers_own_copy():
    scenario = _main(
        alice={"hand": ["Lightning Bolt"], "battlefield": ["Anointed Peacekeeper"]},
    )
    _choose(scenario, "Anointed Peacekeeper", "alice", ChoiceKind.CARD_NAME, "Lightning Bolt")
    assert _cost(scenario, "Lightning Bolt", targets=["alice"]) == "{R}"


def test_anointed_peacekeeper_does_not_tax_a_differently_named_spell():
    scenario = _main(
        alice={"hand": ["Lightning Helix"]},
        bob={"battlefield": ["Anointed Peacekeeper"]},
    )
    _choose(scenario, "Anointed Peacekeeper", "bob", ChoiceKind.CARD_NAME, "Lightning Bolt")
    assert _cost(scenario, "Lightning Helix", targets=["bob"]) == "{R}{W}"


# -- Bard Class: legendary spells cost {R}{G} less, coloured mana only -----------


def test_bard_class_level_two_takes_red_and_green_off_a_legendary_spell():
    scenario = _main(
        alice={
            "hand": ["Aerid Konstrari", "Agatha of the Vile Cauldron"],
            "battlefield": ["Bard Class"],
        },
    )
    scenario.find("Bard Class", Zone.BATTLEFIELD, "alice").class_level = 2
    assert _cost(scenario, "Aerid Konstrari") == "{1}{G}"
    assert _cost(scenario, "Agatha of the Vile Cauldron") == ""


def test_bard_class_never_reduces_generic_mana():
    """ "This effect reduces only the amount of colored mana you pay" (CR 118.7a)."""
    scenario = _main(
        alice={
            "hand": ["Ardoz, Cobbler of War", "Akroma's Memorial"],
            "battlefield": ["Bard Class"],
        },
    )
    scenario.find("Bard Class", Zone.BATTLEFIELD, "alice").class_level = 2
    assert _cost(scenario, "Ardoz, Cobbler of War") == "{1}"
    assert _cost(scenario, "Akroma's Memorial") == "{7}"


def test_bard_class_ignores_a_nonlegendary_spell_and_level_one():
    scenario = _main(
        alice={
            "hand": ["Grizzly Bears", "Agatha of the Vile Cauldron"],
            "battlefield": ["Bard Class"],
        },
    )
    bard = scenario.find("Bard Class", Zone.BATTLEFIELD, "alice")
    assert bard.class_level == 1
    assert _cost(scenario, "Agatha of the Vile Cauldron") == "{R}{G}"
    bard.class_level = 2
    assert _cost(scenario, "Grizzly Bears") == "{1}{G}"


def test_bard_class_discounts_only_its_controllers_spells():
    scenario = _main(
        alice={"hand": ["Agatha of the Vile Cauldron"]},
        bob={"battlefield": ["Bard Class"]},
    )
    scenario.find("Bard Class", Zone.BATTLEFIELD, "bob").class_level = 2
    assert _cost(scenario, "Agatha of the Vile Cauldron") == "{R}{G}"


# -- The Balrog: {1} less for each permanent sacrificed this turn ---------------


def test_the_balrog_costs_one_less_per_permanent_sacrificed_this_turn():
    scenario = _main(
        alice={
            "hand": ["The Balrog, Durin's Bane"],
            "battlefield": ["Grizzly Bears", "Llanowar Elves"],
        },
        bob={"battlefield": ["Grizzly Bears"]},
    )
    assert _cost(scenario, "The Balrog, Durin's Bane") == "{5}{B}{R}"
    scenario.game.sacrifice(scenario.creature("Grizzly Bears", "alice"))
    assert _cost(scenario, "The Balrog, Durin's Bane") == "{4}{B}{R}"
    scenario.game.sacrifice(scenario.creature("Grizzly Bears", "bob"))
    assert _cost(scenario, "The Balrog, Durin's Bane") == "{3}{B}{R}"


def test_the_balrog_does_not_count_a_permanent_that_merely_died():
    scenario = _main(
        alice={"hand": ["The Balrog, Durin's Bane"], "battlefield": ["Grizzly Bears"]},
    )
    scenario.game.destroy(scenario.creature("Grizzly Bears", "alice"))
    assert _cost(scenario, "The Balrog, Durin's Bane") == "{5}{B}{R}"


# -- Wildvine Pummeler: Vivid ---------------------------------------------------


def test_wildvine_pummeler_costs_one_less_per_colour_among_your_permanents():
    scenario = _main(
        alice={
            "hand": ["Wildvine Pummeler"],
            "battlefield": ["Grizzly Bears", "Serra Angel", "Forest", "Shivan Dragon"],
        },
        bob={"battlefield": ["Counterspell"]},
    )
    assert _cost(scenario, "Wildvine Pummeler") == "{3}{G}"


def test_wildvine_pummeler_ignores_colourless_permanents_and_opponents():
    scenario = _main(
        alice={"hand": ["Wildvine Pummeler"], "battlefield": ["Sol Ring", "Forest"]},
        bob={"battlefield": ["Serra Angel"]},
    )
    assert _cost(scenario, "Wildvine Pummeler") == "{6}{G}"


# -- Vizier of the Menagerie: mana of any type for creature spells --------------


def test_vizier_lets_any_mana_pay_for_a_creature_spell():
    scenario = _main(
        alice={
            "hand": ["Grizzly Bears", "Lightning Bolt"],
            "battlefield": ["Vizier of the Menagerie", "Island", "Island"],
        },
    )
    assert _can_pay(scenario, "Grizzly Bears")
    assert not _can_pay(scenario, "Lightning Bolt")


def test_vizier_does_not_help_the_opponent():
    scenario = _main(
        alice={"battlefield": ["Vizier of the Menagerie"]},
        bob={"hand": ["Grizzly Bears"], "battlefield": ["Island", "Island"]},
    )
    assert not _can_pay(scenario, "Grizzly Bears", "bob")


def test_without_vizier_an_island_cannot_pay_a_green_symbol():
    scenario = _main(alice={"hand": ["Grizzly Bears"], "battlefield": ["Island", "Island"]})
    assert not _can_pay(scenario, "Grizzly Bears")


# -- Imperiosaur / Myr Superion: spend only mana produced by ... ----------------


def test_imperiosaur_is_paid_with_basic_land_mana():
    scenario = _main(
        alice={"hand": ["Imperiosaur"], "battlefield": ["Forest", "Forest", "Forest", "Forest"]},
    )
    assert _can_pay(scenario, "Imperiosaur")


def test_imperiosaur_cannot_be_paid_with_a_nonbasic_land_or_an_artifact():
    scenario = _main(
        alice={
            "hand": ["Imperiosaur"],
            "battlefield": ["Forest", "Forest", "Sol Ring"],
        },
    )
    assert not _can_pay(scenario, "Imperiosaur")
    scenario = _main(
        alice={
            "hand": ["Imperiosaur"],
            "battlefield": ["Forest", "Forest", "Breeding Pool", "Breeding Pool"],
        },
    )
    assert not _can_pay(scenario, "Imperiosaur")


def test_imperiosaur_can_be_paid_with_snow_covered_basics():
    scenario = _main(
        alice={"hand": ["Imperiosaur"], "battlefield": ["Snow-Covered Forest"] * 4},
    )
    assert _can_pay(scenario, "Imperiosaur")


def test_imperiosaur_cast_refuses_a_tap_of_a_nonbasic_source():
    scenario = _main(
        alice={
            "hand": ["Imperiosaur"],
            "battlefield": ["Forest", "Forest", "Breeding Pool", "Breeding Pool"],
        },
    )
    casting = scenario.cast("Imperiosaur")
    payment = casting.begin_paying()
    pool_source = scenario.untapped_sources("Breeding Pool")[0]
    with pytest.raises(ValueError, match="basic land"):
        payment.tap_for_mana(pool_source, [Color.GREEN])


def test_imperiosaur_auto_payment_leaves_the_nonbasic_untapped():
    scenario = _main(
        alice={
            "hand": ["Imperiosaur"],
            "battlefield": ["Forest", "Forest", "Forest", "Forest", "Breeding Pool"],
        },
    )
    scenario.cast_onto_stack("Imperiosaur", username="alice", auto=True)
    assert "Imperiosaur" in scenario.stack_names()
    (pool,) = scenario.untapped_sources("Breeding Pool")
    assert not pool.tapped


def test_a_spell_without_the_restriction_is_paid_with_any_source():
    scenario = _main(
        alice={"hand": ["Grizzly Bears"], "battlefield": ["Forest", "Sol Ring"]},
    )
    assert _can_pay(scenario, "Grizzly Bears")


def test_myr_superion_is_paid_with_creature_mana_only():
    scenario = _main(
        alice={"hand": ["Myr Superion"], "battlefield": ["Llanowar Elves", "Birds of Paradise"]},
    )
    assert _can_pay(scenario, "Myr Superion")
    scenario = _main(
        alice={"hand": ["Myr Superion"], "battlefield": ["Llanowar Elves", "Forest", "Sol Ring"]},
    )
    assert not _can_pay(scenario, "Myr Superion")


def test_a_pool_only_spends_the_mana_the_restriction_allows():
    """The restriction is on the cost, not the mana (CR 106.6 / 609.4b): floating
    mana that a basic land did not produce is simply unavailable to Imperiosaur."""
    pool = ManaPool()
    pool.add(Color.GREEN, 2, basic_land=True)
    pool.add(Color.GREEN, 2)
    cost = ManaCost.parse("{2}{G}{G}")
    only_basic = ManaSpend(purpose=SpendPurpose.CAST_SPELL, only_from="basic_land")
    assert pool.payment_for(cost, spend=only_basic) is None
    pool.add(Color.GREEN, 2, basic_land=True)
    assert pool.payment_for(cost, spend=only_basic) is not None


# -- Weftwalking: the first spell each player casts on their turn may be free ----


def _free_option(casting):
    (option,) = [o for o in casting.alternative_costs if o.source_name == "Weftwalking"]
    return option


def _weftwalking_board():
    return _main(
        alice={
            "hand": ["Grizzly Bears", "Lightning Bolt"],
            "library": ["Island"] * 5,
            "battlefield": ["Mountain", "Forest", "Mountain"],
        },
        bob={
            "hand": ["Grizzly Bears"],
            "library": ["Island"] * 5,
            "battlefield": ["Forest", "Weftwalking"],
        },
    )


def test_weftwalking_makes_the_first_spell_of_its_casters_turn_free_even_for_an_opponent():
    scenario = _weftwalking_board()
    casting = scenario.cast("Grizzly Bears")
    assert _free_option(casting).unavailable is None
    casting.cancel()


def test_weftwalking_does_not_make_the_second_spell_free():
    scenario = _weftwalking_board()
    (forest,) = scenario.untapped_sources("Forest")
    scenario.cast_and_resolve("Grizzly Bears", forest, scenario.untapped_sources("Mountain")[0])
    casting = scenario.cast("Lightning Bolt", targets=["bob"])
    option = _free_option(casting)
    assert option.unavailable is not None and "first spell" in option.unavailable
    casting.cancel()


def test_weftwalking_reaches_each_player_on_their_own_turn_only():
    scenario = _weftwalking_board()
    scenario.start_at(Step.CLEANUP)
    while scenario.turn.active_player != "bob" or scenario.step is not Step.PRECOMBAT_MAIN:
        scenario.advance()
    free = scenario.cast("Grizzly Bears", username="bob")
    assert _free_option(free).unavailable is None
    free.cancel()
    off_turn = scenario.cast("Lightning Bolt", username="alice", targets=["bob"])
    option = _free_option(off_turn)
    assert option.unavailable is not None and "turn" in option.unavailable
    off_turn.cancel()
