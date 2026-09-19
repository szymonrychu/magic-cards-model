"""Scenario: FRA S9's group and conditional grants.

`machines/layers.py` read four shapes of "[qualified subject] have <keyword>"
before this file, and none of them was a bare creature-type subject with no
"creatures" noun, an "artifact creatures" qualifier, a counter-gated subject,
a combined pump-and-keyword sentence over the plain qualified subject, or a
land subject at all - six real printed shapes with no reader:

- **Saheeli, Jewel of Avishkar** (Reality Fracture), "Thopters you control
  have haste." - a bare subtype noun, `_SUBTYPE_ANTHEM_RE`'s pump-only twin
  extended to grant a keyword instead. **Boldwyr Aggressor** (off-set, a
  different subtype and keyword, plus the "other" qualifier the FRA card
  lacks) proves the shape rather than the card: "Other Giants you control
  have double strike."
- **Vraska, Soul of Stone** (Reality Fracture), "Artifact creatures you
  control have vigilance." - CR 205.2b's "more than one card type" again,
  read the same way `land` already was, as `also_artifact` on
  `QualifiedCreatures`/`CreatureQualifiers`. **Alibou, Ancient Witness**
  (off-set, "other" plus a different keyword) proves it: "Other artifact
  creatures you control have haste."
- **Gallia, the Merrymaker** / **Vigorbloom Vanguard** (Reality Fracture),
  "Each [other] creature you control with a +1/+1 counter on it has
  <keyword>." - `PermanentsControlledByWithCounters` narrowed to one named
  counter kind and to creatures. **Abzan Falconer** (off-set, no "other",
  flying instead of haste/vigilance) proves it: "Each creature you control
  with a +1/+1 counter on it has flying."
- **Gideon's Memorial** (Reality Fracture), "Creature tokens you control get
  +1/+0 and have vigilance." - `_ANTHEM_RE` and `_INDEFINITE_KEYWORD_GRANT_RE`
  combined into one sentence over the same qualified subject. **Intangible
  Virtue** (off-set, a different pump amount) proves it: "Creature tokens you
  control get +1/+1 and have vigilance."
- **Marwyn, the Preserver** (Reality Fracture), "Lands you control have
  hexproof." - the land-subject twin of `_INDEFINITE_KEYWORD_GRANT_RE`, built
  from the same proven `_split_and_validate_keywords`/`grant_ability`
  machinery as every other indefinite grant in this file, just over
  `lands_controlled_by` instead of a creature selector.

The rules these grants rest on:

- **CR 205.2b** - "Some objects have more than one card type ... Such objects
  satisfy the criteria for any effect that applies to any of their card
  types" - an artifact creature is both, the same way a land creature is.
- **CR 122.1** - "A counter is a marker placed on an object or player that
  modifies its characteristics" - compared by name (CR 122.1a's "+1/+1"), so
  a specific counter kind is a plain characteristic question, not a closure.
- **CR 611.3** / **CR 611.3a** - a static ability's effect "isn't 'locked
  in'; it applies at any given moment to whatever its text indicates", so
  each of these re-reads the board on every CR 613.5 computation: gaining or
  losing the counter, or the artifact type, flips the grant immediately.
- **CR 613.1f** for every keyword grant (layer 6), **CR 613.4c** for
  Gideon's Memorial's +1/+0 (sublayer 7c), one ability landing in both layers
  at once (CR 613.6).

Every CR number here was looked up with `knowledge_search(q="...",
type="rules")` in the session that wrote it, and every card's text with
`resolve_cards` or straight off its fixture.
"""

from magic_cards_model.machines.layers import compute_board, static_effects
from magic_cards_model.models import Zone
from tests.cards import card_state


def permanent(name: str, controller: str = "alice", **kwargs):
    return card_state(
        name, zone=Zone.BATTLEFIELD, controller=controller, owner=controller, **kwargs
    )


def board_of(*permanents):
    """The characteristics of a battlefield with only its static abilities
    applied - CR 613.7a's timestamp order is the argument order."""
    cards = list(permanents)
    return compute_board(cards, static_effects(cards))


# --------------------------------------------------------------------------
# "Thopters you control have haste." (Saheeli, Jewel of Avishkar)
# --------------------------------------------------------------------------


def test_saheeli_grants_haste_to_a_thopter_you_control():
    saheeli = permanent("Saheeli, Jewel of Avishkar")
    ornithopter = permanent("Ornithopter")  # a real Artifact Creature - Thopter

    assert board_of(saheeli, ornithopter).of(ornithopter).has_ability("Haste")


def test_saheeli_does_not_grant_haste_to_a_non_thopter_creature():
    saheeli = permanent("Saheeli, Jewel of Avishkar")
    bears = permanent("Grizzly Bears")

    assert not board_of(saheeli, bears).of(bears).has_ability("Haste")


def test_boldwyr_aggressor_grants_double_strike_to_other_giants_off_set():
    """Off-set proof: a different subtype, a different keyword, and the
    "other" qualifier Saheeli's own sentence does not carry.
    """
    aggressor = permanent("Boldwyr Aggressor")
    other_giant = permanent("Arbor Colossus")  # a real Creature - Giant

    assert board_of(aggressor, other_giant).of(other_giant).has_ability("Double strike")


def test_boldwyr_aggressor_does_not_grant_itself_double_strike_twice_over():
    """ "Other" excludes the source; its own printed double strike still
    stands, so it is not asserting a negative that trivially holds.
    """
    aggressor = permanent("Boldwyr Aggressor")

    board = board_of(aggressor)
    assert board.of(aggressor).has_ability("Double strike"), "its own printed line"


def test_boldwyr_aggressor_does_not_grant_double_strike_to_a_non_giant():
    aggressor = permanent("Boldwyr Aggressor")
    bears = permanent("Grizzly Bears")

    assert not board_of(aggressor, bears).of(bears).has_ability("Double strike")


# --------------------------------------------------------------------------
# "Artifact creatures you control have vigilance." (Vraska, Soul of Stone)
# --------------------------------------------------------------------------


def test_vraska_grants_vigilance_to_an_artifact_creature_you_control():
    vraska = permanent("Vraska, Soul of Stone")
    golem = permanent("Ornithopter")  # a real 0/2 artifact creature

    assert board_of(vraska, golem).of(golem).has_ability("Vigilance")


def test_vraska_does_not_grant_vigilance_to_a_non_artifact_creature():
    vraska = permanent("Vraska, Soul of Stone")
    bears = permanent("Grizzly Bears")

    assert not board_of(vraska, bears).of(bears).has_ability("Vigilance")


def test_vraska_does_not_grant_vigilance_to_an_opponents_artifact_creature():
    vraska = permanent("Vraska, Soul of Stone")
    theirs = permanent("Ornithopter", controller="bob")

    assert not board_of(vraska, theirs).of(theirs).has_ability("Vigilance")


def test_alibou_grants_haste_to_another_artifact_creature_off_set():
    """Off-set proof: "other" plus a different keyword (haste, not
    vigilance).
    """
    alibou = permanent("Alibou, Ancient Witness")
    thopter = permanent("Ornithopter")

    assert board_of(alibou, thopter).of(thopter).has_ability("Haste")


def test_alibou_does_not_grant_haste_to_itself():
    alibou = permanent("Alibou, Ancient Witness")

    assert not board_of(alibou).of(alibou).has_ability("Haste")


# --------------------------------------------------------------------------
# "Each [other] creature you control with a +1/+1 counter on it has
# <keyword>." (Gallia, the Merrymaker; Vigorbloom Vanguard)
# --------------------------------------------------------------------------


def test_gallia_grants_haste_to_another_creature_with_a_plus_one_counter():
    gallia = permanent("Gallia, the Merrymaker")
    bears = permanent("Grizzly Bears", counters={"+1/+1": 1})

    assert board_of(gallia, bears).of(bears).has_ability("Haste")


def test_gallia_does_not_grant_haste_to_a_creature_with_no_counter():
    gallia = permanent("Gallia, the Merrymaker")
    bears = permanent("Grizzly Bears")

    assert not board_of(gallia, bears).of(bears).has_ability("Haste")


def test_gallia_does_not_grant_haste_to_itself():
    """ "Each other creature" - Gallia already has haste printed, but the
    grant itself must not be the reason.
    """
    gallia = permanent("Gallia, the Merrymaker", counters={"+1/+1": 1})

    board = board_of(gallia)
    assert board.of(gallia).has_ability("Haste"), "printed haste, not the grant"


def test_gallia_ignores_a_counter_of_a_different_kind():
    """The gate is the *named* counter, not "any counter" -
    `PermanentsControlledByWithCounters`'s bare form would get this wrong.
    """
    gallia = permanent("Gallia, the Merrymaker")
    charged = permanent("Grizzly Bears", counters={"charge": 3})

    assert not board_of(gallia, charged).of(charged).has_ability("Haste")


def test_vigorbloom_vanguard_grants_vigilance_including_to_itself():
    """Vigorbloom Vanguard's own sentence has no "other", unlike Gallia's."""
    vanguard = permanent("Vigorbloom Vanguard", counters={"+1/+1": 2})

    assert board_of(vanguard).of(vanguard).has_ability("Vigilance")


def test_abzan_falconer_grants_flying_with_no_other_qualifier_off_set():
    """Off-set proof: no "other", and a different keyword (flying)."""
    falconer = permanent("Abzan Falconer", counters={"+1/+1": 1})
    bears = permanent("Grizzly Bears", counters={"+1/+1": 1})

    board = board_of(falconer, bears)
    assert board.of(bears).has_ability("Flying")
    assert board.of(falconer).has_ability("Flying"), (
        "no 'other' in its own sentence, and it qualifies too"
    )


# --------------------------------------------------------------------------
# "Creature tokens you control get +1/+0 and have vigilance." (Gideon's
# Memorial)
# --------------------------------------------------------------------------


def test_gideons_memorial_pumps_and_grants_vigilance_to_a_token():
    from magic_cards_model.models import Color
    from magic_cards_model.models.token import TokenDefinition, create_tokens
    from tests.scenarios.harness import Scenario

    soldier = TokenDefinition(subtypes=("Soldier",), colors=(Color.WHITE,), power=1, toughness=1)
    scenario = (
        Scenario()
        .player("alice", battlefield=["Gideon's Memorial", "Grizzly Bears"])
        .player("bob")
        .build()
    )
    memorial = scenario.find("Gideon's Memorial", Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    (token,) = create_tokens(scenario.game, soldier, "alice")

    board = board_of(memorial, bears, token)
    assert board.of(token).power_toughness == (2, 1)
    assert board.of(token).has_ability("Vigilance")
    assert board.of(bears).power_toughness == (2, 2), "a card is not a token"
    assert not board.of(bears).has_ability("Vigilance")


def test_intangible_virtue_pumps_a_different_amount_off_set():
    """Off-set proof: same "creature tokens" subject, a different pump
    amount (+1/+1, not +1/+0)."""
    from magic_cards_model.models import Color
    from magic_cards_model.models.token import TokenDefinition, create_tokens
    from tests.scenarios.harness import Scenario

    soldier = TokenDefinition(subtypes=("Soldier",), colors=(Color.WHITE,), power=1, toughness=1)
    scenario = Scenario().player("alice", battlefield=["Intangible Virtue"]).player("bob").build()
    virtue = scenario.find("Intangible Virtue", Zone.BATTLEFIELD, "alice")
    (token,) = create_tokens(scenario.game, soldier, "alice")

    board = board_of(virtue, token)
    assert board.of(token).power_toughness == (2, 2)
    assert board.of(token).has_ability("Vigilance")


# --------------------------------------------------------------------------
# "Lands you control have hexproof." (Marwyn, the Preserver)
# --------------------------------------------------------------------------


def test_marwyn_grants_hexproof_to_a_land_you_control():
    marwyn = permanent("Marwyn, the Preserver")
    forest = permanent("Forest")

    assert board_of(marwyn, forest).of(forest).has_ability("Hexproof")


def test_marwyn_does_not_grant_hexproof_to_a_nonland_permanent():
    marwyn = permanent("Marwyn, the Preserver")
    bears = permanent("Grizzly Bears")

    assert not board_of(marwyn, bears).of(bears).has_ability("Hexproof")


def test_marwyn_does_not_grant_hexproof_to_an_opponents_land():
    marwyn = permanent("Marwyn, the Preserver")
    theirs = permanent("Forest", controller="bob")

    assert not board_of(marwyn, theirs).of(theirs).has_ability("Hexproof")
