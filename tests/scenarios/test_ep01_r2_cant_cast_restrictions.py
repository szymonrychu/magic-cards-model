"""EP-01 R2 T4: static "can't cast" prohibitions on spells by name, mana value,
colour, type and zone (CR 601.3, CR 101.2).

CR 601.3: a player "can begin to cast a spell only if a rule or effect allows
that player to cast it and no rule or effect prohibits that player from casting
it"; CR 101.2: "can't" beats "can". Every prohibition below is read live off
the battlefield (CR 604.2, CR 611.3a), so it ends the moment its source leaves
and never touches the source's controller unless it says "players".

Shapes, each proven on at least two differently-worded printings:

- "Spells with the chosen name can't be cast." (Meddling Mage, Nevermore,
  Voidstone Gargoyle) - every player; "Your opponents can't cast spells with
  the chosen name." (Gideon's Intervention, Council of the Absolute,
  Alhammarret) - the controller is spared.
- "... with the same name as the exiled card / a card exiled with ~"
  (Ixalan's Binding, Ashiok's Erasure, Exclusion Ritual, Godsend, Circu).
- mana value: "3 or less" (Brisela), "even mana values" (Void Winnower),
  "noncreature spells with mana value 4 or greater" / "{X} in their mana
  costs" (Gaddock Teeg), "equal to the chosen number" (Sanctum Prelate),
  "greater than the number of lands that player controls" (Lavinia).
- "of the chosen color" (Iona).
- type bans: "You can't cast creature / noncreature / permanent spells"
  (Grid Monitor, Steel Golem, Nikya, Nullhide Ferox, Codie).
- zones: "Your opponents can't cast spells from anywhere other than their
  hands." (Drannith Magistrate), graveyards (Ashes of the Abhorrent).
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone

from .harness import Scenario

BOLT = "Lightning Bolt"
ISLANDS = ["Island"] * 4 + ["Mountain"] * 4


def _scenario(*, alice=(), bob=(), alice_hand=(), bob_hand=(), alice_gy=(), bob_gy=()):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=[*alice, *ISLANDS],
            hand=list(alice_hand),
            graveyard=list(alice_gy),
            library=["Island"] * 5,
        )
        .player(
            "bob",
            battlefield=[*bob, *ISLANDS],
            hand=list(bob_hand),
            graveyard=list(bob_gy),
            library=["Island"] * 5,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _try(world, spell, user="alice", from_zone=Zone.HAND, **kwargs):
    """The engine's refusal of `user` casting `spell` in a freshly built
    `world()`, or None when it is legal. A legal announcement leaves the card
    on the stack, so every question gets its own world."""
    scenario = world()
    try:
        scenario.cast(spell, username=user, from_zone=from_zone, **kwargs)
    except ValueError as error:
        return str(error)
    return None


def _enter(scenario, source, *, username="bob", choose=None):
    if choose is not None:
        scenario.will_choose(choose, source=source, username=username)
    return scenario.put_onto_battlefield(source, username)


def _world(source, *, owner="bob", choose=None, alice_hand=(), bob_hand=(), **sides):
    """A main phase of alice's turn with `source` put onto the battlefield
    under `owner`, naming `choose` as it enters."""

    def build():
        hands = {"alice": list(alice_hand), "bob": list(bob_hand)}
        hands[owner].append(source)
        scenario = _scenario(alice_hand=hands["alice"], bob_hand=hands["bob"], **sides)
        _enter(scenario, source, username=owner, choose=choose)
        return scenario

    return build


BOB = {"targets": ["alice"]}
ALICE = {"targets": ["bob"]}


# -- the chosen card name --------------------------------------------------
#
# alice is the active player (sorcery speed) and bob controls the source.


@pytest.mark.parametrize("source", ["Meddling Mage", "Nevermore", "Voidstone Gargoyle"])
def test_spells_with_the_chosen_name_cant_be_cast_by_anyone(source):
    world = _world(source, choose=BOLT, alice_hand=[BOLT, "Shock"], bob_hand=[BOLT, "Shock"])
    refusal = _try(world, BOLT, "alice", **ALICE)
    assert refusal is not None and source in refusal and "chosen name" in refusal
    # the controller too: "Spells with the chosen name can't be cast."
    assert _try(world, BOLT, "bob", **BOB) is not None
    # another name is unaffected
    assert _try(world, "Shock", "alice", **ALICE) is None


@pytest.mark.parametrize("source", ["Meddling Mage", "Nevermore"])
def test_the_name_ban_ends_when_its_source_leaves(source):
    scenario = _world(source, choose=BOLT, alice_hand=[BOLT])()
    permanent = scenario.find(source, Zone.BATTLEFIELD, "bob")
    scenario.game.exile_permanent(permanent)
    scenario.cast(BOLT, username="alice", targets=["bob"])


@pytest.mark.parametrize(
    "source", ["Gideon's Intervention", "Council of the Absolute", "Alhammarret, High Arbiter"]
)
def test_opponents_cant_cast_the_chosen_name_but_the_controller_can(source):
    world = _world(source, choose=BOLT, alice_hand=[BOLT, "Shock"], bob_hand=[BOLT])
    refusal = _try(world, BOLT, "alice", **ALICE)
    assert refusal is not None and source in refusal
    assert _try(world, "Shock", "alice", **ALICE) is None
    assert _try(world, BOLT, "bob", **BOB) is None


def _try_half(world, spell, half, user="alice"):
    """Refusal of casting just the `half` of a split card (CR 709.3a)."""
    scenario = world()
    casting = scenario.cast(spell, username=user)
    try:
        casting.cast_as_split_half(half)
    except ValueError as error:
        return str(error)
    return None


def test_a_split_card_is_banned_by_the_name_of_the_half_cast():
    """CR 709.3a: only the chosen half is evaluated, so naming one half bans
    that half and leaves the other castable."""
    world = _world("Meddling Mage", choose="Determined", alice_hand=["Bound // Determined"])
    assert _try_half(world, "Bound // Determined", "Determined") is not None
    assert _try_half(world, "Bound // Determined", "Bound") is None


# -- "the same name as the exiled card" -----------------------------------


def _exile_world(source, mana, *, victim="Spectral Sailor"):
    """bob (the active player here) resolves `source`, whose enters trigger
    exiles alice's `victim` - a flash creature, so alice can still try to cast
    its name at instant speed - while another copy waits in alice's hand."""

    def build():
        scenario = (
            Scenario()
            .manual_turn_based_actions()
            .player(
                "bob",
                battlefield=[*ISLANDS, *["Plains"] * 6],
                hand=[source, victim],
                library=["Island"] * 5,
            )
            .player(
                "alice",
                battlefield=[victim, *ISLANDS],
                hand=[victim, BOLT],
                library=["Island"] * 5,
            )
            .build()
        )
        scenario.start_at(Step.PRECOMBAT_MAIN)
        exiled = scenario.creature(victim, "alice")
        scenario.cast_onto_stack(
            source, *scenario.untapped_sources(*mana, username="bob"), username="bob"
        )
        scenario.resolve_top()
        scenario.choose_trigger_targets(source, [exiled])
        scenario.pass_until_resolved()
        assert exiled.zone is Zone.EXILE
        return scenario

    return build


def test_ixalans_binding_bans_the_name_of_the_card_it_exiled():
    world = _exile_world("Ixalan's Binding", ["Plains"] * 4)
    refusal = _try(world, "Spectral Sailor", "alice")
    assert refusal is not None and "Ixalan's Binding" in refusal
    assert _try(world, BOLT, "alice", **ALICE) is None
    # "your opponents": the Binding's own controller may cast that name
    assert _try(world, "Spectral Sailor", "bob") is None
    # when the Binding leaves the exiled card returns and the ban ends
    scenario = world()
    scenario.game.exile_permanent(scenario.find("Ixalan's Binding", Zone.BATTLEFIELD, "bob"))
    scenario.cast("Spectral Sailor", username="alice")


def test_exclusion_ritual_bans_the_imprinted_name_for_every_player():
    world = _exile_world("Exclusion Ritual", ["Plains"] * 6)
    assert _try(world, "Spectral Sailor", "alice") is not None
    assert _try(world, "Spectral Sailor", "bob") is not None  # "Players can't"


# -- mana value -------------------------------------------------------------


@pytest.mark.parametrize(
    ("spell", "banned"),
    [
        (BOLT, True),
        ("Divination", True),
        ("Cloud Elemental", True),
        ("Hill Giant", False),
        ("Wrath of God", False),
    ],
)
def test_brisela_bans_mana_value_three_or_less_for_opponents(spell, banned):
    world = _world("Brisela, Voice of Nightmares", alice_hand=[spell], bob_hand=[BOLT])
    kwargs = ALICE if spell == BOLT else {}
    refusal = _try(world, spell, "alice", **kwargs)
    assert (refusal is not None) is banned
    if banned:
        assert "Brisela" in refusal
    # Brisela's controller casts mana value 1 freely
    assert _try(world, BOLT, "bob", **BOB) is None


@pytest.mark.parametrize(
    ("spell", "banned"),
    [
        ("Grizzly Bears", True),  # 2
        ("Wrath of God", True),  # 4
        ("Ornithopter", True),  # 0 is even
        ("Cloud Elemental", False),  # 3
        ("Serra Angel", False),  # 5
        ("Hill Giant", True),  # 4
        (BOLT, False),  # 1
    ],
)
def test_void_winnower_bans_even_mana_values_zero_included(spell, banned):
    world = _world("Void Winnower", alice_hand=[spell])
    kwargs = ALICE if spell == BOLT else {}
    assert (_try(world, spell, "alice", **kwargs) is not None) is banned


def test_gaddock_teeg_bans_noncreature_high_mana_value_and_x_spells_for_everyone():
    world = _world(
        "Gaddock Teeg",
        alice_hand=["Wrath of God", "Fireball", "Serra Angel", BOLT, "Divination"],
    )
    assert _try(world, "Wrath of God", "alice") is not None  # noncreature, mana value 4
    assert _try(world, "Fireball", "alice", **ALICE) is not None  # {X}
    assert _try(world, "Serra Angel", "alice") is None  # a creature spell
    assert _try(world, BOLT, "alice", **ALICE) is None
    assert _try(world, "Divination", "alice") is None


def test_sanctum_prelate_bans_noncreature_spells_of_the_chosen_number():
    world = _world("Sanctum Prelate", choose="1", alice_hand=[BOLT, "Divination", "Memnite"])
    assert _try(world, BOLT, "alice", **ALICE) is not None
    assert _try(world, "Divination", "alice") is None  # mana value 3
    assert _try(world, "Memnite", "alice") is None  # a creature


def test_lavinia_compares_mana_value_to_that_players_lands():
    def few_lands():
        scenario = _world("Lavinia, Azorius Renegade", alice_hand=["Wrath of God", "Divination"])()
        for land in scenario.game.permanents_controlled_by("alice")[3:]:
            scenario.game.exile_permanent(land)
        return scenario

    world = _world("Lavinia, Azorius Renegade", alice_hand=["Wrath of God", "Divination"])
    assert _try(world, "Wrath of God", "alice") is None  # 4 <= 8 lands
    assert _try(few_lands, "Wrath of God", "alice") is not None  # 4 > 3 lands
    assert _try(few_lands, "Divination", "alice") is None  # 3 <= 3


# -- colour -----------------------------------------------------------------


def test_iona_bans_the_chosen_colour_for_opponents_only():
    world = _world(
        "Iona, Shield of Emeria", choose="R", alice_hand=[BOLT, "Divination"], bob_hand=[BOLT]
    )
    assert _try(world, BOLT, "alice", **ALICE) is not None
    assert _try(world, "Divination", "alice") is None
    assert _try(world, BOLT, "bob", **BOB) is None


# -- type bans on yourself --------------------------------------------------


@pytest.mark.parametrize(
    ("source", "banned", "allowed"),
    [
        ("Grid Monitor", "Hill Giant", "Divination"),
        ("Steel Golem", "Serra Angel", "Divination"),
        ("Nikya of the Old Ways", "Divination", "Hill Giant"),
        ("Nullhide Ferox", "Divination", "Hill Giant"),
        ("Codie, Vociferous Codex", "Hill Giant", "Divination"),
    ],
)
def test_type_bans_only_bind_their_controller(source, banned, allowed):
    world = _world(source, owner="alice", alice_hand=[banned, allowed], bob_hand=[BOLT])
    assert _try(world, banned, "alice") is not None
    assert _try(world, allowed, "alice") is None
    # the opponent is untouched
    assert _try(world, BOLT, "bob", **BOB) is None


def test_a_permanent_spell_ban_lets_instants_through():
    world = _world(
        "Codie, Vociferous Codex", owner="alice", alice_hand=["Divination", "Memnite", BOLT]
    )
    assert _try(world, "Memnite", "alice") is not None
    assert _try(world, BOLT, "alice", **ALICE) is None


# -- zones ------------------------------------------------------------------


def test_drannith_magistrate_bans_casting_from_anywhere_but_the_hand():
    world = _world("Drannith Magistrate", alice_gy=["Faithless Looting"], alice_hand=["Shock"])
    assert _try(world, "Faithless Looting", "alice", from_zone=Zone.GRAVEYARD) is not None
    assert _try(world, "Shock", "alice", **ALICE) is None
    # its controller may still cast from a graveyard
    own = _world("Drannith Magistrate", bob_gy=["Faithless Looting"])
    assert _try(own, "Faithless Looting", "bob", from_zone=Zone.GRAVEYARD) is None


def test_ashes_of_the_abhorrent_bans_graveyard_casts_for_every_player():
    def build():
        return _scenario(
            alice_gy=["Faithless Looting"],
            bob=["Ashes of the Abhorrent"],
            bob_gy=["Faithless Looting"],
        )

    assert _try(build, "Faithless Looting", "alice", from_zone=Zone.GRAVEYARD) is not None
    assert _try(build, "Faithless Looting", "bob", from_zone=Zone.GRAVEYARD) is not None


# -- Council of the Absolute's own discount ---------------------------------


def _discount(source_owner, caster, spell="Shock", *, choose="Shock"):
    """The reduction (in mana) `caster` gets on `spell` with a Council of the
    Absolute owned by `source_owner` naming `choose`."""
    world = _world(
        "Council of the Absolute",
        owner=source_owner,
        choose=choose,
        alice_hand=[spell],
        bob_hand=[spell],
    )
    scenario = world()
    card = scenario.find(spell, Zone.HAND, caster)
    _, decreases, _ = scenario.game.static_cost_modifiers_for(card, caster)
    return sum(cost.converted for cost in decreases)


def test_council_of_the_absolute_discounts_its_controllers_chosen_name_by_two():
    assert _discount("alice", "alice") == 2


def test_council_of_the_absolute_discounts_only_spells_its_controller_casts():
    assert _discount("alice", "bob") == 0


def test_council_of_the_absolute_discounts_only_the_chosen_name():
    assert _discount("alice", "alice", spell="Shock", choose=BOLT) == 0


def test_the_discount_ends_with_the_permanent():
    world = _world("Council of the Absolute", owner="alice", choose="Shock", alice_hand=["Shock"])
    scenario = world()
    scenario.game.exile_permanent(
        scenario.find("Council of the Absolute", Zone.BATTLEFIELD, "alice")
    )
    card = scenario.find("Shock", Zone.HAND, "alice")
    _, decreases, _ = scenario.game.static_cost_modifiers_for(card, "alice")
    assert decreases == []
