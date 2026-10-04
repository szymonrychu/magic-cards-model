"""Empower Jace, CR 701.71 - the ten Reality Fracture cards whose whole text
rides on it, each proven on its real `set:fra` printing (fixtures refreshed
with `scripts/add_card.py`; the Scryfall printing now carries the keyword
"Empower Jace" and is legal in Standard).

CR 701.71a (read with `mise run rules:find 701.71`): "To empower Jace N means
'If you don't control a Jace planeswalker token, create a blue Jace
planeswalker token with 0 loyalty, "[-1]: Surveil 1," and "[-3]: Draw a
card." Choose a Jace planeswalker token you control. Put N loyalty counters
on it.'" Loyalty is counters (CR 306.5c); a planeswalker with 0 loyalty goes
to the graveyard as a state-based action (CR 704.5i); excess damage is CR
120.10. No Modern/Pioneer/Standard printing outside this round's FRA cards
has "empower Jace", so there is no off-set proof printing.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import has_keyword
from magic_cards_model.models import CardState, Zone
from magic_cards_model.models.card_state import Counter
from magic_cards_model.models.token import PREDEFINED, create_tokens

from .harness import Scenario


def _jace_tokens(scenario: Scenario, username: str = "alice") -> list[CardState]:
    return [
        permanent
        for permanent in scenario.game.battlefield
        if permanent.name == "Jace" and permanent.controller == username
    ]


def _jace_token(scenario: Scenario, username: str = "alice") -> CardState:
    (token,) = _jace_tokens(scenario, username)
    return token


def _cast_with_targets(scenario: Scenario, name: str, targets, *sources, modes=None):
    casting = scenario.cast(name, username="alice")
    if modes is not None:
        casting.choose_modes(modes)
    if targets is not None:
        casting.choose_targets(targets)
    payment = casting.begin_paying()
    scenario.pay_with(payment, *sources)
    scenario.put_on_stack(casting)
    return casting


# -- Protege's Awakening: empower 6, then draw; the shared token rules ---------


def test_protege_awakening_creates_the_token_with_six_loyalty_then_draws():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Protege's Awakening"],
            library=["Forest"] * 3,
            battlefield=["Island"] * 4,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    hand_before = len(scenario.player("alice").hand)
    sources = scenario.untapped_sources(*["Island"] * 4)

    scenario.cast_and_resolve("Protege's Awakening", *sources)

    jace = _jace_token(scenario)
    assert jace.loyalty == 6, "CR 701.71a: 0 loyalty plus six counters (CR 306.5c)"
    assert jace.counter_count(Counter.LOYALTY) == 6
    assert jace.card.name == "Jace"
    assert "Jace" in jace.subtypes
    assert "planeswalker" in jace.card.type_line.lower()
    assert len(scenario.player("alice").hand) == hand_before - 1 + 1, "cast one, drew one"


def test_an_existing_token_gets_the_counters_and_no_second_token_is_made():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Protege's Awakening"],
            library=["Forest"] * 3,
            battlefield=["Island"] * 4,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (existing,) = create_tokens(scenario.game, PREDEFINED["Jace"], "alice", count=1)
    scenario.game.add_counters(existing, Counter.LOYALTY, 2)
    sources = scenario.untapped_sources(*["Island"] * 4)

    scenario.cast_and_resolve("Protege's Awakening", *sources)

    assert _jace_tokens(scenario) == [existing]
    assert existing.loyalty == 8


def test_a_nontoken_jace_planeswalker_does_not_count_as_the_token():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Protege's Awakening"],
            library=["Forest"] * 3,
            battlefield=["Jace, Reality Sculptor"] + ["Island"] * 4,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sculptor = scenario.creature("Jace, Reality Sculptor", "alice")
    sources = scenario.untapped_sources(*["Island"] * 4)

    scenario.cast_and_resolve("Protege's Awakening", *sources)

    assert sculptor.loyalty == 5, "the real planeswalker is untouched"
    assert _jace_token(scenario).loyalty == 6, "a token was created anyway"


def test_two_jace_tokens_the_controller_chooses_which_gets_the_counters():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Protege's Awakening"],
            library=["Forest"] * 3,
            battlefield=["Island"] * 4,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    first, second = create_tokens(scenario.game, PREDEFINED["Jace"], "alice", count=2)
    scenario.game.add_counters(first, Counter.LOYALTY, 1)
    scenario.game.add_counters(second, Counter.LOYALTY, 2)
    scenario.will_choose_cards(first, source="Protege's Awakening")
    sources = scenario.untapped_sources(*["Island"] * 4)

    scenario.cast_and_resolve("Protege's Awakening", *sources)

    assert first.loyalty == 7, "chosen: 1 + 6"
    assert second.loyalty == 2, "not chosen, untouched"


def test_the_tokens_minus_one_surveils_one():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Protege's Awakening"],
            library=["Forest", "Mountain", "Swamp"],
            battlefield=["Island"] * 4,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources(*["Island"] * 4)
    scenario.cast_and_resolve("Protege's Awakening", *sources)
    jace = _jace_token(scenario)
    top = scenario.top_of_library(1)[0]
    scenario.surveil_to_graveyard(top)

    scenario.activate(jace, index=0)  # "[-1]: Surveil 1"
    scenario.pass_until_resolved()

    assert jace.loyalty == 5
    assert top.zone is Zone.GRAVEYARD, "CR 701.25a: surveilled into the graveyard"


def test_the_tokens_minus_three_draws_and_zero_loyalty_is_a_state_based_action():
    scenario = (
        Scenario()
        .player("alice", library=["Forest"] * 5, battlefield=["Island"] * 4)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (jace,) = create_tokens(scenario.game, PREDEFINED["Jace"], "alice", count=1)
    scenario.game.add_counters(jace, Counter.LOYALTY, 3)
    library_before = len(scenario.player("alice").library)

    scenario.activate(jace, index=1)  # "[-3]: Draw a card."
    scenario.pass_until_resolved()
    scenario.state_based_actions()

    assert len(scenario.player("alice").library) == library_before - 1
    assert jace not in scenario.game.battlefield, "CR 704.5i: 0 loyalty, put into the graveyard"
    assert _jace_tokens(scenario) == []


# -- Repurposed Enforcer: X at resolution --------------------------------------


def test_repurposed_enforcer_counts_creatures_at_resolution_not_at_attack():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Repurposed Enforcer", "Grizzly Bears"],
            hand=["Grizzly Bears"],
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    enforcer = scenario.creature("Repurposed Enforcer", "alice")

    scenario.attack_with(enforcer)
    scenario.game.put_triggers_on_stack()
    assert scenario.game.stack, "the attack trigger is on the stack"
    scenario.put_onto_battlefield("Grizzly Bears")  # a third creature arrives in response
    scenario.pass_until_resolved()

    assert _jace_token(scenario).loyalty == 3, "X computed at resolution: 3 creatures"


def test_repurposed_enforcer_reuses_an_existing_token():
    scenario = Scenario().player("alice", battlefield=["Repurposed Enforcer"]).player("bob").build()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    (existing,) = create_tokens(scenario.game, PREDEFINED["Jace"], "alice", count=1)
    scenario.game.add_counters(existing, Counter.LOYALTY, 4)
    enforcer = scenario.creature("Repurposed Enforcer", "alice")

    scenario.attack_with(enforcer)
    scenario.pass_until_resolved()

    assert _jace_tokens(scenario) == [existing]
    assert existing.loyalty == 5


# -- Plan for All Outcomes ------------------------------------------------------


def test_plan_for_all_outcomes_etb_puts_the_permanent_on_top_of_its_owners_library():
    scenario = (
        Scenario()
        .player("alice", hand=["Plan for All Outcomes"], battlefield=["Island"] * 4)
        .player("bob", battlefield=["Grizzly Bears"], library=["Forest"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    sources = scenario.untapped_sources(*["Island"] * 4)

    scenario.will_choose_targets(bears, username="alice")
    scenario.will_choose_top(True, source="Plan for All Outcomes")
    scenario.cast_and_resolve("Plan for All Outcomes", *sources)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert bears.zone is Zone.LIBRARY
    assert scenario.player("bob").library[0] is bears, "chose the top"


def test_plan_for_all_outcomes_etb_with_zero_targets_is_legal():
    scenario = (
        Scenario()
        .player("alice", hand=["Plan for All Outcomes"], battlefield=["Island"] * 4)
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    sources = scenario.untapped_sources(*["Island"] * 4)

    scenario.will_choose_targets(username="alice")
    scenario.cast_and_resolve("Plan for All Outcomes", *sources)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert bears.zone is Zone.BATTLEFIELD


def test_plan_for_all_outcomes_empowers_on_the_first_noncreature_spell_each_turn_only():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Grizzly Bears", "Lightning Bolt", "Lightning Bolt"],
            battlefield=[
                "Plan for All Outcomes",
                "Mountain",
                "Mountain",
                "Mountain",
                "Forest",
                "Forest",
            ],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    # A creature spell is not a noncreature spell: no trigger.
    scenario.cast_and_resolve("Grizzly Bears", *scenario.untapped_sources("Forest", "Forest"))
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()
    assert _jace_tokens(scenario) == []

    # The first noncreature spell: the trigger resolves, empower Jace 1.
    scenario.cast_and_resolve(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=["bob"]
    )
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()
    assert _jace_token(scenario).loyalty == 1

    # The second noncreature spell the same turn does not trigger it again.
    scenario.cast_and_resolve(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=["bob"]
    )
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()
    assert _jace_token(scenario).loyalty == 1


# -- Rewrite Regrets ------------------------------------------------------------


def test_rewrite_regrets_returns_a_creature_then_empowers_two():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Rewrite Regrets"],
            battlefield=["Swamp"] * 4,
            graveyard=["Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")
    sources = scenario.untapped_sources(*["Swamp"] * 4)

    _cast_with_targets(scenario, "Rewrite Regrets", [bears], *sources)
    scenario.resolve_top()

    assert bears.zone is Zone.BATTLEFIELD
    assert _jace_token(scenario).loyalty == 2


def test_rewrite_regrets_returns_a_planeswalker_card_and_the_nontoken_jace_is_not_the_token():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Rewrite Regrets"],
            battlefield=["Swamp"] * 4,
            graveyard=["Jace, Reality Sculptor"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sculptor = scenario.find("Jace, Reality Sculptor", Zone.GRAVEYARD, "alice")
    sources = scenario.untapped_sources(*["Swamp"] * 4)

    _cast_with_targets(scenario, "Rewrite Regrets", [sculptor], *sources)
    scenario.resolve_top()

    assert sculptor.zone is Zone.BATTLEFIELD
    assert sculptor.loyalty == 5, "CR 306.5b: enters with its printed loyalty, untouched"
    assert _jace_token(scenario).loyalty == 2


def test_rewrite_regrets_cannot_target_mana_value_seven():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Rewrite Regrets"],
            battlefield=["Swamp"] * 4,
            graveyard=["Ulamog, the Ceaseless Hunger"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    hulk = scenario.find("Ulamog, the Ceaseless Hunger", Zone.GRAVEYARD, "alice")

    casting = scenario.cast("Rewrite Regrets", username="alice")
    with pytest.raises(ValueError, match="(?i)mana value|target"):
        casting.choose_targets([hulk])


def test_rewrite_regrets_whose_only_target_left_the_graveyard_does_nothing():
    """CR 608.2b: the sole target is illegal on resolution, so the spell does
    not resolve at all - the empower clause does not run either."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Rewrite Regrets"],
            battlefield=["Swamp"] * 4,
            graveyard=["Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")
    sources = scenario.untapped_sources(*["Swamp"] * 4)
    _cast_with_targets(scenario, "Rewrite Regrets", [bears], *sources)
    scenario.game.exile_cards([bears])

    scenario.resolve_top()

    assert _jace_tokens(scenario) == []
    assert bears.zone is Zone.EXILE


# -- Solve for Disappointment ---------------------------------------------------


def test_solve_for_disappointment_discards_the_chosen_nonland_permanent_and_empowers_one():
    scenario = (
        Scenario()
        .player("alice", hand=["Solve for Disappointment"], battlefield=["Swamp", "Swamp"])
        .player("bob", hand=["Grizzly Bears", "Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.HAND, "bob")
    mountain = scenario.find("Mountain", Zone.HAND, "bob")
    sources = scenario.untapped_sources("Swamp", "Swamp")

    _cast_with_targets(scenario, "Solve for Disappointment", ["bob"], *sources)
    scenario.will_choose_cards(bears, username="alice")
    scenario.resolve_top()

    assert bears.zone is Zone.GRAVEYARD
    assert mountain.zone is Zone.HAND
    assert _jace_token(scenario).loyalty == 1


def test_solve_for_disappointment_empowers_even_with_no_nonland_permanent_card():
    scenario = (
        Scenario()
        .player("alice", hand=["Solve for Disappointment"], battlefield=["Swamp", "Swamp"])
        .player("bob", hand=["Mountain", "Lightning Bolt"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Swamp", "Swamp")

    _cast_with_targets(scenario, "Solve for Disappointment", ["bob"], *sources)
    scenario.resolve_top()

    assert len(scenario.player("bob").hand) == 2, "nothing was discardable"
    assert _jace_token(scenario).loyalty == 1


# -- Tam's Resistance -----------------------------------------------------------


def test_tams_resistance_pumps_the_target_and_empowers_four():
    scenario = (
        Scenario()
        .player(
            "alice", hand=["Tam's Resistance"], battlefield=["Island", "Island", "Grizzly Bears"]
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bear = scenario.creature("Grizzly Bears", "alice")
    sources = scenario.untapped_sources("Island", "Island")

    scenario.cast_and_resolve("Tam's Resistance", *sources, targets=[bear])

    assert bear.counter_count(Counter.PLUS_ONE) == 1
    assert has_keyword(bear, "vigilance", scenario.game)
    assert _jace_token(scenario).loyalty == 4


def test_tams_resistance_with_zero_targets_still_empowers():
    scenario = (
        Scenario()
        .player(
            "alice", hand=["Tam's Resistance"], battlefield=["Island", "Island", "Grizzly Bears"]
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bear = scenario.creature("Grizzly Bears", "alice")
    sources = scenario.untapped_sources("Island", "Island")

    scenario.cast_and_resolve("Tam's Resistance", *sources, targets=[])

    assert bear.counter_count(Counter.PLUS_ONE) == 0
    assert _jace_token(scenario).loyalty == 4


# -- Theorist's Proxy -----------------------------------------------------------


def test_theorists_proxy_has_flash_and_empowers_three_on_entering():
    scenario = (
        Scenario()
        .player("alice", hand=["Theorist's Proxy"], battlefield=["Island", "Island"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    # Flash: castable with a nonempty stack / in the opponent's turn window.
    proxy = scenario.find("Theorist's Proxy", Zone.HAND, "alice")
    assert has_keyword(proxy, "flash", scenario.game)
    sources = scenario.untapped_sources("Island", "Island")

    scenario.cast_and_resolve("Theorist's Proxy", *sources)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert _jace_token(scenario).loyalty == 3


def test_theorists_proxy_sacrifice_ability_still_works_after_empowering():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Bolt"],
            battlefield=["Theorist's Proxy", "Island", "Mountain"],
        )
        .player("bob", hand=["Counterspell"], battlefield=["Island", "Island"], life=20)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    proxy = scenario.creature("Theorist's Proxy", "alice")
    (blue,) = scenario.untapped_sources("Island", username="alice")

    scenario.activate(proxy, blue, sacrificing=[proxy])
    while scenario.game.stack:
        scenario.resolve_top()
    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    bolt = scenario.cast_onto_stack("Lightning Bolt", mountain, username="alice", targets=["bob"])
    while scenario.game.stack and scenario.game.stack[-1] is not bolt:
        scenario.resolve_top()
    scenario.pass_priority("alice")
    counters = scenario.untapped_sources("Island", "Island", username="bob")
    scenario.cast_onto_stack("Counterspell", *counters, username="bob", targets=[bolt])
    while scenario.game.stack:
        scenario.resolve_top()

    assert scenario.player("bob").life == 17, "the Bolt could not be countered"


# -- Theorist's Sanctum ---------------------------------------------------------


def test_theorists_sanctum_is_an_island_that_taps_for_blue():
    scenario = Scenario().player("alice", battlefield=["Theorist's Sanctum"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sanctum = scenario.find("Theorist's Sanctum", Zone.BATTLEFIELD, "alice")

    assert "Island" in sanctum.subtypes
    assert "Land" in sanctum.card.type_line


def test_theorists_sanctum_enters_untapped_when_beholding_a_jace_token():
    scenario = Scenario().player("alice", hand=["Theorist's Sanctum"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (token,) = create_tokens(scenario.game, PREDEFINED["Jace"], "alice", count=1)
    scenario.will_take_the_may(True, source="Theorist's Sanctum")
    scenario.will_choose_cards(token, username="alice", source="Theorist's Sanctum")

    sanctum = scenario.play_land("Theorist's Sanctum")

    assert not sanctum.tapped


def test_theorists_sanctum_enters_tapped_without_a_jace():
    scenario = Scenario().player("alice", hand=["Theorist's Sanctum"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    assert scenario.play_land("Theorist's Sanctum").tapped


def test_theorists_sanctum_ability_empowers_two():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Theorist's Sanctum", "Island", "Island", "Island"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sanctum = scenario.find("Theorist's Sanctum", Zone.BATTLEFIELD, "alice")
    sources = scenario.untapped_sources("Island", "Island", "Island")

    scenario.activate(sanctum, *sources, index=0)
    scenario.pass_until_resolved()

    assert sanctum.tapped
    assert _jace_token(scenario).loyalty == 2


# -- Violent Echoes -------------------------------------------------------------


def test_violent_echoes_empowers_the_excess_over_lethal_on_a_creature():
    scenario = (
        Scenario()
        .player("alice", hand=["Violent Echoes"], battlefield=["Mountain"] * 4)
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bear = scenario.creature("Grizzly Bears", "bob")
    sources = scenario.untapped_sources(*["Mountain"] * 4)

    scenario.cast_and_resolve("Violent Echoes", *sources, targets=[bear])

    assert bear.zone is Zone.GRAVEYARD
    assert _jace_token(scenario).loyalty == 4, "CR 120.10: 6 - lethal 2"


def test_violent_echoes_planeswalker_excess_is_damage_beyond_its_loyalty():
    scenario = (
        Scenario()
        .player("alice", hand=["Violent Echoes"], battlefield=["Mountain"] * 4)
        .player("bob", battlefield=["Jace, Reality Sculptor"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    walker = scenario.creature("Jace, Reality Sculptor", "bob")
    sources = scenario.untapped_sources(*["Mountain"] * 4)

    scenario.cast_and_resolve("Violent Echoes", *sources, targets=[walker])

    assert walker.zone is Zone.GRAVEYARD
    assert _jace_token(scenario).loyalty == 1, "6 damage vs 5 loyalty"


def test_violent_echoes_without_excess_makes_no_token():
    scenario = (
        Scenario()
        .player("alice", hand=["Violent Echoes"], battlefield=["Mountain"] * 4)
        .player("bob", battlefield=["Slumbering Trudge"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    trudge = scenario.creature("Slumbering Trudge", "bob")
    sources = scenario.untapped_sources(*["Mountain"] * 4)

    scenario.cast_and_resolve("Violent Echoes", *sources, targets=[trudge])

    assert trudge.zone is Zone.GRAVEYARD
    assert _jace_tokens(scenario) == []


# -- Vraska's Final Mercy -------------------------------------------------------


def test_vraskas_final_mercy_destroy_mode_loses_two_life_and_destroys():
    scenario = (
        Scenario()
        .player("alice", hand=["Vraska's Final Mercy"], battlefield=["Swamp", "Swamp"], life=20)
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bear = scenario.creature("Grizzly Bears", "bob")
    sources = scenario.untapped_sources("Swamp", "Swamp")

    _cast_with_targets(scenario, "Vraska's Final Mercy", [bear], *sources, modes=[1])
    scenario.resolve_top()

    assert bear.zone is Zone.GRAVEYARD
    assert scenario.player("alice").life == 18
    assert _jace_tokens(scenario) == []


def test_vraskas_final_mercy_empower_mode_loses_two_life_and_empowers_six():
    scenario = (
        Scenario()
        .player("alice", hand=["Vraska's Final Mercy"], battlefield=["Swamp", "Swamp"], life=20)
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bear = scenario.creature("Grizzly Bears", "bob")
    sources = scenario.untapped_sources("Swamp", "Swamp")

    _cast_with_targets(scenario, "Vraska's Final Mercy", None, *sources, modes=[2])
    scenario.resolve_top()

    assert bear.zone is Zone.BATTLEFIELD
    assert scenario.player("alice").life == 18
    assert _jace_token(scenario).loyalty == 6
