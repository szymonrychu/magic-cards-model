"""A card-in-zone target ("target creature card in a graveyard ...") reads
every qualifier printed around its zone clause, or fails closed (CR 115.1).

Before this, `_read_phrase`'s card-in-zone branch reported `understood=True`
while ignoring whatever followed the zone clause, so a printed restriction was
silently dropped and illegal targets were offered. Every qualifier family a
Modern/Pioneer/Standard printing puts there is read here from the real
printing; text no reader owns makes the phrase not-understood.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import DecisionKind
from magic_cards_model.machines.targeting import (
    ComparisonAttribute,
    ComparisonOperator,
    ControllerRestriction,
    profile_for_text,
    targeting_profile,
)
from magic_cards_model.models import Zone
from tests.cards import card
from tests.scenarios.harness import Scenario


def ability_profile(name: str):
    return profile_for_text(card(name).front_oracle_text)


ability_profile_text = ability_profile


# -- fail closed on anything unread ----------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "Return target creature card from your graveyard that frobnicates to your hand.",
        "Return target creature card in your graveyard with a frobnicator on it to your hand.",
        "Return target creature card that is frobnicating from your graveyard to your hand.",
        "Return target creature card from your graveyard that was put there from the battlefield "
        "or exile this turn to your hand.",
    ],
)
def test_unread_text_around_the_zone_clause_is_not_understood(text):
    assert not profile_for_text(text).understood


@pytest.mark.parametrize(
    "text",
    [
        "Return target creature card from your graveyard to your hand.",
        "Return target creature card from your graveyard to the battlefield tapped.",
        "Put target creature card from a graveyard onto the battlefield under your control.",
        "Return target creature card with mana value 3 or less from your graveyard to your hand.",
    ],
)
def test_effect_text_after_the_zone_clause_is_not_a_qualifier(text):
    assert profile_for_text(text).understood


# -- "that was put there this turn" / "from anywhere this turn" -------------------


@pytest.mark.parametrize("name", ["Abyssal Harvester", "Night Nurse, Healer of Heroes"])
def test_put_there_this_turn_is_read_for_an_ability(name):
    profile = ability_profile(name)
    (requirement,) = profile.requirements

    assert profile.understood
    assert requirement.put_there_this_turn
    assert not requirement.put_there_from_battlefield_this_turn
    assert requirement.zones == frozenset({Zone.GRAVEYARD})


def test_put_there_from_anywhere_this_turn_is_read_for_a_spell():
    profile = targeting_profile(card("Reenact the Crime"))
    (requirement,) = profile.requirements

    assert profile.understood
    assert requirement.put_there_this_turn


def test_put_there_from_the_battlefield_plural_is_still_read():
    (requirement,) = targeting_profile(card("Brought Back")).requirements

    assert requirement.put_there_from_battlefield_this_turn


# -- "that wasn't put there this combat" -----------------------------------------


def test_not_put_there_this_combat_is_read():
    profile = ability_profile("Storrev, Devkarin Lich")
    (requirement,) = profile.requirements

    assert profile.understood
    assert requirement.not_put_there_this_combat
    assert requirement.controller is ControllerRestriction.YOU


# -- "that has an Adventure" / "you own" -----------------------------------------


def test_that_has_an_adventure_after_the_zone_clause_is_read():
    profile = ability_profile("Edgewall Inn")
    (requirement,) = profile.requirements

    assert profile.understood
    assert requirement.must_have_adventure
    assert requirement.zones == frozenset({Zone.GRAVEYARD})


def test_you_own_in_exile_that_has_an_adventure_is_read():
    profile = ability_profile("Sentinel of Lost Lore")

    assert profile.understood
    requirement = profile.requirements[0]
    assert requirement.must_have_adventure
    assert requirement.owned_by_caster
    assert requirement.zones == frozenset({Zone.EXILE})


# -- "or exiled card with flashback you own" ------------------------------------


def test_graveyard_or_exiled_flashback_card_is_a_second_alternative():
    profile = targeting_profile(card("Sorceress's Schemes"))
    (requirement,) = profile.requirements

    assert profile.understood
    assert requirement.zones == frozenset({Zone.GRAVEYARD})
    (alternative,) = requirement.alternatives
    assert alternative.zones == frozenset({Zone.EXILE})
    assert alternative.required_keyword == "flashback"
    assert alternative.owned_by_caster


# -- "with lesser mana value" / "equal or lesser power": the event's own object --


@pytest.mark.parametrize(
    ("name", "attribute", "operator"),
    [
        ("Scrap Trawler", ComparisonAttribute.MANA_VALUE, ComparisonOperator.LESS_THAN),
        ("Havi, the All-Father", ComparisonAttribute.MANA_VALUE, ComparisonOperator.LESS_THAN),
        ("Jackdaw Savior", ComparisonAttribute.MANA_VALUE, ComparisonOperator.LESS_THAN),
        ("Body Launderer", ComparisonAttribute.POWER, ComparisonOperator.LESS_OR_EQUAL),
    ],
)
def test_lesser_than_the_event_object_is_read(name, attribute, operator):
    profile = ability_profile(name)
    requirement = profile.requirements[-1]

    assert profile.understood
    assert requirement.event_comparison_attribute is attribute
    assert requirement.event_comparison_operator is operator


def test_the_event_object_binds_the_lesser_than_bound():
    profile = ability_profile("Scrap Trawler").for_event_subject(mana_value=3, power=None)

    assert profile.requirements[0].event_comparison_value == 3


# -- qualifiers before the zone clause ------------------------------------------


def test_named_card_is_enforced():
    (requirement,) = ability_profile("Groffskithur").requirements

    assert requirement.required_name == "groffskithur"


def test_an_excluded_subtype_after_the_noun_is_enforced():
    profile = ability_profile("Heliod, the Radiant Dawn // Heliod, the Warped Eclipse")

    assert profile.understood
    assert "god" in profile.requirements[0].excluded_subtypes


@pytest.mark.parametrize(
    ("name", "keyword"),
    [("Sacred Excavation", "cycling"), ("Murasa Sproutling", "kicker")],
)
def test_with_a_keyword_ability_on_a_card_in_a_graveyard_is_enforced(name, keyword):
    (requirement,) = ability_profile(name).requirements

    assert requirement.required_keyword == keyword


def test_of_the_chosen_type_is_enforced():
    profile = ability_profile("Dawn-Blessed Pennant")

    assert profile.understood
    assert profile.requirements[-1].of_chosen_type


def test_you_dont_own_is_read():
    profile = ability_profile("Sentinel of Lost Lore")

    assert any(requirement.not_owned_by_caster for requirement in profile.requirements)


def _share_type_requirement():
    (requirement,) = profile_for_text(
        "Return two target creature cards that share a creature type from your graveyard "
        "to your hand."
    ).requirements
    return requirement


def test_two_cards_that_share_a_creature_type_is_read_for_the_real_printings():
    for name in ("Raise the Draugr", "Return from Extinction", "Unbury"):
        text = card(name).front_oracle_text.split("\u2022")[-1].strip()
        profile = profile_for_text(text)
        assert profile.understood, name
        assert profile_for_text(text).requirements[0].share_a_creature_type, name


def test_cards_that_share_a_creature_type_are_enforced_across_targets():
    scenario = (
        Scenario()
        .player(
            "alice",
            graveyard=["Grizzly Bears", "Llanowar Elves", "Elvish Mystic", "Changeling Outcast"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    find = lambda name: scenario.find(name, Zone.GRAVEYARD, "alice")  # noqa: E731
    profile = profile_for_text(
        "Return two target creature cards that share a creature type from your graveyard "
        "to your hand."
    )

    profile.check([find("Llanowar Elves"), find("Elvish Mystic")], "alice", scenario.game)
    with pytest.raises(ValueError, match="creature type"):
        profile.check([find("Llanowar Elves"), find("Grizzly Bears")], "alice", scenario.game)
    # CR 702.73a: a changeling is every creature type.
    profile.check([find("Changeling Outcast"), find("Grizzly Bears")], "alice", scenario.game)


def test_cards_with_different_names_is_read_for_the_real_printing():
    profile = ability_profile_text("Behold the Sinister Six!")
    (requirement,) = profile.requirements

    assert profile.understood
    assert requirement.distinct_names
    assert requirement.maximum == 6


def test_cards_with_different_names_are_enforced_across_targets():
    scenario = (
        Scenario()
        .player(
            "alice",
            graveyard=["Grizzly Bears", "Grizzly Bears", "Llanowar Elves"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = [
        state for state in scenario.game.player("alice").graveyard if state.name == "Grizzly Bears"
    ]
    elves = scenario.find("Llanowar Elves", Zone.GRAVEYARD, "alice")
    profile = profile_for_text(card("Behold the Sinister Six!").front_oracle_text)

    profile.check([bears[0], elves], "alice", scenario.game)
    with pytest.raises(ValueError, match="different names"):
        profile.check(bears, "alice", scenario.game)


def test_of_an_opponents_choice_is_read_for_the_real_printing():
    profile = ability_profile("Mausoleum Turnkey")

    assert profile.understood
    assert profile.requirements[0].chosen_by_opponent


def test_mausoleum_turnkey_asks_an_opponent_which_card_returns():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Mausoleum Turnkey"],
            battlefield=["Swamp"] * 4,
            graveyard=["Grizzly Bears", "Llanowar Elves"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    elves = scenario.find("Llanowar Elves", Zone.GRAVEYARD, "alice")
    scenario.will_choose_targets(elves, username="bob")

    scenario.cast_and_resolve("Mausoleum Turnkey", auto=True)
    scenario.pass_until_resolved()

    asked = [d for d in scenario.questions_asked() if d.kind is DecisionKind.CHOOSE_TARGETS]
    assert [d.player for d in asked] == ["bob"]
    assert elves in scenario.game.player("alice").hand
