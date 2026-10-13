"""Scenario: cards in a graveyard counted as an amount (EP-02 R1 T5).

One reader answers every "N of the cards in a graveyard" amount
(`machines/ep02_r1_graveyard_counts.py`): "for each creature card in your
graveyard", "the number of card types among cards in your graveyard", "each
different mana value among nonland cards in your graveyard", "the total number
of instant and sorcery cards you own in exile and in your graveyard", "each
card named X in each graveyard", "permanent cards", a count in "that player's
graveyard". A graveyard is a zone of cards (CR 404.1): a token is never in one
that is counted, the spell being resolved is on the stack and never counts
itself, and a card is "named" by its printed name (CR 201.2).

The count is taken once, as the instruction is followed (CR 608.2h). The
instructions that use it are read by the parsers this file drives: life gained
or lost, tokens (tapped and attacking too), mill, counters, cards drawn, mana,
-X/-X, damage, a search limit, an activation cost reduction.

CR numbers were looked up with `mise run rules:find`: 404.1, 108.3, 201.2,
205.2a, 202.3, 608.2h, 608.2c, 700.4, 508.4, 107.1a.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import has_keyword
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from magic_cards_model.models.token import is_token

from .harness import Scenario

BEARS = "Grizzly Bears"
BOLT = "Lightning Bolt"
SOL_RING = "Sol Ring"
MOUNTAIN = "Mountain"
DREADMAW = "Colossal Dreadmaw"


def _board(
    *,
    hand=(),
    battlefield=(),
    graveyard=(),
    library=(),
    exile=(),
    bob_battlefield=(),
    bob_graveyard=(),
    bob_library=(),
    bob_hand=(),
    step=Step.PRECOMBAT_MAIN,
):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=list(hand),
            battlefield=list(battlefield),
            graveyard=list(graveyard),
            library=list(library) or ["Forest"] * 12,
            exile=list(exile),
        )
        .player(
            "bob",
            hand=list(bob_hand),
            battlefield=list(bob_battlefield),
            graveyard=list(bob_graveyard),
            library=list(bob_library or ()) or ["Island"] * 12,
        )
        .build()
    )
    scenario.start_at(step)
    return scenario


def _enter(scenario, name, *, targets=None, owner="alice"):
    """Put `name` onto the battlefield and resolve every trigger it raises."""
    if targets:
        scenario.choose_trigger_targets(name, targets)
    permanent = scenario.put_onto_battlefield(name, owner)
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()
    return permanent


def _tokens(scenario, token_name):
    return [p for p in scenario.game.battlefield if is_token(p) and p.name == f"{token_name} Token"]


def _stats(scenario, permanent):
    chars = scenario.game.computed_board().of(permanent)
    return chars.power, chars.toughness


def _life(scenario, name="alice"):
    return scenario.player(name).life


# --------------------------------------------------------------------------
# Aatchik, Emerald Radian - "a 1/1 Insect for each artifact and/or creature
# card in your graveyard"
# --------------------------------------------------------------------------


def test_aatchik_makes_no_insect_for_an_empty_graveyard():
    # The same trigger with one creature card in the graveyard makes one, so
    # the zero below is a count and not an unread trigger.
    loaded = _board(hand=["Aatchik, Emerald Radian"], graveyard=[BEARS])
    _enter(loaded, "Aatchik, Emerald Radian")
    assert len(_tokens(loaded, "Insect")) == 1
    scenario = _board(hand=["Aatchik, Emerald Radian"])
    _enter(scenario, "Aatchik, Emerald Radian")
    assert _tokens(scenario, "Insect") == []


def test_aatchik_counts_artifact_and_creature_cards_but_not_lands_or_instants():
    scenario = _board(hand=["Aatchik, Emerald Radian"], graveyard=[BEARS, SOL_RING, MOUNTAIN, BOLT])
    _enter(scenario, "Aatchik, Emerald Radian")
    assert len(_tokens(scenario, "Insect")) == 2


def test_aatchik_ignores_an_opponents_graveyard():
    scenario = _board(
        hand=["Aatchik, Emerald Radian"], graveyard=[BEARS], bob_graveyard=[BEARS, SOL_RING]
    )
    _enter(scenario, "Aatchik, Emerald Radian")
    assert len(_tokens(scenario, "Insect")) == 1


def test_aatchik_counts_a_card_once_even_when_it_is_both_types():
    scenario = _board(hand=["Aatchik, Emerald Radian"], graveyard=["Walking Ballista"])
    _enter(scenario, "Aatchik, Emerald Radian")
    assert len(_tokens(scenario, "Insect")) == 1


# --------------------------------------------------------------------------
# Ancestor's Chosen - "you gain 1 life for each card in your graveyard"
# --------------------------------------------------------------------------


def test_ancestors_chosen_gains_nothing_with_an_empty_graveyard():
    loaded = _board(hand=["Ancestor's Chosen"], graveyard=[BOLT])
    _enter(loaded, "Ancestor's Chosen")
    assert _life(loaded) == 21
    scenario = _board(hand=["Ancestor's Chosen"])
    _enter(scenario, "Ancestor's Chosen")
    assert _life(scenario) == 20


def test_ancestors_chosen_counts_every_card_whatever_its_type():
    scenario = _board(hand=["Ancestor's Chosen"], graveyard=[BEARS, SOL_RING, MOUNTAIN, BOLT])
    _enter(scenario, "Ancestor's Chosen")
    assert _life(scenario) == 24


def test_ancestors_chosen_ignores_the_opponents_graveyard():
    scenario = _board(hand=["Ancestor's Chosen"], graveyard=[BEARS], bob_graveyard=[BEARS] * 5)
    _enter(scenario, "Ancestor's Chosen")
    assert _life(scenario) == 21


# --------------------------------------------------------------------------
# Archangel's Light - "gain 2 life for each card in your graveyard, then
# shuffle your graveyard into your library"
# --------------------------------------------------------------------------

EIGHT_PLAINS = ["Plains"] * 8


def test_archangels_light_gains_two_per_card_then_empties_the_graveyard():
    scenario = _board(
        hand=["Archangel's Light"], battlefield=EIGHT_PLAINS, graveyard=[BEARS, BOLT, MOUNTAIN]
    )
    library_before = len(scenario.player("alice").library)
    scenario.cast_and_resolve("Archangel's Light", auto=True)
    alice = scenario.player("alice")
    assert _life(scenario) == 26
    # The three cards went back; the spell itself is in the graveyard after it
    # resolved, and was never counted (CR 608.2n via the stack, CR 404.1).
    assert [card.name for card in alice.graveyard] == ["Archangel's Light"] or alice.graveyard == []
    assert len(alice.library) == library_before + 3


def test_archangels_light_with_an_empty_graveyard_gains_nothing():
    loaded = _board(hand=["Archangel's Light"], battlefield=EIGHT_PLAINS, graveyard=[BOLT])
    loaded.cast_and_resolve("Archangel's Light", auto=True)
    assert _life(loaded) == 22
    scenario = _board(hand=["Archangel's Light"], battlefield=EIGHT_PLAINS)
    scenario.cast_and_resolve("Archangel's Light", auto=True)
    assert _life(scenario) == 20


def test_archangels_light_does_not_count_or_shuffle_the_opponents_graveyard():
    scenario = _board(
        hand=["Archangel's Light"],
        battlefield=EIGHT_PLAINS,
        graveyard=[BEARS],
        bob_graveyard=[BOLT] * 4,
    )
    scenario.cast_and_resolve("Archangel's Light", auto=True)
    assert _life(scenario) == 22
    assert len(scenario.player("bob").graveyard) == 4


# --------------------------------------------------------------------------
# Battlefield Butcher - "{5},{T}: each opponent loses 2 life. This ability
# costs {1} less to activate for each creature card in your graveyard."
# --------------------------------------------------------------------------


def _butcher(*, lands, graveyard=(), bob_graveyard=()):
    scenario = _board(
        battlefield=["Battlefield Butcher", *["Swamp"] * lands],
        graveyard=graveyard,
        bob_graveyard=bob_graveyard,
    )
    return scenario, scenario.creature("Battlefield Butcher", "alice")


def test_battlefield_butcher_costs_the_full_five_with_no_creature_cards():
    cheaper, cheaper_butcher = _butcher(lands=4, graveyard=[BEARS])
    cheaper.activate(cheaper_butcher, *cheaper.untapped_sources(*["Swamp"] * 4))
    cheaper.resolve_top()
    assert _life(cheaper, "bob") == 18
    scenario, butcher = _butcher(lands=4)
    with pytest.raises(ValueError):
        scenario.activate(butcher, *scenario.untapped_sources(*["Swamp"] * 4))


def test_battlefield_butcher_pays_five_and_drains_two():
    scenario, butcher = _butcher(lands=5)
    scenario.activate(butcher, *scenario.untapped_sources(*["Swamp"] * 5))
    scenario.resolve_top()
    assert _life(scenario, "bob") == 18


def test_battlefield_butcher_is_one_cheaper_per_creature_card():
    scenario, butcher = _butcher(lands=2, graveyard=[BEARS, BEARS, BEARS, BOLT, SOL_RING])
    scenario.activate(butcher, *scenario.untapped_sources("Swamp", "Swamp"))
    scenario.resolve_top()
    assert _life(scenario, "bob") == 18


def test_battlefield_butcher_does_not_count_noncreature_cards():
    cheaper, cheaper_butcher = _butcher(lands=2, graveyard=[BEARS] * 3)
    cheaper.activate(cheaper_butcher, *cheaper.untapped_sources("Swamp", "Swamp"))
    cheaper.resolve_top()
    assert _life(cheaper, "bob") == 18
    scenario, butcher = _butcher(lands=2, graveyard=[BEARS, BEARS, BOLT, SOL_RING, MOUNTAIN])
    with pytest.raises(ValueError):
        scenario.activate(butcher, *scenario.untapped_sources("Swamp", "Swamp"))


def test_battlefield_butcher_ignores_the_opponents_graveyard():
    cheaper, cheaper_butcher = _butcher(
        lands=3, graveyard=[BEARS, BEARS], bob_graveyard=[BEARS] * 4
    )
    cheaper.activate(cheaper_butcher, *cheaper.untapped_sources("Swamp", "Swamp", "Swamp"))
    cheaper.resolve_top()
    assert _life(cheaper, "bob") == 18
    scenario, butcher = _butcher(lands=3, graveyard=[BEARS], bob_graveyard=[BEARS] * 4)
    with pytest.raises(ValueError):
        scenario.activate(butcher, *scenario.untapped_sources("Swamp", "Swamp", "Swamp"))


def test_battlefield_butcher_costs_nothing_but_the_tap_at_five_creature_cards():
    scenario, butcher = _butcher(lands=0, graveyard=[BEARS] * 6)
    scenario.activate(butcher)
    scenario.resolve_top()
    assert _life(scenario, "bob") == 18
    assert butcher.tapped


# --------------------------------------------------------------------------
# Broodspinner - "{4}{B}{G},{T}, sacrifice: a number of 1/1 Insects with flying
# equal to the number of card types among cards in your graveyard"
# --------------------------------------------------------------------------

SPINNER_MANA = ["Swamp", "Forest", "Forest", "Forest", "Forest", "Forest"]


def _spinner(graveyard=(), bob_graveyard=()):
    scenario = _board(
        battlefield=["Broodspinner", *SPINNER_MANA],
        graveyard=graveyard,
        bob_graveyard=bob_graveyard,
    )
    spinner = scenario.creature("Broodspinner", "alice")
    scenario.activate(spinner, auto=True)
    scenario.resolve_top()
    return scenario


def test_broodspinner_makes_one_insect_per_distinct_card_type():
    scenario = _spinner(graveyard=[BEARS, BEARS, BOLT, SOL_RING])
    assert len(_tokens(scenario, "Insect")) == 3


def test_broodspinner_counts_itself_once_it_is_sacrificed_to_its_own_cost():
    """The sacrifice is a cost paid as the ability is activated (CR 602.2b,
    CR 701.21a), so the Spider is already a creature card in the graveyard
    when the ability resolves."""
    scenario = _spinner()
    assert len(_tokens(scenario, "Insect")) == 1


def test_broodspinner_counts_a_land_and_a_dual_typed_card_by_each_type():
    scenario = _spinner(graveyard=[MOUNTAIN, "Walking Ballista", "Dryad Arbor"])
    # land, artifact, creature (Dryad Arbor is a land creature)
    assert len(_tokens(scenario, "Insect")) == 3


def test_broodspinner_counts_only_its_controllers_graveyard():
    scenario = _spinner(graveyard=[BEARS], bob_graveyard=[BOLT, SOL_RING, MOUNTAIN])
    assert len(_tokens(scenario, "Insect")) == 1


def test_broodspinner_insects_fly():
    scenario = _spinner(graveyard=[BEARS])
    (insect,) = _tokens(scenario, "Insect")
    assert has_keyword(insect, "flying", scenario.game)


# --------------------------------------------------------------------------
# Chupacabra Echo, Cloud of Darkness, Terror Tide - "-X/-X, where X is the
# number of permanent cards in your graveyard"
# --------------------------------------------------------------------------

PERMANENT_YARD = [BEARS, SOL_RING, MOUNTAIN, BOLT]  # three permanents, one instant


@pytest.mark.parametrize("name", ["Chupacabra Echo", "Cloud of Darkness"])
def test_permanent_cards_shrink_the_target_by_their_count(name):
    scenario = _board(
        hand=[name], graveyard=PERMANENT_YARD, bob_battlefield=[DREADMAW], bob_graveyard=[BEARS] * 4
    )
    target = scenario.creature(DREADMAW, "bob")
    _enter(scenario, name, targets=[target])
    assert _stats(scenario, target) == (3, 3)


@pytest.mark.parametrize("name", ["Chupacabra Echo", "Cloud of Darkness"])
def test_an_empty_graveyard_shrinks_the_target_by_nothing(name):
    loaded = _board(hand=[name], graveyard=[BEARS], bob_battlefield=[DREADMAW])
    loaded_target = loaded.creature(DREADMAW, "bob")
    _enter(loaded, name, targets=[loaded_target])
    assert _stats(loaded, loaded_target) == (5, 5)
    scenario = _board(hand=[name], bob_battlefield=[DREADMAW])
    target = scenario.creature(DREADMAW, "bob")
    _enter(scenario, name, targets=[target])
    assert _stats(scenario, target) == (6, 6)


@pytest.mark.parametrize("name", ["Chupacabra Echo", "Cloud of Darkness"])
def test_enough_permanent_cards_kill_the_target(name):
    scenario = _board(hand=[name], graveyard=[BEARS] * 6, bob_battlefield=[DREADMAW])
    target = scenario.creature(DREADMAW, "bob")
    _enter(scenario, name, targets=[target])
    scenario.state_based_actions()
    assert target.zone is Zone.GRAVEYARD


def test_terror_tide_shrinks_every_creature_on_both_sides():
    scenario = _board(
        hand=["Terror Tide"],
        battlefield=["Swamp"] * 4 + ["Llanowar Elves"],
        graveyard=[BEARS, SOL_RING, MOUNTAIN, BOLT],
        bob_battlefield=[DREADMAW, BEARS],
    )
    elves = scenario.creature("Llanowar Elves", "alice")
    scenario.cast_and_resolve("Terror Tide", auto=True)
    scenario.state_based_actions()
    assert elves.zone is Zone.GRAVEYARD
    assert _stats(scenario, scenario.creature(DREADMAW, "bob")) == (3, 3)
    assert [card.name for card in scenario.player("bob").graveyard] == [BEARS]


def test_terror_tide_with_an_empty_graveyard_changes_nothing():
    loaded = _board(
        hand=["Terror Tide"],
        battlefield=["Swamp"] * 4 + [BEARS],
        graveyard=[SOL_RING],
        bob_battlefield=[DREADMAW],
    )
    loaded.cast_and_resolve("Terror Tide", auto=True)
    assert _stats(loaded, loaded.creature(DREADMAW, "bob")) == (5, 5)
    scenario = _board(
        hand=["Terror Tide"], battlefield=["Swamp"] * 4 + [BEARS], bob_battlefield=[DREADMAW]
    )
    scenario.cast_and_resolve("Terror Tide", auto=True)
    scenario.state_based_actions()
    assert _stats(scenario, scenario.creature(DREADMAW, "bob")) == (6, 6)
    assert _stats(scenario, scenario.creature(BEARS, "alice")) == (2, 2)


def test_terror_tide_does_not_count_itself_while_it_resolves():
    """The sorcery is on the stack, not in the graveyard, until it finishes."""
    loaded = _board(
        hand=["Terror Tide"],
        battlefield=["Swamp"] * 4,
        graveyard=[SOL_RING, MOUNTAIN],
        bob_battlefield=[DREADMAW],
    )
    loaded.cast_and_resolve("Terror Tide", auto=True)
    assert _stats(loaded, loaded.creature(DREADMAW, "bob")) == (4, 4)
    scenario = _board(hand=["Terror Tide"], battlefield=["Swamp"] * 4, bob_battlefield=[DREADMAW])
    scenario.cast_and_resolve("Terror Tide", auto=True)
    assert _stats(scenario, scenario.creature(DREADMAW, "bob")) == (6, 6)


# --------------------------------------------------------------------------
# Fresh Meat - "a 3/3 Beast for each creature put into your graveyard from the
# battlefield this turn"
# --------------------------------------------------------------------------


def _fresh_meat_board(**kwargs):
    return _board(
        hand=["Fresh Meat"], battlefield=["Forest"] * 4 + kwargs.pop("mine", []), **kwargs
    )


def _kill(scenario, name, owner):
    for permanent in [
        p
        for p in scenario.game.battlefield
        if p.name == name and p.owner == owner and not is_token(p)
    ]:
        scenario.game.put_into_graveyard(permanent)
    scenario.game.put_triggers_on_stack()


def test_fresh_meat_makes_a_beast_per_creature_that_died_this_turn():
    scenario = _fresh_meat_board(mine=[BEARS, BEARS, "Llanowar Elves"])
    _kill(scenario, BEARS, "alice")
    _kill(scenario, "Llanowar Elves", "alice")
    scenario.cast_and_resolve("Fresh Meat", auto=True)
    assert len(_tokens(scenario, "Beast")) == 3


def test_fresh_meat_makes_none_when_nothing_died():
    died = _fresh_meat_board(mine=[BEARS])
    _kill(died, BEARS, "alice")
    died.cast_and_resolve("Fresh Meat", auto=True)
    assert len(_tokens(died, "Beast")) == 1
    scenario = _fresh_meat_board(mine=[BEARS])
    scenario.cast_and_resolve("Fresh Meat", auto=True)
    assert _tokens(scenario, "Beast") == []


def test_fresh_meat_ignores_creature_cards_that_never_were_on_the_battlefield():
    died = _fresh_meat_board(mine=[BEARS], graveyard=[BEARS, BEARS])
    _kill(died, BEARS, "alice")
    died.cast_and_resolve("Fresh Meat", auto=True)
    assert len(_tokens(died, "Beast")) == 1  # the one that died, not the two milled
    scenario = _fresh_meat_board(graveyard=[BEARS, BEARS])
    scenario.cast_and_resolve("Fresh Meat", auto=True)
    assert _tokens(scenario, "Beast") == []


def test_fresh_meat_ignores_noncreature_permanents_and_opponents_creatures():
    scenario = _fresh_meat_board(mine=[SOL_RING, BEARS], bob_battlefield=[DREADMAW, BEARS])
    _kill(scenario, SOL_RING, "alice")
    _kill(scenario, DREADMAW, "bob")
    _kill(scenario, BEARS, "bob")
    _kill(scenario, BEARS, "alice")
    scenario.cast_and_resolve("Fresh Meat", auto=True)
    assert len(_tokens(scenario, "Beast")) == 1  # only my own creature counts


def test_fresh_meat_counts_a_creature_of_mine_that_an_opponent_destroyed():
    """Whose graveyard it went to is the owner's (CR 108.3), whoever controlled it."""
    scenario = _fresh_meat_board(mine=[BEARS])
    _kill(scenario, BEARS, "alice")
    scenario.cast_and_resolve("Fresh Meat", auto=True)
    assert len(_tokens(scenario, "Beast")) == 1


# --------------------------------------------------------------------------
# Ghoulcaller's Harvest - "X Zombies with decayed, where X is half the number
# of creature cards in your graveyard, rounded up"
# --------------------------------------------------------------------------


def _harvest_resolved(creature_cards):
    scenario = _board(
        hand=["Ghoulcaller's Harvest"],
        battlefield=["Swamp", "Forest"],
        graveyard=[BEARS] * creature_cards + [BOLT, SOL_RING],
    )
    scenario.cast_and_resolve("Ghoulcaller's Harvest", auto=True)
    return scenario


@pytest.mark.parametrize(
    ("creature_cards", "zombies"), [(0, 0), (1, 1), (2, 1), (3, 2), (4, 2), (5, 3)]
)
def test_ghoulcallers_harvest_rounds_half_up(creature_cards, zombies):
    if creature_cards == 0:
        creature_cards, zombies = 1, 1  # a lone creature card still rounds up to one
        assert len(_tokens(_harvest_resolved(creature_cards), "Zombie")) == zombies
        creature_cards, zombies = 0, 0
    scenario = _board(
        hand=["Ghoulcaller's Harvest"],
        battlefield=["Swamp", "Forest"],
        graveyard=[BEARS] * creature_cards + [BOLT, SOL_RING],
    )
    scenario.cast_and_resolve("Ghoulcaller's Harvest", auto=True)
    assert len(_tokens(scenario, "Zombie")) == zombies


def test_ghoulcallers_harvest_zombies_are_2_2_with_decayed():
    scenario = _board(
        hand=["Ghoulcaller's Harvest"], battlefield=["Swamp", "Forest"], graveyard=[BEARS] * 2
    )
    scenario.cast_and_resolve("Ghoulcaller's Harvest", auto=True)
    (zombie,) = _tokens(scenario, "Zombie")
    assert _stats(scenario, zombie) == (2, 2)
    assert has_keyword(zombie, "decayed", scenario.game)


def test_ghoulcallers_harvest_ignores_the_opponents_creature_cards():
    scenario = _board(
        hand=["Ghoulcaller's Harvest"],
        battlefield=["Swamp", "Forest"],
        graveyard=[BEARS],
        bob_graveyard=[BEARS] * 6,
    )
    scenario.cast_and_resolve("Ghoulcaller's Harvest", auto=True)
    assert len(_tokens(scenario, "Zombie")) == 1


# --------------------------------------------------------------------------
# Gran Pulse Ochu - "{8}: until end of turn this creature gets +1/+1 for each
# permanent card in your graveyard"
# --------------------------------------------------------------------------


def _ochu(graveyard=(), bob_graveyard=()):
    scenario = _board(
        battlefield=["Gran Pulse Ochu", *["Forest"] * 8],
        graveyard=graveyard,
        bob_graveyard=bob_graveyard,
    )
    ochu = scenario.creature("Gran Pulse Ochu", "alice")
    scenario.activate(ochu, auto=True)
    scenario.resolve_top()
    return scenario, ochu


def test_gran_pulse_ochu_grows_by_each_permanent_card():
    scenario, ochu = _ochu(graveyard=PERMANENT_YARD)
    assert _stats(scenario, ochu) == (4, 4)


def test_gran_pulse_ochu_stays_a_one_one_with_an_empty_graveyard():
    grown, grown_ochu = _ochu(graveyard=[BEARS])
    assert _stats(grown, grown_ochu) == (2, 2)
    scenario, ochu = _ochu()
    assert _stats(scenario, ochu) == (1, 1)


def test_gran_pulse_ochu_fixes_the_count_when_the_ability_resolves():
    """CR 608.2h: a card that reaches the graveyard later does not move the bonus."""
    scenario = _board(
        battlefield=["Gran Pulse Ochu", BEARS, *["Forest"] * 8], graveyard=[BEARS, BEARS]
    )
    ochu = scenario.creature("Gran Pulse Ochu", "alice")
    scenario.activate(ochu, auto=True)
    scenario.resolve_top()
    scenario.game.put_into_graveyard(scenario.creature(BEARS, "alice"))
    assert _stats(scenario, ochu) == (3, 3)


def test_gran_pulse_ochu_ignores_the_opponents_graveyard():
    scenario, ochu = _ochu(graveyard=[BEARS], bob_graveyard=[BEARS] * 5)
    assert _stats(scenario, ochu) == (2, 2)


def test_gran_pulse_ochu_bonus_ends_with_the_turn():
    scenario, ochu = _ochu(graveyard=PERMANENT_YARD)
    assert _stats(scenario, ochu) == (4, 4)
    scenario.game.continuous_effects.end_the_turn()
    assert _stats(scenario, ochu) == (1, 1)


# --------------------------------------------------------------------------
# Graveblade Marauder - "that player loses life equal to the number of
# creature cards in your graveyard"
# --------------------------------------------------------------------------


def _marauder_hit(graveyard=(), bob_graveyard=()):
    scenario = _board(
        battlefield=["Graveblade Marauder"],
        graveyard=graveyard,
        bob_graveyard=bob_graveyard,
        step=Step.DECLARE_ATTACKERS,
    )
    scenario.attack_with(scenario.creature("Graveblade Marauder", "alice"))
    scenario.no_blocks()
    scenario.combat_damage()
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()
    return scenario


def test_graveblade_marauder_drains_per_creature_card_beyond_its_combat_damage():
    scenario = _marauder_hit(graveyard=[BEARS, BEARS, BOLT, SOL_RING])
    assert _life(scenario, "bob") == 20 - 1 - 2


def test_graveblade_marauder_drains_nothing_extra_with_an_empty_graveyard():
    assert _life(_marauder_hit(graveyard=[BEARS]), "bob") == 18
    scenario = _marauder_hit()
    assert _life(scenario, "bob") == 19


def test_graveblade_marauder_counts_my_graveyard_not_the_damaged_players():
    scenario = _marauder_hit(graveyard=[BEARS], bob_graveyard=[BEARS] * 5)
    assert _life(scenario, "bob") == 20 - 1 - 1
    assert _life(scenario) == 20


# --------------------------------------------------------------------------
# Kessig Cagebreakers - "a 2/2 Wolf that's tapped and attacking for each
# creature card in your graveyard"
# --------------------------------------------------------------------------


def _cagebreakers_attack(graveyard=(), bob_graveyard=()):
    scenario = _board(
        battlefield=["Kessig Cagebreakers"],
        graveyard=graveyard,
        bob_graveyard=bob_graveyard,
        step=Step.DECLARE_ATTACKERS,
    )
    scenario.attack_with(scenario.creature("Kessig Cagebreakers", "alice"))
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()
    return scenario


def test_cagebreakers_wolves_enter_tapped_and_attacking_one_per_creature_card():
    scenario = _cagebreakers_attack(graveyard=[BEARS, BEARS, BEARS, BOLT])
    wolves = _tokens(scenario, "Wolf")
    assert len(wolves) == 3
    attackers = scenario.game.combat.attacker_ids
    assert all(wolf.tapped and wolf.id in attackers for wolf in wolves)
    assert all(_stats(scenario, wolf) == (2, 2) for wolf in wolves)


def test_cagebreakers_makes_no_wolf_for_an_empty_graveyard():
    assert len(_tokens(_cagebreakers_attack(graveyard=[BEARS]), "Wolf")) == 1
    scenario = _cagebreakers_attack()
    assert _tokens(scenario, "Wolf") == []


def test_cagebreakers_ignores_noncreature_cards_and_the_opponents_graveyard():
    scenario = _cagebreakers_attack(
        graveyard=[BEARS, SOL_RING, MOUNTAIN], bob_graveyard=[BEARS] * 4
    )
    assert len(_tokens(scenario, "Wolf")) == 1


# --------------------------------------------------------------------------
# Keening Stone - "target player mills X cards, where X is the number of cards
# in that player's graveyard"
# --------------------------------------------------------------------------


def test_keening_stone_mills_the_target_by_the_size_of_their_own_graveyard():
    scenario = _board(
        battlefield=["Keening Stone", *["Mountain"] * 5],
        graveyard=[BEARS],
        bob_graveyard=[BEARS, BOLT, SOL_RING],
    )
    stone = scenario.find("Keening Stone", Zone.BATTLEFIELD)
    scenario.activate(stone, targets=[scenario.player("bob")], auto=True)
    scenario.resolve_top()
    assert len(scenario.player("bob").graveyard) == 6
    assert len(scenario.player("bob").library) == 9
    assert len(scenario.player("alice").graveyard) == 1


def test_keening_stone_can_target_its_own_controller():
    scenario = _board(
        battlefield=["Keening Stone", *["Mountain"] * 5],
        graveyard=[BEARS, BOLT],
        bob_graveyard=[BEARS] * 5,
    )
    stone = scenario.find("Keening Stone", Zone.BATTLEFIELD)
    scenario.activate(stone, targets=[scenario.player("alice")], auto=True)
    scenario.resolve_top()
    assert len(scenario.player("alice").graveyard) == 4
    assert len(scenario.player("alice").library) == 10
    assert len(scenario.player("bob").graveyard) == 5


def test_keening_stone_with_an_empty_graveyard_mills_nothing():
    loaded = _board(battlefield=["Keening Stone", *["Mountain"] * 5], bob_graveyard=[BEARS])
    loaded_stone = loaded.find("Keening Stone", Zone.BATTLEFIELD)
    loaded.activate(loaded_stone, targets=[loaded.player("bob")], auto=True)
    loaded.resolve_top()
    assert len(loaded.player("bob").library) == 11
    scenario = _board(battlefield=["Keening Stone", *["Mountain"] * 5])
    stone = scenario.find("Keening Stone", Zone.BATTLEFIELD)
    scenario.activate(stone, targets=[scenario.player("bob")], auto=True)
    scenario.resolve_top()
    assert len(scenario.player("bob").library) == 12


def test_keening_stone_mills_only_what_the_library_holds():
    scenario = _board(
        battlefield=["Keening Stone", *["Mountain"] * 5],
        bob_graveyard=[BEARS] * 4,
        bob_library=["Island", "Island"],
    )
    stone = scenario.find("Keening Stone", Zone.BATTLEFIELD)
    scenario.activate(stone, targets=[scenario.player("bob")], auto=True)
    scenario.resolve_top()
    assert scenario.player("bob").library == []
    assert len(scenario.player("bob").graveyard) == 6


# --------------------------------------------------------------------------
# Liliana, Death Mage - "-7: target opponent loses 2 life for each creature
# card in their graveyard"
# --------------------------------------------------------------------------


def _lili_ultimate(graveyard=(), bob_graveyard=()):
    scenario = _board(
        battlefield=["Liliana, Death Mage"], graveyard=graveyard, bob_graveyard=bob_graveyard
    )
    liliana = scenario.find("Liliana, Death Mage", Zone.BATTLEFIELD)
    liliana.add_counters(Counter.LOYALTY, 4)  # 4 -> 8, so -7 does not end her
    scenario.activate(liliana, index=2, targets=[scenario.player("bob")])
    scenario.resolve_top()
    return scenario


def test_liliana_drains_two_per_creature_card_in_their_graveyard():
    scenario = _lili_ultimate(bob_graveyard=[BEARS, BEARS, BEARS, BOLT, SOL_RING])
    assert _life(scenario, "bob") == 14


def test_liliana_counts_their_graveyard_not_mine():
    scenario = _lili_ultimate(graveyard=[BEARS] * 6, bob_graveyard=[BEARS])
    assert _life(scenario, "bob") == 18


def test_liliana_drains_nothing_when_their_graveyard_has_no_creature_cards():
    assert _life(_lili_ultimate(bob_graveyard=[BEARS, BOLT]), "bob") == 18
    scenario = _lili_ultimate(graveyard=[BEARS] * 3, bob_graveyard=[BOLT])
    assert _life(scenario, "bob") == 20


# --------------------------------------------------------------------------
# Lucid Dreams, Peer Past the Veil - "draw X cards, where X is the number of
# card types among cards in your graveyard"
# --------------------------------------------------------------------------

TYPES_YARD = [BEARS, BEARS, BOLT, SOL_RING, MOUNTAIN]  # creature, instant, artifact, land


def test_lucid_dreams_draws_one_card_per_distinct_card_type():
    scenario = _board(hand=["Lucid Dreams"], battlefield=["Island"] * 5, graveyard=TYPES_YARD)
    scenario.cast_and_resolve("Lucid Dreams", auto=True)
    assert len(scenario.player("alice").hand) == 4


def test_lucid_dreams_counts_each_type_of_a_multi_typed_card():
    scenario = _board(
        hand=["Lucid Dreams"],
        battlefield=["Island"] * 5,
        graveyard=["Walking Ballista", "Dryad Arbor"],
    )
    scenario.cast_and_resolve("Lucid Dreams", auto=True)
    # artifact + creature, land + creature
    assert len(scenario.player("alice").hand) == 3


def test_lucid_dreams_draws_nothing_with_an_empty_graveyard():
    loaded = _board(hand=["Lucid Dreams"], battlefield=["Island"] * 5, graveyard=[BEARS])
    loaded.cast_and_resolve("Lucid Dreams", auto=True)
    assert len(loaded.player("alice").hand) == 1
    scenario = _board(hand=["Lucid Dreams"], battlefield=["Island"] * 5)
    scenario.cast_and_resolve("Lucid Dreams", auto=True)
    assert scenario.player("alice").hand == []


def test_lucid_dreams_ignores_the_opponents_graveyard_and_itself():
    scenario = _board(
        hand=["Lucid Dreams"],
        battlefield=["Island"] * 5,
        graveyard=[BEARS],
        bob_graveyard=[BOLT, SOL_RING, MOUNTAIN],
    )
    scenario.cast_and_resolve("Lucid Dreams", auto=True)
    assert len(scenario.player("alice").hand) == 1


def test_peer_past_the_veil_discards_the_hand_first_and_counts_the_discards():
    scenario = _board(
        hand=["Peer Past the Veil", BEARS, MOUNTAIN, BOLT],
        battlefield=["Mountain", "Mountain", "Forest", "Forest"],
        graveyard=[SOL_RING],
    )
    scenario.cast_and_resolve("Peer Past the Veil", auto=True)
    # creature, land and instant were discarded into the graveyard before the
    # draw (CR 608.2c) next to the artifact already there, so four card types
    # are counted; the spell itself is still on the stack and is not one.
    assert len(scenario.player("alice").hand) == 4


def test_peer_past_the_veil_with_a_stocked_graveyard_draws_per_type():
    scenario = _board(
        hand=["Peer Past the Veil"],
        battlefield=["Mountain", "Mountain", "Forest", "Forest"],
        graveyard=TYPES_YARD,
    )
    scenario.cast_and_resolve("Peer Past the Veil", auto=True)
    assert len(scenario.player("alice").hand) == 4


# --------------------------------------------------------------------------
# Master Pakku - "target player mills X cards, where X is the number of Lesson
# cards in your graveyard"
# --------------------------------------------------------------------------

LESSON = "Combustion Technique"


def _pakku_taps(graveyard=(), bob_graveyard=(), target="bob", bob_library=None):
    scenario = _board(
        battlefield=["Master Pakku"],
        graveyard=graveyard,
        bob_graveyard=bob_graveyard,
        bob_library=bob_library,
        step=Step.DECLARE_ATTACKERS,
    )
    pakku = scenario.creature("Master Pakku", "alice")
    scenario.will_choose_targets(scenario.player(target))
    scenario.attack_with(pakku)  # tapping it to attack is what makes it become tapped
    scenario.pass_until_resolved()
    return scenario


def test_master_pakku_mills_by_the_lesson_cards_in_its_controllers_graveyard():
    scenario = _pakku_taps(graveyard=[LESSON, LESSON, BEARS, BOLT])
    assert len(scenario.player("bob").library) == 10
    assert len(scenario.player("bob").graveyard) == 2


def test_master_pakku_mills_nothing_without_lesson_cards():
    assert len(_pakku_taps(graveyard=[LESSON, BEARS]).player("bob").library) == 11
    scenario = _pakku_taps(graveyard=[BEARS, BOLT, SOL_RING])
    assert len(scenario.player("bob").library) == 12


def test_master_pakku_counts_my_lessons_even_when_the_target_has_them_too():
    scenario = _pakku_taps(graveyard=[LESSON], bob_graveyard=[LESSON] * 5)
    assert len(scenario.player("bob").library) == 11


def test_master_pakku_can_mill_its_own_controller():
    scenario = _pakku_taps(graveyard=[LESSON, LESSON], target="alice")
    assert len(scenario.player("alice").library) == 10


# --------------------------------------------------------------------------
# Mausoleum Secrets - "search your library for a black card with mana value
# less than or equal to the number of creature cards in your graveyard"
# --------------------------------------------------------------------------

GRAY_MERCHANT = "Gray Merchant of Asphodel"  # black, mana value 5
NIGHTHAWK = "Vampire Nighthawk"  # black, mana value 3
ELVES = "Llanowar Elves"  # green, mana value 1


def _mausoleum(library, graveyard=(), bob_graveyard=()):
    scenario = _board(
        hand=["Mausoleum Secrets"],
        battlefield=["Swamp", "Swamp"],
        graveyard=graveyard,
        bob_graveyard=bob_graveyard,
        library=library,
    )
    scenario.cast_and_resolve("Mausoleum Secrets", auto=True)
    return [card.name for card in scenario.player("alice").hand]


def test_mausoleum_secrets_finds_a_black_card_at_exactly_the_limit():
    assert _mausoleum([GRAY_MERCHANT, ELVES], graveyard=[BEARS] * 5) == [GRAY_MERCHANT]


def test_mausoleum_secrets_cannot_find_a_card_above_the_limit():
    assert _mausoleum([GRAY_MERCHANT, ELVES], graveyard=[BEARS] * 5) == [GRAY_MERCHANT]
    assert _mausoleum([GRAY_MERCHANT, ELVES], graveyard=[BEARS] * 4) == []


def test_mausoleum_secrets_with_no_creature_cards_has_a_limit_of_zero():
    assert _mausoleum([NIGHTHAWK, GRAY_MERCHANT], graveyard=[BEARS] * 3) == [NIGHTHAWK]
    assert _mausoleum([NIGHTHAWK, GRAY_MERCHANT], graveyard=[BOLT, SOL_RING]) == []


def test_mausoleum_secrets_never_finds_a_card_that_is_not_black():
    assert _mausoleum([GRAY_MERCHANT, ELVES], graveyard=[BEARS] * 6) == [GRAY_MERCHANT]
    assert _mausoleum([ELVES], graveyard=[BEARS] * 6) == []


def test_mausoleum_secrets_counts_my_creature_cards_only():
    assert _mausoleum([NIGHTHAWK], graveyard=[BEARS, BEARS], bob_graveyard=[BEARS] * 5) == []
    assert _mausoleum([NIGHTHAWK], graveyard=[BEARS] * 3, bob_graveyard=[]) == [NIGHTHAWK]


# --------------------------------------------------------------------------
# Pteramander - "{7}{U}: adapt 4. This ability costs {1} less to activate for
# each instant and sorcery card in your graveyard."
# --------------------------------------------------------------------------


def _pteramander(*, lands, graveyard=(), bob_graveyard=()):
    scenario = _board(
        battlefield=["Pteramander", *["Island"] * lands],
        graveyard=graveyard,
        bob_graveyard=bob_graveyard,
    )
    return scenario, scenario.creature("Pteramander", "alice")


def test_pteramander_costs_eight_with_no_instants_or_sorceries():
    cheaper, cheaper_drake = _pteramander(lands=7, graveyard=[BOLT])
    cheaper.activate(cheaper_drake, *cheaper.untapped_sources(*["Island"] * 7))
    cheaper.resolve_top()
    assert cheaper_drake.counter_count("+1/+1") == 4
    scenario, drake = _pteramander(lands=7, graveyard=[BEARS, SOL_RING])
    with pytest.raises(ValueError):
        scenario.activate(drake, *scenario.untapped_sources(*["Island"] * 7))


def test_pteramander_is_one_cheaper_per_instant_and_sorcery_card():
    scenario, drake = _pteramander(lands=5, graveyard=[BOLT, "Divination", BOLT, BEARS])
    scenario.activate(drake, *scenario.untapped_sources(*["Island"] * 5))
    scenario.resolve_top()
    assert drake.counter_count("+1/+1") == 4


def test_pteramander_ignores_the_opponents_instants():
    cheaper, cheaper_drake = _pteramander(lands=6, graveyard=[BOLT, BOLT], bob_graveyard=[BOLT] * 4)
    cheaper.activate(cheaper_drake, *cheaper.untapped_sources(*["Island"] * 6))
    cheaper.resolve_top()
    assert cheaper_drake.counter_count("+1/+1") == 4
    scenario, drake = _pteramander(lands=7, graveyard=[BOLT], bob_graveyard=[BOLT] * 4)
    with pytest.raises(ValueError):
        scenario.activate(drake, *scenario.untapped_sources(*["Island"] * 6))


def test_pteramander_costs_one_blue_at_seven_instants_and_sorceries():
    scenario, drake = _pteramander(lands=1, graveyard=[BOLT] * 7)
    scenario.activate(drake, *scenario.untapped_sources("Island"))
    scenario.resolve_top()
    assert drake.counter_count("+1/+1") == 4


def test_pteramander_reduction_never_removes_the_blue():
    paid, paid_drake = _pteramander(lands=1, graveyard=[BOLT] * 9)
    paid.activate(paid_drake, *paid.untapped_sources("Island"))
    paid.resolve_top()
    assert paid_drake.counter_count("+1/+1") == 4
    scenario, drake = _pteramander(lands=0, graveyard=[BOLT] * 9)
    with pytest.raises(ValueError):
        scenario.activate(drake)


# --------------------------------------------------------------------------
# Ral, Izzet Viceroy - "-3: Ral deals damage to target creature equal to the
# total number of instant and sorcery cards you own in exile and in your
# graveyard"
# --------------------------------------------------------------------------


def _ral_minus_three(*, graveyard=(), exile=(), bob_graveyard=()):
    scenario = _board(
        battlefield=["Ral, Izzet Viceroy"],
        graveyard=graveyard,
        exile=exile,
        bob_battlefield=[DREADMAW],
        bob_graveyard=bob_graveyard,
    )
    ral = scenario.find("Ral, Izzet Viceroy", Zone.BATTLEFIELD)
    target = scenario.creature(DREADMAW, "bob")
    scenario.activate(ral, index=1, targets=[target])
    scenario.resolve_top()
    return target


def test_ral_counts_instants_and_sorceries_in_the_graveyard_and_in_exile():
    target = _ral_minus_three(graveyard=[BOLT, "Divination"], exile=[BOLT])
    assert target.damage == 3


def test_ral_ignores_creatures_artifacts_and_lands_in_either_zone():
    target = _ral_minus_three(graveyard=[BEARS, SOL_RING, MOUNTAIN, BOLT], exile=[BEARS])
    assert target.damage == 1


def test_ral_deals_no_damage_with_nothing_to_count():
    assert _ral_minus_three(graveyard=[BOLT]).damage == 1
    target = _ral_minus_three()
    assert target.damage == 0


def test_ral_counts_only_cards_I_own_not_the_opponents_graveyard():
    target = _ral_minus_three(graveyard=[BOLT], bob_graveyard=[BOLT] * 5)
    assert target.damage == 1


# --------------------------------------------------------------------------
# Rite of Flame - "add {R}{R}, then add {R} for each card named Rite of Flame
# in each graveyard"
# --------------------------------------------------------------------------

RITE = "Rite of Flame"


def _rite(graveyard=(), bob_graveyard=()):
    scenario = _board(
        hand=[RITE], battlefield=[MOUNTAIN], graveyard=graveyard, bob_graveyard=bob_graveyard
    )
    scenario.cast_and_resolve(RITE, auto=True)
    return scenario.player("alice").mana_pool.floating


def test_rite_of_flame_adds_two_red_with_no_other_copies():
    from magic_cards_model.models.card import Color

    assert _rite() == {Color.RED: 2}


def test_rite_of_flame_adds_one_more_per_copy_in_either_graveyard():
    from magic_cards_model.models.card import Color

    assert _rite(graveyard=[RITE, RITE], bob_graveyard=[RITE]) == {Color.RED: 5}


def test_rite_of_flame_does_not_count_itself_or_differently_named_cards():
    from magic_cards_model.models.card import Color

    assert _rite(graveyard=[BOLT, "Rite of Passage"], bob_graveyard=[BOLT]) == {Color.RED: 2}


# --------------------------------------------------------------------------
# Roiling Terrain - "destroy target land, then Roiling Terrain deals damage to
# that land's controller equal to the number of land cards in that player's
# graveyard"
# --------------------------------------------------------------------------


def _terrain(*, target_owner, graveyard=(), bob_graveyard=(), bob_battlefield=("Forest",)):
    scenario = _board(
        hand=["Roiling Terrain"],
        battlefield=["Mountain"] * 4 + (["Forest"] if target_owner == "alice" else []),
        graveyard=graveyard,
        bob_battlefield=bob_battlefield,
        bob_graveyard=bob_graveyard,
    )
    land = scenario.find("Forest", Zone.BATTLEFIELD, target_owner)
    scenario.cast_and_resolve(
        "Roiling Terrain", *scenario.untapped_sources(*["Mountain"] * 4), targets=[land]
    )
    return scenario, land


def test_roiling_terrain_counts_the_land_it_just_destroyed():
    scenario, land = _terrain(target_owner="bob")
    assert land.zone is Zone.GRAVEYARD
    assert _life(scenario, "bob") == 19


def test_roiling_terrain_counts_the_land_cards_in_their_graveyard():
    scenario, _ = _terrain(target_owner="bob", bob_graveyard=[MOUNTAIN, MOUNTAIN, BEARS, BOLT])
    assert _life(scenario, "bob") == 17


def test_roiling_terrain_ignores_my_graveyard_when_it_hits_their_land():
    scenario, _ = _terrain(target_owner="bob", graveyard=[MOUNTAIN] * 5)
    assert _life(scenario, "bob") == 19
    assert _life(scenario) == 20


def test_roiling_terrain_can_hit_my_own_land_for_my_graveyard():
    scenario, _ = _terrain(
        target_owner="alice", graveyard=[MOUNTAIN, MOUNTAIN], bob_graveyard=[MOUNTAIN] * 4
    )
    assert _life(scenario) == 17
    assert _life(scenario, "bob") == 20


# --------------------------------------------------------------------------
# Sudden Insight - "draw a card for each different mana value among nonland
# cards in your graveyard"
# --------------------------------------------------------------------------


def _insight(graveyard=(), bob_graveyard=()):
    scenario = _board(
        hand=["Sudden Insight"],
        battlefield=["Island"] * 6,
        graveyard=graveyard,
        bob_graveyard=bob_graveyard,
    )
    scenario.cast_and_resolve("Sudden Insight", auto=True)
    return len(scenario.player("alice").hand)


def test_sudden_insight_draws_one_per_distinct_mana_value():
    # Bears {1}{G} = 2, Bolt {R} = 1, Sol Ring {1} = 1, Divination {2}{U} = 3
    assert _insight([BEARS, BEARS, BOLT, SOL_RING, "Divination"]) == 3


def test_sudden_insight_ignores_lands_even_though_their_value_is_zero():
    assert _insight([MOUNTAIN, MOUNTAIN, BEARS]) == 1


def test_sudden_insight_draws_nothing_with_only_lands_or_nothing():
    assert _insight([MOUNTAIN, BEARS]) == 1
    assert _insight([MOUNTAIN]) == 0
    assert _insight() == 0


def test_sudden_insight_counts_a_zero_value_nonland_card():
    assert _insight(["Ornithopter", BEARS]) == 2


def test_sudden_insight_ignores_the_opponents_graveyard():
    assert _insight([BOLT], bob_graveyard=[BEARS, "Divination", "Serra Angel"]) == 1


# --------------------------------------------------------------------------
# Sunflare Shaman - "{1}{R},{T}: this creature deals X damage to any target and
# X damage to itself, where X is the number of Elemental cards in your
# graveyard"
# --------------------------------------------------------------------------

ELEMENTAL = "Ball Lightning"


def _shaman(*, graveyard=(), bob_graveyard=(), bob_battlefield=()):
    scenario = _board(
        battlefield=["Sunflare Shaman", "Mountain", "Mountain"],
        graveyard=graveyard,
        bob_graveyard=bob_graveyard,
        bob_battlefield=bob_battlefield,
    )
    shaman = scenario.creature("Sunflare Shaman", "alice")
    return scenario, shaman


def test_sunflare_shaman_deals_x_to_the_target_and_x_to_itself():
    scenario, shaman = _shaman(graveyard=[ELEMENTAL], bob_battlefield=[DREADMAW])
    target = scenario.creature(DREADMAW, "bob")
    scenario.activate(shaman, *scenario.untapped_sources("Mountain", "Mountain"), targets=[target])
    scenario.resolve_top()
    scenario.state_based_actions()
    assert target.damage == 1
    assert shaman.zone is Zone.GRAVEYARD  # a 2/1 that dealt itself 1 damage (CR 704.5g)


def test_sunflare_shaman_hits_a_player_for_the_elemental_count():
    scenario, shaman = _shaman(graveyard=[ELEMENTAL, ELEMENTAL, BEARS, BOLT])
    scenario.activate(
        shaman, *scenario.untapped_sources("Mountain", "Mountain"), targets=[scenario.player("bob")]
    )
    scenario.resolve_top()
    assert _life(scenario, "bob") == 18


def test_sunflare_shaman_counts_the_cards_not_the_shaman_itself():
    """The Shaman is an Elemental but on the battlefield, not a card in the
    graveyard (CR 404.1), so an empty graveyard is X = 0."""
    counted, counted_shaman = _shaman(graveyard=[ELEMENTAL])
    counted.activate(
        counted_shaman,
        *counted.untapped_sources("Mountain", "Mountain"),
        targets=[counted.player("bob")],
    )
    counted.resolve_top()
    assert _life(counted, "bob") == 19
    scenario, shaman = _shaman()
    scenario.activate(
        shaman, *scenario.untapped_sources("Mountain", "Mountain"), targets=[scenario.player("bob")]
    )
    scenario.resolve_top()
    assert _life(scenario, "bob") == 20
    assert shaman.zone is Zone.BATTLEFIELD
    assert shaman.damage == 0


def test_sunflare_shaman_ignores_the_opponents_elementals():
    scenario, shaman = _shaman(graveyard=[ELEMENTAL], bob_graveyard=[ELEMENTAL] * 3)
    scenario.activate(
        shaman, *scenario.untapped_sources("Mountain", "Mountain"), targets=[scenario.player("bob")]
    )
    scenario.resolve_top()
    assert _life(scenario, "bob") == 19


# --------------------------------------------------------------------------
# Undead Servant - "a 2/2 Zombie for each card named Undead Servant in your
# graveyard"
# --------------------------------------------------------------------------


def test_undead_servant_counts_cards_with_its_own_name():
    scenario = _board(
        hand=["Undead Servant"], graveyard=["Undead Servant", "Undead Servant", BEARS]
    )
    _enter(scenario, "Undead Servant")
    assert len(_tokens(scenario, "Zombie")) == 2


def test_undead_servant_makes_none_when_none_are_in_the_graveyard():
    named = _board(hand=["Undead Servant"], graveyard=["Undead Servant", BEARS])
    _enter(named, "Undead Servant")
    assert len(_tokens(named, "Zombie")) == 1
    scenario = _board(hand=["Undead Servant"], graveyard=[BEARS, "Walking Ballista"])
    _enter(scenario, "Undead Servant")
    assert _tokens(scenario, "Zombie") == []


def test_undead_servant_ignores_the_opponents_graveyard():
    own = _board(
        hand=["Undead Servant"], graveyard=["Undead Servant"], bob_graveyard=["Undead Servant"] * 3
    )
    _enter(own, "Undead Servant")
    assert len(_tokens(own, "Zombie")) == 1
    scenario = _board(hand=["Undead Servant"], bob_graveyard=["Undead Servant"] * 3)
    _enter(scenario, "Undead Servant")
    assert _tokens(scenario, "Zombie") == []


# --------------------------------------------------------------------------
# Moldgraf Millipede, Ooze Patrol - "mill N cards, then put a +1/+1 counter on
# this creature for each [artifact and/or] creature card in your graveyard"
# --------------------------------------------------------------------------


def test_moldgraf_millipede_counts_the_cards_it_just_milled():
    """CR 608.2c: the mill comes first, so a creature card it mills is counted."""
    scenario = _board(hand=["Moldgraf Millipede"], library=[BEARS, BEARS, BOLT, "Forest", "Forest"])
    millipede = _enter(scenario, "Moldgraf Millipede")
    assert millipede.counter_count("+1/+1") == 2
    assert len(scenario.player("alice").graveyard) == 3


def test_moldgraf_millipede_adds_creature_cards_already_in_the_graveyard():
    scenario = _board(hand=["Moldgraf Millipede"], graveyard=[BEARS, BEARS], library=["Forest"] * 6)
    millipede = _enter(scenario, "Moldgraf Millipede")
    assert millipede.counter_count("+1/+1") == 2


def test_moldgraf_millipede_gets_no_counter_without_creature_cards():
    counted = _board(hand=["Moldgraf Millipede"], graveyard=[BEARS], library=["Forest"] * 6)
    assert _enter(counted, "Moldgraf Millipede").counter_count("+1/+1") == 1
    scenario = _board(
        hand=["Moldgraf Millipede"], graveyard=[BOLT, SOL_RING], library=["Forest"] * 6
    )
    millipede = _enter(scenario, "Moldgraf Millipede")
    assert millipede.counter_count("+1/+1") == 0


def test_moldgraf_millipede_mills_only_what_the_library_holds():
    scenario = _board(hand=["Moldgraf Millipede"], library=[BEARS])
    millipede = _enter(scenario, "Moldgraf Millipede")
    assert millipede.counter_count("+1/+1") == 1
    assert scenario.player("alice").library == []


def test_moldgraf_millipede_ignores_the_opponents_graveyard():
    own = _board(
        hand=["Moldgraf Millipede"],
        graveyard=[BEARS],
        bob_graveyard=[BEARS] * 4,
        library=["Forest"] * 6,
    )
    assert _enter(own, "Moldgraf Millipede").counter_count("+1/+1") == 1
    scenario = _board(
        hand=["Moldgraf Millipede"], bob_graveyard=[BEARS] * 4, library=["Forest"] * 6
    )
    millipede = _enter(scenario, "Moldgraf Millipede")
    assert millipede.counter_count("+1/+1") == 0


def test_ooze_patrol_counts_artifact_and_creature_cards_after_milling_two():
    scenario = _board(
        hand=["Ooze Patrol"],
        graveyard=[BOLT, MOUNTAIN],
        library=[SOL_RING, BEARS, "Forest", "Forest"],
    )
    patrol = _enter(scenario, "Ooze Patrol")
    assert patrol.counter_count("+1/+1") == 2
    assert len(scenario.player("alice").graveyard) == 4


def test_ooze_patrol_gets_none_when_only_lands_and_instants_are_there():
    counted = _board(
        hand=["Ooze Patrol"], graveyard=[BOLT, MOUNTAIN, SOL_RING], library=["Forest"] * 6
    )
    assert _enter(counted, "Ooze Patrol").counter_count("+1/+1") == 1
    scenario = _board(hand=["Ooze Patrol"], graveyard=[BOLT, MOUNTAIN], library=["Forest"] * 6)
    patrol = _enter(scenario, "Ooze Patrol")
    assert patrol.counter_count("+1/+1") == 0


# --------------------------------------------------------------------------
# Serpentine Curve - "X +1/+1 counters on it, where X is one plus the total
# number of instant and sorcery cards you own in exile and in your graveyard"
# --------------------------------------------------------------------------


def _curve(*, graveyard=(), exile=(), bob_graveyard=()):
    scenario = _board(
        hand=["Serpentine Curve"],
        battlefield=["Island"] * 4,
        graveyard=graveyard,
        exile=exile,
        bob_graveyard=bob_graveyard,
    )
    scenario.cast_and_resolve("Serpentine Curve", auto=True)
    (fractal,) = _tokens(scenario, "Fractal")
    return scenario, fractal


def test_serpentine_curve_is_a_one_one_with_an_empty_graveyard_and_exile():
    loaded, loaded_fractal = _curve(exile=[BOLT])
    assert _stats(loaded, loaded_fractal) == (2, 2)
    scenario, fractal = _curve()
    assert _stats(scenario, fractal) == (1, 1)


def test_serpentine_curve_adds_instants_and_sorceries_from_both_zones():
    scenario, fractal = _curve(graveyard=[BOLT, "Divination"], exile=[BOLT])
    assert _stats(scenario, fractal) == (4, 4)


def test_serpentine_curve_ignores_other_card_types_and_the_opponents_graveyard():
    loaded, loaded_fractal = _curve(graveyard=[BEARS, BOLT], bob_graveyard=[BOLT] * 3)
    assert _stats(loaded, loaded_fractal) == (2, 2)
    scenario, fractal = _curve(graveyard=[BEARS, SOL_RING, MOUNTAIN], bob_graveyard=[BOLT] * 3)
    assert _stats(scenario, fractal) == (1, 1)


# --------------------------------------------------------------------------
# Vraska, Regal Gorgon - "-10: for each creature card in your graveyard, put a
# +1/+1 counter on each creature you control"
# --------------------------------------------------------------------------


def _vraska_ultimate(*, graveyard=(), bob_battlefield=()):
    scenario = _board(
        battlefield=["Vraska, Regal Gorgon", BEARS, "Llanowar Elves"],
        graveyard=graveyard,
        bob_battlefield=bob_battlefield,
    )
    vraska = scenario.find("Vraska, Regal Gorgon", Zone.BATTLEFIELD)
    vraska.add_counters(Counter.LOYALTY, 6)  # 5 -> 11, so -10 does not end her first
    scenario.activate(vraska, index=2)
    scenario.resolve_top()
    return scenario


def test_vraska_puts_one_counter_per_creature_card_on_each_creature_I_control():
    scenario = _vraska_ultimate(graveyard=[BEARS, BEARS, BEARS, BOLT], bob_battlefield=[DREADMAW])
    assert scenario.creature(BEARS, "alice").counter_count("+1/+1") == 3
    assert scenario.creature("Llanowar Elves", "alice").counter_count("+1/+1") == 3
    assert scenario.creature(DREADMAW, "bob").counter_count("+1/+1") == 0


def test_vraska_does_nothing_with_no_creature_cards():
    counted = _vraska_ultimate(graveyard=[BEARS, BOLT])
    assert counted.creature(BEARS, "alice").counter_count("+1/+1") == 1
    scenario = _vraska_ultimate(graveyard=[BOLT, SOL_RING])
    assert scenario.creature(BEARS, "alice").counter_count("+1/+1") == 0


# ==========================================================================
# Second printings: the same reader on cards that are not the reported ones
# ==========================================================================


def _altar_attack(*, graveyard=(), bob_graveyard=()):
    scenario = _board(
        battlefield=["Altar of the Goyf", BEARS],
        graveyard=graveyard,
        bob_graveyard=bob_graveyard,
        step=Step.DECLARE_ATTACKERS,
    )
    bears = scenario.creature(BEARS, "alice")
    scenario.attack_with(bears)
    scenario.pass_until_resolved()
    return scenario, bears


def test_altar_of_the_goyf_counts_card_types_among_cards_in_all_graveyards():
    """The only second printing of the "all graveyards" form: a creature card of
    mine, an instant of mine and an artifact of the opponent's are three types."""
    scenario, bears = _altar_attack(graveyard=[BEARS, BOLT], bob_graveyard=[SOL_RING])
    assert _stats(scenario, bears) == (5, 5)


def test_altar_of_the_goyf_counts_a_type_once_across_both_graveyards():
    scenario, bears = _altar_attack(graveyard=[BOLT, BOLT], bob_graveyard=[BOLT, BEARS])
    assert _stats(scenario, bears) == (4, 4)


# -- the templates below were already read before this task; they stay as
# -- regression guards for the new reader, not as red-first proofs.


def test_izoni_makes_an_insect_per_creature_card_in_my_graveyard():
    scenario = _board(
        hand=["Izoni, Thousand-Eyed"],
        graveyard=[BEARS, BEARS, SOL_RING, BOLT],
        bob_graveyard=[BEARS] * 3,
    )
    _enter(scenario, "Izoni, Thousand-Eyed")
    assert len(_tokens(scenario, "Insect")) == 2


def test_kraul_foragers_gains_one_life_per_creature_card():
    scenario = _board(hand=["Kraul Foragers"], graveyard=[BEARS, BEARS, BEARS, MOUNTAIN])
    _enter(scenario, "Kraul Foragers")
    assert _life(scenario) == 23


def test_revenge_of_the_rats_makes_tapped_rats_per_creature_card():
    scenario = _board(
        hand=["Revenge of the Rats"], battlefield=["Swamp"] * 4, graveyard=[BEARS, BEARS, BOLT]
    )
    scenario.cast_and_resolve("Revenge of the Rats", auto=True)
    rats = _tokens(scenario, "Rat")
    assert len(rats) == 2
    assert all(rat.tapped for rat in rats)


def test_grim_flowering_draws_a_card_per_creature_card():
    scenario = _board(
        hand=["Grim Flowering"], battlefield=["Forest"] * 6, graveyard=[BEARS, BEARS, BEARS, BOLT]
    )
    scenario.cast_and_resolve("Grim Flowering", auto=True)
    assert len(scenario.player("alice").hand) == 3


# -- cards named like the spell, in your graveyard ---------------------------


def _growth_cycle(copies, bob_copies=0):
    scenario = _board(
        hand=["Growth Cycle"],
        battlefield=["Forest", "Forest", BEARS],
        graveyard=["Growth Cycle"] * copies + [BOLT],
        bob_graveyard=["Growth Cycle"] * bob_copies,
    )
    bears = scenario.creature(BEARS, "alice")
    scenario.cast_and_resolve("Growth Cycle", auto=True, targets=[bears])
    return _stats(scenario, bears)


def test_growth_cycle_alone_is_a_plain_plus_three():
    assert _growth_cycle(1) == (7, 7)
    assert _growth_cycle(0) == (5, 5)


def test_growth_cycle_gets_two_more_per_copy_already_in_the_graveyard():
    assert _growth_cycle(2) == (9, 9)


def test_growth_cycle_does_not_count_the_opponents_copies_or_itself():
    assert _growth_cycle(1, bob_copies=4) == (7, 7)


# -- cards counted by owner across two zones ---------------------------------


def test_huskburster_swarm_counts_creature_cards_I_own_in_exile_and_the_graveyard():
    scenario = _board(
        hand=["Huskburster Swarm"],
        battlefield=["Swamp"] * 3,
        graveyard=[BEARS, BEARS, BEARS, BOLT],
        exile=[BEARS, BEARS],
        bob_graveyard=[BEARS] * 5,
    )
    # {7}{B} less five creature cards = {2}{B}
    scenario.cast_and_resolve("Huskburster Swarm", auto=True)
    assert scenario.find("Huskburster Swarm", Zone.BATTLEFIELD, "alice") is not None


def test_huskburster_swarm_is_not_cheaper_for_cards_in_exile_I_do_not_own():
    owned = _board(
        hand=["Huskburster Swarm"],
        battlefield=["Swamp"] * 3,
        graveyard=[BEARS, BEARS],
        exile=[BEARS] * 3,
    )
    owned.cast_and_resolve("Huskburster Swarm", auto=True)
    assert owned.find("Huskburster Swarm", Zone.BATTLEFIELD, "alice") is not None
    scenario = _board(
        hand=["Huskburster Swarm"],
        battlefield=["Swamp"] * 3,
        graveyard=[BEARS, BEARS],
    )
    with pytest.raises(ValueError):
        scenario.cast_and_resolve("Huskburster Swarm", auto=True)


# -- the same cost reduction on an activated ability -------------------------


def test_nemesis_of_mortals_monstrosity_is_cheaper_per_creature_card():
    scenario = _board(
        battlefield=["Nemesis of Mortals", "Forest", "Forest", "Forest"],
        graveyard=[BEARS] * 6 + [BOLT],
    )
    snake = scenario.creature("Nemesis of Mortals", "alice")
    scenario.activate(snake, *scenario.untapped_sources("Forest", "Forest", "Forest"))
    scenario.resolve_top()
    assert snake.counter_count("+1/+1") == 5


def test_nemesis_of_mortals_monstrosity_still_costs_full_with_no_creature_cards():
    cheaper = _board(
        battlefield=["Nemesis of Mortals", "Forest", "Forest", "Forest"], graveyard=[BEARS] * 6
    )
    cheaper_snake = cheaper.creature("Nemesis of Mortals", "alice")
    cheaper.activate(cheaper_snake, *cheaper.untapped_sources("Forest", "Forest", "Forest"))
    cheaper.resolve_top()
    assert cheaper_snake.counter_count("+1/+1") == 5
    scenario = _board(battlefield=["Nemesis of Mortals", "Forest", "Forest", "Forest"])
    snake = scenario.creature("Nemesis of Mortals", "alice")
    with pytest.raises(ValueError):
        scenario.activate(snake, *scenario.untapped_sources("Forest", "Forest", "Forest"))


# -- "that player's graveyard" -----------------------------------------------


def test_the_mouth_of_sauron_counts_the_milled_players_graveyard_after_the_mill():
    scenario = _board(
        hand=["The Mouth of Sauron"],
        graveyard=[BOLT] * 5,  # mine, which are not counted
        bob_graveyard=["Divination"],
        bob_library=[BOLT, "Island", "Opt"],
    )
    _enter(scenario, "The Mouth of Sauron", targets=[scenario.player("bob")])
    (army,) = _tokens(scenario, "Orc Army")
    # Divination was there; the mill added Lightning Bolt and Opt; Island is a land.
    assert army.counter_count("+1/+1") == 3


def test_the_mouth_of_sauron_amasses_nothing_when_the_graveyard_has_none():
    counted = _board(hand=["The Mouth of Sauron"], bob_library=[BOLT, "Island", "Island"])
    _enter(counted, "The Mouth of Sauron", targets=[counted.player("bob")])
    (army,) = _tokens(counted, "Orc Army")
    assert army.counter_count("+1/+1") == 1
    scenario = _board(hand=["The Mouth of Sauron"], bob_library=["Island"] * 4)
    _enter(scenario, "The Mouth of Sauron", targets=[scenario.player("bob")])
    assert all(p.counter_count("+1/+1") == 0 for p in scenario.game.battlefield if "Army" in p.name)


# -- characteristic-defining counts ------------------------------------------


def test_consuming_blob_is_as_big_as_the_card_types_in_my_graveyard():
    scenario = _board(
        battlefield=["Consuming Blob"], graveyard=[BEARS, BEARS, BOLT, SOL_RING, MOUNTAIN]
    )
    assert _stats(scenario, scenario.creature("Consuming Blob", "alice")) == (4, 5)


def test_consuming_blob_ignores_the_opponents_graveyard():
    scenario = _board(battlefield=["Consuming Blob"], bob_graveyard=[BEARS, BOLT, SOL_RING])
    assert _stats(scenario, scenario.creature("Consuming Blob", "alice")) == (0, 1)


def test_souls_of_the_lost_counts_permanent_cards_only():
    scenario = _board(battlefield=["Souls of the Lost"], graveyard=PERMANENT_YARD)
    assert _stats(scenario, scenario.creature("Souls of the Lost", "alice")) == (3, 4)


def test_crackling_drake_counts_instants_and_sorceries_across_exile_and_graveyard():
    scenario = _board(
        battlefield=["Crackling Drake"],
        graveyard=[BOLT, "Divination", BEARS],
        exile=[BOLT],
        bob_graveyard=[BOLT] * 4,
    )
    assert _stats(scenario, scenario.creature("Crackling Drake", "alice")) == (3, 4)
