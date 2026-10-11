"""Scenario: a count of "permanents you control that are `<A>` and/or `<B>`",
as a characteristic-defining ability and as an Aura's "+X/+X, where X is",
plus protection from a creature type on a double-faced card.

- Katilda, Dawnhart Martyr: "Flying, lifelink, protection from Vampires /
  Katilda's power and toughness are each equal to the number of permanents
  you control that are Spirits and/or enchantments." - CR 604.3a's
  characteristic-defining ability, applied in sublayer 7a (CR 613.4a); a
  permanent that is both a Spirit and an enchantment counts once (CR 205.2b's
  "any" reading of an and/or list).
- Katilda's Rising Dawn (its disturb back face): "Enchanted creature has
  flying, lifelink, and protection from Vampires, and it gets +X/+X, where X
  is the number of permanents you control that are Spirits and/or
  enchantments." - layer 6 for the keywords (CR 613.1f), sublayer 7c for the
  bonus (CR 613.4c), recounted on every computation.
- Protection from Vampires (CR 702.16a: a subtype quality applies to
  permanents with that subtype; CR 702.16f: an attacking creature with
  protection can't be blocked by creatures with the quality).
- Wreath of Geists (Modern, not a listed card and in no api deck): "Enchanted
  creature gets +X/+X, where X is the number of creature cards in your
  graveyard." - the second printing of the attached "+X/+X, where X is
  `<count>`" reader, without a keyword list in front.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import Keyword, has_keyword
from magic_cards_model.models import Zone
from magic_cards_model.support import card_support
from tests.cards import card

from .harness import Scenario

KATILDA = "Katilda, Dawnhart Martyr"


def _board(alice: dict, bob: dict | None = None, step: Step = Step.PRECOMBAT_MAIN):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", **{"library": ["Island"] * 10, **alice})
        .player("bob", **{"library": ["Island"] * 10, **(bob or {})})
        .build()
    )
    scenario.start_at(step)
    return scenario


def _pt(scenario, state):
    return scenario.game.power_of(state), scenario.game.toughness_of(state)


# -- the characteristic-defining ability ------------------------------------


def test_katilda_alone_counts_herself():
    """She is a Spirit: 1/1 with nothing else."""
    scenario = _board({"battlefield": [KATILDA]})

    assert _pt(scenario, scenario.creature(KATILDA)) == (1, 1)


def test_katilda_counts_spirits_and_enchantments_you_control():
    scenario = _board(
        {"battlefield": [KATILDA, "Spectral Sailor", "Ghostly Prison", "Grizzly Bears"]}
    )

    assert _pt(scenario, scenario.creature(KATILDA)) == (3, 3)


def test_katilda_ignores_an_opponents_spirits_and_enchantments():
    scenario = _board(
        {"battlefield": [KATILDA]}, {"battlefield": ["Spectral Sailor", "Ghostly Prison"]}
    )

    assert _pt(scenario, scenario.creature(KATILDA)) == (1, 1)


def test_the_count_follows_the_board():
    scenario = _board({"battlefield": [KATILDA, "Spectral Sailor"]})
    katilda = scenario.creature(KATILDA)
    assert _pt(scenario, katilda) == (2, 2)

    scenario.game.put_into_graveyard(scenario.creature("Spectral Sailor"))

    assert _pt(scenario, katilda) == (1, 1)


# -- protection from Vampires -----------------------------------------------


def test_katilda_cannot_be_blocked_by_a_vampire():
    scenario = _board(
        {"battlefield": [KATILDA]},
        {"battlefield": ["Vampire Nighthawk"]},
        step=Step.DECLARE_ATTACKERS,
    )
    katilda = scenario.creature(KATILDA)
    scenario.attack_with(katilda)
    scenario.advance()

    with pytest.raises(ValueError, match="(?i)protection"):
        scenario.block(katilda, scenario.creature("Vampire Nighthawk", "bob"))


def test_katilda_can_be_blocked_by_a_non_vampire_with_flying():
    scenario = _board(
        {"battlefield": [KATILDA]},
        {"battlefield": ["Spectral Sailor"]},
        step=Step.DECLARE_ATTACKERS,
    )
    katilda = scenario.creature(KATILDA)
    scenario.attack_with(katilda)
    scenario.advance()

    scenario.block(katilda, scenario.creature("Spectral Sailor", "bob"))

    assert scenario.attackers() == [katilda]


# -- the Aura back face -----------------------------------------------------


def _rising_dawn(alice_battlefield: list[str], bob: dict | None = None):
    scenario = _board(
        {
            "graveyard": [KATILDA],
            "battlefield": ["Plains"] * 5 + ["Grizzly Bears", *alice_battlefield],
        },
        bob,
    )
    bears = scenario.creature("Grizzly Bears")
    sources = scenario.untapped_sources(*["Plains"] * 5)
    casting = scenario.cast(KATILDA, from_zone=Zone.GRAVEYARD)
    casting.use_keyword("Disturb")
    casting.choose_targets([bears])
    scenario.pay_with(casting.begin_paying(), *sources)
    scenario.put_on_stack(casting)
    aura = scenario.resolve_top()
    assert aura.name == "Katilda's Rising Dawn"
    assert aura.attached_to == bears.id
    return scenario, bears


def test_rising_dawn_grants_flying_lifelink_and_protection():
    scenario, bears = _rising_dawn([])

    assert has_keyword(bears, Keyword.FLYING, scenario.game)
    assert has_keyword(bears, Keyword.LIFELINK, scenario.game)
    assert "Vampires" in scenario.game._effective_protection_qualities(bears)


def test_rising_dawn_counts_itself_and_your_spirits():
    """The Aura is an enchantment you control (1) and Spectral Sailor a Spirit
    (2): Grizzly Bears 2/2 becomes 4/4."""
    scenario, bears = _rising_dawn(["Spectral Sailor"])

    assert _pt(scenario, bears) == (4, 4)


def test_rising_dawn_does_not_count_an_opponents_enchantment():
    scenario, bears = _rising_dawn([], {"battlefield": ["Ghostly Prison"]})

    assert _pt(scenario, bears) == (3, 3)


# -- the second printing ----------------------------------------------------


def test_wreath_of_geists_counts_creature_cards_in_your_graveyard():
    scenario = _board(
        {
            "hand": ["Wreath of Geists"],
            "battlefield": ["Forest", "Grizzly Bears"],
            "graveyard": ["Hill Giant", "Spectral Sailor", "Island"],
        },
        {"graveyard": ["Vampire Nighthawk"]},
    )
    bears = scenario.creature("Grizzly Bears")

    scenario.cast_and_resolve(
        "Wreath of Geists", *scenario.untapped_sources("Forest"), targets=[bears]
    )

    assert _pt(scenario, bears) == (4, 4)


def test_wreath_of_geists_with_an_empty_graveyard_adds_nothing():
    scenario = _board({"hand": ["Wreath of Geists"], "battlefield": ["Forest", "Grizzly Bears"]})
    bears = scenario.creature("Grizzly Bears")

    scenario.cast_and_resolve(
        "Wreath of Geists", *scenario.untapped_sources("Forest"), targets=[bears]
    )

    assert _pt(scenario, bears) == (2, 2)


@pytest.mark.parametrize("name", [KATILDA, "Wreath of Geists"])
def test_the_printings_read_handled(name):
    support = card_support(card(name))

    assert support.status == "handled", [c for c in support.clauses if c.status != "handled"]
