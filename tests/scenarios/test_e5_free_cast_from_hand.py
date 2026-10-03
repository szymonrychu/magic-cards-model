"""The Expertise cycle's closing sentence: "You may cast a spell with mana
value N or less from your hand without paying its mana cost."

- **CR 608.2g** a spell cast during resolution follows 601.2a-i with no
  priority; it goes on the stack above the resolving spell, which finishes.
- **CR 118.9** casting without paying its mana cost is an alternative cost.
- **CR 107.3b** X is 0 for a spell cast without paying its mana cost.
- **CR 608.2d** the player cannot choose an option that is illegal or
  impossible: a spell above the limit is not offered, and "may" can be declined.
- **CR 305.9** a land is never cast.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import DecisionKind
from magic_cards_model.models import Zone

from .harness import Scenario

YAHENNI = "Yahenni's Expertise"


def _yahenni(hand=("Lightning Bolt", "Serra Angel", "Forest")):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[YAHENNI, *hand],
            battlefield=["Swamp"] * 4 + ["Grizzly Bears"],
        )
        .player("bob", battlefield=["Hill Giant"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _cast(scenario):
    return scenario.cast_and_resolve(YAHENNI, *scenario.untapped_sources(*["Swamp"] * 4))


def test_all_creatures_shrink_then_a_cheap_spell_is_cast_free():
    scenario = _yahenni()
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "alice")
    scenario.will_choose_cards(bolt, username="alice", source=YAHENNI)
    scenario.will_choose_targets("bob", username="alice", source="Lightning Bolt")
    giant = scenario.creature("Hill Giant", "bob")
    bears = scenario.creature("Grizzly Bears", "alice")
    _cast(scenario)
    assert bears.zone is Zone.GRAVEYARD, "2/2 minus 3/3"
    assert giant.zone is Zone.GRAVEYARD, "3/3 minus 3/3"
    assert bolt.zone is Zone.STACK, "cast during resolution, above the Expertise"
    scenario.resolve_top()
    assert bolt.zone is Zone.GRAVEYARD
    assert scenario.player("bob").life == 17
    assert scenario.player("alice").mana_pool.total == 0, "no mana was spent on it"


def test_only_spells_at_or_below_the_limit_are_offered():
    scenario = _yahenni()
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "alice")
    scenario.will_choose_cards(username="alice", source=YAHENNI)
    _cast(scenario)
    asked = [d for d in scenario.questions_asked() if d.kind is DecisionKind.CHOOSE_CARDS]
    assert len(asked) == 1
    assert asked[0].cards == (bolt.id,), "no Serra Angel (mana value 5), no Forest (a land)"


def test_the_player_may_decline_to_cast_anything():
    scenario = _yahenni()
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "alice")
    scenario.will_choose_cards(username="alice", source=YAHENNI)
    _cast(scenario)
    assert bolt.zone is Zone.HAND
    assert scenario.game.stack_is_empty


def test_nothing_is_asked_when_no_card_in_hand_qualifies():
    scenario = _yahenni(hand=("Serra Angel", "Forest"))
    _cast(scenario)
    assert [d for d in scenario.questions_asked() if d.kind is DecisionKind.CHOOSE_CARDS] == []


# --- the rest of the cycle: same sentence, different limit and first sentence


def test_srams_expertise_makes_three_servos_then_casts_free():
    scenario = (
        Scenario()
        .player("alice", hand=["Sram's Expertise", "Shock"], battlefield=["Plains"] * 4)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    shock = scenario.find("Shock", Zone.HAND, "alice")
    scenario.will_choose_cards(shock, username="alice", source="Sram's Expertise")
    scenario.will_choose_targets("bob", username="alice", source="Shock")
    scenario.cast_and_resolve("Sram's Expertise", *scenario.untapped_sources(*["Plains"] * 4))
    scenario.resolve_top()
    servos = [s for s in scenario.game.battlefield if s.name == "Servo Token"]
    assert len(servos) == 3
    assert scenario.player("bob").life == 18


def test_rishkars_expertise_draws_for_greatest_power_then_casts_free():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Rishkar's Expertise", "Lightning Bolt"],
            battlefield=["Forest"] * 6 + ["Hill Giant"],
            library=["Island"] * 5,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "alice")
    scenario.will_choose_cards(bolt, username="alice", source="Rishkar's Expertise")
    scenario.will_choose_targets("bob", username="alice", source="Lightning Bolt")
    scenario.cast_and_resolve("Rishkar's Expertise", *scenario.untapped_sources(*["Forest"] * 6))
    scenario.resolve_top()
    assert len([c for c in scenario.player("alice").hand]) == 3, "Hill Giant has power 3: drew 3"
    assert scenario.player("bob").life == 17


def test_barals_expertise_returns_up_to_three_then_casts_free():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Baral's Expertise", "Shock"],
            battlefield=["Island"] * 5,
        )
        .player("bob", battlefield=["Hill Giant", "Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    giant = scenario.creature("Hill Giant", "bob")
    bears = scenario.creature("Grizzly Bears", "bob")
    shock = scenario.find("Shock", Zone.HAND, "alice")
    scenario.will_choose_cards(shock, username="alice", source="Baral's Expertise")
    scenario.will_choose_targets("bob", username="alice", source="Shock")
    scenario.cast_and_resolve(
        "Baral's Expertise", *scenario.untapped_sources(*["Island"] * 5), targets=[giant, bears]
    )
    scenario.resolve_top()
    assert giant.zone is Zone.HAND and bears.zone is Zone.HAND
    assert scenario.player("bob").life == 18


def test_kari_zevs_expertise_steals_untaps_hastes_then_casts_free():
    scenario = (
        Scenario()
        .player(
            "alice", hand=["Kari Zev's Expertise", "Shock"], battlefield=["Mountain"] * 3
        )
        .player("bob", battlefield=["Hill Giant"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    giant = scenario.creature("Hill Giant", "bob")
    shock = scenario.find("Shock", Zone.HAND, "alice")
    scenario.will_choose_cards(shock, username="alice", source="Kari Zev's Expertise")
    scenario.will_choose_targets("bob", username="alice", source="Shock")
    scenario.cast_and_resolve(
        "Kari Zev's Expertise", *scenario.untapped_sources(*["Mountain"] * 3), targets=[giant]
    )
    scenario.resolve_top()
    assert scenario.game.controller_of(giant).username == "alice"
    assert scenario.game.characteristics_of(giant).has_keyword("haste")
    assert scenario.player("bob").life == 18
