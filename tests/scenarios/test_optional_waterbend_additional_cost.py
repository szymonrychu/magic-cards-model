"""An optional waterbend additional cost on a spell: "As an additional cost
to cast this spell, you may waterbend {N}."

Every CR number here was read in full with `mise run rules:find` in the
session that wrote this file:

- **CR 601.2b** - the caster announces their intention to pay any optional
  additional cost as the spell is cast; **CR 118.8b** - some additional costs
  are optional.
- **CR 601.2f** - an additional cost is added to the total cost.
- **CR 701.67a** - "Waterbend [cost]" means "Pay [cost]. For each generic mana
  in that cost, you may tap an untapped artifact or creature you control
  rather than pay that mana."
- **CR 701.67b** - when a waterbend cost is part of the total cost to cast a
  spell, the tap method may pay only the generic mana in the waterbend cost
  itself, "even if the total cost ... includes other generic mana components".
- **CR 701.67c** - "whenever a player waterbends" triggers whenever that player
  pays a waterbend cost, regardless of how they paid it.
- **CR 603.7b** - a delayed triggered ability lasting "this turn" triggers
  every time its event occurs that turn; **CR 700.4** - "dies" means put into
  a graveyard from the battlefield.
- **CR 608.2g** - a spell cast while another resolves (cascade, CR 702.85a)
  still announces and pays its additional costs.

The mechanic is proved on Ruinous Waterbending ({1}{B}{B}, waterbend {4}:
"All creatures get -2/-2 until end of turn. If this spell's additional cost
was paid, whenever a creature dies this turn, you gain 1 life.") and, for
generality, on Spirit Water Revival ({1}{U}{U}, waterbend {6}), whose
different amount and colour exercise the reader rather than one sentence.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.casting import optional_additional_costs
from magic_cards_model.machines.keywords import cascade
from magic_cards_model.machines.objects_as_costs import waterbend
from magic_cards_model.models import Zone
from tests.cards import card
from tests.scenarios.harness import Scenario


def _settle(scenario) -> None:
    """State-based actions, then every trigger they put on the stack."""
    for _ in range(30):
        scenario.state_based_actions()
        if scenario.game.stack_is_empty and not scenario.pending_triggers:
            return
        scenario.pass_until_resolved()
    raise AssertionError("the stack never emptied")


def _board(*, alice=(), bob=(), hand=("Ruinous Waterbending",)) -> Scenario:
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=list(hand),
            battlefield=["Swamp", "Swamp", "Swamp", *alice],
            library=["Swamp"] * 10,
        )
        .player("bob", battlefield=list(bob), library=["Mountain"] * 10)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _life(scenario, who: str = "alice") -> int:
    return scenario.player(who).life


# -- the enumeration (CR 601.2b, CR 118.8b) ----------------------------------


@pytest.mark.parametrize(
    ("name", "printed"),
    [("Ruinous Waterbending", "{4}"), ("Spirit Water Revival", "{6}")],
)
def test_the_optional_waterbend_is_enumerated_as_understood(name, printed):
    options = optional_additional_costs(card(name))
    (option,) = [option for option in options if option.keyword == "waterbend"]
    assert option.understood
    assert option.rule == "CR 701.67a"
    assert printed in option.cost
    assert not option.repeatable


# -- paid by tapping (CR 701.67a) ---------------------------------------------


def test_paid_by_tapping_creatures_and_artifacts_and_gains_a_life_per_death():
    """Four taps - two creatures, two artifacts - pay the whole waterbend {4};
    the three Swamps pay {1}{B}{B}. The -2/-2 kills alice's Bears, Elves and
    Ornithopter and bob's Bears: four deaths, four lives."""
    scenario = _board(
        alice=["Grizzly Bears", "Llanowar Elves", "Welding Jar", "Ornithopter"],
        bob=["Grizzly Bears", "Hill Giant"],
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    elves = scenario.creature("Llanowar Elves", "alice")
    jar = scenario.creature("Welding Jar", "alice")
    thopter = scenario.creature("Ornithopter", "alice")

    casting = scenario.cast("Ruinous Waterbending")
    casting.pay_waterbend()
    payment = casting.begin_paying()
    assert payment.waterbend_generic == 4
    assert payment.mana_owed.converted == 7
    waterbend(payment, bears, elves, jar, thopter)
    scenario.pay_with(payment, *scenario.untapped_sources("Swamp", "Swamp", "Swamp"))
    scenario.put_on_stack(casting)
    assert bears.tapped and elves.tapped and jar.tapped and thopter.tapped

    before = _life(scenario)
    scenario.resolve_top()
    _settle(scenario)

    assert bears.zone is Zone.GRAVEYARD
    assert scenario.creature("Hill Giant", "bob").zone is Zone.BATTLEFIELD
    assert _life(scenario) == before + 4


def test_paid_through_game_cast_with_taps_and_mana():
    """`Game.cast`'s `waterbend` announcement and `waterbend_tapping` taps:
    the same cost paid through the one atomic entry point a seat uses."""
    scenario = _board(
        alice=["Grizzly Bears", "Welding Jar", "Swamp", "Swamp"],
        bob=["Grizzly Bears"],
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    jar = scenario.creature("Welding Jar", "alice")
    spell = scenario.find("Ruinous Waterbending", Zone.HAND, "alice")
    swamps = scenario.untapped_sources("Swamp", "Swamp", "Swamp", "Swamp", "Swamp")

    before = _life(scenario)
    scenario.game.cast(
        spell, "alice", waterbend=True, waterbend_tapping=[bears, jar], mana_sources=swamps
    )
    assert bears.tapped and jar.tapped
    assert all(swamp.tapped for swamp in swamps)
    assert scenario.game.cast_record(spell).waterbend_paid
    scenario.resolve_top()
    _settle(scenario)

    assert _life(scenario) == before + 2


# -- paid with mana alone (CR 701.67c: "regardless of how") ------------------


def test_paid_entirely_with_mana_still_counts_as_paid():
    scenario = _board(
        alice=["Swamp", "Swamp", "Swamp", "Swamp"],
        bob=["Grizzly Bears", "Llanowar Elves"],
    )
    casting = scenario.cast("Ruinous Waterbending")
    casting.pay_waterbend()
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources(*["Swamp"] * 7))
    scenario.put_on_stack(casting)

    before = _life(scenario)
    scenario.resolve_top()
    _settle(scenario)

    assert scenario.game.turn_fact_holds("waterbent", "alice") is True
    assert _life(scenario) == before + 2


# -- declined (CR 118.8b) ----------------------------------------------------


def test_declined_the_creatures_still_shrink_but_no_life_is_gained():
    scenario = _board(alice=["Grizzly Bears"], bob=["Grizzly Bears", "Llanowar Elves"])
    bears = scenario.creature("Grizzly Bears", "alice")
    before = _life(scenario)

    spell = scenario.cast_and_resolve(
        "Ruinous Waterbending", *scenario.untapped_sources("Swamp", "Swamp", "Swamp")
    )
    _settle(scenario)

    assert spell.zone is Zone.GRAVEYARD
    assert bears.zone is Zone.GRAVEYARD
    assert _life(scenario) == before
    assert scenario.game.turn_fact_holds("waterbent", "alice") is False


def test_without_the_waterbend_announced_no_permanent_may_be_tapped_for_it():
    """The tap method exists only for a waterbend cost being paid: a seat that
    did not announce one cannot tap a creature toward {1}{B}{B}."""
    scenario = _board(alice=["Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears", "alice")
    spell = scenario.find("Ruinous Waterbending", Zone.HAND, "alice")

    with pytest.raises(ValueError, match="701.67"):
        scenario.game.cast(
            spell,
            "alice",
            waterbend_tapping=[bears],
            mana_sources=scenario.untapped_sources("Swamp", "Swamp"),
        )
    assert spell.zone is Zone.HAND
    assert not bears.tapped


# -- CR 701.67b's bound ------------------------------------------------------


def test_a_fifth_tap_is_refused_although_the_spell_has_generic_mana_left():
    """The total cost is {5}{B}{B}: four of those five generic are the
    waterbend's own, one is Ruinous Waterbending's printed {1}. A fifth tap
    aimed at that printed {1} is refused (CR 701.67b), and a tap can never pay
    a {B} at all - the Swamps still have to."""
    scenario = _board(
        alice=["Grizzly Bears", "Llanowar Elves", "Welding Jar", "Ornithopter", "Serra Angel"],
    )
    taps = [
        scenario.creature(name, "alice")
        for name in ("Grizzly Bears", "Llanowar Elves", "Welding Jar", "Ornithopter")
    ]
    angel = scenario.creature("Serra Angel", "alice")

    casting = scenario.cast("Ruinous Waterbending")
    casting.pay_waterbend()
    payment = casting.begin_paying()
    waterbend(payment, *taps)
    with pytest.raises(ValueError, match="701.67b"):
        waterbend(payment, angel)

    assert payment.mana_owed.converted == 3
    scenario.pay_with(payment, *scenario.untapped_sources("Swamp", "Swamp", "Swamp"))
    assert payment.step.value == "paid"
    assert not angel.tapped


def test_the_waterbend_cannot_be_announced_twice():
    scenario = _board()
    casting = scenario.cast("Ruinous Waterbending")
    casting.pay_waterbend()
    with pytest.raises(ValueError, match="already"):
        casting.pay_waterbend()


def test_a_spell_without_the_cost_cannot_announce_it():
    scenario = _board(hand=("Lightning Bolt",))
    casting = scenario.cast("Lightning Bolt", targets=["bob"])
    with pytest.raises(ValueError, match="701.67a"):
        casting.pay_waterbend()


# -- "whenever a creature dies this turn" (CR 603.7b) ------------------------


def test_every_creature_dying_this_turn_gains_a_life_not_only_the_shrunk_ones():
    """The -2/-2 kills two creatures; a Lightning Bolt afterwards kills the
    Hill Giant it left as a 1/1 - a third death the same turn, a third life."""
    scenario = _board(
        alice=["Swamp", "Swamp", "Swamp", "Swamp", "Mountain", "Grizzly Bears"],
        bob=["Grizzly Bears", "Hill Giant"],
        hand=("Ruinous Waterbending", "Lightning Bolt"),
    )
    casting = scenario.cast("Ruinous Waterbending")
    casting.pay_waterbend()
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources(*["Swamp"] * 7))
    scenario.put_on_stack(casting)
    before = _life(scenario)
    scenario.resolve_top()
    _settle(scenario)
    assert _life(scenario) == before + 2

    giant = scenario.creature("Hill Giant", "bob")
    scenario.cast_and_resolve(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=[giant]
    )
    _settle(scenario)

    assert giant.zone is Zone.GRAVEYARD
    assert _life(scenario) == before + 3


# -- CR 701.67c: "whenever you waterbend" ------------------------------------


def test_the_waterbend_trigger_fires_exactly_once_for_the_spells_cost():
    """Avatar Aang (4/4, survives the -2/-2) draws one card for the one
    waterbend cost paid, however many permanents were tapped to pay it."""
    scenario = _board(
        alice=["Avatar Aang", "Welding Jar", "Ornithopter", "Swamp", "Swamp"],
    )
    jar = scenario.creature("Welding Jar", "alice")
    thopter = scenario.creature("Ornithopter", "alice")
    alice = scenario.player("alice")
    hand_before = len(alice.hand)

    casting = scenario.cast("Ruinous Waterbending")
    casting.pay_waterbend()
    payment = casting.begin_paying()
    waterbend(payment, jar, thopter)
    scenario.pay_with(payment, *scenario.untapped_sources(*["Swamp"] * 5))
    scenario.put_on_stack(casting)
    _settle(scenario)

    # The spell left the hand (-1) and Aang drew exactly one card (+1).
    assert len(alice.hand) == hand_before
    assert scenario.game.turn_fact_holds("waterbent", "alice") is True


def test_declining_the_waterbend_never_fires_the_trigger():
    scenario = _board(alice=["Avatar Aang"])
    alice = scenario.player("alice")
    hand_before = len(alice.hand)

    scenario.cast_onto_stack(
        "Ruinous Waterbending", *scenario.untapped_sources("Swamp", "Swamp", "Swamp")
    )
    _settle(scenario)

    assert len(alice.hand) == hand_before - 1


# -- CR 608.2g: offered on a cast made during resolution ---------------------


def test_a_cascaded_cast_is_offered_the_waterbend_and_may_tap_for_it():
    """Bloodbraid Elf cascades into Ruinous Waterbending, cast without paying
    its mana cost - but its additional cost is still offered (CR 601.2b) and,
    taken, paid by tapping two creatures and two artifacts."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Bloodbraid Elf"],
            library=["Ruinous Waterbending", "Swamp", "Swamp"],
            battlefield=[
                "Mountain",
                "Forest",
                "Forest",
                "Forest",
                "Grizzly Bears",
                "Llanowar Elves",
                "Welding Jar",
                "Ornithopter",
            ],
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    tappers = [
        scenario.creature(name, "alice")
        for name in ("Grizzly Bears", "Llanowar Elves", "Welding Jar", "Ornithopter")
    ]
    elf = scenario.cast_onto_stack(
        "Bloodbraid Elf", *scenario.untapped_sources("Mountain", "Forest", "Forest", "Forest")
    )
    scenario.will_take_the_may(True, source="Ruinous Waterbending")
    scenario.will_choose_cards(*tappers, source="Ruinous Waterbending")

    result = cascade(scenario.game, elf, seed=0)

    assert result.hit is not None and result.hit.name == "Ruinous Waterbending"
    assert all(state.tapped for state in tappers)
    assert scenario.game.cast_record(result.hit).waterbend_paid
    before = _life(scenario)
    scenario.resolve_top()
    _settle(scenario)
    # alice's Bears, Elves, Ornithopter and bob's Bears die; the Elf is
    # still on the stack.
    assert _life(scenario) == before + 4


# -- generality: Spirit Water Revival's waterbend {6} ------------------------


def test_spirit_water_revival_waterbend_six_paid_by_taps_draws_seven():
    """A second printing with the same shape: waterbend {6} on a blue
    sorcery. Six taps pay the whole waterbend; the Islands pay {1}{U}{U}; the
    paid branch shuffles the graveyard in and draws seven."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Spirit Water Revival"],
            battlefield=[
                "Island",
                "Island",
                "Island",
                "Grizzly Bears",
                "Llanowar Elves",
                "Welding Jar",
                "Ornithopter",
                "Memnite",
                "Serra Angel",
            ],
            library=["Island"] * 10,
            graveyard=["Lightning Bolt"],
        )
        .player("bob", library=["Mountain"] * 10)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    taps = [
        scenario.creature(name, "alice")
        for name in (
            "Grizzly Bears",
            "Llanowar Elves",
            "Welding Jar",
            "Ornithopter",
            "Memnite",
            "Serra Angel",
        )
    ]
    casting = scenario.cast("Spirit Water Revival")
    casting.pay_waterbend()
    payment = casting.begin_paying()
    assert payment.waterbend_generic == 6
    waterbend(payment, *taps)
    scenario.pay_with(payment, *scenario.untapped_sources("Island", "Island", "Island"))
    spell = scenario.put_on_stack(casting)
    scenario.resolve_top()
    _settle(scenario)

    alice = scenario.player("alice")
    assert all(state.tapped for state in taps)
    assert len(alice.hand) == 7
    assert spell.zone is Zone.EXILE
    assert not alice.graveyard


def test_spirit_water_revival_declined_draws_two():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Spirit Water Revival"],
            battlefield=["Island", "Island", "Island"],
            library=["Island"] * 10,
        )
        .player("bob", library=["Mountain"] * 10)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    spell = scenario.cast_and_resolve(
        "Spirit Water Revival", *scenario.untapped_sources("Island", "Island", "Island")
    )
    _settle(scenario)
    assert len(scenario.player("alice").hand) == 2
    assert spell.zone is Zone.EXILE
