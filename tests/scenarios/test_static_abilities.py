"""Scenario: static abilities, and the continuous effects they generate.

CR 604.2: "Static abilities create continuous effects ... These effects are
active as long as the permanent with the ability remains on the battlefield and
has the ability". CR 113.3d says the same thing from the other end: "Static
abilities are written as statements. They're simply true."

Which effects a card generates is the hand-written `LAYER_EFFECTS` registry in
`machines/layers.py` - nothing parses a static ability off oracle text - so this
file is also the test that the registry says the right thing about the cards in
it. The cards themselves are real Scryfall printings and the boards are built by
the scenario harness; only the mapping from text to effect is written by hand.

The interesting cases are the ones where the layer a static ability lives in
decides the answer:

- **Layer 4** (CR 613.1d), Dryad of the Ilysian Grove, which adds land types.
- **Layer 6** (CR 613.1f), Dress Down, which takes abilities away - and so can
  switch another static ability off before it ever applies (CR 613.6).
- **Sublayer 7c** (CR 613.4c), Elesh Norn and Relentless Rats, which modify
  power and toughness without setting it.

Most tests here build a real board and ask the layer engine directly what it
computes, which is the sharpest way to pin a layer's behaviour. The last one
asks the other end: `Game` binds a permanent as it enters the battlefield, so
`CardState.power`/`.toughness` answer through the same engine (CR 613.5) and a
static ability is visible to every caller that reads those two properties.
Every CR number here was looked up with `knowledge_search(type="rules")`.
"""

from magic_cards_model.machines.layers import compute_board, static_effects
from tests.scenarios.harness import Scenario


def computed(scenario):
    """The whole board with every registered static ability applied (CR 613.7a)."""
    permanents = scenario.game.battlefield
    return compute_board(permanents, static_effects(permanents))


# --------------------------------------------------------------------------
# Layer 4: Dryad of the Ilysian Grove
# --------------------------------------------------------------------------


def test_the_dryad_makes_your_lands_every_basic_land_type():
    """CR 613.1d, and CR 305.6 for the abilities that come with the types.

    "An object with the land card type and a basic land type has the intrinsic
    ability '{T}: Add [mana symbol]'", so a Mountain under a Dryad taps for any
    of the five colours without anything having granted it an ability.
    """
    scenario = (
        Scenario().player("alice", battlefield=["Dryad of the Ilysian Grove", "Mountain"]).build()
    )
    mountain = scenario.creature("Mountain", "alice")

    board = computed(scenario)

    assert set(board.of(mountain).subtypes) == {
        "Mountain",
        "Plains",
        "Island",
        "Swamp",
        "Forest",
    }
    assert board.of(mountain).has_ability("{T}: Add {U}.")
    assert board.of(mountain).has_ability("{T}: Add {R}."), "and it is still a Mountain"


def test_a_nonbasic_land_keeps_its_own_text_under_the_dryad():
    """ "In addition to" is not CR 305.7's replacement.

    CR 305.7 strips a land's old types and rules text only when an effect *sets*
    the subtype - Blood Moon. The Dryad adds, so Tinder Farm keeps both of its
    printed mana abilities and picks up five more.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Dryad of the Ilysian Grove", "Tinder Farm"])
        .build()
    )
    farm = scenario.creature("Tinder Farm", "alice")

    board = computed(scenario)

    assert board.of(farm).has_ability("{T}: Add {G}."), "its own printed ability survives"
    assert board.of(farm).has_ability("{T}: Add {B}."), "and it gained the Swamp's"
    assert board.of(farm).is_land and not board.of(farm).is_basic
    assert set(board.of(farm).subtypes) >= {"Plains", "Island", "Swamp", "Mountain", "Forest"}


def test_the_dryad_does_not_touch_lands_it_does_not_control():
    """ "Lands *you control*" - the selector is a controller test, not a board sweep."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Dryad of the Ilysian Grove", "Forest"])
        .player("bob", battlefield=["Mountain"])
        .build()
    )
    mountain = scenario.creature("Mountain", "bob")

    board = computed(scenario)

    assert board.of(mountain).subtypes == ("Mountain",)
    assert not board.of(mountain).has_ability("{T}: Add {B}.")


def test_the_dryad_is_a_creature_and_an_enchantment_but_not_a_land():
    """The Dryad's own type line is untouched by its own ability.

    Enchantment Creature - Nymph Dryad. It grants land types to lands, and it is
    not one, so nothing lands on it.
    """
    scenario = Scenario().player("alice", battlefield=["Dryad of the Ilysian Grove"]).build()
    dryad = scenario.creature("Dryad of the Ilysian Grove", "alice")

    board = computed(scenario)

    assert board.of(dryad).is_creature
    assert not board.of(dryad).is_land
    assert board.of(dryad).subtypes == ("Nymph", "Dryad")


# --------------------------------------------------------------------------
# Layer 6: Dress Down
# --------------------------------------------------------------------------


def test_dress_down_strips_a_creature_but_not_an_enchantment():
    """CR 613.1f: "ability-removing effects".

    "Creatures lose all abilities." Dress Down is an Enchantment and not a
    creature, so - unlike Humility, which becomes one under an Opalescence - it
    never strips itself, and neither does it touch Glorious Anthem.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Dress Down", "Glorious Anthem", "Questing Beast"])
        .build()
    )
    dress_down = scenario.creature("Dress Down", "alice")
    anthem = scenario.creature("Glorious Anthem", "alice")
    beast = scenario.creature("Questing Beast", "alice")

    board = computed(scenario)

    assert board.of(beast).abilities == ()
    assert board.of(dress_down).abilities != ()
    assert board.of(anthem).abilities != ()


def test_an_anthem_on_an_enchantment_still_pumps_under_dress_down():
    """Layer 6 removed nothing that mattered, so 7c runs as normal.

    Glorious Anthem is not a creature, so Dress Down leaves its ability alone
    and the +1/+1 still reaches every creature - including the ones Dress Down
    has just made vanilla.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Dress Down", "Glorious Anthem", "Grizzly Bears"])
        .build()
    )
    bears = scenario.creature("Grizzly Bears", "alice")

    board = computed(scenario)

    assert board.of(bears).power_toughness == (3, 3)


def test_dress_down_switches_off_a_creatures_own_anthem_before_it_applies():
    """CR 613.6, read the way round that stops an effect existing.

    Elesh Norn's two anthems are effects of *her* static abilities, and she is a
    creature. Layer 6 (CR 613.1f) removes the abilities before layer 7 is
    reached, so neither effect has started applying and neither ever does - the
    journal records them as skipped rather than applied.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Elesh Norn, Grand Cenobite", "Grizzly Bears", "Dress Down"])
        .player("bob", battlefield=["Watchwolf"])
        .build()
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    wolf = scenario.creature("Watchwolf", "bob")

    board = computed(scenario)

    assert board.of(bears).power_toughness == (2, 2)
    assert board.of(wolf).power_toughness == (3, 3)
    assert len(board.journal.skipped) == 2
    assert board.journal.applied == ["Dress Down: creatures lose all abilities"]


# --------------------------------------------------------------------------
# Sublayer 7c: Elesh Norn
# --------------------------------------------------------------------------


def test_elesh_norn_pumps_yours_and_shrinks_theirs():
    """Two static abilities, one sublayer (CR 613.4c).

    "Other creatures you control get +2/+2. Creatures your opponents control get
    -2/-2." Both modify without setting, so both land in 7c and both apply.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Elesh Norn, Grand Cenobite", "Grizzly Bears"])
        .player("bob", battlefield=["Watchwolf"])
        .build()
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    wolf = scenario.creature("Watchwolf", "bob")

    board = computed(scenario)

    assert board.of(bears).power_toughness == (4, 4)
    assert board.of(wolf).power_toughness == (1, 1)


def test_elesh_norn_does_not_pump_herself():
    """ "*Other* creatures you control" - she is excluded from her own anthem,
    and "your opponents control" excludes her from the other half too."""
    scenario = Scenario().player("alice", battlefield=["Elesh Norn, Grand Cenobite"]).build()
    norn = scenario.creature("Elesh Norn, Grand Cenobite", "alice")

    board = computed(scenario)

    assert board.of(norn).power_toughness == (4, 7)


def test_two_elesh_norns_on_opposite_sides_cancel_out():
    """Both anthems and both shrinks apply, in 7c, and 7c is addition.

    Alice's Bears is +2/+2 from her own Norn and -2/-2 from Bob's, ending where
    it started - and each Norn is pumped by nobody and shrunk by the other, so
    both are 2/5. Timestamps cannot matter here, which is the point: CR 613.4c
    effects commute.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Elesh Norn, Grand Cenobite", "Grizzly Bears"])
        .player("bob", battlefield=["Elesh Norn, Grand Cenobite"])
        .build()
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    alices_norn = scenario.creature("Elesh Norn, Grand Cenobite", "alice")
    bobs_norn = scenario.creature("Elesh Norn, Grand Cenobite", "bob")

    board = computed(scenario)

    assert board.of(bears).power_toughness == (2, 2)
    assert board.of(alices_norn).power_toughness == (2, 5)
    assert board.of(bobs_norn).power_toughness == (2, 5)


def test_elesh_norn_takes_an_opposing_two_two_to_zero_toughness():
    """The board CR 704.5f would act on: "toughness 0 or less".

    Two Norns on Alice's side is -4/-4 on everything Bob has, so his Watchwolf
    computes as a -1/-1. Whether the game *destroys* it is a different question
    - `Game.check_state_based_actions` reads `CardState.toughness`, which knows
    about counters and nothing else - so the assertion here is the number the
    rule would read.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Elesh Norn, Grand Cenobite", "Elesh Norn, Grand Cenobite"],
        )
        .player("bob", battlefield=["Watchwolf"])
        .build()
    )
    wolf = scenario.creature("Watchwolf", "bob")

    board = computed(scenario)

    assert board.of(wolf).power_toughness == (-1, -1)


# --------------------------------------------------------------------------
# Sublayer 7c, counted: Relentless Rats
# --------------------------------------------------------------------------


def test_one_relentless_rats_is_its_printed_two_two():
    """ "for each *other* creature ... named Relentless Rats" - alone, that is none."""
    scenario = Scenario().player("alice", battlefield=["Relentless Rats"]).build()
    (rat,) = scenario.creatures("Relentless Rats", username="alice")

    board = computed(scenario)

    assert board.of(rat).power_toughness == (2, 2)


def test_three_rats_are_each_a_four_four():
    """Each Rat counts the other two, so n of them are each an (n+1)/(n+1).

    Every one of the three effects is in 7c (CR 613.4c) and none of them reads
    another's output - they count *creatures named Relentless Rats*, which is a
    name and not a power - so there is no dependency and no loop.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Relentless Rats", "Relentless Rats", "Relentless Rats"])
        .build()
    )
    rats = scenario.creatures("Relentless Rats", "Relentless Rats", "Relentless Rats")

    board = computed(scenario)

    assert [board.of(rat).power_toughness for rat in rats] == [(4, 4)] * 3
    assert board.journal.cycles == []


def test_a_rat_counts_the_rats_the_other_player_controls():
    """The ability says "on the battlefield", not "you control"."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Relentless Rats"])
        .player("bob", battlefield=["Relentless Rats"])
        .build()
    )
    (mine,) = scenario.creatures("Relentless Rats", username="alice")
    (theirs,) = scenario.creatures("Relentless Rats", username="bob")

    board = computed(scenario)

    assert board.of(mine).power_toughness == (3, 3)
    assert board.of(theirs).power_toughness == (3, 3)


def test_dress_down_takes_the_rats_back_to_two_two():
    """Layer 6 before layer 7 again (CR 613.1f, CR 613.1g).

    The Rats' pump is one of their own abilities, so removing it in layer 6
    stops the 7c effect from ever applying. Three vanilla 2/2s.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[
                "Relentless Rats",
                "Relentless Rats",
                "Relentless Rats",
                "Dress Down",
            ],
        )
        .build()
    )
    rats = scenario.creatures("Relentless Rats", "Relentless Rats", "Relentless Rats")

    board = computed(scenario)

    assert [board.of(rat).power_toughness for rat in rats] == [(2, 2)] * 3
    assert len(board.journal.skipped) == 3


def test_an_anthem_stacks_with_the_rats_own_count():
    """Two independent 7c effects on one creature, both added (CR 613.4c).

    Two Rats are 3/3 from each other, and Glorious Anthem makes them 4/4.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Relentless Rats", "Relentless Rats", "Glorious Anthem"])
        .build()
    )
    rats = scenario.creatures("Relentless Rats", "Relentless Rats")

    board = computed(scenario)

    assert [board.of(rat).power_toughness for rat in rats] == [(4, 4)] * 2


# --------------------------------------------------------------------------
# The integration: a static ability the rest of the engine can see
# --------------------------------------------------------------------------


def test_the_game_sees_the_anthem_a_static_ability_generates():
    """The one integration this whole file used to work around, now closed.

    A permanent is bound to its game as it enters the battlefield, so
    `CardState.power`/`.toughness` answer through `Game.characteristics_of` -
    the layer system, which CR 613.5 says the game performs "continually and
    automatically" - rather than the printed value plus counters (CR 122.1a).
    Glorious Anthem's "Creatures you control get +1/+1" is an effect that
    modifies power and toughness without setting them, applied in layer 7c
    (CR 613.4c), so the two properties the rest of the engine reads directly -
    machines/combat.py for CR 510.1a's damage assignment, `has_lethal_damage`
    for CR 704.5g - now see the anthem too.
    """
    scenario = Scenario().player("alice", battlefield=["Glorious Anthem", "Grizzly Bears"]).build()
    bears = scenario.creature("Grizzly Bears", "alice")

    assert (bears.card.power, bears.card.toughness) == ("2", "2"), "the printing is a 2/2"
    assert (bears.power, bears.toughness) == (3, 3)
