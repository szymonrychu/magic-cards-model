"""Scenario: CR 709.3a - only the *chosen* half of a split card is evaluated
to see if it can be cast, and that includes CR 117.1a's timing rule.

The defect this file pins: `why_cannot_cast_now` read `Card.types`, which is
the **front** half's type line (`Card.front_type_line` splits on `//`), so a
split card's timing was decided by whichever half happened to be printed on
the left. Measured both ways round, on two real printings:

- Repudiate // Replicate is `Instant // Sorcery`. The front half is an
  Instant, so the *Sorcery* half Replicate was castable during an upkeep
  step - a sorcery-speed spell cast at instant speed.
- Incubation // Incongruity is `Sorcery // Instant`. The front half is a
  Sorcery, so the *Instant* half Incongruity was refused during an upkeep
  step - a legal instant refused.

Both are the same bug: the card's front face answering a question CR 709.3a
puts to the chosen half.

Every CR number in this file was read in full off `.rules/MagicCompRules.txt`
(effective August 7, 2026) with `mise run rules:find` in the session that
wrote it - `knowledge_search` was not reachable, so the on-disk primary source
was used instead (`CLAUDE.md`, "When `knowledge_search` is not enough"):

- **CR 709.3** - "A player chooses which half of a split card they are casting
  before putting it onto the stack."
- **CR 709.3a** - "Only the chosen half is evaluated to see if it can be cast.
  Only that half is considered to be put onto the stack."
- **CR 709.4** - "In every zone except the stack, the characteristics of a
  split card are those of its two halves combined."
- **CR 709.4c** - "A split card has each card type specified on either of its
  halves and each ability in the text box of each half."
- **CR 117.1a** - "A player may cast an instant spell any time they have
  priority. A player may cast a noninstant spell during their main phase any
  time they have priority and the stack is empty."
- **CR 307.1** - "A player who has priority may cast a sorcery card from their
  hand during a main phase of their turn when the stack is empty."
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.casting import Casting
from magic_cards_model.models import Zone
from magic_cards_model.models.action import ActionKind
from tests.scenarios.harness import Scenario


def _board(hand: list[str]) -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=hand,
            battlefield=["Forest", "Forest", "Island", "Island"],
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )


def _cast_faces(game, player: str) -> dict[str | None, object]:
    return {
        action.spell_face: action
        for action in game.legal_actions(player)
        if action.kind is ActionKind.CAST
    }


# -- the sorcery half is refused at instant speed ---------------------------


def test_the_sorcery_half_cannot_be_cast_during_upkeep():
    """CR 709.3a with CR 307.1: Replicate is the Sorcery half, so the upkeep
    step is not a legal time to cast it, even though Repudiate - the Instant
    printed to its left - could be cast right now.
    """
    scenario = _board(["Repudiate // Replicate"])
    scenario.start_at(Step.UPKEEP)

    casting = scenario.cast("Repudiate")

    with pytest.raises(ValueError, match="CR 117.1a"):
        casting.cast_as_split_half("Replicate")


def test_the_instant_half_of_the_same_card_can_be_cast_during_upkeep():
    """The other side of the same printing: Repudiate is an Instant, and
    CR 117.1a's first sentence is unconditional about when that may be cast.
    """
    scenario = _board(["Repudiate // Replicate"])
    scenario.start_at(Step.UPKEEP)

    casting = scenario.cast("Repudiate")
    casting.cast_as_split_half("Repudiate")

    assert casting.face == "Repudiate"
    assert str(casting.base_cost) == "{G/U}{G/U}"


def test_naming_the_sorcery_half_at_construction_is_refused_too():
    """CR 709.3 puts the choice *before* CR 601.2a's move to the stack, which
    is the order `Casting`'s own constructor takes: a `face` handed in with
    the proposal is the on-time choice, and the timing check must read it
    rather than the front face.
    """
    scenario = _board(["Repudiate // Replicate"])
    scenario.start_at(Step.UPKEEP)
    spell = scenario.find("Repudiate", Zone.HAND, "alice")

    with pytest.raises(ValueError, match="CR 117.1a"):
        Casting(
            spell=spell,
            caster="alice",
            origin_zone=Zone.HAND,
            game=scenario.game,
            face="Replicate",
        )

    assert spell.zone is Zone.HAND, "CR 601.3: a refused proposal moves nothing"


def test_both_halves_are_castable_in_the_main_phase():
    scenario = _board(["Repudiate // Replicate"])
    scenario.start_at(Step.PRECOMBAT_MAIN)

    for face in ("Repudiate", "Replicate"):
        casting = scenario.cast("Repudiate")
        casting.cast_as_split_half(face)
        assert casting.face == face
        casting.cancel()


# -- generality: the mirror arrangement, on a card neither defect named -----


def test_the_instant_back_half_can_be_cast_during_upkeep():
    """Generality, and the mirror bug. Incubation // Incongruity is
    `Sorcery // Instant` - the arrangement Repudiate // Replicate does not
    cover - so the front-face read refused Incongruity, a plain Instant, at
    instant speed. Neither of the two printings that motivated this wave, and
    in no decklist in this repo.
    """
    scenario = _board(["Incubation // Incongruity"])
    scenario.start_at(Step.UPKEEP)

    casting = scenario.cast("Incubation")
    casting.cast_as_split_half("Incongruity")

    assert casting.face == "Incongruity"
    assert str(casting.base_cost) == "{1}{G}{U}"


def test_the_sorcery_front_half_of_the_mirror_card_is_refused_during_upkeep():
    scenario = _board(["Incubation // Incongruity"])
    scenario.start_at(Step.UPKEEP)

    casting = scenario.cast("Incubation")

    with pytest.raises(ValueError, match="CR 117.1a"):
        casting.cast_as_split_half("Incubation")


# -- the enumeration says the same thing -----------------------------------


def test_legal_actions_offers_only_the_instant_half_during_upkeep():
    """`legal_actions` asked `why_cannot_cast_now` once, with no face, before
    it ever looped over the halves - so at upkeep it reported *both* halves of
    Repudiate // Replicate as castable and *neither* half of
    Incubation // Incongruity. Both answers were the front face's.
    """
    scenario = _board(["Repudiate // Replicate", "Incubation // Incongruity"])
    scenario.start_at(Step.UPKEEP)

    faces = _cast_faces(scenario.game, "alice")

    assert "Repudiate" in faces, "an Instant, CR 117.1a"
    assert "Incongruity" in faces, "also an Instant, on the back half"
    assert "Replicate" not in faces, "a Sorcery, CR 307.1"
    assert "Incubation" not in faces, "also a Sorcery, on the front half"


def test_legal_actions_offers_every_half_in_the_main_phase():
    scenario = _board(["Repudiate // Replicate", "Incubation // Incongruity"])
    scenario.start_at(Step.PRECOMBAT_MAIN)

    faces = _cast_faces(scenario.game, "alice")

    assert {"Repudiate", "Replicate", "Incubation", "Incongruity"} <= set(faces)
