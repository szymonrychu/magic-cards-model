"""Beam me up: cast an instant or sorcery from the graveyard for an
alternative cost that also returns a creature you control to its owner's hand,
then exile the spell (CR 702.196).

Rules verified in the session that wrote this file, against the CR effective
November 6, 2026 (`mise run rules:find`):

- **CR 702.196a** - "Beam me up appears on some instants and sorceries. It
  represents two static abilities: one that functions while the card is in a
  player's graveyard and another that functions while the card is on the
  stack. 'Beam me up [cost]' means 'You may cast this card from your graveyard
  if the resulting spell is an instant or sorcery spell by paying [cost] and
  returning a creature you control to its owner's hand rather than paying its
  mana cost' and 'If the beam me up cost was paid, exile this card instead of
  putting it anywhere else any time it would leave the stack.' Casting a spell
  using its beam me up ability follows the rules for paying alternative costs
  in rules 601.2b and 601.2f-h."
- **CR 702.196b** - "If a creature can't be beamed up, its controller can't
  return it to its owner's hand to pay the portion of a beam me up cost that
  requires them to return a creature they control to its owner's hand."
- **CR 601.2b** - the alternative cost is announced, and the objects a cost
  needs are chosen, as the spell is proposed; **CR 601.2h** - the creature is
  returned as the total cost is paid.
- **CR 505.1** - "There are two main phases in a turn", Scotty's "During your
  main phase" window.
- **CR 611.3d** - a static ability may grant an ability to a card that allows
  it to be cast (Scotty, Miracle Worker's grant to every card in your
  graveyard).

The return half is web-slinging's (CR 702.188a) and sneak's
`ComponentKind.RETURN_TO_HAND` cost, already proven on non-trk printings in
`test_web_slinging.py` and `test_sneak.py`; this file proves the graveyard
half, the exile half, the CR 702.196b restriction and Scotty's grant, then
plays every trk card with the keyword (and Marooned, which forbids it) once.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.casting import keyword_cast_options
from magic_cards_model.machines.combat import has_keyword
from magic_cards_model.machines.legal_actions import legal_actions
from magic_cards_model.models import Zone
from magic_cards_model.models.action import ActionKind
from tests.cards import card
from tests.scenarios.harness import Scenario

BEAM_ME_UP_CARDS = {
    "Federation Resupply": "{3}{W}",
    "Pure Energy": "{2}{W}",
    "There's Coffee in that Nebula": "{2}{W}",
    "Energize": "{3}{U}",
    "Open Communications": "{2}{U}",
    "Pattern Buffer Preservation": "{1}{B}",
    "Boarding Action": "{2}{R}",
    "Transporter Malfunction": "{3}{R}{R}{R}",
    "Adversary by Algorithm": "{3}{G}",
    "Final Frontier": "{1}{G}",
}


def _board(
    *,
    graveyard: list[str],
    battlefield: list[str],
    hand: list[str] | None = None,
    library: list[str] | None = None,
    bob_battlefield: list[str] | None = None,
    bob_hand: list[str] | None = None,
    step: Step = Step.PRECOMBAT_MAIN,
):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=list(hand or []),
            graveyard=graveyard,
            battlefield=battlefield,
            library=list(library or ["Plains"] * 5),
        )
        .player(
            "bob",
            hand=list(bob_hand or []),
            battlefield=list(bob_battlefield or []),
            library=["Plains"] * 5,
        )
        .build()
    )
    scenario.start_at(step)
    return scenario


def _beam(scenario, name, returned, lands, **kwargs):
    spell = scenario.find(name, Zone.GRAVEYARD, "alice")
    return scenario.game.cast(
        spell,
        "alice",
        keyword="Beam me up",
        choosing=list(returned),
        mana_sources=list(lands),
        **kwargs,
    )


def _beam_casts(scenario, username="alice"):
    return [
        action
        for action in legal_actions(scenario.game, username)
        if action.kind is ActionKind.CAST and (action.keyword or "").lower() == "beam me up"
    ]


# -- what the keyword offers --------------------------------------------------


@pytest.mark.parametrize(("name", "cost"), sorted(BEAM_ME_UP_CARDS.items()))
def test_every_printed_beam_me_up_is_a_graveyard_alternative_cost(name, cost):
    """Read off the keyword line itself: Energize, There's Coffee in that
    Nebula and Adversary by Algorithm print it with an empty Scryfall
    `keywords` list, and still have it."""
    (option,) = [o for o in keyword_cast_options(card(name)) if o.keyword == "Beam me up"]
    assert option.zone is Zone.GRAVEYARD
    assert option.rule == "CR 702.196a"
    assert option.understood
    assert not option.pays_mana_cost
    assert str(option.cost) == f"{cost}, Return a creature you control to its owner's hand"


# -- casting it ---------------------------------------------------------------


def test_cast_from_the_graveyard_returns_the_creature_and_exiles_the_spell():
    scenario = _board(
        graveyard=["Open Communications"],
        battlefield=["Grizzly Bears", "Island", "Island", "Island"],
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    hand_before = len(scenario.player("alice").hand)
    spell = _beam(
        scenario,
        "Open Communications",
        [bears],
        scenario.untapped_sources("Island", "Island", "Island"),
    )
    # CR 601.2h: the creature went back as the cost was paid, before resolution.
    assert spell.zone is Zone.STACK
    assert scenario.find("Grizzly Bears", Zone.HAND, "alice") is not None
    scenario.pass_until_resolved()
    # Bears plus the drawn card.
    assert len(scenario.player("alice").hand) == hand_before + 2
    exiled = scenario.find("Open Communications", Zone.EXILE, "alice")
    assert exiled is not None
    assert not scenario.player("alice").graveyard


def test_a_summoning_sick_creature_may_be_returned():
    scenario = _board(
        graveyard=["Open Communications"],
        battlefield=["Grizzly Bears", "Island", "Island", "Island"],
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    bears.summoning_sick = True
    _beam(
        scenario,
        "Open Communications",
        [bears],
        scenario.untapped_sources("Island", "Island", "Island"),
    )
    assert scenario.find("Grizzly Bears", Zone.HAND, "alice") is not None


def test_no_creature_returned_is_refused():
    scenario = _board(
        graveyard=["Open Communications"],
        battlefield=["Grizzly Bears", "Island", "Island", "Island"],
    )
    with pytest.raises(ValueError):
        _beam(
            scenario,
            "Open Communications",
            [],
            scenario.untapped_sources("Island", "Island", "Island"),
        )
    assert scenario.find("Open Communications", Zone.GRAVEYARD, "alice") is not None
    assert scenario.creature("Grizzly Bears", "alice").zone is Zone.BATTLEFIELD


def test_with_no_creature_to_return_it_cannot_be_cast_or_offered():
    scenario = _board(
        graveyard=["Open Communications"],
        battlefield=["Island", "Island", "Island"],
    )
    assert _beam_casts(scenario) == []
    with pytest.raises(ValueError, match="no creature"):
        _beam(
            scenario,
            "Open Communications",
            [],
            scenario.untapped_sources("Island", "Island", "Island"),
        )


def test_with_a_creature_the_enumerator_offers_it():
    scenario = _board(
        graveyard=["Open Communications"],
        battlefield=["Grizzly Bears", "Island", "Island", "Island"],
    )
    (action,) = _beam_casts(scenario)
    assert action.card_id == scenario.find("Open Communications", Zone.GRAVEYARD, "alice").id


def test_an_opponents_creature_is_not_yours_to_return():
    scenario = _board(
        graveyard=["Open Communications"],
        battlefield=["Grizzly Bears", "Island", "Island", "Island"],
        bob_battlefield=["Grizzly Bears"],
    )
    theirs = scenario.creature("Grizzly Bears", "bob")
    with pytest.raises(ValueError, match="control"):
        _beam(
            scenario,
            "Open Communications",
            [theirs],
            scenario.untapped_sources("Island", "Island", "Island"),
        )
    assert theirs.zone is Zone.BATTLEFIELD


def test_a_land_is_not_a_creature_to_return():
    scenario = _board(
        graveyard=["Open Communications"],
        battlefield=["Grizzly Bears", "Island", "Island", "Island", "Island"],
    )
    land, *paying = scenario.untapped_sources("Island", "Island", "Island", "Island")
    with pytest.raises(ValueError, match="creature"):
        _beam(scenario, "Open Communications", [land], paying)
    assert land.zone is Zone.BATTLEFIELD


def test_the_mana_half_must_be_paid_in_full():
    scenario = _board(
        graveyard=["Open Communications"],
        battlefield=["Grizzly Bears", "Island", "Island"],
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    with pytest.raises(ValueError):
        _beam(
            scenario, "Open Communications", [bears], scenario.untapped_sources("Island", "Island")
        )
    assert bears.zone is Zone.BATTLEFIELD
    assert scenario.find("Open Communications", Zone.GRAVEYARD, "alice") is not None


def test_from_the_hand_it_is_an_ordinary_cast_and_goes_to_the_graveyard():
    scenario = _board(
        hand=["Open Communications"],
        graveyard=[],
        battlefield=["Grizzly Bears", "Island"],
    )
    spell = scenario.find("Open Communications", Zone.HAND, "alice")
    scenario.game.cast(spell, "alice", mana_sources=scenario.untapped_sources("Island"))
    scenario.pass_until_resolved()
    assert scenario.find("Open Communications", Zone.GRAVEYARD, "alice") is not None
    assert scenario.creature("Grizzly Bears", "alice").zone is Zone.BATTLEFIELD


def test_beam_me_up_cannot_be_used_from_the_hand():
    scenario = _board(
        hand=["Open Communications"],
        graveyard=[],
        battlefield=["Grizzly Bears", "Island", "Island", "Island"],
    )
    spell = scenario.find("Open Communications", Zone.HAND, "alice")
    with pytest.raises(ValueError, match="graveyard"):
        scenario.game.cast(
            spell,
            "alice",
            keyword="Beam me up",
            choosing=[scenario.creature("Grizzly Bears", "alice")],
            mana_sources=scenario.untapped_sources("Island", "Island", "Island"),
        )


def test_countered_after_beam_me_up_it_is_exiled():
    scenario = _board(
        graveyard=["Open Communications"],
        battlefield=["Grizzly Bears", "Island", "Island", "Island"],
        bob_battlefield=["Island", "Island"],
        bob_hand=["Counterspell"],
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    spell = _beam(
        scenario,
        "Open Communications",
        [bears],
        scenario.untapped_sources("Island", "Island", "Island"),
    )
    scenario.pass_priority("alice")
    counterspell = scenario.find("Counterspell", Zone.HAND, "bob")
    scenario.game.cast(
        counterspell,
        "bob",
        targets=[spell],
        mana_sources=scenario.untapped_sources("Island", "Island", username="bob"),
    )
    scenario.pass_until_resolved()
    assert scenario.find("Open Communications", Zone.EXILE, "alice") is not None
    assert not scenario.player("alice").graveyard
    # The creature stays returned: the cost was paid.
    assert scenario.find("Grizzly Bears", Zone.HAND, "alice") is not None


def test_sorcery_timing_still_applies():
    scenario = _board(
        graveyard=["Open Communications"],
        battlefield=["Grizzly Bears", "Island", "Island", "Island"],
        step=Step.BEGINNING_OF_COMBAT,
    )
    with pytest.raises(ValueError):
        _beam(
            scenario,
            "Open Communications",
            [scenario.creature("Grizzly Bears", "alice")],
            scenario.untapped_sources("Island", "Island", "Island"),
        )
    assert scenario.find("Open Communications", Zone.GRAVEYARD, "alice") is not None


# -- CR 702.196b: a creature that can't be beamed up ------------------------


def _marooned_on(scenario, target, lands, *, pay=False):
    marooned = scenario.find("Marooned", Zone.HAND, "alice")
    scenario.will_pay_the_mana_cost(pay, source="Marooned")
    scenario.game.cast(marooned, "alice", targets=[target], mana_sources=list(lands))
    scenario.pass_until_resolved()
    if scenario.stack_names():
        scenario.pass_until_resolved()
    return marooned


def test_a_marooned_creature_cannot_be_returned_for_the_cost():
    scenario = _board(
        hand=["Marooned"],
        graveyard=["Open Communications"],
        battlefield=["Grizzly Bears", "Llanowar Elves", "Island", "Island", "Island", "Island"],
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    island, *rest = scenario.untapped_sources("Island", "Island", "Island", "Island")
    _marooned_on(scenario, bears, [island])
    with pytest.raises(ValueError, match="beamed up"):
        _beam(scenario, "Open Communications", [bears], rest)
    assert bears.zone is Zone.BATTLEFIELD
    elves = scenario.creature("Llanowar Elves", "alice")
    _beam(scenario, "Open Communications", [elves], rest)
    assert scenario.find("Llanowar Elves", Zone.HAND, "alice") is not None


def test_when_the_only_creature_is_marooned_beam_me_up_is_not_offered():
    scenario = _board(
        hand=["Marooned"],
        graveyard=["Open Communications"],
        battlefield=["Grizzly Bears", "Island", "Island", "Island", "Island"],
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    (island,) = scenario.untapped_sources("Island")
    _marooned_on(scenario, bears, [island])
    assert _beam_casts(scenario) == []


# -- Scotty, Miracle Worker's grant -------------------------------------------


def test_scotty_grants_beam_me_up_for_the_cards_own_mana_cost():
    """Lightning Bolt prints no beam me up: Scotty's grant gives it one whose
    cost is its own {R}, plus the creature (CR 611.3d)."""
    scenario = _board(
        graveyard=["Lightning Bolt"],
        battlefield=["Scotty, Miracle Worker", "Grizzly Bears", "Mountain"],
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    bob_life = scenario.player("bob").life
    _beam(
        scenario,
        "Lightning Bolt",
        [bears],
        scenario.untapped_sources("Mountain"),
        targets=[scenario.player("bob")],
    )
    assert scenario.find("Grizzly Bears", Zone.HAND, "alice") is not None
    scenario.pass_until_resolved()
    assert scenario.player("bob").life == bob_life - 3
    assert scenario.find("Lightning Bolt", Zone.EXILE, "alice") is not None


def test_scotty_cannot_be_beamed_up_for_his_own_grant():
    scenario = _board(
        graveyard=["Lightning Bolt"],
        battlefield=["Scotty, Miracle Worker", "Mountain"],
    )
    scotty = scenario.creature("Scotty, Miracle Worker", "alice")
    assert _beam_casts(scenario) == []
    with pytest.raises(ValueError, match="beamed up"):
        _beam(
            scenario,
            "Lightning Bolt",
            [scotty],
            scenario.untapped_sources("Mountain"),
            targets=[scenario.player("bob")],
        )
    assert scotty.zone is Zone.BATTLEFIELD


def test_scotty_may_be_returned_for_a_printed_beam_me_up():
    """ "Scotty can't be beamed up to cast a spell **this way**": the card's
    own printed beam me up is another way."""
    scenario = _board(
        graveyard=["Open Communications"],
        battlefield=["Scotty, Miracle Worker", "Island", "Island", "Island"],
    )
    scotty = scenario.creature("Scotty, Miracle Worker", "alice")
    _beam(
        scenario,
        "Open Communications",
        [scotty],
        scenario.untapped_sources("Island", "Island", "Island"),
    )
    assert scenario.find("Scotty, Miracle Worker", Zone.HAND, "alice") is not None


def test_scotty_grants_nothing_outside_the_main_phase():
    scenario = _board(
        graveyard=["Lightning Bolt"],
        battlefield=["Scotty, Miracle Worker", "Grizzly Bears", "Mountain"],
        step=Step.BEGINNING_OF_COMBAT,
    )
    with pytest.raises(ValueError):
        _beam(
            scenario,
            "Lightning Bolt",
            [scenario.creature("Grizzly Bears", "alice")],
            scenario.untapped_sources("Mountain"),
            targets=[scenario.player("bob")],
        )
    assert scenario.find("Lightning Bolt", Zone.GRAVEYARD, "alice") is not None


def test_scotty_grants_nothing_to_a_creature_card():
    """CR 702.196a: only an instant or sorcery spell can be cast this way."""
    scenario = _board(
        graveyard=["Llanowar Elves"],
        battlefield=["Scotty, Miracle Worker", "Grizzly Bears", "Forest"],
    )
    with pytest.raises(ValueError, match="instant and sorcery"):
        _beam(
            scenario,
            "Llanowar Elves",
            [scenario.creature("Grizzly Bears", "alice")],
            scenario.untapped_sources("Forest"),
        )
    assert scenario.find("Llanowar Elves", Zone.GRAVEYARD, "alice") is not None


def test_scotty_grants_nothing_to_an_opponents_graveyard():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Scotty, Miracle Worker", "Grizzly Bears", "Mountain"])
        .player("bob", graveyard=["Lightning Bolt"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bolt = scenario.find("Lightning Bolt", Zone.GRAVEYARD, "bob")
    with pytest.raises(ValueError):
        scenario.game.cast(
            bolt,
            "alice",
            keyword="Beam me up",
            choosing=[scenario.creature("Grizzly Bears", "alice")],
            mana_sources=scenario.untapped_sources("Mountain"),
            targets=[scenario.player("bob")],
        )
    assert bolt.zone is Zone.GRAVEYARD


# -- one test per card --------------------------------------------------------


def test_federation_resupply_finds_an_equipment_from_the_graveyard():
    scenario = _board(
        graveyard=["Federation Resupply"],
        battlefield=["Grizzly Bears", "Plains", "Plains", "Plains", "Plains"],
        library=["Plains", "Avacyn's Collar", "Plains"],
    )
    collar = scenario.find("Avacyn's Collar", Zone.LIBRARY, "alice")
    scenario.will_choose_cards(collar, source="Federation Resupply")
    _beam(
        scenario,
        "Federation Resupply",
        [scenario.creature("Grizzly Bears", "alice")],
        scenario.untapped_sources("Plains", "Plains", "Plains", "Plains"),
    )
    scenario.pass_until_resolved()
    assert collar.zone is Zone.HAND
    assert scenario.find("Federation Resupply", Zone.EXILE, "alice") is not None


def test_pure_energy_distributes_two_counters_from_the_graveyard():
    scenario = _board(
        graveyard=["Pure Energy"],
        battlefield=["Grizzly Bears", "Llanowar Elves", "Memnite", "Plains", "Plains", "Plains"],
    )
    elves = scenario.creature("Llanowar Elves", "alice")
    memnite = scenario.creature("Memnite", "alice")
    _beam(
        scenario,
        "Pure Energy",
        [scenario.creature("Grizzly Bears", "alice")],
        scenario.untapped_sources("Plains", "Plains", "Plains"),
        targets=[elves, memnite],
        division=[1, 1],
    )
    scenario.pass_until_resolved()
    assert (elves.power, elves.toughness) == (2, 2)
    assert (memnite.power, memnite.toughness) == (2, 2)
    assert scenario.find("Pure Energy", Zone.EXILE, "alice") is not None


def test_theres_coffee_in_that_nebula_takes_a_plains_or_a_cheap_permanent():
    scenario = _board(
        graveyard=["There's Coffee in that Nebula"],
        battlefield=["Grizzly Bears", "Plains", "Plains", "Plains"],
        library=["Memnite", "Lightning Bolt", "Aetherling", "Shock", "Opt", "Island"],
    )
    memnite = scenario.find("Memnite", Zone.LIBRARY, "alice")
    scenario.scry_bottoming(memnite, username="alice")
    _beam(
        scenario,
        "There's Coffee in that Nebula",
        [scenario.creature("Grizzly Bears", "alice")],
        scenario.untapped_sources("Plains", "Plains", "Plains"),
    )
    scenario.pass_until_resolved()
    assert memnite.zone is Zone.HAND
    library = scenario.player("alice").library
    # The four others went to the bottom, under the sixth card.
    assert library[0].name == "Island"
    assert {state.name for state in library[1:]} == {
        "Lightning Bolt",
        "Aetherling",
        "Shock",
        "Opt",
    }
    assert scenario.find("There's Coffee in that Nebula", Zone.EXILE, "alice") is not None


def test_energize_bounces_an_opponents_creature_from_the_graveyard():
    scenario = _board(
        graveyard=["Energize"],
        battlefield=["Grizzly Bears", "Island", "Island", "Island", "Island"],
        bob_battlefield=["Llanowar Elves"],
    )
    elves = scenario.creature("Llanowar Elves", "bob")
    _beam(
        scenario,
        "Energize",
        [scenario.creature("Grizzly Bears", "alice")],
        scenario.untapped_sources("Island", "Island", "Island", "Island"),
        targets=[elves],
    )
    scenario.pass_until_resolved()
    assert scenario.find("Llanowar Elves", Zone.HAND, "bob") is not None
    assert scenario.find("Grizzly Bears", Zone.HAND, "alice") is not None
    assert scenario.find("Energize", Zone.EXILE, "alice") is not None


def test_marooned_taps_on_payment_and_holds_it_down():
    scenario = _board(
        hand=["Marooned"],
        graveyard=[],
        battlefield=["Island", "Island", "Island", "Island"],
        bob_battlefield=["Grizzly Bears"],
    )
    bears = scenario.creature("Grizzly Bears", "bob")
    _marooned_on(scenario, bears, scenario.untapped_sources("Island"), pay=True)
    assert bears.tapped
    assert scenario.find("Marooned", Zone.BATTLEFIELD, "alice").attached_to == bears.id
    # Bob's untap step: it stays tapped (CR 502.3).
    scenario.game.begin_turn_for("bob")
    scenario.game.untap_step()
    assert bears.tapped


def test_open_communications_draws_from_the_graveyard():
    scenario = _board(
        graveyard=["Open Communications"],
        battlefield=["Grizzly Bears", "Island", "Island", "Island"],
        library=["Opt", "Plains"],
    )
    opt = scenario.find("Opt", Zone.LIBRARY, "alice")
    _beam(
        scenario,
        "Open Communications",
        [scenario.creature("Grizzly Bears", "alice")],
        scenario.untapped_sources("Island", "Island", "Island"),
    )
    scenario.pass_until_resolved()
    assert opt.zone is Zone.HAND
    assert scenario.find("Open Communications", Zone.EXILE, "alice") is not None


def test_scotty_miracle_worker_lets_a_sorcery_without_the_keyword_be_beamed_up():
    scenario = _board(
        graveyard=["Divination"],
        battlefield=["Scotty, Miracle Worker", "Grizzly Bears", "Island", "Island", "Island"],
        library=["Opt", "Shock", "Plains"],
    )
    hand_before = len(scenario.player("alice").hand)
    _beam(
        scenario,
        "Divination",
        [scenario.creature("Grizzly Bears", "alice")],
        scenario.untapped_sources("Island", "Island", "Island"),
    )
    scenario.pass_until_resolved()
    # Bears back plus two cards drawn.
    assert len(scenario.player("alice").hand) == hand_before + 3
    assert scenario.find("Divination", Zone.EXILE, "alice") is not None
    assert scenario.creature("Scotty, Miracle Worker", "alice").zone is Zone.BATTLEFIELD


def test_pattern_buffer_preservation_from_the_graveyard():
    scenario = _board(
        graveyard=["Pattern Buffer Preservation"],
        battlefield=["Grizzly Bears", "Swamp", "Swamp"],
        library=["Opt", "Shock", "Plains"],
    )
    opt = scenario.find("Opt", Zone.LIBRARY, "alice")
    shock = scenario.find("Shock", Zone.LIBRARY, "alice")
    scenario.will_choose_cards(opt, source="Pattern Buffer Preservation")
    _beam(
        scenario,
        "Pattern Buffer Preservation",
        [scenario.creature("Grizzly Bears", "alice")],
        scenario.untapped_sources("Swamp", "Swamp"),
    )
    scenario.pass_until_resolved()
    assert opt.zone is Zone.HAND
    assert shock.zone is Zone.GRAVEYARD
    assert scenario.find("Pattern Buffer Preservation", Zone.EXILE, "alice") is not None


def test_boarding_action_makes_a_hasty_klingon_from_the_graveyard():
    scenario = _board(
        graveyard=["Boarding Action"],
        battlefield=["Grizzly Bears", "Mountain", "Mountain", "Mountain"],
    )
    _beam(
        scenario,
        "Boarding Action",
        [scenario.creature("Grizzly Bears", "alice")],
        scenario.untapped_sources("Mountain", "Mountain", "Mountain"),
    )
    scenario.pass_until_resolved()
    (token,) = [
        state
        for state in scenario.game.permanents_controlled_by("alice")
        if "Klingon" in state.subtypes
    ]
    assert (token.power, token.toughness) == (2, 1)
    assert has_keyword(token, "haste", scenario.game)
    # Haste: the token entered this turn and still attacks (CR 302.6).
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(token)
    assert token in scenario.attackers()
    assert scenario.find("Boarding Action", Zone.EXILE, "alice") is not None


def test_transporter_malfunction_deals_three_from_the_graveyard():
    scenario = _board(
        graveyard=["Transporter Malfunction"],
        battlefield=["Grizzly Bears", *["Mountain"] * 6],
    )
    bob_life = scenario.player("bob").life
    _beam(
        scenario,
        "Transporter Malfunction",
        [scenario.creature("Grizzly Bears", "alice")],
        scenario.untapped_sources(*["Mountain"] * 6),
        targets=[scenario.player("bob")],
    )
    scenario.pass_until_resolved()
    assert scenario.player("bob").life == bob_life - 3
    assert scenario.find("Transporter Malfunction", Zone.EXILE, "alice") is not None


def test_adversary_by_algorithm_makes_an_illusion_from_the_graveyard():
    scenario = _board(
        graveyard=["Adversary by Algorithm"],
        battlefield=["Grizzly Bears", "Forest", "Forest", "Forest", "Forest"],
    )
    _beam(
        scenario,
        "Adversary by Algorithm",
        [scenario.creature("Grizzly Bears", "alice")],
        scenario.untapped_sources("Forest", "Forest", "Forest", "Forest"),
    )
    scenario.pass_until_resolved()
    (token,) = [
        state
        for state in scenario.game.permanents_controlled_by("alice")
        if "Illusion" in state.subtypes
    ]
    assert (token.power, token.toughness) == (3, 3)
    assert scenario.game.characteristics_of(token).is_creature
    assert not token.colors
    assert scenario.find("Adversary by Algorithm", Zone.EXILE, "alice") is not None


def test_final_frontier_fetches_a_planet_tapped_from_the_graveyard():
    scenario = _board(
        graveyard=["Final Frontier"],
        battlefield=["Grizzly Bears", "Forest", "Forest"],
        library=["Opt", "Evendo, Waking Haven", "Shock"],
    )
    planet = scenario.find("Evendo, Waking Haven", Zone.LIBRARY, "alice")
    scenario.will_choose_cards(planet, source="Final Frontier")
    _beam(
        scenario,
        "Final Frontier",
        [scenario.creature("Grizzly Bears", "alice")],
        scenario.untapped_sources("Forest", "Forest"),
    )
    scenario.pass_until_resolved()
    assert planet.zone is Zone.BATTLEFIELD
    assert planet.tapped
    assert scenario.find("Final Frontier", Zone.EXILE, "alice") is not None


def test_final_frontier_still_takes_a_basic_land():
    scenario = _board(
        hand=["Final Frontier"],
        graveyard=[],
        battlefield=["Forest", "Forest", "Forest"],
        library=["Opt", "Plains", "Shock"],
    )
    plains = scenario.find("Plains", Zone.LIBRARY, "alice")
    scenario.will_choose_cards(plains, source="Final Frontier")
    spell = scenario.find("Final Frontier", Zone.HAND, "alice")
    scenario.game.cast(
        spell, "alice", mana_sources=scenario.untapped_sources("Forest", "Forest", "Forest")
    )
    scenario.pass_until_resolved()
    assert plains.zone is Zone.BATTLEFIELD
    assert plains.tapped
    assert scenario.find("Final Frontier", Zone.GRAVEYARD, "alice") is not None


def test_theres_coffee_in_that_nebula_refuses_a_permanent_over_mana_value_3():
    """Aetherling is a nonland permanent card with mana value 6: the bound
    belongs to the second description, and it is not a Plains card either."""
    scenario = _board(
        hand=["There's Coffee in that Nebula"],
        graveyard=[],
        battlefield=["Plains", "Plains"],
        library=["Aetherling", "Lightning Bolt", "Shock", "Opt", "Island", "Plains"],
    )
    aetherling = scenario.find("Aetherling", Zone.LIBRARY, "alice")
    scenario.scry_bottoming(aetherling, username="alice")
    spell = scenario.find("There's Coffee in that Nebula", Zone.HAND, "alice")
    scenario.game.cast(spell, "alice", mana_sources=scenario.untapped_sources("Plains", "Plains"))
    with pytest.raises(ValueError, match="not a Plains card or nonland permanent card"):
        scenario.pass_until_resolved()
    assert aetherling.zone is not Zone.HAND


def test_theres_coffee_in_that_nebula_takes_a_plains_card():
    scenario = _board(
        hand=["There's Coffee in that Nebula"],
        graveyard=[],
        battlefield=["Plains", "Plains"],
        library=["Aetherling", "Lightning Bolt", "Plains", "Opt", "Island", "Swamp"],
    )
    plains = scenario.find("Plains", Zone.LIBRARY, "alice")
    scenario.scry_bottoming(plains, username="alice")
    spell = scenario.find("There's Coffee in that Nebula", Zone.HAND, "alice")
    scenario.game.cast(spell, "alice", mana_sources=scenario.untapped_sources("Plains", "Plains"))
    scenario.pass_until_resolved()
    assert plains.zone is Zone.HAND
    assert scenario.find("There's Coffee in that Nebula", Zone.GRAVEYARD, "alice") is not None


# -- proof cards for the two description readers B1 widened -----------------


def test_proof_open_the_gates_search_joins_two_descriptions_without_an_article():
    """Open the Gates (not trk) prints Final Frontier's "a basic land card or
    Gate card" shape with a different destination, the hand."""
    scenario = _board(
        hand=["Open the Gates"],
        graveyard=[],
        battlefield=["Forest"],
        library=["Opt", "Plains", "Shock"],
    )
    plains = scenario.find("Plains", Zone.LIBRARY, "alice")
    scenario.will_choose_cards(plains, source="Open the Gates")
    spell = scenario.find("Open the Gates", Zone.HAND, "alice")
    scenario.game.cast(spell, "alice", mana_sources=scenario.untapped_sources("Forest"))
    scenario.pass_until_resolved()
    assert plains.zone is Zone.HAND


def test_proof_frontier_seeker_reveals_either_description():
    """Frontier Seeker (not trk) prints the "or a" spelling of the two-
    description reveal on an enters trigger: "a Mount creature card or a
    Plains card"."""
    scenario = _board(
        hand=["Frontier Seeker"],
        graveyard=[],
        battlefield=["Plains", "Plains"],
        library=["Opt", "Plains", "Shock", "Island", "Swamp", "Mountain"],
    )
    plains = scenario.find("Plains", Zone.LIBRARY, "alice")
    scenario.scry_bottoming(plains, username="alice")
    seeker = scenario.find("Frontier Seeker", Zone.HAND, "alice")
    scenario.game.cast(seeker, "alice", mana_sources=scenario.untapped_sources("Plains", "Plains"))
    scenario.pass_until_resolved()
    if scenario.stack_names():
        scenario.pass_until_resolved()
    assert plains.zone is Zone.HAND
