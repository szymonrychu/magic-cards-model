"""A mana ability that adds "one mana of **the chosen color**".

Sunken Citadel is the whole mechanic in one card (oracle text confirmed with
`resolve_cards` this session):

    This land enters tapped. As it enters, choose a color.
    {T}: Add one mana of the chosen color.
    {T}: Add two mana of the chosen color. Spend this mana only to activate
         abilities of land sources.

Three rules meet on it, all looked up with `knowledge_search(type="rules")` in
the session that wrote this file:

- **CR 614.1c** - "Effects that read '[This permanent] enters with . . . ,'
  'As [this permanent] enters . . . ,' or '[This permanent] enters as . . .'
  are replacement effects." So the colour is chosen as the land enters, not
  when the ability is activated.
- **CR 614.12a** - "If a replacement effect that modifies how a permanent
  enters the battlefield requires a choice, that choice is made before the
  permanent enters the battlefield." The answer is recorded on the permanent
  (`CardState.choice`) and every later "the chosen color" reads it back.
- **CR 105.4** - "If a player is asked to choose a color, they must choose one
  of the five colors. 'Multicolored' is not a color. Neither is 'colorless.'"
  So the ability's universe is five options, never six.

And, until the choice reaches the ability, **CR 106.5**: "If an ability would
produce one or more mana of an undefined type, it produces no mana instead."

Where the engine stands, measured: `machines/abilities.py` now reads both
abilities (before this file existed, `parse_mana_abilities(card("Sunken
Citadel"))` was `[]` - the land was mute, and it is three-of in the
boros-ponza list), and `replacement.py` already records the colour as the land
enters. What is *not* wired is the step between them: `machines/cost.
_mana_context` builds `ManaAbility.effective`'s arguments off the permanent and
does not yet pass `chosen_color=source.choice`, so the ability's type stays
undefined at activation time and CR 106.5 applies. That is the `xfail` at the
bottom, and it is a one-value change in `cost.py`, which this file's task does
not own.

The CR 106.6 spend restriction on the second ability - "Spend this mana only to
activate abilities of land sources" - is already read and already enforced; see
`tests/scenarios/test_mana_spend_restrictions.py` for the mechanic. It is
checked here only as data, because the mana it restricts is what this file is
about.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.abilities import parse_mana_abilities
from magic_cards_model.machines.cost import spend_restriction
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Color
from magic_cards_model.models.card_state import ChoiceKind
from magic_cards_model.models.mana import ManaSpend, SpendPurpose
from tests.cards import card
from tests.scenarios.harness import Scenario

# --------------------------------------------------------------------------
# What the parser reads
# --------------------------------------------------------------------------


def test_both_of_the_citadels_abilities_are_read_as_chosen_colour_abilities():
    """Two `{T}` mana abilities, one adding one mana and one adding two.

    Each keeps CR 105.4's five colours as its universe and records that the
    colour is not the player's to pick at activation time - it was fixed as the
    land entered.
    """
    one, two = parse_mana_abilities(card("Sunken Citadel"))

    assert one.uses_chosen_color and two.uses_chosen_color
    assert one.any_color is False and two.any_color is False
    assert {option[0] for option in one.options} == {
        Color.WHITE,
        Color.BLUE,
        Color.BLACK,
        Color.RED,
        Color.GREEN,
    }
    assert one.any_color_count == 1
    assert two.any_color_count == 2
    assert [len(option) for option in two.options] == [2, 2, 2, 2, 2]


def test_the_chosen_colour_narrows_the_ability_to_exactly_that_colour():
    """CR 614.12a's recorded answer, handed to the ability.

    One colour, and the printed count of it - two mana for the restricted
    ability, both of them the chosen colour, which is what "two mana of the
    chosen color" says and what a two-colour read would get wrong.
    """
    one, two = parse_mana_abilities(card("Sunken Citadel"))

    assert one.effective(chosen_color=Color.RED) == ([[Color.RED]], False)
    assert two.effective(chosen_color=Color.RED) == ([[Color.RED, Color.RED]], False)
    assert one.resolve(chosen_color=Color.RED, color=Color.RED) == [Color.RED]


def test_with_no_colour_chosen_the_ability_produces_no_mana():
    """CR 106.5, which is also what the engine falls back to while `cost.py`
    does not pass the choice through: an undefined type produces nothing, and
    `resolve` says so rather than picking a colour nobody chose."""
    one, _two = parse_mana_abilities(card("Sunken Citadel"))

    assert one.effective() == ([], False)
    with pytest.raises(ValueError, match="CR 106.5"):
        one.resolve(color=Color.RED)


def test_the_restricted_ability_still_carries_its_spend_restriction():
    """CR 106.6 on the second ability, unchanged by the colour clause: the
    restriction is read, and it permits exactly a land source's ability."""
    restriction = spend_restriction(
        "Add two mana of the chosen color. "
        "Spend this mana only to activate abilities of land sources."
    )

    assert restriction is not None
    assert restriction.understood is True
    assert restriction.allows(
        ManaSpend(purpose=SpendPurpose.ACTIVATE_ABILITY, types=frozenset({"land"}))
    )


# --------------------------------------------------------------------------
# On the battlefield
# --------------------------------------------------------------------------


def test_the_colour_is_chosen_as_the_land_enters():
    """CR 614.1c/614.12a: playing the land asks for the colour, and the answer
    is recorded on the permanent before it is on the battlefield."""
    scenario = Scenario().player("alice", hand=["Sunken Citadel"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    citadel = scenario.play_land("Sunken Citadel")

    assert citadel.zone is Zone.BATTLEFIELD
    assert citadel.choice is not None
    assert citadel.choice.kind is ChoiceKind.COLOR
    assert Color(citadel.choice.value) in (
        Color.WHITE,
        Color.BLUE,
        Color.BLACK,
        Color.RED,
        Color.GREEN,
    )
    # "This land enters tapped." - the same sentence, and the reason the
    # `xfail` below untaps before activating rather than playing and tapping in
    # one turn.
    assert citadel.tapped


@pytest.mark.xfail(
    strict=True,
    reason="`machines/cost._mana_context` builds `ManaAbility.effective`'s arguments "
    "from the permanent (its controller's land types, its own counters, whether a "
    "card is imprinted on it) and does not pass `chosen_color=source.choice`, so the "
    "colour CR 614.12a recorded as the land entered never reaches the ability and "
    "CR 106.5 leaves it producing no mana. The parser reads the clause; the payment "
    "path has yet to answer it.",
)
def test_the_citadel_taps_for_the_colour_chosen_as_it_entered():
    """The whole mechanic, end to end: a Sunken Citadel that entered naming
    black taps for black, and for nothing else."""
    scenario = Scenario().player("alice", battlefield=["Sunken Citadel"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    citadel = scenario.find("Sunken Citadel", Zone.BATTLEFIELD, "alice")
    citadel.choice = _black()

    scenario.activate(citadel)

    assert scenario.player("alice").mana_pool.floating == {Color.BLACK: 1}


@pytest.mark.xfail(
    strict=True,
    reason="same missing hook as above - the ability produces no mana at all, so "
    "there is none for the CR 106.6 restriction to be attached to.",
)
def test_the_citadels_restricted_ability_makes_two_restricted_mana():
    """boros-ponza's actual use of the card: two mana of the chosen colour that
    can only pay for a land's activated ability (CR 106.6)."""
    scenario = Scenario().player("alice", battlefield=["Sunken Citadel"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    citadel = scenario.find("Sunken Citadel", Zone.BATTLEFIELD, "alice")
    citadel.choice = _black()

    scenario.activate(citadel, index=1)
    pool = scenario.player("alice").mana_pool

    assert pool.floating == {Color.BLACK: 2}
    assert pool.restricted_total == 2
    assert pool.restrictions()[0].understood is True


def _black():
    """The recorded answer to "As it enters, choose a color", built the same
    way `machines/replacement.py` builds it when the land is actually played -
    see `test_the_colour_is_chosen_as_the_land_enters`, which plays one and
    reads this exact field back."""
    from magic_cards_model.models.card_state import Choice

    return Choice(kind=ChoiceKind.COLOR, value=Color.BLACK.value)
