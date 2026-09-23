"""Hexproof: a permanent an opponent cannot target (CR 702.11).

CR 702.11a: "Hexproof is a static ability." CR 702.11b: "'Hexproof' on a
permanent means "This permanent can't be the target of spells or abilities your
opponents control.""

The word doing the work is *opponents*. Hexproof is not shroud (CR 702.18a,
"can't be the target of spells or abilities" full stop), so the controller's own
spells target it happily - which is the first corner case here.

The refusal belongs at CR 601.2c, as the targets are announced, so an illegal
target is never chosen and the caster keeps their card. CR 702.11c's hexproof on
a player is `test_player_hexproof_shroud.py`'s, and hexproof against abilities
is `test_hexproof_abilities.py`'s.

CR 702.11d's "hexproof from [quality]" is the second half of this file:
"'Hexproof from [quality]' is a variant of the hexproof ability. 'Hexproof from
[quality]' on a permanent means 'This permanent can't be the target of [quality]
spells your opponents control...'" - so it refuses a spell *of that quality* and
nothing else. CR 702.11f: "'Hexproof from [quality A] and from [quality B]' is
shorthand for 'hexproof from [quality A]' and 'hexproof from [quality B]'; it
behaves as two separate hexproof abilities." Nevinyrral, Urborg Tyrant prints
the list form of that shorthand, "Hexproof from artifacts, creatures, and
enchantments".

Every CR number here was verified with `knowledge_search(type="rules")` in the
session that wrote it.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.keywords import equip_activation
from magic_cards_model.models import Zone
from tests.cards import card
from tests.scenarios.harness import Scenario, mana_from


def board(bolt_owner: str = "alice") -> Scenario:
    hands = {"alice": [], "bob": []}
    hands[bolt_owner] = ["Lightning Bolt"]
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=hands["alice"],
            battlefield=["Mountain", "Striped Riverwinder"],
        )
        .player("bob", hand=hands["bob"], battlefield=["Mountain"])
    )


def test_an_opponent_cannot_target_a_hexproof_creature():
    """CR 702.11b, the whole rule."""
    scenario = board(bolt_owner="bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    riverwinder = scenario.creature("Striped Riverwinder", "alice")

    casting = scenario.cast("Lightning Bolt", username="bob")
    with pytest.raises(ValueError, match="has hexproof"):
        casting.choose_targets([riverwinder])


def test_its_own_controller_can_target_it():
    """Hexproof is not shroud: CR 702.11b only names *your opponents*."""
    scenario = board(bolt_owner="alice").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    riverwinder = scenario.creature("Striped Riverwinder", "alice")

    scenario.cast_and_resolve(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=[riverwinder]
    )
    assert riverwinder.damage == 3


def test_a_refused_target_leaves_the_spell_in_hand():
    """CR 601.2c is an announcement step: a refusal is not a cast."""
    scenario = board(bolt_owner="bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    riverwinder = scenario.creature("Striped Riverwinder", "alice")

    casting = scenario.cast("Lightning Bolt", username="bob")
    with pytest.raises(ValueError):
        casting.choose_targets([riverwinder])

    bolt = scenario.find("Lightning Bolt", Zone.HAND, "bob")
    assert bolt.zone is Zone.HAND
    assert scenario.game.stack_is_empty


def test_the_opponents_face_is_still_a_legal_target():
    """A hexproof creature on the board changes nothing about other targets."""
    scenario = board(bolt_owner="bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.pass_priority("alice")

    scenario.cast_and_resolve(
        "Lightning Bolt",
        *scenario.untapped_sources("Mountain", username="bob"),
        username="bob",
        targets=["alice"],
    )
    assert scenario.player("alice").life == 17


def test_hexproof_in_the_graveyard_protects_nothing():
    """CR 702.11b speaks of a *permanent*, and a permanent is on the battlefield.

    The engine has no card in the pool that targets a graveyard, so this asserts
    the shape of the check rather than a whole spell: a hexproof card that is
    not on the battlefield is not refused.
    """
    scenario = board(bolt_owner="bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    riverwinder = scenario.creature("Striped Riverwinder", "alice")
    scenario.game.put_into_graveyard(riverwinder)

    casting = scenario.cast("Lightning Bolt", username="bob")
    assert casting._hexproof_refusal(riverwinder) is None


# -- CR 702.11d: hexproof from [quality] -----------------------------------


def quality_board() -> Scenario:
    """Nevinyrral, Urborg Tyrant under bob, with alice - the active player, so
    her Aura is castable (CR 117.1a) - holding one spell of a named quality
    (Hyena Umbra, an enchantment) and one of another (Lightning Bolt, an
    instant)."""
    return (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Hyena Umbra", "Lightning Bolt"], battlefield=["Plains", "Mountain"])
        .player("bob", battlefield=["Nevinyrral, Urborg Tyrant"])
    )


def test_scryfall_flattens_hexproof_from_into_a_bare_hexproof_keyword():
    """Why the refusal cannot be read off `keywords` (the defect this pins).

    Scryfall's `keywords` array on Nevinyrral lists both "Hexproof from" and a
    bare "Hexproof", though the printed ability is only CR 702.11d's variant.
    Trusting that list grants CR 702.11b's full hexproof to a permanent that
    never had it, so the check reads the printed ability text instead.
    """
    nevinyrral = card("Nevinyrral, Urborg Tyrant")
    assert "Hexproof" in nevinyrral.keywords
    assert nevinyrral.oracle_text.startswith("Hexproof from artifacts, creatures, and enchantments")


def test_an_opponents_spell_of_the_named_quality_is_refused():
    """CR 702.11d: an enchantment spell against "hexproof from ... enchantments".

    Hyena Umbra is an Aura, so the target is announced at CR 601.2c the same way
    Lightning Bolt's is, and Nevinyrral is a creature, so `Enchant creature`
    (CR 702.5a) has nothing to say about it - the refusal is hexproof's alone.
    """
    scenario = quality_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    nevinyrral = scenario.creature("Nevinyrral, Urborg Tyrant", "bob")

    casting = scenario.cast("Hyena Umbra", username="alice")
    with pytest.raises(ValueError, match="hexproof from enchantments"):
        casting.choose_targets([nevinyrral])


def test_an_opponents_spell_of_another_quality_is_allowed():
    """The defect: a Lightning Bolt the printed card plainly allows.

    An instant is none of artifacts, creatures, or enchantments, so CR 702.11d
    says nothing about it and the Bolt resolves.
    """
    scenario = quality_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    nevinyrral = scenario.creature("Nevinyrral, Urborg Tyrant", "bob")

    scenario.cast_and_resolve(
        "Lightning Bolt",
        *scenario.untapped_sources("Mountain", username="alice"),
        username="alice",
        targets=[nevinyrral],
    )
    assert nevinyrral.damage == 3


def test_its_own_controller_can_target_it_with_the_named_quality():
    """CR 702.11d names "your opponents control" the same way CR 702.11b does,
    so alice's own enchantment spell is free to target her Nevinyrral."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Hyena Umbra"], battlefield=["Nevinyrral, Urborg Tyrant", "Plains"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    nevinyrral = scenario.creature("Nevinyrral, Urborg Tyrant", "alice")

    casting = scenario.cast("Hyena Umbra", username="alice", targets=[nevinyrral])

    assert casting.targets[0].card_id == nevinyrral.id


def test_plain_hexproof_still_refuses_a_spell_of_any_quality():
    """The control: a card whose printed ability really is CR 702.11b's plain
    hexproof still stops an opponent's instant, which "hexproof from
    enchantments" does not."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Striped Riverwinder"])
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    riverwinder = scenario.creature("Striped Riverwinder", "alice")

    casting = scenario.cast("Lightning Bolt", username="bob")
    with pytest.raises(ValueError, match="has hexproof"):
        casting.choose_targets([riverwinder])


# -- CR 702.11d via a *granted* static ability (Dragonfire Blade) ----------
#
# Everything above reads hexproof-from-quality off a permanent's own printed
# text (Nevinyrral). Dragonfire Blade grants the identical CR 702.11d
# variant from an Equipment instead: "Equipped creature gets +2/+2 and has
# hexproof from monocolored." (CR 613.1f, layer 6). `_hexproof_abilities`
# already read a *granted* ability off the computed board before this file
# was written - the gap was one layer earlier, in `machines/layers.py`'s own
# equip/aura static-ability parser, which never produced the grant in the
# first place, and in `Casting._spell_has_quality`, which had no notion of a
# colour-*count* quality ("monocolored"/"multicolored", CR 105.2a/CR 105.2b)
# at all, only a colour, a card type, a subtype, or a supertype.


def dragonfire_board(bolt_owner: str = "bob") -> Scenario:
    hands = {"alice": [], "bob": []}
    hands[bolt_owner] = ["Lightning Bolt"]
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=hands["alice"],
            battlefield=[
                "Dragonfire Blade",
                "Grizzly Bears",
                "Forest",
                "Forest",
                "Forest",
                "Mountain",
            ],
        )
        .player("bob", hand=hands["bob"], battlefield=["Mountain"])
    )


def equip_dragonfire_blade(scenario: Scenario, bears):
    blade = scenario.find("Dragonfire Blade", Zone.BATTLEFIELD, "alice")
    activation = equip_activation(scenario.game, blade, bears, "alice")
    payment = activation.begin_paying()
    for source in scenario.untapped_sources("Forest", "Forest", "Forest", username="alice"):
        payment.tap_for_mana(source, mana_from(source))
    payment.pay()
    activation.activate()
    activation.resolve()
    return blade


def test_dragonfire_blade_grants_hexproof_from_monocolored_once_equipped():
    """Grizzly Bears is monocolored green (CR 105.2a), so the granted line
    shows up on the computed board the moment the equip resolves - and the
    pump lands beside it, CR 613.6's "one ability spanning multiple layers"."""
    scenario = dragonfire_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    equip_dragonfire_blade(scenario, bears)

    board = scenario.game.continuous_effects.board(scenario.game.battlefield)
    assert board.of(bears).has_ability("Hexproof from monocolored")
    assert bears.power == 4 and bears.toughness == 4


def test_an_opponents_monocolored_spell_cannot_target_the_equipped_creature():
    """CR 702.11d: Lightning Bolt is red alone, one color - monocolored."""
    scenario = dragonfire_board(bolt_owner="bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    equip_dragonfire_blade(scenario, bears)

    casting = scenario.cast("Lightning Bolt", username="bob")
    with pytest.raises(ValueError, match="hexproof from monocolored"):
        casting.choose_targets([bears])


def test_an_opponents_multicolored_spell_can_target_the_equipped_creature():
    """The defect this pins: Lightning Helix is red *and* white - CR 105.2b's
    multicolored, so "hexproof from monocolored" says nothing about it."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=["Dragonfire Blade", "Grizzly Bears", "Forest", "Forest", "Forest"],
        )
        .player("bob", hand=["Lightning Helix"], battlefield=["Mountain", "Plains"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    equip_dragonfire_blade(scenario, bears)
    scenario.pass_priority("alice")

    scenario.cast_and_resolve(
        "Lightning Helix",
        *scenario.untapped_sources("Mountain", "Plains", username="bob"),
        username="bob",
        targets=[bears],
    )
    assert bears.damage == 3


def test_its_own_controller_can_still_target_it_with_a_monocolored_spell():
    """CR 702.11d names "your opponents control" the same way CR 702.11b
    does - alice's own Lightning Bolt is unaffected by her Blade's grant."""
    scenario = dragonfire_board(bolt_owner="alice").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    equip_dragonfire_blade(scenario, bears)
    (mountain,) = scenario.untapped_sources("Mountain", username="alice")

    scenario.cast_and_resolve("Lightning Bolt", mountain, targets=[bears])
    assert bears.damage == 3


# -- CR 608.2b: hexproof gained after targeting ------------------------------
#
# CR 608.2b: "Other changes to the game state may cause a target to no longer
# be legal". Blossoming Defense ("Target creature you control gets +2/+2 and
# gains hexproof until end of turn.") cast in response to an opponent's spell
# makes that spell's only target illegal by the time it resolves.


def test_a_spell_whose_target_gains_hexproof_in_response_does_not_resolve():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Blossoming Defense"], battlefield=["Grizzly Bears", "Forest"])
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.pass_priority("alice")
    scenario.cast_onto_stack(
        "Lightning Bolt",
        *scenario.untapped_sources("Mountain", username="bob"),
        username="bob",
        targets=[bears],
    )
    scenario.pass_priority("bob")
    scenario.cast_onto_stack(
        "Blossoming Defense", *scenario.untapped_sources("Forest"), targets=[bears]
    )

    scenario.resolve_top()  # Blossoming Defense: bears gain hexproof
    bolt = scenario.game.stack[-1]
    assert scenario.game.spell_fizzles(bolt)
    scenario.resolve_top()  # Lightning Bolt, now without a legal target

    assert bears.damage == 0
    assert scenario.find("Lightning Bolt", Zone.GRAVEYARD, "bob").zone is Zone.GRAVEYARD


def test_hexproof_gained_in_response_does_not_stop_its_controllers_own_spell():
    """The controller's own spell keeps its target: CR 702.11b names only
    opponents, so the recheck leaves alice's Bolt legal."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Lightning Bolt", "Blossoming Defense"],
            battlefield=["Grizzly Bears", "Forest", "Mountain"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.cast_onto_stack(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=[bears]
    )
    scenario.cast_onto_stack(
        "Blossoming Defense", *scenario.untapped_sources("Forest"), targets=[bears]
    )
    scenario.resolve_top()
    scenario.resolve_top()
    assert bears.damage == 3
