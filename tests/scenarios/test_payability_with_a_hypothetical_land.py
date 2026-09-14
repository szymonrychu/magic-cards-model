"""Whether a hand card is payable now, or would be with one more land.

`payability(game, player, card, *, assuming_land=None)` returns every
mana-paid option `legal_actions` enumerates for `card` (casting it, and the
hand-activated abilities cycling, typecycling and channel), each with the
engine's own affordability verdict, and whether any of them is payable. With
`assuming_land`, a land in `player`'s hand or library, it asks the same
question of a decoded copy of the game in which that land has entered through
`Game.enter_the_battlefield` - enters-tapped replacement effects applied and an
optional life payment made when legal - so a tapped land and a summoning-sick
land creature add nothing, exactly as they would in the real game.

Rules, each read in full with `mise run rules:find` in the session that wrote
this file:

- **CR 118.6** - an unpayable action is still a legal one, which is why
  `legal_actions` reports affordability alongside legality and this reads it.
- **CR 106.6** - mana can carry a spend restriction, so Eldrazi Temple's
  {C}{C} pays for a colorless Eldrazi spell and not for anything else.
- **CR 302.6** - a creature's {T} ability cannot be activated until it has
  been under its controller's control since their most recent turn began, so
  Dryad Arbor entering this turn is not a mana source.
- **CR 614.1d / 614.12a** - how the hypothetical land enters (see
  `test_predicting_how_a_land_enters.py`).
- **CR 702.29a / 702.29e** - cycling and typecycling are activated abilities
  that function from the hand.
- **CR 207.2c** - channel is an ability word with no rules meaning of its own:
  the ability is an ordinary activated ability usable from the hand.
"""

from magic_cards_model.machines import EntersState, Step, payability
from magic_cards_model.models import ActionKind, Affordability, Zone
from tests.scenarios.harness import Scenario


def _board(hand=(), battlefield=(), library=(), life=20):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=list(hand),
            battlefield=list(battlefield),
            library=list(library),
            life=life,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _payable(scenario, name, assuming=None, assuming_zone=Zone.HAND):
    card = scenario.find(name, Zone.HAND, "alice")
    land = scenario.find(assuming, assuming_zone, "alice") if assuming is not None else None
    return payability(scenario.game, "alice", card, assuming_land=land)


# --------------------------------------------------------------------------
# Right now, with no hypothetical
# --------------------------------------------------------------------------


def test_nothing_untapped_pays_for_nothing():
    scenario = _board(hand=["Preordain", "Island"])

    report = _payable(scenario, "Preordain")

    assert not report.payable
    assert report.assumed_land is None
    assert [option.kind for option in report.options] == [ActionKind.CAST]
    assert report.options[0].affordable is Affordability.NO


def test_an_island_on_the_battlefield_pays_for_preordain():
    scenario = _board(hand=["Preordain"], battlefield=["Island"])

    assert _payable(scenario, "Preordain").payable


def test_timing_is_honoured():
    """A sorcery outside a main phase has no cast option to be payable."""
    scenario = (
        Scenario().player("alice", hand=["Preordain"], battlefield=["Island"]).player("bob").build()
    )
    scenario.start_at(Step.UPKEEP)

    report = payability(scenario.game, "alice", scenario.find("Preordain", Zone.HAND, "alice"))

    assert not report.payable
    assert report.options == ()


# --------------------------------------------------------------------------
# One more land from hand
# --------------------------------------------------------------------------


def test_an_island_in_hand_makes_preordain_payable():
    scenario = _board(hand=["Preordain", "Island"])

    report = _payable(scenario, "Preordain", assuming="Island")

    assert report.payable
    assert report.assumed_land.state is EntersState.UNTAPPED


def test_an_island_in_hand_makes_psychic_frog_payable_beside_a_swamp():
    scenario = _board(hand=["Psychic Frog", "Island"], battlefield=["Swamp"])

    assert not _payable(scenario, "Psychic Frog").payable
    assert _payable(scenario, "Psychic Frog", assuming="Island").payable


def test_a_shockland_counts_once_its_life_is_paid():
    scenario = _board(hand=["Psychic Frog", "Watery Grave"], battlefield=["Swamp"])

    report = _payable(scenario, "Psychic Frog", assuming="Watery Grave")

    assert report.payable
    assert report.assumed_land.state is EntersState.UNTAPPED_IF_PAID


def test_a_shockland_at_one_life_does_not_count():
    """CR 119.4: the 2 life cannot be paid, so the Grave would enter tapped."""
    scenario = _board(hand=["Psychic Frog", "Watery Grave"], battlefield=["Swamp"], life=1)

    report = _payable(scenario, "Psychic Frog", assuming="Watery Grave")

    assert not report.payable
    assert report.assumed_land.state is EntersState.TAPPED


def test_a_tapped_surveil_land_never_pays_this_turn():
    scenario = _board(hand=["Psychic Frog", "Undercity Sewers"], battlefield=["Swamp"])

    report = _payable(scenario, "Psychic Frog", assuming="Undercity Sewers")

    assert not report.payable
    assert report.assumed_land.state is EntersState.TAPPED


def test_a_land_creature_that_just_entered_is_not_a_mana_source():
    """CR 302.6: Dryad Arbor is summoning sick the turn it enters. A Forest
    from the same hand, the control case, does pay."""
    scenario = _board(hand=["Basking Broodscale", "Dryad Arbor", "Forest"], battlefield=["Forest"])

    assert not _payable(scenario, "Basking Broodscale", assuming="Dryad Arbor").payable
    assert _payable(scenario, "Basking Broodscale", assuming="Forest").payable


# --------------------------------------------------------------------------
# CR 106.6: a restricted source
# --------------------------------------------------------------------------


def test_eldrazi_temple_does_not_make_basking_broodscale_payable():
    """Basking Broodscale is a colorless Eldrazi (devoid), so the Temple's
    restriction would let its {C}{C} pay the generic part - but nothing here
    makes {G}, so it is still not payable."""
    scenario = _board(hand=["Basking Broodscale", "Eldrazi Temple"], battlefield=["Island"])

    assert not _payable(scenario, "Basking Broodscale", assuming="Eldrazi Temple").payable


def test_eldrazi_temple_restricted_mana_pays_only_for_a_colorless_eldrazi():
    """Island plus Eldrazi Temple makes three mana only through the {C}{C}
    ability. Glaring Fleshraker ({2}{C}, colorless Eldrazi) may spend it;
    Ensnaring Bridge ({3}, an artifact) may not, and one Island plus the
    unrestricted {C} is only two."""
    scenario = _board(
        hand=["Glaring Fleshraker", "Ensnaring Bridge", "Eldrazi Temple"], battlefield=["Island"]
    )

    assert _payable(scenario, "Glaring Fleshraker", assuming="Eldrazi Temple").payable
    assert not _payable(scenario, "Ensnaring Bridge", assuming="Eldrazi Temple").payable


# --------------------------------------------------------------------------
# A land in the library: the fetch target
# --------------------------------------------------------------------------


def test_a_library_shockland_makes_psychic_frog_payable():
    """Polluted Delta in hand, Watery Grave in the library. The caller composes
    fetch-then-search itself; this answers the library-land half."""
    scenario = _board(
        hand=["Psychic Frog", "Polluted Delta"], battlefield=["Swamp"], library=["Watery Grave"]
    )

    report = _payable(scenario, "Psychic Frog", assuming="Watery Grave", assuming_zone=Zone.LIBRARY)

    assert report.payable
    assert report.assumed_land.state is EntersState.UNTAPPED_IF_PAID


# --------------------------------------------------------------------------
# Hand-activated abilities paid with mana
# --------------------------------------------------------------------------


def test_islandcycling_is_a_payable_option_when_the_spell_is_not():
    scenario = _board(hand=["Lórien Revealed", "Island"])

    report = _payable(scenario, "Lórien Revealed", assuming="Island")

    by_kind = {option.kind: option for option in report.options}
    assert report.payable
    assert by_kind[ActionKind.CAST].affordable is Affordability.NO
    assert by_kind[ActionKind.ACTIVATE_OFF_ZONE].affordable is Affordability.YES
    assert by_kind[ActionKind.ACTIVATE_OFF_ZONE].keyword == "Islandcycling"


def test_channel_is_a_payable_option_with_the_fourth_land():
    """Takenuma's channel costs {3}{B} and targets nothing."""
    scenario = _board(
        hand=["Takenuma, Abandoned Mire", "Swamp"], battlefield=["Swamp", "Island", "Island"]
    )

    assert not _payable(scenario, "Takenuma, Abandoned Mire").payable
    report = _payable(scenario, "Takenuma, Abandoned Mire", assuming="Swamp")
    assert report.payable
    assert [option.kind for option in report.options] == [ActionKind.ACTIVATE_OFF_ZONE]


# --------------------------------------------------------------------------
# Side-effect free
# --------------------------------------------------------------------------


def test_asking_mutates_nothing():
    scenario = _board(
        hand=["Psychic Frog", "Watery Grave", "Dryad Arbor"],
        battlefield=["Swamp"],
        library=["Watery Grave"],
    )
    before = scenario.game.model_dump_json()

    _payable(scenario, "Psychic Frog")
    _payable(scenario, "Psychic Frog", assuming="Watery Grave")
    _payable(scenario, "Psychic Frog", assuming="Watery Grave", assuming_zone=Zone.LIBRARY)
    _payable(scenario, "Psychic Frog", assuming="Dryad Arbor")

    assert scenario.game.model_dump_json() == before
