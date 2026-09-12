"""Scenario: CR 709.3b - the enumerated action for a split card's half must
describe *that* half's targets, not the front half's.

`Action.target_slots` and `Game.legal_targets` both came from
`Game._announcement_profile`, which took no face at all and fell through to
`targeting_profile(card)` - and `targeting_profile` reads
`Card.front_oracle_text`. So every row `legal_actions` emitted for a split
card carried the **front** half's targeting phrase, on both halves:

    Wear      cost={1}{R}     slots=[('target artifact', 1, 1)]
    Tear      cost={W}        slots=[('target artifact', 1, 1)]    <- Tear's
    Repudiate cost={G/U}{G/U} slots=[('target activated or triggered ability', 1, 1)]
    Replicate cost={1}{G}{U}  slots=[('target activated or triggered ability', 1, 1)]

That is a lying enumeration: a seat reading the Tear row is told to find an
artifact for a spell that destroys an enchantment. `Casting.targeting` already
read the chosen half correctly (CR 709.3b), and `Game._resolution_profile`
already read it at the CR 608.2b recheck; this file is about the third path,
the one a caller consults *before* announcing anything.

Every CR number here was read in full off `.rules/MagicCompRules.txt`
(effective August 7, 2026) with `mise run rules:find` in the session that
wrote it - `knowledge_search` was not reachable, so the on-disk primary source
was used (`CLAUDE.md`, "When `knowledge_search` is not enough"):

- **CR 709.3a** - "Only the chosen half is evaluated to see if it can be cast.
  Only that half is considered to be put onto the stack."
- **CR 709.3b** - "While on the stack, only the characteristics of the half
  being cast exist. The other half's characteristics are treated as though
  they didn't exist."
- **CR 709.4** - "In every zone except the stack, the characteristics of a
  split card are those of its two halves combined."
- **CR 601.2c** - the announcement step targets are chosen in.
- **CR 608.2b** - the recheck on resolution, `_resolution_profile`'s own rule.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.action import ActionKind
from tests.scenarios.harness import Scenario


def _slots(game, player: str) -> dict[str | None, tuple[tuple[str, int, int | None], ...]]:
    return {
        action.spell_face: tuple(
            (slot.phrase, slot.minimum, slot.maximum) for slot in action.target_slots
        )
        for action in game.legal_actions(player)
        if action.kind is ActionKind.CAST
    }


# -- each half reports its own phrase ---------------------------------------


def test_each_half_of_wear_tear_reports_its_own_targeting_phrase():
    scenario = (
        Scenario()
        .player("alice", hand=["Wear // Tear"], battlefield=["Mountain", "Plains"])
        .player("bob", battlefield=["Sol Ring", "Blood Moon"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    slots = _slots(scenario.game, "alice")

    assert slots["Wear"] == (("target artifact", 1, 1),)
    assert slots["Tear"] == (("target enchantment", 1, 1),)


def test_each_half_of_repudiate_replicate_reports_its_own_targeting_phrase():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Repudiate // Replicate"],
            battlefield=["Forest", "Island", "Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    slots = _slots(scenario.game, "alice")

    assert slots["Repudiate"] == (("target activated or triggered ability", 1, 1),)
    assert slots["Replicate"] == (("target creature", 1, 1),)


def test_a_half_that_targets_nothing_reports_no_slots_and_its_sibling_still_does():
    """Generality, on a printing neither defect named and no decklist here
    uses: Incubation // Incongruity. Incubation targets nothing at all and
    Incongruity exiles a target creature, so the front-face read gave the
    *Incongruity* row zero slots - a seat told a spell needs no target when
    CR 601.2c will refuse it without one.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Incubation // Incongruity"], battlefield=["Forest", "Island"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    slots = _slots(scenario.game, "alice")

    assert slots["Incubation"] == ()
    assert slots["Incongruity"] == (("target creature", 1, 1),)


# -- candidates agree with the slots ----------------------------------------


def test_legal_targets_for_a_face_agrees_with_that_faces_slots():
    """CR 709.3b through `Game.legal_targets`: the candidate list for Tear is
    the enchantment, for Wear the artifact. Without a face both came back as
    Wear's.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Wear // Tear"], battlefield=["Mountain", "Plains"])
        .player("bob", battlefield=["Sol Ring", "Blood Moon"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    split = scenario.find("Wear", Zone.HAND, "alice")
    ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "bob")
    moon = scenario.find("Blood Moon", Zone.BATTLEFIELD, "bob")

    (wear_candidates,) = scenario.game.legal_targets(split, "alice", spell_face="Wear")
    (tear_candidates,) = scenario.game.legal_targets(split, "alice", spell_face="Tear")

    assert wear_candidates == (ring,)
    assert tear_candidates == (moon,)


def test_legal_targets_honours_the_faces_own_controller_restriction():
    """Replicate's "target creature you control" is the chosen half's own
    restriction, and Repudiate - the front half - has no creature target at
    all, so without a face this pair could not be told apart.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Repudiate // Replicate"],
            battlefield=["Forest", "Island", "Grizzly Bears"],
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    split = scenario.find("Repudiate", Zone.HAND, "alice")
    mine = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice")

    (candidates,) = scenario.game.legal_targets(split, "alice", spell_face="Replicate")

    assert candidates == (mine,), "CR 709.3b: Replicate's own restriction"
    assert scenario.game.legal_targets(split, "alice", spell_face="Repudiate") == ((),), (
        "no ability on the stack to counter, but the requirement is still Repudiate's"
    )


def test_legal_targets_for_the_generality_cards_faces():
    scenario = (
        Scenario()
        .player("alice", hand=["Incubation // Incongruity"], battlefield=["Forest", "Island"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    split = scenario.find("Incubation", Zone.HAND, "alice")
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "bob")

    assert scenario.game.legal_targets(split, "alice", spell_face="Incubation") == ()
    (candidates,) = scenario.game.legal_targets(split, "alice", spell_face="Incongruity")
    assert candidates == (bears,)


# -- and the announced spell still resolves against that half --------------


def test_the_back_half_announced_from_its_own_slot_resolves():
    """End to end on the mirror card: the Incongruity row says one creature
    target, that target is announced, and the spell exiles it.
    """
    scenario = (
        Scenario()
        .player(
            "alice", hand=["Incubation // Incongruity"], battlefield=["Forest", "Island", "Island"]
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "bob")

    casting = scenario.cast("Incubation")
    casting.cast_as_split_half("Incongruity")
    casting.choose_targets([bears])
    payment = casting.begin_paying()
    assert str(payment.cost) == "{1}{G}{U}"
    scenario.pay_with(payment, *scenario.untapped_sources("Forest", "Island", "Island"))
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert bears.zone is Zone.EXILE
