"""Scenario: "Return target `<X>` card and all other cards with the same
name as that card from your graveyard to `<destination>`" (CR 201.2a's
same-name grouping), plus the "Sacrifice three `<subtype>`s" cost that pays
for Rat King, Verminister's own activation.

Rat King, Verminister: "{T}, Sacrifice three Rats: Return target creature
card and all other cards with the same name as that card from your
graveyard to the battlefield tapped." `split_effect_clauses`'s bare "and"
cuts the effect into `['Return target creature card', 'all other cards with
the same name as that card from your graveyard to the battlefield
tapped']` - the second fragment opens with no verb of its own - so it is
read whole. CR 201.2a: "Two or more objects have the same name if they have
at least one name in common" - read here as an exact `CardState.name` match
against every other card presently in the same graveyard, moving as one
CR 603.6a arrival together with the chosen target.

"Sacrifice three Rats" needed no new cost code at all:
`machines/cost.py`'s own sacrifice-cost reader already reads a printed count
ahead of a capitalised subtype noun (its own comment cites "Sacrifice three"
against Ward as the precedent) - this file's own
`test_paying_the_cost_requires_exactly_three_rats*` cases are the proof that
premise actually holds for this printing, not merely an assumption carried
over from the sweep.

Proof printing (Modern-legal, added with `scripts/add_card.py`, not Rat
King and not in any deck list): **Echoing Return** - "Return target
creature card and all other cards with the same name as that card from
your graveyard to your hand." The identical same-name grouping as a plain
sorcery rather than an activated ability, and to hand rather than tapped
onto the battlefield - proving the reader generalises across both what
resolves it and where the group ends up, not only Rat King's own printed
destination.

CR numbers verified with `mise run rules:find` in the session that wrote
this file: 201.2a (same name), 603.6a (several objects arriving together
see each other as they do), 701.21a (sacrifice moves straight to the
graveyard - no destruction, so an indestructible Rat would not have
mattered either), 608.2b (an illegal target - gone from the graveyard by
resolution - simply is not returned).
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.support import card_support
from tests.cards import card

from .harness import Scenario

RAT_KING = "Rat King, Verminister"
ECHOING_RETURN = "Echoing Return"


def test_listed_and_proof_printings_are_handled():
    for name in (RAT_KING, ECHOING_RETURN):
        bad = [
            c
            for c in card_support(card(name)).clauses
            if c.outcome not in ("handled", "static_unaudited")
        ]
        assert not bad, (name, bad)


def _rat_king_board(rat_count: int = 3):
    return (
        Scenario()
        .player(
            "alice",
            battlefield=[RAT_KING] + ["Rat Colony"] * rat_count,
            graveyard=["Rat Colony", "Rat Colony", "Grizzly Bears"],
        )
        .player("bob")
        .build()
    )


def _alice_battlefield_named(scenario, name: str) -> list:
    return [
        state for state in scenario.game.permanents_controlled_by("alice") if state.name == name
    ]


def _alice_graveyard_named(scenario, name: str) -> list:
    return [state for state in scenario.player("alice").graveyard if state.name == name]


def test_returns_the_target_and_every_other_card_with_the_same_name():
    """CR 601.2b: the sacrifice cost is paid before the ability even goes on
    the stack, so by the time it resolves the three just-sacrificed Rat
    Colonies are sitting in the same graveyard as the two already there -
    all five share the name "Rat Colony" (CR 201.2a), so all five return
    together, cost fodder included."""
    scenario = _rat_king_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    rat_king = scenario.creature(RAT_KING)
    colonies = _alice_graveyard_named(scenario, "Rat Colony")
    rats = _alice_battlefield_named(scenario, "Rat Colony")

    ability = scenario.activate(rat_king, index=0, targets=[colonies[0]], sacrificing=rats[:3])
    assert ability is not None
    scenario.pass_until_resolved()

    battlefield_colonies = _alice_battlefield_named(scenario, "Rat Colony")
    assert len(battlefield_colonies) == 5, "the target, the other pre-existing one, and the fodder"
    assert all(state.tapped for state in battlefield_colonies)
    assert not _alice_graveyard_named(scenario, "Rat Colony")


def test_returns_only_the_pre_existing_sibling_when_the_cost_uses_a_different_creature():
    """Isolating CR 201.2a's own count from CR 601.2b's cost-fodder wrinkle
    above: sacrificing three *Grizzly Bears* instead leaves the graveyard's
    Rat Colony count exactly where it started."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[RAT_KING, "Grizzly Bears", "Grizzly Bears", "Grizzly Bears"],
            graveyard=["Rat Colony", "Rat Colony"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    rat_king = scenario.creature(RAT_KING)
    colonies = _alice_graveyard_named(scenario, "Rat Colony")
    bears = _alice_battlefield_named(scenario, "Grizzly Bears")
    assert len(bears) == 3

    try:
        scenario.activate(rat_king, index=0, targets=[colonies[0]], sacrificing=bears[:3])
    except ValueError:
        return
    raise AssertionError('"Sacrifice three Rats" accepted three Grizzly Bears')


def test_a_creature_with_a_different_name_stays_in_the_graveyard():
    scenario = _rat_king_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    rat_king = scenario.creature(RAT_KING)
    colonies = _alice_graveyard_named(scenario, "Rat Colony")
    rats = _alice_battlefield_named(scenario, "Rat Colony")

    scenario.activate(rat_king, index=0, targets=[colonies[0]], sacrificing=rats[:3])
    scenario.pass_until_resolved()

    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")
    assert bears.zone is Zone.GRAVEYARD, "a different name is not part of the group"


def test_paying_the_cost_requires_exactly_three_rats():
    scenario = _rat_king_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    rat_king = scenario.creature(RAT_KING)
    colonies = _alice_graveyard_named(scenario, "Rat Colony")
    rats = _alice_battlefield_named(scenario, "Rat Colony")

    try:
        scenario.activate(rat_king, index=0, targets=[colonies[0]], sacrificing=rats[:2])
    except ValueError:
        return
    raise AssertionError("activated Rat King by sacrificing only two Rats")


def test_paying_the_cost_sacrifices_exactly_three_rats_not_more():
    scenario = _rat_king_board(rat_count=4)
    scenario.start_at(Step.PRECOMBAT_MAIN)
    rat_king = scenario.creature(RAT_KING)
    colonies = _alice_graveyard_named(scenario, "Rat Colony")
    rats = _alice_battlefield_named(scenario, "Rat Colony")
    assert len(rats) == 4
    untouched = rats[3]

    scenario.activate(rat_king, index=0, targets=[colonies[0]], sacrificing=rats[:3])
    scenario.pass_until_resolved()

    assert untouched.zone is Zone.BATTLEFIELD, "the cost never touched the fourth Rat Colony"
    # The fourth was never sacrificed, so it never joined the graveyard group -
    # only the two pre-existing colonies and the three sacrificed as the cost do.
    assert len(_alice_battlefield_named(scenario, "Rat Colony")) == 6


# -- proof printing: Echoing Return, a spell returning the group to hand ----


def test_echoing_return_returns_the_group_to_hand_instead():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[ECHOING_RETURN],
            battlefield=["Swamp"],
            graveyard=["Rat Colony", "Rat Colony", "Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    colonies = [state for state in scenario.player("alice").graveyard if state.name == "Rat Colony"]
    (swamp,) = scenario.untapped_sources("Swamp")

    scenario.cast_and_resolve(ECHOING_RETURN, swamp, targets=[colonies[0]])

    hand_colonies = [state for state in scenario.player("alice").hand if state.name == "Rat Colony"]
    assert len(hand_colonies) == 2
    assert not [state for state in scenario.player("alice").graveyard if state.name == "Rat Colony"]
