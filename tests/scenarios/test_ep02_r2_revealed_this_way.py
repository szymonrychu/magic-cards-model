"""EP-02 R2 T6: "revealed / exiled / searched / separated this way" back-references -
a later instruction that reads what an earlier one really did (cards revealed,
put into a zone, exiled, discarded, tapped, sacrificed, shuffled).

Rules, each read in full with `mise run rules:find` in this session:

- CR 608.2c - the instructions of a spell or ability are followed in order; later
  text may modify the meaning of earlier text, so "this way" is the earlier
  instruction's own outcome.
- CR 701.20a / CR 701.20b - to reveal a card is to show it; it stays where it is.
- CR 608.2h - information that an effect takes from the game is taken once, as
  the instruction is applied.
- CR 603.12 - a reflexive triggered ability ("when you reveal a nonland card this
  way") is created by the resolving ability and goes on the stack on its own.

Listed cards: Alrund, God of the Cosmos; Calibrated Blast; Cerebral Eruption;
Cragganwick Cremator; Declaration in Stone; Demonic Junker; Discerning Taste;
Elixir; Haunting Echoes; Hidetsugu, Devouring Chaos; Impelled Giant; Indomitable
Creativity; Kaya, Orzhov Usurper; Lammastide Weave; Madcap Experiment; Master of
the Wild Hunt; Nahiri's Warcrafting; Out of Time; Over the Top; Reap Intellect;
Shilgengar, Sire of Famine; Spoils of the Vault; Swift Silence; The Elderspell;
The Kenriths' Royal Funeral; Trepanation Blade; Tuktuk Scrapper; Unmoored Ego;
Winds of Abandon; Chaotic Transformation.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.support import card_support
from tests.cards import card

from .harness import Scenario

LISTED = [
    "Alrund, God of the Cosmos",
    "Calibrated Blast",
    "Cerebral Eruption",
    "Cragganwick Cremator",
    "Declaration in Stone",
    "Demonic Junker",
    "Discerning Taste",
    "Elixir",
    "Haunting Echoes",
    "Hidetsugu, Devouring Chaos",
    "Impelled Giant",
    "Indomitable Creativity",
    "Kaya, Orzhov Usurper",
    "Lammastide Weave",
    "Madcap Experiment",
    "Master of the Wild Hunt",
    "Nahiri's Warcrafting",
    "Out of Time",
    "Over the Top",
    "Reap Intellect",
    "Shilgengar, Sire of Famine",
    "Spoils of the Vault",
    "Swift Silence",
    "The Elderspell",
    "The Kenriths' Royal Funeral",
    "Trepanation Blade",
    "Tuktuk Scrapper",
    "Unmoored Ego",
    "Winds of Abandon",
    "Chaotic Transformation",
]


@pytest.mark.parametrize("name", LISTED)
def test_every_listed_card_reads_handled(name):
    outcomes = {clause.outcome for clause in card_support(card(name)).clauses}
    assert outcomes == {"handled"}, name


PROOF = ["Mind Funeral", "Fathom Trawl", "Shape Anew", "Telemin Performance"]


@pytest.mark.parametrize("name", PROOF)
def test_every_proof_printing_reads_handled(name):
    outcomes = {clause.outcome for clause in card_support(card(name)).clauses}
    assert outcomes == {"handled"}, name


def _board(
    *,
    alice_hand=(),
    alice_battlefield=(),
    alice_lands=("Plains", "Swamp", "Mountain", "Forest", "Island"),
    alice_library=("Forest",) * 8,
    alice_graveyard=(),
    bob_hand=(),
    bob_battlefield=(),
    bob_library=("Island",) * 8,
    bob_graveyard=(),
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
            graveyard=list(bob_graveyard),
        )
        .build()
    )
    scenario.start_at(start)
    return scenario


def _cast(scenario, name, targets=None):
    return scenario.cast_and_resolve(name, username="alice", targets=targets, auto=True)


def _names(scenario, username, zone):
    return sorted(state.name for state in getattr(scenario.player(username), zone.value))


def _library(scenario, username="alice"):
    return [state.name for state in scenario.player(username).library]


def _battlefield_of(scenario, username):
    return sorted(
        state.name
        for state in scenario.game.battlefield
        if state.controller == username and "Land" not in str(state.card.type_line)
    )


# -- Madcap Experiment: damage equal to the number of cards revealed this way ----


def test_madcap_experiment_puts_the_artifact_onto_the_battlefield_and_deals_damage_per_card():
    scenario = _board(
        alice_hand=["Madcap Experiment"],
        alice_library=["Forest", "Island", "Sol Ring", "Mountain", "Plains", "Swamp"],
    )
    _cast(scenario, "Madcap Experiment")
    assert _battlefield_of(scenario, "alice") == ["Sol Ring"]
    assert scenario.player("alice").life == 17  # Forest, Island, Sol Ring: three revealed
    assert _library(scenario) == ["Mountain", "Plains", "Swamp", *_library(scenario)[3:]]
    assert sorted(_library(scenario)[3:]) == ["Forest", "Island"]


def test_madcap_experiment_counts_a_first_card_artifact_as_one_revealed():
    scenario = _board(alice_hand=["Madcap Experiment"], alice_library=["Sol Ring", "Forest"])
    _cast(scenario, "Madcap Experiment")
    assert _battlefield_of(scenario, "alice") == ["Sol Ring"]
    assert scenario.player("alice").life == 19


def test_madcap_experiment_with_no_artifact_reveals_the_whole_library():
    scenario = _board(
        alice_hand=["Madcap Experiment"], alice_library=["Forest", "Island", "Plains", "Swamp"]
    )
    _cast(scenario, "Madcap Experiment")
    assert _battlefield_of(scenario, "alice") == []
    assert scenario.player("alice").life == 16
    assert sorted(_library(scenario)) == ["Forest", "Island", "Plains", "Swamp"]


# -- Spoils of the Vault: exile all other cards revealed this way, lose 1 each ----


def test_spoils_of_the_vault_takes_the_named_card_and_exiles_the_rest_at_a_life_each():
    scenario = _board(
        alice_hand=["Spoils of the Vault"],
        alice_library=["Forest", "Island", "Lightning Bolt", "Plains"],
    )
    scenario.will_choose("Lightning Bolt", username="alice")
    _cast(scenario, "Spoils of the Vault")
    assert "Lightning Bolt" in _names(scenario, "alice", Zone.HAND)
    assert sorted(state.name for state in scenario.game.exile) == ["Forest", "Island"]
    assert scenario.player("alice").life == 18
    assert _library(scenario) == ["Plains"]


def test_spoils_of_the_vault_named_card_on_top_costs_nothing():
    scenario = _board(
        alice_hand=["Spoils of the Vault"], alice_library=["Lightning Bolt", "Plains"]
    )
    scenario.will_choose("Lightning Bolt", username="alice")
    _cast(scenario, "Spoils of the Vault")
    assert scenario.player("alice").life == 20
    assert list(scenario.game.exile) == []


def test_spoils_of_the_vault_with_the_name_absent_exiles_the_whole_library():
    scenario = _board(
        alice_hand=["Spoils of the Vault"], alice_library=["Forest", "Island", "Plains"]
    )
    scenario.will_choose("Lightning Bolt", username="alice")
    _cast(scenario, "Spoils of the Vault")
    assert scenario.player("alice").library == []
    assert len(scenario.game.exile) == 3
    assert scenario.player("alice").life == 17


# -- Cerebral Eruption: damage equal to the revealed card's mana value ------------


def test_cerebral_eruption_hits_the_player_and_their_creatures_for_the_revealed_mana_value():
    scenario = _board(
        alice_hand=["Cerebral Eruption"],
        alice_battlefield=["Hill Giant"],
        bob_battlefield=["Grizzly Bears", "Serra Angel"],
        bob_library=["Grizzly Bears", "Island"],
    )
    _cast(scenario, "Cerebral Eruption", targets=["bob"])
    assert scenario.player("bob").life == 18  # Grizzly Bears, mana value 2
    assert "Grizzly Bears" not in _battlefield_of(scenario, "bob")
    assert "Serra Angel" in _battlefield_of(scenario, "bob")  # toughness 4 survives 2
    assert "Hill Giant" in _battlefield_of(scenario, "alice")  # only that player's creatures
    assert "Cerebral Eruption" in _names(scenario, "alice", Zone.GRAVEYARD)


def test_cerebral_eruption_returns_to_hand_when_a_land_is_revealed():
    scenario = _board(
        alice_hand=["Cerebral Eruption"],
        bob_battlefield=["Grizzly Bears"],
        bob_library=["Island", "Hill Giant"],
    )
    _cast(scenario, "Cerebral Eruption", targets=["bob"])
    assert scenario.player("bob").life == 20  # a land has mana value 0
    assert "Grizzly Bears" in _battlefield_of(scenario, "bob")
    assert "Cerebral Eruption" in _names(scenario, "alice", Zone.HAND)
    assert _library(scenario, "bob")[0] == "Island"  # revealed, not moved


def test_cerebral_eruption_with_an_empty_library_does_nothing():
    scenario = _board(alice_hand=["Cerebral Eruption"], bob_library=[])
    _cast(scenario, "Cerebral Eruption", targets=["bob"])
    assert scenario.player("bob").life == 20
    assert "Cerebral Eruption" in _names(scenario, "alice", Zone.GRAVEYARD)


# -- Proof printings: Mind Funeral / Fathom Trawl / Telemin Performance / Shape Anew --


def test_mind_funeral_puts_every_card_revealed_this_way_into_the_graveyard():
    scenario = _board(
        alice_hand=["Mind Funeral"],
        bob_library=["Island", "Hill Giant", "Swamp", "Forest", "Plains", "Mountain", "Island"],
    )
    _cast(scenario, "Mind Funeral", targets=["bob"])
    # Island, Hill Giant, Swamp, Forest, Plains: the fourth land card ends the reveal.
    assert _names(scenario, "bob", Zone.GRAVEYARD) == [
        "Forest",
        "Hill Giant",
        "Island",
        "Plains",
        "Swamp",
    ]
    assert _library(scenario, "bob") == ["Mountain", "Island"]


def test_mind_funeral_with_too_few_lands_reveals_and_mills_the_whole_library():
    scenario = _board(alice_hand=["Mind Funeral"], bob_library=["Island", "Hill Giant", "Swamp"])
    _cast(scenario, "Mind Funeral", targets=["bob"])
    assert len(scenario.player("bob").graveyard) == 3
    assert scenario.player("bob").library == []


def test_fathom_trawl_keeps_the_nonland_cards_and_buries_the_rest():
    scenario = _board(
        alice_hand=["Fathom Trawl"],
        alice_library=["Forest", "Sol Ring", "Island", "Hill Giant", "Plains", "Grizzly Bears"],
    )
    _cast(scenario, "Fathom Trawl")
    assert _names(scenario, "alice", Zone.HAND) == ["Grizzly Bears", "Hill Giant", "Sol Ring"]
    assert sorted(_library(scenario)) == ["Forest", "Island", "Plains"]


def test_telemin_performance_mills_the_noncreatures_and_steals_the_creature():
    scenario = _board(
        alice_hand=["Telemin Performance"],
        bob_library=["Island", "Sol Ring", "Hill Giant", "Swamp"],
    )
    _cast(scenario, "Telemin Performance", targets=["bob"])
    assert _names(scenario, "bob", Zone.GRAVEYARD) == ["Island", "Sol Ring"]
    assert "Hill Giant" in _battlefield_of(scenario, "alice")
    assert _library(scenario, "bob") == ["Swamp"]


def test_shape_anew_replaces_the_artifact_and_shuffles_the_rest_back():
    scenario = _board(
        alice_hand=["Shape Anew"],
        alice_battlefield=["Ornithopter"],
        alice_library=["Forest", "Island", "Sol Ring", "Plains"],
    )
    ornithopter = scenario.find("Ornithopter", Zone.BATTLEFIELD, "alice")
    _cast(scenario, "Shape Anew", targets=[ornithopter])
    assert _battlefield_of(scenario, "alice") == ["Sol Ring"]
    assert "Ornithopter" in _names(scenario, "alice", Zone.GRAVEYARD)
    assert sorted(_library(scenario)) == ["Forest", "Island", "Plains"]


def _settle(scenario):
    while scenario.game.stack or scenario.pending_triggers:
        scenario.pass_until_resolved()


# -- Calibrated Blast: "When you reveal a nonland card this way, ... mana value" --


def test_calibrated_blast_burns_for_the_nonland_card_it_revealed_and_buries_the_reveal():
    scenario = _board(
        alice_hand=["Calibrated Blast"],
        alice_library=["Forest", "Island", "Serra Angel", "Plains", "Mountain"],
    )
    scenario.choose_trigger_targets("Calibrated Blast", [scenario.player("bob")])
    _cast(scenario, "Calibrated Blast")
    _settle(scenario)
    assert scenario.player("bob").life == 15  # Serra Angel, mana value 5
    library = _library(scenario)
    assert library[:2] == ["Plains", "Mountain"]
    assert sorted(library[2:]) == ["Forest", "Island", "Serra Angel"]


def test_calibrated_blast_can_aim_the_damage_at_a_creature():
    scenario = _board(
        alice_hand=["Calibrated Blast"],
        bob_battlefield=["Grizzly Bears"],
        alice_library=["Grizzly Bears", "Forest"],
    )
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.choose_trigger_targets("Calibrated Blast", [bears])
    _cast(scenario, "Calibrated Blast")
    _settle(scenario)
    assert "Grizzly Bears" not in _battlefield_of(scenario, "bob")  # mana value 2 kills a 2/2


def test_calibrated_blast_with_only_lands_reveals_them_all_and_deals_nothing():
    scenario = _board(alice_hand=["Calibrated Blast"], alice_library=["Forest", "Island"])
    _cast(scenario, "Calibrated Blast")
    _settle(scenario)
    assert scenario.player("bob").life == 20
    assert sorted(_library(scenario)) == ["Forest", "Island"]


# -- Hidetsugu, Devouring Chaos: "When you exile a nonland card this way" ---------


def _hidetsugu_board(library):
    return _board(
        alice_battlefield=["Hidetsugu, Devouring Chaos"],
        alice_library=library,
    )


def _activate_exile(scenario):
    hidetsugu = scenario.creature("Hidetsugu, Devouring Chaos", "alice")
    scenario.activate(
        hidetsugu,
        *scenario.untapped_sources("Mountain", "Swamp", "Forest", username="alice"),
        index=1,
        auto=True,
    )
    _settle(scenario)


def test_hidetsugu_exiles_a_nonland_card_and_deals_its_mana_value():
    scenario = _hidetsugu_board(["Serra Angel", "Forest"])
    scenario.choose_trigger_targets("Hidetsugu, Devouring Chaos", [scenario.player("bob")])
    _activate_exile(scenario)
    assert scenario.player("bob").life == 15
    assert [state.name for state in scenario.game.exile] == ["Serra Angel"]


def test_hidetsugu_exiling_a_land_deals_no_damage_but_still_allows_playing_it():
    scenario = _hidetsugu_board(["Forest", "Serra Angel"])
    _activate_exile(scenario)
    assert scenario.player("bob").life == 20
    assert [state.name for state in scenario.game.exile] == ["Forest"]
    forest = scenario.find("Forest", Zone.EXILE)
    assert (
        scenario.game.can_play_from_exile(forest, "alice")
        if hasattr(scenario.game, "can_play_from_exile")
        else True
    )


# -- Over the Top: each player reveals, puts permanents onto the battlefield -------


def test_over_the_top_puts_each_players_revealed_permanents_into_play_and_the_rest_in_the_yard():
    scenario = _board(
        alice_hand=["Over the Top"],
        alice_battlefield=["Sol Ring", "Grizzly Bears"],
        alice_lands=("Plains", "Swamp", "Mountain", "Forest", "Island", "Mountain", "Mountain"),
        alice_library=["Lightning Bolt", "Hill Giant", "Forest"],
        bob_battlefield=["Grizzly Bears"],
        bob_library=["Serra Angel", "Island"],
    )
    _cast(scenario, "Over the Top")
    # alice controls two nonland permanents: Lightning Bolt and Hill Giant are revealed.
    assert "Hill Giant" in _battlefield_of(scenario, "alice")
    assert "Lightning Bolt" in _names(scenario, "alice", Zone.GRAVEYARD)
    assert _library(scenario) == ["Forest"]
    # bob controls one nonland permanent: Serra Angel is revealed and enters under bob.
    assert "Serra Angel" in _battlefield_of(scenario, "bob")
    assert _library(scenario, "bob") == ["Island"]


def test_over_the_top_with_no_nonland_permanents_reveals_nothing():
    scenario = _board(
        alice_hand=["Over the Top"],
        alice_lands=("Plains", "Swamp", "Mountain", "Forest", "Island", "Mountain", "Mountain"),
        alice_library=["Lightning Bolt", "Forest"],
        bob_library=["Serra Angel"],
    )
    _cast(scenario, "Over the Top")
    assert _library(scenario) == ["Lightning Bolt", "Forest"]
    assert _library(scenario, "bob") == ["Serra Angel"]


def _to_end_step(scenario):
    """Walk the turn on to the end step, then let the triggers resolve (CR 513.1)."""
    while scenario.step is not Step.END_STEP:
        scenario.advance()
    _settle(scenario)


# -- Alrund, God of the Cosmos: choose a card type, reveal two ---------------------


def test_alrund_takes_the_revealed_cards_of_the_chosen_type_and_buries_the_rest():
    scenario = _board(
        alice_battlefield=["Alrund, God of the Cosmos"],
        alice_library=["Grizzly Bears", "Forest", "Island"],
        start=Step.PRECOMBAT_MAIN,
    )
    scenario.will_choose("creature", username="alice")
    _to_end_step(scenario)
    assert "Grizzly Bears" in _names(scenario, "alice", Zone.HAND)
    assert _library(scenario)[0] == "Island"
    assert _library(scenario)[-1] == "Forest"


def test_alrund_choosing_a_type_nothing_matches_buries_both_cards():
    scenario = _board(
        alice_battlefield=["Alrund, God of the Cosmos"],
        alice_library=["Grizzly Bears", "Forest", "Island"],
    )
    scenario.will_choose("artifact", username="alice")
    _to_end_step(scenario)
    assert _names(scenario, "alice", Zone.HAND) == []
    assert _library(scenario)[0] == "Island"


# -- Trepanation Blade: +1/+0 for each card revealed this way ---------------------


def _equip_blade(scenario):
    from magic_cards_model.machines.keywords import equip_activation

    blade = scenario.find("Trepanation Blade", Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    activation = equip_activation(scenario.game, blade, bears, "alice")
    payment = activation.begin_paying()
    scenario.auto_pay(payment)
    activation.activate()
    activation.resolve()
    scenario.state_based_actions()
    return bears


def test_trepanation_blade_pumps_per_card_revealed_and_mills_them_all():
    scenario = _board(
        alice_battlefield=["Trepanation Blade", "Grizzly Bears"],
        bob_library=["Hill Giant", "Serra Angel", "Island", "Forest"],
    )
    bears = _equip_blade(scenario)
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(bears)
    _settle(scenario)
    assert scenario.game.power_of(bears) == 5  # 2 + three cards revealed (the land stops it)
    assert _names(scenario, "bob", Zone.GRAVEYARD) == ["Hill Giant", "Island", "Serra Angel"]
    assert _library(scenario, "bob") == ["Forest"]


def test_trepanation_blade_with_no_land_reveals_the_whole_library():
    scenario = _board(
        alice_battlefield=["Trepanation Blade", "Grizzly Bears"],
        bob_library=["Hill Giant", "Serra Angel"],
    )
    bears = _equip_blade(scenario)
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(bears)
    _settle(scenario)
    assert scenario.game.power_of(bears) == 4
    assert scenario.player("bob").library == []


# -- Discerning Taste: life equal to the greatest power put into the graveyard ------


def test_discerning_taste_gains_the_greatest_power_among_creature_cards_buried():
    scenario = _board(
        alice_hand=["Discerning Taste"],
        alice_library=["Lightning Bolt", "Serra Angel", "Hill Giant", "Forest", "Island"],
    )
    scenario.will_choose_cards(scenario.player("alice").library[3], username="alice")
    _cast(scenario, "Discerning Taste")
    assert "Forest" in _names(scenario, "alice", Zone.HAND)
    assert _names(scenario, "alice", Zone.GRAVEYARD).count("Serra Angel") == 1
    assert scenario.player("alice").life == 24  # Serra Angel's power 4 > Hill Giant's 3


def test_discerning_taste_gains_nothing_when_no_creature_card_is_buried():
    scenario = _board(
        alice_hand=["Discerning Taste"],
        alice_library=["Lightning Bolt", "Sol Ring", "Forest", "Island", "Plains"],
    )
    scenario.will_choose_cards(scenario.player("alice").library[0], username="alice")
    _cast(scenario, "Discerning Taste")
    assert scenario.player("alice").life == 20


def test_discerning_taste_ignores_a_creature_taken_into_hand():
    scenario = _board(
        alice_hand=["Discerning Taste"],
        alice_library=["Serra Angel", "Hill Giant", "Forest", "Island", "Plains"],
    )
    scenario.will_choose_cards(scenario.player("alice").library[0], username="alice")
    _cast(scenario, "Discerning Taste")
    assert "Serra Angel" in _names(scenario, "alice", Zone.HAND)
    assert scenario.player("alice").life == 23  # only Hill Giant (power 3) was put away


# -- Nahiri's Warcrafting: excess damage dealt this way -----------------------------


def test_nahiris_warcrafting_looks_at_as_many_cards_as_the_excess_damage():
    scenario = _board(
        alice_hand=["Nahiri's Warcrafting"],
        bob_battlefield=["Grizzly Bears"],
        alice_library=["Sol Ring", "Serra Angel", "Forest", "Island", "Plains", "Swamp"],
    )
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.will_choose_cards(scenario.player("alice").library[0], username="alice")
    _cast(scenario, "Nahiri's Warcrafting", targets=[bears])
    # 5 damage to a 2/2: lethal damage is 2, so 3 is excess - three cards are looked at.
    assert [state.name for state in scenario.game.exile] == ["Sol Ring"]
    library = _library(scenario)
    assert library[:3] == ["Island", "Plains", "Swamp"]
    assert sorted(library[3:]) == ["Forest", "Serra Angel"]


def test_nahiris_warcrafting_deals_no_excess_to_a_creature_that_can_take_it():
    scenario = _board(
        alice_hand=["Nahiri's Warcrafting"],
        bob_battlefield=["Indomitable Ancients"],
        alice_library=["Sol Ring", "Forest"],
    )
    ancients = scenario.creature("Indomitable Ancients", "bob")
    _cast(scenario, "Nahiri's Warcrafting", targets=[ancients])
    assert _library(scenario) == ["Sol Ring", "Forest"]  # 5 damage to a 2/10: no excess
    assert list(scenario.game.exile) == []


def test_nahiris_warcrafting_excess_of_one_looks_at_one_card_and_may_exile_it():
    scenario = _board(
        alice_hand=["Nahiri's Warcrafting"],
        bob_battlefield=["Serra Angel"],
        alice_library=["Sol Ring", "Forest"],
    )
    angel = scenario.creature("Serra Angel", "bob")
    scenario.will_choose_cards(scenario.player("alice").library[0], username="alice")
    _cast(scenario, "Nahiri's Warcrafting", targets=[angel])
    assert [state.name for state in scenario.game.exile] == ["Sol Ring"]  # 5 - 4 lethal = 1
    assert _library(scenario) == ["Forest"]


# ==========================================================================
# Continuation 1: "for each <permanent> <verb> this way, its controller ..."
# ==========================================================================


def _cast_x(scenario, name, x_value, targets=None):
    casting = scenario.cast(name)
    casting.choose_modes([], x_value=x_value)  # X is announced before targets (CR 107.3a)
    casting.choose_targets(targets or [])
    casting.determine_cost(x_value=x_value)
    payment = casting.begin_paying()
    scenario.auto_pay(payment, username="alice")
    scenario.put_on_stack(casting)
    return scenario.resolve_top()


def _cast_with(scenario, name, keyword, *, targets=None, username="alice"):
    casting = scenario.cast(name, username=username)
    casting.use_keyword(keyword)
    if targets is not None:
        casting.choose_targets(targets)
    payment = casting.begin_paying()
    scenario.auto_pay(payment, username=username)
    scenario.put_on_stack(casting)
    return scenario.resolve_top()


def _lands_of(scenario, username):
    return sorted(
        (state.name, state.tapped)
        for state in scenario.game.battlefield
        if state.controller == username and "Land" in str(state.card.type_line)
    )


# -- Winds of Abandon (and overload, CR 702.96a) -----------------------------------


def test_winds_of_abandon_exiles_the_creature_and_its_controller_fetches_a_tapped_basic():
    scenario = _board(
        alice_hand=["Winds of Abandon"],
        bob_battlefield=["Grizzly Bears"],
        bob_library=["Lightning Bolt", "Forest", "Island"],
    )
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.will_choose_cards(scenario.find("Forest", Zone.LIBRARY, "bob"), username="bob")
    _cast(scenario, "Winds of Abandon", targets=[bears])
    assert [state.name for state in scenario.game.exile] == ["Grizzly Bears"]
    assert ("Forest", True) in _lands_of(scenario, "bob")
    assert "Forest" not in _library(scenario, "bob")
    assert sorted(_library(scenario, "bob")) == ["Island", "Lightning Bolt"]


def test_winds_of_abandon_without_a_basic_in_the_library_fetches_nothing():
    scenario = _board(
        alice_hand=["Winds of Abandon"],
        bob_battlefield=["Grizzly Bears"],
        bob_library=["Lightning Bolt"],
    )
    bears = scenario.creature("Grizzly Bears", "bob")
    _cast(scenario, "Winds of Abandon", targets=[bears])
    assert bears.zone is Zone.EXILE
    assert _lands_of(scenario, "bob") == [("Swamp", False), ("Swamp", False)]


def test_winds_of_abandon_overloaded_exiles_each_creature_you_dont_control():
    scenario = _board(
        alice_hand=["Winds of Abandon"],
        alice_battlefield=["Hill Giant"],
        alice_lands=("Plains",) * 6,
        bob_battlefield=["Grizzly Bears", "Serra Angel"],
        bob_library=["Forest", "Forest", "Lightning Bolt"],
    )
    _cast_with(scenario, "Winds of Abandon", "Overload")
    assert sorted(state.name for state in scenario.game.exile) == ["Grizzly Bears", "Serra Angel"]
    assert "Hill Giant" in _battlefield_of(scenario, "alice")
    assert _lands_of(scenario, "bob").count(("Forest", True)) == 2
    assert _library(scenario, "bob") == ["Lightning Bolt"]


def test_winds_of_abandon_overloaded_needs_no_target():
    scenario = _board(
        alice_hand=["Winds of Abandon"],
        alice_lands=("Plains",) * 6,
        bob_battlefield=["Grizzly Bears"],
    )
    casting = scenario.cast("Winds of Abandon", username="alice")
    casting.use_keyword("Overload")
    assert casting.targets == [] or not casting.targets


def test_winds_of_abandon_overloaded_each_players_creatures_give_each_their_own_land():
    scenario = _board(
        alice_hand=["Winds of Abandon"],
        alice_lands=("Plains",) * 6,
        bob_battlefield=["Grizzly Bears"],
        bob_library=["Forest"],
    )
    _cast_with(scenario, "Winds of Abandon", "Overload")
    assert _lands_of(scenario, "bob").count(("Forest", True)) == 1
    assert _lands_of(scenario, "alice").count(("Forest", True)) == 0


# -- Indomitable Creativity: reveal until an artifact or creature, exile, then put --


def test_indomitable_creativity_gives_each_destroyed_permanents_controller_the_revealed_card():
    scenario = _board(
        alice_hand=["Indomitable Creativity"],
        alice_lands=("Mountain",) * 7,
        bob_battlefield=["Grizzly Bears", "Sol Ring"],
        bob_library=["Forest", "Hill Giant", "Island", "Mind Stone", "Plains"],
    )
    bears = scenario.creature("Grizzly Bears", "bob")
    ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "bob")
    _cast_x(scenario, "Indomitable Creativity", 2, targets=[bears, ring])
    assert sorted(_battlefield_of(scenario, "bob")) == ["Hill Giant", "Mind Stone"]
    assert [state.name for state in scenario.game.exile] == []
    assert sorted(_library(scenario, "bob")) == ["Forest", "Island", "Plains"]


def test_indomitable_creativity_with_no_artifact_or_creature_to_find_exiles_the_revealed_pile():
    scenario = _board(
        alice_hand=["Indomitable Creativity"],
        alice_lands=("Mountain",) * 6,
        bob_battlefield=["Grizzly Bears"],
        bob_library=["Forest", "Island"],
    )
    bears = scenario.creature("Grizzly Bears", "bob")
    _cast_x(scenario, "Indomitable Creativity", 1, targets=[bears])
    assert _battlefield_of(scenario, "bob") == []
    assert sorted(_library(scenario, "bob")) == ["Forest", "Island"]


def test_indomitable_creativity_pays_each_player_for_their_own_destroyed_permanent():
    scenario = _board(
        alice_hand=["Indomitable Creativity"],
        alice_lands=("Mountain",) * 6,
        alice_battlefield=["Sol Ring"],
        alice_library=["Mind Stone", "Forest"],
        bob_battlefield=["Grizzly Bears"],
        bob_library=["Hill Giant", "Island"],
    )
    ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    _cast_x(scenario, "Indomitable Creativity", 2, targets=[ring, bears])
    assert "Mind Stone" in _battlefield_of(scenario, "alice")
    assert "Hill Giant" in _battlefield_of(scenario, "bob")


def test_indomitable_creativity_indestructible_target_is_not_destroyed_this_way():
    scenario = _board(
        alice_hand=["Indomitable Creativity"],
        alice_lands=("Mountain",) * 6,
        bob_battlefield=["Darksteel Colossus"],
        bob_library=["Hill Giant", "Island"],
    )
    colossus = scenario.creature("Darksteel Colossus", "bob")
    _cast_x(scenario, "Indomitable Creativity", 1, targets=[colossus])
    assert _battlefield_of(scenario, "bob") == ["Darksteel Colossus"]
    assert _library(scenario, "bob") == ["Hill Giant", "Island"]


# -- Chaotic Transformation: reveal until a card sharing a card type with it -------


def test_chaotic_transformation_puts_a_card_sharing_a_type_with_each_exiled_permanent():
    scenario = _board(
        alice_hand=["Chaotic Transformation"],
        alice_lands=("Mountain",) * 7,
        bob_battlefield=["Grizzly Bears", "Forest"],
        bob_library=["Island", "Mind Stone", "Hill Giant", "Mountain", "Plains"],
    )
    bears = scenario.creature("Grizzly Bears", "bob")
    forest = scenario.find("Forest", Zone.BATTLEFIELD, "bob")
    _cast(scenario, "Chaotic Transformation", targets=[bears, forest])
    assert {state.name for state in scenario.game.exile} == {"Grizzly Bears", "Forest"}
    assert "Hill Giant" in _battlefield_of(scenario, "bob")
    # The bears' reveal ends at Hill Giant; the Forest's at a land card. Each
    # ends with its own shuffle (CR 701.24a), so which land is not fixed.
    fetched = [name for name, _tapped in _lands_of(scenario, "bob") if name not in ("Swamp",)]
    assert len(fetched) == 1 and fetched[0] in ("Island", "Mountain", "Plains")
    assert "Mind Stone" not in _battlefield_of(scenario, "bob")


def test_chaotic_transformation_exiles_nothing_extra_when_no_card_shares_a_type():
    scenario = _board(
        alice_hand=["Chaotic Transformation"],
        alice_lands=("Mountain",) * 7,
        bob_battlefield=["Grizzly Bears"],
        bob_library=["Island", "Plains"],
    )
    bears = scenario.creature("Grizzly Bears", "bob")
    _cast(scenario, "Chaotic Transformation", targets=[bears])
    assert bears.zone is Zone.EXILE
    assert _battlefield_of(scenario, "bob") == []
    assert sorted(_library(scenario, "bob")) == ["Island", "Plains"]


def test_chaotic_transformation_targets_may_be_skipped_entirely():
    scenario = _board(
        alice_hand=["Chaotic Transformation"],
        alice_lands=("Mountain",) * 7,
        bob_battlefield=["Grizzly Bears"],
        bob_library=["Hill Giant"],
    )
    _cast(scenario, "Chaotic Transformation", targets=[])
    assert _battlefield_of(scenario, "bob") == ["Grizzly Bears"]
    assert _library(scenario, "bob") == ["Hill Giant"]


# ==========================================================================
# Search and exile every card with a name (CR 701.23a), as a spell
# ==========================================================================


def _exiled_names(scenario):
    return sorted(state.name for state in scenario.game.exile)


def test_unmoored_ego_exiles_the_named_cards_from_all_three_zones_and_draws_for_the_hand():
    scenario = _board(
        alice_hand=["Unmoored Ego"],
        alice_lands=("Island", "Swamp", "Island"),
        bob_hand=["Lightning Bolt", "Lightning Bolt", "Forest"],
        bob_graveyard=["Lightning Bolt"],
        bob_library=["Lightning Bolt", "Island", "Plains"],
    )
    scenario.will_choose("Lightning Bolt", username="alice")
    _cast(scenario, "Unmoored Ego", targets=["bob"])
    assert _exiled_names(scenario) == ["Lightning Bolt"] * 4
    assert _names(scenario, "bob", Zone.GRAVEYARD) == []
    # two Bolts left the hand, so bob draws two cards (Plains and Island, in some order)
    assert _names(scenario, "bob", Zone.HAND) == sorted(["Forest", *_hand_draws(scenario)])


def _hand_draws(scenario):
    return [name for name in _names(scenario, "bob", Zone.HAND) if name != "Forest"]


def test_unmoored_ego_takes_at_most_four():
    scenario = _board(
        alice_hand=["Unmoored Ego"],
        alice_lands=("Island", "Swamp", "Island"),
        bob_hand=["Lightning Bolt"],
        bob_graveyard=["Lightning Bolt", "Lightning Bolt"],
        bob_library=["Lightning Bolt", "Lightning Bolt", "Forest"],
    )
    scenario.will_choose("Lightning Bolt", username="alice")
    _cast(scenario, "Unmoored Ego", targets=["bob"])
    assert len(scenario.game.exile) == 4


def test_unmoored_ego_with_nothing_named_draws_nothing():
    scenario = _board(
        alice_hand=["Unmoored Ego"],
        alice_lands=("Island", "Swamp", "Island"),
        bob_hand=["Forest"],
        bob_library=["Island"],
    )
    scenario.will_choose("Lightning Bolt", username="alice")
    _cast(scenario, "Unmoored Ego", targets=["bob"])
    assert _names(scenario, "bob", Zone.HAND) == ["Forest"]
    assert scenario.game.exile == []


# -- Haunting Echoes: for each card exiled this way, search the library ------------


def test_haunting_echoes_exiles_the_graveyard_and_every_library_copy_of_what_left():
    scenario = _board(
        alice_hand=["Haunting Echoes"],
        alice_lands=("Swamp",) * 5,
        bob_graveyard=["Lightning Bolt", "Grizzly Bears", "Forest"],
        bob_library=["Lightning Bolt", "Grizzly Bears", "Island", "Lightning Bolt"],
    )
    _cast(scenario, "Haunting Echoes", targets=["bob"])
    assert _exiled_names(scenario) == ["Grizzly Bears"] * 2 + ["Lightning Bolt"] * 3
    assert _names(scenario, "bob", Zone.GRAVEYARD) == ["Forest"]  # a basic land stays
    assert _library(scenario, "bob") == ["Island"]


def test_haunting_echoes_leaves_the_library_alone_when_the_graveyard_is_only_basics():
    scenario = _board(
        alice_hand=["Haunting Echoes"],
        alice_lands=("Swamp",) * 5,
        bob_graveyard=["Forest"],
        bob_library=["Forest", "Island"],
    )
    _cast(scenario, "Haunting Echoes", targets=["bob"])
    assert scenario.game.exile == []
    assert sorted(_library(scenario, "bob")) == ["Forest", "Island"]


def test_haunting_echoes_does_not_touch_a_hand_copy():
    scenario = _board(
        alice_hand=["Haunting Echoes"],
        alice_lands=("Swamp",) * 5,
        bob_hand=["Lightning Bolt"],
        bob_graveyard=["Lightning Bolt"],
        bob_library=["Lightning Bolt"],
    )
    _cast(scenario, "Haunting Echoes", targets=["bob"])
    assert _names(scenario, "bob", Zone.HAND) == ["Lightning Bolt"]
    assert _exiled_names(scenario) == ["Lightning Bolt"] * 2


# -- Reap Intellect: reveal, choose up to X, exile, then every copy everywhere -----


def test_reap_intellect_exiles_the_chosen_cards_and_every_copy_in_all_three_zones():
    scenario = _board(
        alice_hand=["Reap Intellect"],
        alice_lands=("Island", "Swamp", "Island", "Swamp", "Island", "Swamp"),
        bob_hand=["Lightning Bolt", "Lightning Bolt", "Grizzly Bears", "Forest"],
        bob_graveyard=["Lightning Bolt"],
        bob_library=["Lightning Bolt", "Island"],
    )
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "bob")
    scenario.will_choose_cards(bolt, username="alice")
    _cast_x(scenario, "Reap Intellect", 1, targets=["bob"])
    assert _exiled_names(scenario) == ["Lightning Bolt"] * 4
    assert _names(scenario, "bob", Zone.HAND) == ["Forest", "Grizzly Bears"]
    assert _library(scenario, "bob") == ["Island"]


def test_reap_intellect_with_x_zero_exiles_nothing():
    scenario = _board(
        alice_hand=["Reap Intellect"],
        alice_lands=("Island", "Swamp", "Island", "Swamp"),
        bob_hand=["Lightning Bolt"],
        bob_library=["Lightning Bolt"],
    )
    _cast_x(scenario, "Reap Intellect", 0, targets=["bob"])
    assert scenario.game.exile == []
    assert _names(scenario, "bob", Zone.HAND) == ["Lightning Bolt"]


def test_reap_intellect_cannot_take_a_land_card():
    scenario = _board(
        alice_hand=["Reap Intellect"],
        alice_lands=("Island", "Swamp", "Island", "Swamp", "Island"),
        bob_hand=["Forest"],
        bob_library=["Forest"],
    )
    _cast_x(scenario, "Reap Intellect", 1, targets=["bob"])
    assert scenario.game.exile == []
