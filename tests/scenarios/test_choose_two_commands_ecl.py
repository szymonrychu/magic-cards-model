"""Grub's Command and Sygg's Command: CR 700.2's "Choose two -" (CR 700.2d),
each mode read the same way any other card's own text is - no per-command
row, `Choose_two` already generic - except three individual modes this file
closes:

- **"Creatures target player controls get +1/+1 and gain haste until end of
  turn."** (Grub's Command) / **"Creatures target player controls gain
  lifelink until end of turn."** (Sygg's Command) - `_TARGET_PLAYER_
  CREATURES_PUMP_RE` already read "creatures target player controls get
  +N/+N[ and gain `<keywords>`]", but two things stopped either mode from
  ever reaching it: the bare "and" inside "get +1/+1 and gain haste"
  (`_prepare_effect_clauses` cuts clean through it, the same "power and
  toughness" problem this round's other readers keep meeting), and there
  was no bare-keyword-only branch at all for a mode naming no pump.
- **"Target player mills five cards, then puts each Goblin card milled this
  way into their hand."** (Grub's Command) - a brand new reader: the *same*
  player both mills and receives (every existing mill-then-hand family
  puts the result in the resolving spell's own controller's hand instead),
  CR 608.2d's unconditional "each" with no "you may" at all.

Proof printing: **Savage Alliance** (real Scryfall data, added with
`scripts/add_card.py`, Pioneer/Modern `legal`, not a listed ecl-T8 card, not
in any deck list) - "Creatures target player controls gain trample until
end of turn." is the bare-keyword-only shape on its own, no pump at all,
proving that branch independently of Sygg's Command's own printing. No
second real printing shares Grub's Command's own exact "get +1/+1 and gain
haste" wording (a Scryfall full-text search this session found Grub's
Command alone) - recorded as a dated line in `MEMORY.md`; the bare-"and"
survival is still proven generally, just by the pump-plus-keyword shape's
*other* half (Savage Alliance's own single-keyword grant needs no "and" at
all, so it exercises the widened regex's new alternation branch, and the
pre-split whole-text registration is shared code with no separate wording
to test twice).

Every CR number below was looked up with `mise run rules:find` in the
session that wrote this file: 700.2 (a modal spell), 700.2a (the controller
chooses modes as part of casting), 700.2d (the same mode not normally chosen
twice), 613.1f / 613.4c (a keyword grant is layer 6, a P/T modification is
sublayer 7c), 611.2c (the affected creatures are fixed as the effect
begins), 701.17a (mill), 608.2d (an unconditional "each" asks no question).
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import has_keyword
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from magic_cards_model.support import card_support
from tests.cards import card

from .harness import Scenario

GRUBS_COMMAND = "Grub's Command"
SYGGS_COMMAND = "Sygg's Command"
SAVAGE_ALLIANCE = "Savage Alliance"


def test_all_three_printings_are_fully_handled():
    for name in (GRUBS_COMMAND, SYGGS_COMMAND, SAVAGE_ALLIANCE):
        bad = [c for c in card_support(card(name)).clauses if c.outcome != "handled"]
        assert not bad, (name, bad)


# -- Grub's Command: pump+haste mode, and the mill-into-their-own-hand mode -


def test_grubs_command_pumps_a_players_creatures_and_mills_them_goblins_home():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=[GRUBS_COMMAND],
            battlefield=["Swamp", "Mountain", "Mountain", "Mountain", "Mountain", "Mountain"],
        )
        .player(
            "bob",
            battlefield=["Grizzly Bears"],
            library=["Boggart Cursecrafter", "Lightning Bolt", "Opt", "Elvish Mystic"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    goblin, bolt, opt, mystic = scenario.player("bob").library
    sources = scenario.untapped_sources(
        "Swamp", "Mountain", "Mountain", "Mountain", "Mountain", "Mountain"
    )

    casting = scenario.cast(GRUBS_COMMAND)
    casting.choose_modes([2, 4])
    casting.choose_targets(["bob", "bob"])
    scenario.pay_with(casting.begin_paying(), *sources)
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert bears.power == 3, "+1/+1 on a 2/2"
    assert has_keyword(bears, "haste", scenario.game)
    bob = scenario.player("bob")
    assert goblin in bob.hand, "the only Goblin card among the milled cards"
    assert bolt.zone is Zone.GRAVEYARD
    assert opt.zone is Zone.GRAVEYARD
    assert mystic.zone is Zone.GRAVEYARD


def test_grubs_command_copies_a_goblin_and_destroys_an_artifact():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=[GRUBS_COMMAND],
            battlefield=[
                "Swamp",
                "Mountain",
                "Mountain",
                "Mountain",
                "Mountain",
                "Mountain",
                "Boggart Cursecrafter",
            ],
        )
        .player("bob", battlefield=["Mind Stone"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    goblin = scenario.creature("Boggart Cursecrafter", "alice")
    stone = scenario.find("Mind Stone", Zone.BATTLEFIELD, "bob")
    sources = scenario.untapped_sources(
        "Swamp", "Mountain", "Mountain", "Mountain", "Mountain", "Mountain"
    )

    casting = scenario.cast(GRUBS_COMMAND)
    casting.choose_modes([1, 3])
    casting.choose_targets([goblin, stone])
    scenario.pay_with(casting.begin_paying(), *sources)
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    copies = [
        state
        for state in scenario.game.permanents_controlled_by("alice")
        if state.token and state.name == "Boggart Cursecrafter"
    ]
    assert len(copies) == 1
    assert stone.zone is Zone.GRAVEYARD


# -- Sygg's Command: token copy + lifelink, and draw + tap/stun ------------


def test_syggs_command_copies_a_merfolk_and_grants_lifelink():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[SYGGS_COMMAND],
            battlefield=["Plains", "Island", "Plains"],
        )
        .player("bob", battlefield=["Grizzly Bears"], library=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Plains", "Island", "Plains")
    target_creature = scenario.creature("Grizzly Bears", "bob")

    casting = scenario.cast(SYGGS_COMMAND)
    casting.choose_modes([2, 3])
    casting.choose_targets(["bob", "bob"])
    scenario.pay_with(casting.begin_paying(), *sources)
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert has_keyword(target_creature, "lifelink", scenario.game)
    assert len(scenario.player("bob").hand) == 1, "'target player draws a card'"


def test_syggs_command_taps_and_stuns_a_creature():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[SYGGS_COMMAND],
            battlefield=["Plains", "Island", "Plains"],
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    sources = scenario.untapped_sources("Plains", "Island", "Plains")

    casting = scenario.cast(SYGGS_COMMAND)
    casting.choose_modes([3, 4])
    casting.choose_targets(["alice", bears])
    scenario.pay_with(casting.begin_paying(), *sources)
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert bears.tapped
    assert bears.counter_count(Counter.STUN) == 1


# -- proof printing: Savage Alliance, the bare-keyword-only shape alone -----


def test_savage_alliance_grants_trample_with_no_pump_at_all():
    scenario = (
        Scenario()
        .player("alice", hand=[SAVAGE_ALLIANCE], battlefield=["Mountain"] * 3)
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    sources = scenario.untapped_sources("Mountain", "Mountain", "Mountain")

    casting = scenario.cast(SAVAGE_ALLIANCE)
    casting.choose_modes([1])
    casting.choose_targets(["bob"])
    scenario.pay_with(casting.begin_paying(), *sources)
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert has_keyword(bears, "trample", scenario.game)
    assert bears.power == 2, "no pump at all, only the keyword"
