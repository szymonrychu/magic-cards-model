"""Token and Role creation shapes the damage chunk (NW-01) leaves silent, plus
the two "this way" readers of Torrent Sculptor // Flamethrower Sonata.

Listed cards: Carrion Call (two infect Insect tokens), Cut In (damage, then a
Role on "up to one target"), Extus, Oriq Overlord // Awaken the Blood Avatar
(a token that carries a quoted attack trigger), Torrent Sculptor // Flamethrower
Sonata (ETB exile-then-counters; discard-then-draw with a reflexive trigger).

Second printings that prove each reader is the template and not the card:
Trigon of Infestation and Phyrexian Swarmlord (infect tokens), Shatter the Oath
(a different first sentence, same trailing Role), Protective Parents (the Role
in a triggered ability), Into the Fae Court (a token "with flying and "<quoted
ability>"" behind another sentence), Glacial Dragonhunt (a "may discard" with a
fixed-damage reflexive trigger) and Teo, Spirited Glider (the same shape as a
triggered ability).

Rules verified with `mise run rules:find` in the session that wrote this file:

- CR 111.3 - a token's defining text; a quoted ability belongs to the token.
- CR 111.10r - the Young Hero Role token.
- CR 120.3b / 120.3d / 702.90b - infect: poison to players, -1/-1 counters to
  creatures.
- CR 303.7 / 303.7a - Roles are Auras; a second Role you control on the same
  permanent sends the older one to the graveyard.
- CR 603.12 - reflexive triggers ("when you discard ... this way").
- CR 608.2b - an illegal target is not affected.
- CR 701.7a - creating tokens.
- CR 701.9a - discard.
- CR 202.3 - mana value.
- CR 508.1m - attack triggers.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import Keyword, has_keyword
from magic_cards_model.models import Color, Zone
from magic_cards_model.models.token import is_token
from tests.scenarios.harness import Scenario


def _tokens(scenario, name: str, username: str = "alice") -> list:
    return [
        state
        for state in scenario.game.battlefield
        if state.name == name and state.controller == username
    ]


def _roles_on(scenario, creature) -> list:
    return [
        state
        for state in scenario.game.battlefield
        if "Role" in state.card.subtypes and state.attached_to == creature.id
    ]


# --------------------------------------------------------------------------
# Carrion Call: "Create two 1/1 green Phyrexian Insect creature tokens with infect."
# --------------------------------------------------------------------------


def _carrion_board(**bob) -> Scenario:
    return (
        Scenario()
        .player("alice", hand=["Carrion Call"], battlefield=["Forest"] * 4, library=["Forest"] * 5)
        .player("bob", library=["Forest"] * 5, **bob)
    )


def test_carrion_call_creates_two_green_phyrexian_insect_tokens_with_infect():
    scenario = _carrion_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.cast_and_resolve("Carrion Call", auto=True, username="alice")

    tokens = _tokens(scenario, "Phyrexian Insect Token")
    assert len(tokens) == 2
    for token in tokens:
        assert is_token(token)
        assert (token.power, token.toughness) == (1, 1)
        assert token.card.colors == [Color.GREEN]
        assert token.card.subtypes == ["Phyrexian", "Insect"]
        assert has_keyword(token, Keyword.INFECT)


def test_carrion_call_tokens_deal_damage_to_a_player_as_poison_counters():
    """CR 120.3b / 702.90b: bob's life total is untouched, each Insect gives one
    poison counter. The tokens are made on bob's turn so alice can attack with
    them on hers (CR 302.6)."""
    scenario = _carrion_board().build()
    scenario.start_at(Step.END_STEP)
    scenario.cast_and_resolve("Carrion Call", auto=True, username="alice")
    _advance_to_declare_attackers_of(scenario, "alice")

    tokens = _tokens(scenario, "Phyrexian Insect Token")
    scenario.attack_with(*tokens)
    scenario.no_blocks()
    scenario.combat_damage()

    assert scenario.player("bob").poison == 2
    assert scenario.player("bob").life == 20


def test_carrion_call_token_deals_damage_to_a_creature_as_minus_one_counters():
    """CR 120.3d: the blocker gets a -1/-1 counter, not marked damage."""
    scenario = _carrion_board(battlefield=["Hill Giant"]).build()
    scenario.start_at(Step.END_STEP)
    scenario.cast_and_resolve("Carrion Call", auto=True, username="alice")
    _advance_to_declare_attackers_of(scenario, "alice")

    token = _tokens(scenario, "Phyrexian Insect Token")[0]
    giant = scenario.creature("Hill Giant", "bob")
    scenario.attack_with(token)
    scenario.block(token, giant)
    scenario.combat_damage()

    assert scenario.game.power_of(giant) == 2
    assert scenario.game.toughness_of(giant) == 2
    assert giant.damage == 0


def _advance_to_declare_attackers_of(scenario, username: str) -> None:
    for _ in range(40):
        if scenario.step is Step.DECLARE_ATTACKERS and scenario.turn.active_player == username:
            return
        scenario.advance()
    raise AssertionError(f"never reached {username}'s declare attackers step")


# --- second printings: the same "with infect" tail on a different source -----


def test_trigon_of_infestation_creates_one_infect_insect():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Trigon of Infestation", "Forest", "Forest", "Forest", "Forest"],
            library=["Forest"] * 5,
        )
        .player("bob", library=["Forest"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    trigon = scenario.find("Trigon of Infestation", Zone.BATTLEFIELD, "alice")
    scenario.game.add_counters(trigon, "charge", 3)
    scenario.activate(trigon, index=1, auto=True, username="alice")
    scenario.pass_until_resolved()

    (token,) = _tokens(scenario, "Phyrexian Insect Token")
    assert has_keyword(token, Keyword.INFECT)
    assert token.card.subtypes == ["Phyrexian", "Insect"]


# --------------------------------------------------------------------------
# Cut In: "deals 4 damage to target creature. Create a Young Hero Role token
# attached to up to one target creature you control."
# --------------------------------------------------------------------------


def _cut_in_board(**extra) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=["Cut In"],
            battlefield=["Mountain"] * 4 + ["Grizzly Bears", "Savannah Lions"],
            library=["Mountain"] * 5,
        )
        .player("bob", battlefield=["Hill Giant"], library=["Island"] * 5, **extra)
    )


def test_cut_in_damages_one_creature_and_attaches_a_young_hero_to_the_other():
    scenario = _cut_in_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    giant = scenario.creature("Hill Giant", "bob")
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.cast_and_resolve("Cut In", auto=True, username="alice", targets=[giant, bears])

    assert giant.zone is not Zone.BATTLEFIELD
    assert bears.damage == 0, "the damage went to the first target only"
    (role,) = _roles_on(scenario, bears)
    assert role.name == "Young Hero"
    assert role.controller == "alice"
    assert role.card.subtypes == ["Aura", "Role"]


def test_cut_in_with_no_second_target_deals_damage_and_makes_no_role():
    """CR 115.6: "up to one" allows zero targets, and then there is nothing to
    attach the Role to, so no token is created."""
    scenario = _cut_in_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    giant = scenario.creature("Hill Giant", "bob")

    scenario.cast_and_resolve("Cut In", auto=True, username="alice", targets=[giant])

    assert giant.zone is not Zone.BATTLEFIELD
    assert "Young Hero" not in scenario.battlefield_names()


def test_cut_in_can_aim_both_halves_at_the_same_creature_it_controls():
    """Both instances of "target creature" may name the same permanent (CR 115.3
    only forbids repeating a target within one instance of the word)."""
    scenario = _cut_in_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.cast_and_resolve("Cut In", auto=True, username="alice", targets=[bears, bears])

    assert bears.zone is not Zone.BATTLEFIELD
    assert "Young Hero" not in scenario.battlefield_names(), "its target died first"


def test_cut_in_cannot_put_the_role_on_a_creature_alice_does_not_control():
    scenario = (
        Scenario()
        .player("alice", hand=["Cut In"], battlefield=["Mountain"] * 4, library=["Mountain"] * 5)
        .player("bob", battlefield=["Hill Giant", "Grizzly Bears"], library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    giant = scenario.creature("Hill Giant", "bob")
    theirs = scenario.creature("Grizzly Bears", "bob")

    with pytest.raises(ValueError):
        scenario.cast("Cut In", username="alice", targets=[giant, theirs])


def test_a_second_role_replaces_the_first_one_alice_controls_on_that_creature():
    """CR 303.7a: the older Role goes to the graveyard, the newer stays."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Cut In", "Cut In"],
            battlefield=["Mountain"] * 8 + ["Grizzly Bears"],
            library=["Mountain"] * 5,
        )
        .player("bob", battlefield=["Hill Giant", "Hill Giant"], library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    giants = scenario.creatures("Hill Giant", "Hill Giant", username="bob")

    scenario.cast_and_resolve("Cut In", auto=True, username="alice", targets=[giants[0], bears])
    (first,) = _roles_on(scenario, bears)
    scenario.cast_and_resolve("Cut In", auto=True, username="alice", targets=[giants[1], bears])

    (second,) = _roles_on(scenario, bears)
    assert second is not first
    assert first.zone is not Zone.BATTLEFIELD


def test_young_hero_role_puts_a_counter_on_a_small_attacker():
    """CR 111.10r: "Enchanted creature has 'Whenever this creature attacks, if
    its toughness is 3 or less, put a +1/+1 counter on it.'" A 2/2 qualifies."""
    scenario = _cut_in_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    giant = scenario.creature("Hill Giant", "bob")
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.cast_and_resolve("Cut In", auto=True, username="alice", targets=[giant, bears])
    scenario.start_at(Step.DECLARE_ATTACKERS)

    scenario.attack_with(bears)
    scenario.pass_until_resolved()

    assert scenario.game.power_of(bears) == 3
    assert scenario.game.toughness_of(bears) == 3


# --- second printings: the Role clause beside other instructions ------------


def test_shatter_the_oath_destroys_then_attaches_a_wicked_role_to_up_to_one_target():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Shatter the Oath"],
            battlefield=["Swamp"] * 5 + ["Grizzly Bears"],
            library=["Swamp"] * 5,
        )
        .player("bob", battlefield=["Hill Giant"], library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    giant = scenario.creature("Hill Giant", "bob")
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.cast_and_resolve(
        "Shatter the Oath", auto=True, username="alice", targets=[giant, bears]
    )

    assert giant.zone is not Zone.BATTLEFIELD
    (role,) = _roles_on(scenario, bears)
    assert role.name == "Wicked"
    assert scenario.game.power_of(bears) == 3


def test_shatter_the_oath_with_one_target_makes_no_role():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Shatter the Oath"],
            battlefield=["Swamp"] * 5,
            library=["Swamp"] * 5,
        )
        .player("bob", battlefield=["Hill Giant"], library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    giant = scenario.creature("Hill Giant", "bob")

    scenario.cast_and_resolve("Shatter the Oath", auto=True, username="alice", targets=[giant])

    assert giant.zone is not Zone.BATTLEFIELD
    assert "Wicked" not in scenario.battlefield_names()


def test_protective_parents_dies_trigger_attaches_a_young_hero_to_a_target():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Protective Parents", "Grizzly Bears"],
            library=["Plains"] * 5,
        )
        .player("bob", library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    parents = scenario.creature("Protective Parents", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.choose_trigger_targets("Protective Parents", [bears])
    scenario.game.destroy(parents)
    scenario.pass_until_resolved()

    (role,) = _roles_on(scenario, bears)
    assert role.name == "Young Hero"


# --------------------------------------------------------------------------
# Extus // Awaken the Blood Avatar: a token carrying a quoted attack trigger
# --------------------------------------------------------------------------


def _awaken_board() -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=["Extus, Oriq Overlord // Awaken the Blood Avatar"],
            battlefield=["Swamp"] * 7 + ["Mountain"],
            library=["Swamp"] * 5,
        )
        .player("bob", battlefield=["Grizzly Bears"], library=["Island"] * 5)
    )


def _cast_awaken(scenario) -> None:
    casting = scenario.cast("Extus, Oriq Overlord", username="alice")
    casting.cast_as_split_half("Awaken the Blood Avatar")
    payment = casting.begin_paying()
    scenario.auto_pay(payment, username="alice")
    scenario.put_on_stack(casting)
    scenario.resolve_top()


def test_awaken_the_blood_avatar_makes_a_3_6_black_and_red_haste_avatar():
    scenario = _awaken_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    _cast_awaken(scenario)

    (avatar,) = _tokens(scenario, "Avatar Token")
    assert (avatar.power, avatar.toughness) == (3, 6)
    assert sorted(color.value for color in avatar.card.colors) == ["B", "R"]
    assert avatar.card.subtypes == ["Avatar"]
    assert has_keyword(avatar, Keyword.HASTE)
    assert _opponent_bears(scenario).zone is not Zone.BATTLEFIELD, (
        "bob sacrificed his only creature"
    )


def _opponent_bears(scenario):
    return next(
        state
        for state in scenario.all_card_states()
        if state.name == "Grizzly Bears" and state.owner == "bob"
    )


def test_the_avatar_deals_three_damage_to_each_opponent_whenever_it_attacks():
    """The quoted "Whenever this token attacks, it deals 3 damage to each
    opponent." is the token's own ability (CR 111.3) and fires on the declaration
    of attackers (CR 508.1m); haste lets it attack the turn it arrives."""
    scenario = _awaken_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _cast_awaken(scenario)
    scenario.start_at(Step.DECLARE_ATTACKERS)
    (avatar,) = _tokens(scenario, "Avatar Token")

    scenario.attack_with(avatar)
    scenario.pass_until_resolved()

    assert scenario.player("bob").life == 17


def test_the_avatar_trigger_fires_again_each_time_it_attacks():
    scenario = _awaken_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _cast_awaken(scenario)
    scenario.start_at(Step.DECLARE_ATTACKERS)
    (avatar,) = _tokens(scenario, "Avatar Token")
    scenario.attack_with(avatar)
    scenario.pass_until_resolved()
    scenario.no_blocks()
    scenario.combat_damage()

    assert scenario.player("bob").life == 20 - 3 - 3, "3 from the trigger, 3 combat damage"


def test_into_the_fae_court_token_keeps_flying_and_its_quoted_ability_behind_a_draw():
    """Second printing for "a token with a keyword and a quoted ability": the
    clause sits behind another sentence, and the "and" before the quote is part
    of the token's text, not a second instruction (CR 111.3, CR 608.2c)."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Into the Fae Court"],
            battlefield=["Island"] * 5,
            library=["Island"] * 5,
        )
        .player("bob", library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.cast_and_resolve("Into the Fae Court", auto=True, username="alice")

    (faerie,) = _tokens(scenario, "Faerie Token")
    assert has_keyword(faerie, Keyword.FLYING)
    assert "This token can block only creatures with flying." in faerie.card.oracle_text
    assert len(scenario.player("alice").hand) == 3


# --------------------------------------------------------------------------
# Torrent Sculptor: "exile an instant or sorcery card from your graveyard. Put a
# number of +1/+1 counters on this creature equal to half that card's mana
# value, rounded up."
# --------------------------------------------------------------------------


def _sculptor_board(graveyard: list[str]) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=["Torrent Sculptor // Flamethrower Sonata"],
            battlefield=["Island"] * 4,
            graveyard=graveyard,
            library=["Island"] * 5,
        )
        .player("bob", library=["Island"] * 5)
    )


def _cast_sculptor(scenario) -> None:
    scenario.cast_and_resolve("Torrent Sculptor", auto=True, username="alice")
    scenario.pass_until_resolved()


def _sculptor(scenario):
    return scenario.find("Torrent Sculptor", Zone.BATTLEFIELD, "alice")


def test_sculptor_exiles_the_card_and_gets_counters_equal_to_half_its_value_rounded_up():
    """Divination has mana value 3, so two counters (3 / 2 rounded up)."""
    scenario = _sculptor_board(["Divination"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    _cast_sculptor(scenario)

    sculptor = _sculptor(scenario)
    assert scenario.find("Divination", Zone.EXILE, "alice")
    assert scenario.game.power_of(sculptor) == 2 + 2
    assert scenario.game.toughness_of(sculptor) == 2 + 2


def test_sculptor_with_an_even_mana_value_gets_exactly_half():
    scenario = _sculptor_board(["Counterspell"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    _cast_sculptor(scenario)

    assert scenario.game.power_of(_sculptor(scenario)) == 2 + 1


def test_sculptor_with_no_instant_or_sorcery_in_the_graveyard_exiles_and_counts_nothing():
    """No exile, so "that card" does not exist and no counters are put on it; a
    creature card in the graveyard is not an instant or sorcery."""
    scenario = _sculptor_board(["Grizzly Bears"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    _cast_sculptor(scenario)

    assert scenario.game.power_of(_sculptor(scenario)) == 2
    assert scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")


def test_sculptor_exiles_only_one_of_several_cards_and_the_player_picks_which():
    scenario = _sculptor_board(["Divination", "Lightning Bolt"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bolt = scenario.find("Lightning Bolt", Zone.GRAVEYARD, "alice")
    scenario.will_choose_cards(bolt)

    _cast_sculptor(scenario)

    assert bolt.zone is Zone.EXILE
    assert scenario.find("Divination", Zone.GRAVEYARD, "alice")
    assert scenario.game.power_of(_sculptor(scenario)) == 2 + 1, "Lightning Bolt: 1 / 2, rounded up"


def test_sculptor_ignores_the_opponents_graveyard():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Torrent Sculptor // Flamethrower Sonata"],
            battlefield=["Island"] * 4,
            library=["Island"] * 5,
        )
        .player("bob", graveyard=["Divination"], library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    _cast_sculptor(scenario)

    assert scenario.game.power_of(_sculptor(scenario)) == 2


# --------------------------------------------------------------------------
# Flamethrower Sonata: "Discard a card, then draw a card. When you discard an
# instant or sorcery card this way, Flamethrower Sonata deals damage equal to
# that card's mana value to target creature or planeswalker you don't control."
# --------------------------------------------------------------------------


def _sonata_board(hand: list[str], bob: list[str] | None = None) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=["Torrent Sculptor // Flamethrower Sonata", *hand],
            battlefield=["Mountain"] * 2,
            library=["Mountain"] * 5,
        )
        .player("bob", battlefield=bob or [], library=["Island"] * 5)
    )


def _cast_sonata(scenario, *, discarding: str) -> None:
    card = scenario.find(discarding, Zone.HAND, "alice")
    scenario.will_discard(card)
    casting = scenario.cast("Torrent Sculptor", username="alice")
    casting.cast_as_split_half("Flamethrower Sonata")
    payment = casting.begin_paying()
    scenario.auto_pay(payment, username="alice")
    scenario.put_on_stack(casting)
    scenario.resolve_top()


def test_sonata_discarding_a_sorcery_deals_its_mana_value_to_a_creature():
    """Divination has mana value 3; Hill Giant is 3/3 and dies."""
    scenario = _sonata_board(["Divination"], bob=["Hill Giant"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    giant = scenario.creature("Hill Giant", "bob")
    scenario.choose_trigger_targets("Flamethrower Sonata", [giant])

    _cast_sonata(scenario, discarding="Divination")
    scenario.pass_until_resolved()

    assert scenario.find("Divination", Zone.GRAVEYARD, "alice")
    assert giant.zone is not Zone.BATTLEFIELD
    assert len(scenario.player("alice").hand) == 1, "cast one, discarded the other, drew one"


def test_sonata_discarding_a_land_deals_no_damage():
    """Only an instant or sorcery card discarded this way sets off the trigger."""
    scenario = _sonata_board(["Mountain"], bob=["Hill Giant"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    giant = scenario.creature("Hill Giant", "bob")

    _cast_sonata(scenario, discarding="Mountain")
    scenario.pass_until_resolved()

    assert giant.zone is Zone.BATTLEFIELD
    assert giant.damage == 0


def test_sonata_discarding_a_creature_deals_no_damage():
    scenario = _sonata_board(["Grizzly Bears"], bob=["Hill Giant"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    giant = scenario.creature("Hill Giant", "bob")

    _cast_sonata(scenario, discarding="Grizzly Bears")
    scenario.pass_until_resolved()

    assert giant.damage == 0


def test_sonata_damage_equals_the_discarded_cards_mana_value_not_a_fixed_number():
    scenario = _sonata_board(["Lightning Bolt"], bob=["Hill Giant"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    giant = scenario.creature("Hill Giant", "bob")
    scenario.choose_trigger_targets("Flamethrower Sonata", [giant])

    _cast_sonata(scenario, discarding="Lightning Bolt")
    scenario.pass_until_resolved()

    assert giant.damage == 1, "Lightning Bolt has mana value 1"


def test_sonata_with_an_empty_hand_after_casting_discards_and_draws_nothing_to_discard():
    """No card to discard means no "this way", so no reflexive trigger."""
    scenario = _sonata_board([], bob=["Hill Giant"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    giant = scenario.creature("Hill Giant", "bob")
    casting = scenario.cast("Torrent Sculptor", username="alice")
    casting.cast_as_split_half("Flamethrower Sonata")
    payment = casting.begin_paying()
    scenario.auto_pay(payment, username="alice")
    scenario.put_on_stack(casting)
    scenario.resolve_top()
    scenario.pass_until_resolved()

    assert giant.damage == 0
    assert len(scenario.player("alice").hand) == 1, "drew the one card"


# --- second printings of the reflexive discard template ----------------------


def test_glacial_dragonhunt_may_discard_a_nonland_card_for_fixed_damage():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Glacial Dragonhunt", "Divination"],
            battlefield=["Mountain", "Island"],
            library=["Mountain"] * 5,
        )
        .player("bob", battlefield=["Hill Giant"], library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    giant = scenario.creature("Hill Giant", "bob")
    scenario.will_take_the_may(True)
    scenario.will_discard(scenario.find("Divination", Zone.HAND, "alice"))
    scenario.choose_trigger_targets("Glacial Dragonhunt", [giant])

    scenario.cast_and_resolve("Glacial Dragonhunt", auto=True, username="alice")
    scenario.pass_until_resolved()

    assert giant.zone is not Zone.BATTLEFIELD, "3 damage to a 3/3"


def test_glacial_dragonhunt_declining_the_discard_deals_no_damage():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Glacial Dragonhunt", "Divination"],
            battlefield=["Mountain", "Island"],
            library=["Mountain"] * 5,
        )
        .player("bob", battlefield=["Hill Giant"], library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    giant = scenario.creature("Hill Giant", "bob")
    scenario.will_take_the_may(False)

    scenario.cast_and_resolve("Glacial Dragonhunt", auto=True, username="alice")
    scenario.pass_until_resolved()

    assert giant.damage == 0
    assert scenario.find("Divination", Zone.HAND, "alice")


def test_glacial_dragonhunt_discarding_a_land_does_not_trigger_the_damage():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Glacial Dragonhunt", "Mountain"],
            battlefield=["Mountain", "Island"],
            library=["Mountain"] * 5,
        )
        .player("bob", battlefield=["Hill Giant"], library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    giant = scenario.creature("Hill Giant", "bob")
    scenario.will_take_the_may(True)
    scenario.will_discard(scenario.find("Mountain", Zone.HAND, "alice"))

    scenario.cast_and_resolve("Glacial Dragonhunt", auto=True, username="alice")
    scenario.pass_until_resolved()

    assert giant.damage == 0


def _teo_board(hand: list[str]):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=hand,
            battlefield=["Teo, Spirited Glider"],
            library=["Mountain"] * 5,
        )
        .player("bob", library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    return scenario, scenario.find("Teo, Spirited Glider", Zone.BATTLEFIELD, "alice")


def test_teo_spirited_glider_loots_and_puts_a_counter_when_a_nonland_card_is_discarded():
    """The same template as a triggered ability, with a different reflexive
    consequence ("put a +1/+1 counter on target creature you control") and no
    mana-value count: "draw a card, then discard a card. When you discard a
    nonland card this way, ...". Teo is the only creature, so it is the target."""
    scenario, teo = _teo_board(["Divination"])
    before = scenario.game.power_of(teo)
    scenario.will_discard(scenario.find("Divination", Zone.HAND, "alice"))

    scenario.attack_with(teo)
    scenario.pass_until_resolved()  # Teo's attack trigger: loot
    scenario.pass_until_resolved()  # the reflexive counter

    assert scenario.find("Divination", Zone.GRAVEYARD, "alice")
    assert scenario.game.power_of(teo) == before + 1


def test_teo_spirited_glider_discarding_a_land_puts_no_counter():
    scenario, teo = _teo_board(["Mountain"])
    before = scenario.game.power_of(teo)
    scenario.will_discard(scenario.find("Mountain", Zone.HAND, "alice"))

    scenario.attack_with(teo)
    scenario.pass_until_resolved()
    scenario.pass_until_resolved()

    assert scenario.game.power_of(teo) == before
