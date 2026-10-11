"""Scenario: "each opponent sacrifices a creature or planeswalker with the
greatest mana value among creatures and planeswalkers they control".

The edict narrowed to the sacrificing player's own highest mana value
creatures and planeswalkers:

- **Flare of Malice** - the reported card, an instant whose second line is
  this edict.
- **Soul Shatter** - off-pool second printing, a sorcery carrying the same
  edict as its whole text (the only other Modern/Pioneer/Standard printing of
  the "each opponent" form).
- **Break Under Pressure** - the "target opponent" sibling with a trailing
  "You gain 2 life.", read by the same reader.

Rules, each looked up with `mise run rules:find` in the session that wrote
this file:

- CR 701.21a: the sacrificing player moves a permanent they control to its
  owner's graveyard; nothing is targeted (CR 115.10a).
- CR 202.3: mana value is the total mana in the mana cost; CR 202.3a a token
  with no mana cost has mana value 0; CR 202.3e an {X} counts as 0 off the
  stack.
- CR 101.4: with several opponents each chooses in APNAP order, then the
  sacrifices happen simultaneously.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import DecisionKind
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter

from .harness import Scenario

FLARE = "Flare of Malice"
SHATTER = "Soul Shatter"
SWAMPS = ("Swamp", "Swamp", "Swamp", "Swamp")


def _alice_with_flare(*bob_battlefield: str, alice_extra: tuple[str, ...] = ()) -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=[FLARE], battlefield=[*SWAMPS, *alice_extra])
        .player("bob", battlefield=list(bob_battlefield))
    )


def _cast_flare(scenario) -> None:
    scenario.cast_and_resolve(
        FLARE, *scenario.untapped_sources(*SWAMPS, username="alice"), username="alice"
    )


def _choices_put_to(scenario, username: str) -> list:
    return [
        decision
        for decision in scenario.questions_asked()
        if decision.kind is DecisionKind.CHOOSE_CARDS and decision.player == username
    ]


def test_the_highest_mana_value_creature_is_sacrificed():
    """Serra Angel (MV 5) is strictly above Grizzly Bears (MV 2): no choice
    exists, the Angel goes and the Bears stay."""
    scenario = _alice_with_flare("Grizzly Bears", "Serra Angel").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    angel = scenario.creature("Serra Angel", "bob")

    _cast_flare(scenario)

    assert angel.zone is Zone.GRAVEYARD
    assert bears.zone is Zone.BATTLEFIELD
    assert _choices_put_to(scenario, "bob") == []


def test_a_planeswalker_with_the_greatest_mana_value_is_the_one_sacrificed():
    """Planeswalkers share the pool: Liliana of the Veil (MV 3) outranks
    Grizzly Bears (MV 2), so Liliana is sacrificed."""
    scenario = _alice_with_flare("Grizzly Bears", "Liliana of the Veil").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    liliana = scenario.find("Liliana of the Veil", Zone.BATTLEFIELD, "bob")

    _cast_flare(scenario)

    assert liliana.zone is Zone.GRAVEYARD
    assert bears.zone is Zone.BATTLEFIELD


def test_a_creature_above_the_planeswalker_is_sacrificed_instead():
    """The comparison runs across both types: Serra Angel (MV 5) beats
    Liliana of the Veil (MV 3)."""
    scenario = _alice_with_flare("Liliana of the Veil", "Serra Angel").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.creature("Serra Angel", "bob")
    liliana = scenario.find("Liliana of the Veil", Zone.BATTLEFIELD, "bob")

    _cast_flare(scenario)

    assert angel.zone is Zone.GRAVEYARD
    assert liliana.zone is Zone.BATTLEFIELD


def test_other_permanent_types_neither_count_nor_go():
    """Ugin's Nexus is a mana value 5 artifact: it is neither a creature nor
    a planeswalker, so it sets no bar and is never sacrificed - Grizzly Bears
    is bob's greatest among creatures and planeswalkers."""
    scenario = _alice_with_flare("Grizzly Bears", "Ugin's Nexus").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    nexus = scenario.find("Ugin's Nexus", Zone.BATTLEFIELD, "bob")

    _cast_flare(scenario)

    assert bears.zone is Zone.GRAVEYARD
    assert nexus.zone is Zone.BATTLEFIELD


def test_a_tie_is_the_sacrificing_players_choice_among_the_tied_only():
    """Grizzly Bears and Dark Confidant are both MV 2, Llanowar Elves is 1:
    bob - not alice - picks between the two tied, and the Elves are never
    offered."""
    scenario = _alice_with_flare("Grizzly Bears", "Dark Confidant", "Llanowar Elves").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    confidant = scenario.creature("Dark Confidant", "bob")
    elves = scenario.creature("Llanowar Elves", "bob")
    scenario.will_choose_cards(confidant, username="bob", source=FLARE)

    _cast_flare(scenario)

    assert confidant.zone is Zone.GRAVEYARD
    assert bears.zone is Zone.BATTLEFIELD
    assert elves.zone is Zone.BATTLEFIELD
    (question,) = _choices_put_to(scenario, "bob")
    assert set(question.cards) == {bears.id, confidant.id}
    assert question.amount == 1


def test_an_x_in_the_mana_cost_counts_as_zero_on_the_battlefield():
    """CR 202.3e: Walking Ballista's {X}{X} is 0 off the stack, however many
    counters it carries, so Llanowar Elves (MV 1) is the greatest."""
    scenario = _alice_with_flare("Walking Ballista", "Llanowar Elves").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ballista = scenario.creature("Walking Ballista", "bob")
    ballista.add_counters(Counter.PLUS_ONE, 4)
    elves = scenario.creature("Llanowar Elves", "bob")

    _cast_flare(scenario)

    assert elves.zone is Zone.GRAVEYARD
    assert ballista.zone is Zone.BATTLEFIELD


def _bob_with_spirits(*battlefield: str) -> Scenario:
    """Bob, active, makes three 1/1 Spirit tokens with Spectral Procession;
    alice answers at instant speed once he passes."""
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "bob",
            hand=["Spectral Procession"],
            battlefield=["Plains", "Plains", "Plains", *battlefield],
        )
        .player("alice", hand=[FLARE], battlefield=list(SWAMPS))
    )


def _make_spirits(scenario) -> list:
    scenario.start_at(Step.PRECOMBAT_MAIN)
    plains = scenario.untapped_sources("Plains", "Plains", "Plains", username="bob")
    scenario.cast_and_resolve("Spectral Procession", *plains, username="bob")
    spirits = [
        state
        for state in scenario.game.battlefield
        if state.name == "Spirit Token" and state.controller == "bob"
    ]
    assert len(spirits) == 3
    scenario.pass_priority("bob")
    return spirits


def test_a_token_has_mana_value_zero_so_a_card_above_it_goes():
    """CR 202.3a: the Spirit tokens have no mana cost, so mana value 0, and
    Llanowar Elves (MV 1) is bob's greatest."""
    scenario = _bob_with_spirits("Llanowar Elves").build()
    spirits = _make_spirits(scenario)
    elves = scenario.creature("Llanowar Elves", "bob")

    _cast_flare(scenario)

    assert elves.zone is Zone.GRAVEYARD
    assert all(spirit.zone is Zone.BATTLEFIELD for spirit in spirits)


def test_only_tokens_means_one_token_of_bobs_choice_goes():
    """Three Spirits all tie at 0: bob chooses which one is sacrificed."""
    scenario = _bob_with_spirits().build()
    spirits = _make_spirits(scenario)
    scenario.will_choose_cards(spirits[2], username="bob", source=FLARE)

    _cast_flare(scenario)

    assert spirits[2].zone is not Zone.BATTLEFIELD
    assert spirits[0].zone is Zone.BATTLEFIELD
    assert spirits[1].zone is Zone.BATTLEFIELD
    (question,) = _choices_put_to(scenario, "bob")
    assert set(question.cards) == {spirit.id for spirit in spirits}


def test_an_opponent_with_no_creature_or_planeswalker_does_nothing():
    """Only lands and an artifact: nothing qualifies, nothing is sacrificed,
    and no question is asked."""
    scenario = _alice_with_flare("Plains", "Ugin's Nexus").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    nexus = scenario.find("Ugin's Nexus", Zone.BATTLEFIELD, "bob")

    _cast_flare(scenario)

    assert nexus.zone is Zone.BATTLEFIELD
    assert scenario.find(FLARE, Zone.GRAVEYARD, "alice").zone is Zone.GRAVEYARD
    assert _choices_put_to(scenario, "bob") == []


def test_the_casters_own_permanents_are_never_counted():
    """ "Each opponent": alice's own Serra Angel neither raises bob's bar nor
    is sacrificed."""
    scenario = _alice_with_flare("Grizzly Bears", alice_extra=("Serra Angel",)).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.creature("Serra Angel", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")

    _cast_flare(scenario)

    assert bears.zone is Zone.GRAVEYARD
    assert angel.zone is Zone.BATTLEFIELD


def test_every_opponent_sacrifices_their_own_greatest():
    """CR 101.4: bob and carol each lose their own greatest - computed per
    player, so carol's Grizzly Bears goes even though bob's Serra Angel is
    higher - and the lower ones stay."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=[FLARE], battlefield=list(SWAMPS))
        .player("bob", battlefield=["Serra Angel", "Llanowar Elves"])
        .player("carol", battlefield=["Grizzly Bears", "Elvish Mystic"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.creature("Serra Angel", "bob")
    elves = scenario.creature("Llanowar Elves", "bob")
    bears = scenario.creature("Grizzly Bears", "carol")
    mystic = scenario.creature("Elvish Mystic", "carol")

    _cast_flare(scenario)

    assert angel.zone is Zone.GRAVEYARD
    assert bears.zone is Zone.GRAVEYARD
    assert elves.zone is Zone.BATTLEFIELD
    assert mystic.zone is Zone.BATTLEFIELD


# -- Soul Shatter: the off-pool second printing --------------------------------


def test_soul_shatter_reads_the_same_edict():
    """Soul Shatter, a sorcery whose whole text is the edict: the same
    per-opponent greatest, a planeswalker included."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=[SHATTER], battlefield=["Swamp", "Swamp", "Swamp"])
        .player("bob", battlefield=["Grizzly Bears", "Liliana of the Veil"])
        .player("carol", battlefield=["Serra Angel", "Llanowar Elves"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    liliana = scenario.find("Liliana of the Veil", Zone.BATTLEFIELD, "bob")
    angel = scenario.creature("Serra Angel", "carol")
    elves = scenario.creature("Llanowar Elves", "carol")

    scenario.cast_and_resolve(SHATTER, *scenario.untapped_sources("Swamp", "Swamp", "Swamp"))

    assert liliana.zone is Zone.GRAVEYARD
    assert angel.zone is Zone.GRAVEYARD
    assert bears.zone is Zone.BATTLEFIELD
    assert elves.zone is Zone.BATTLEFIELD


def test_soul_shatter_tie_is_chosen_by_each_opponent():
    """A tie on carol's side is carol's own choice."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=[SHATTER], battlefield=["Swamp", "Swamp", "Swamp"])
        .player("bob", battlefield=["Serra Angel"])
        .player("carol", battlefield=["Grizzly Bears", "Dark Confidant"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.creature("Serra Angel", "bob")
    bears = scenario.creature("Grizzly Bears", "carol")
    confidant = scenario.creature("Dark Confidant", "carol")
    scenario.will_choose_cards(bears, username="carol", source=SHATTER)

    scenario.cast_and_resolve(SHATTER, *scenario.untapped_sources("Swamp", "Swamp", "Swamp"))

    assert angel.zone is Zone.GRAVEYARD
    assert bears.zone is Zone.GRAVEYARD
    assert confidant.zone is Zone.BATTLEFIELD
    (question,) = _choices_put_to(scenario, "carol")
    assert set(question.cards) == {bears.id, confidant.id}
    assert _choices_put_to(scenario, "bob") == []


# -- Break Under Pressure: the targeted sibling stays intact ------------------


def test_break_under_pressure_still_hits_only_its_target_and_gains_life():
    """The "target opponent" form shares the reader: only the targeted
    opponent sacrifices, and the trailing "You gain 2 life." still applies."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Break Under Pressure"], battlefield=["Swamp", "Swamp", "Swamp"])
        .player("bob", battlefield=["Serra Angel"])
        .player("carol", battlefield=["Serra Angel"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bobs = scenario.creature("Serra Angel", "bob")
    carols = scenario.creature("Serra Angel", "carol")
    life_before = scenario.game.player("alice").life

    scenario.cast_and_resolve(
        "Break Under Pressure",
        *scenario.untapped_sources("Swamp", "Swamp", "Swamp"),
        targets=["bob"],
    )

    assert bobs.zone is Zone.GRAVEYARD
    assert carols.zone is Zone.BATTLEFIELD
    assert scenario.game.player("alice").life == life_before + 2
