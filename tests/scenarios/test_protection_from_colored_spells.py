"""Protection from "spells that are one or more colors" (Emrakul, the Aeons
Torn) - a quality naming both a kind of object and a colour count (CR
702.16a: the quality "can be any characteristic value or information").

CR 112.1: a spell is a card on the stack. CR 105.2: an object is one or more
of the five colours, or no colour at all; CR 105.2c: a colorless object has
no colour. So a coloured spell cannot target the protected creature (CR
702.16b), a colorless spell can, and a coloured *ability* can too - it is not
a spell. The quality is read on its own, never with the next keyword on the
printed line ("..., annihilator 6").

Rules looked up this session with `mise run rules:find` (112.1, 105.2,
105.2c, 702.16a, 702.16b).
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models.game import protection_qualities, protection_quality_readable
from tests.cards import card
from tests.scenarios.harness import Scenario

_EMRAKUL = "Emrakul, the Aeons Torn"


def _board(*spells: str) -> Scenario:
    scenario = (
        Scenario()
        .player("alice", hand=list(spells), battlefield=["Mountain", "Wastes", "Wastes"])
        .player("bob", battlefield=[_EMRAKUL])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_the_quality_is_read_without_the_following_keyword():
    assert protection_qualities(card(_EMRAKUL)) == ["spells that are one or more colors"]
    assert protection_quality_readable("spells that are one or more colors")


def test_a_coloured_spell_cannot_target_it():
    scenario = _board("Lightning Bolt")
    emrakul = scenario.creature(_EMRAKUL, "bob")

    casting = scenario.cast("Lightning Bolt", username="alice")
    with pytest.raises(ValueError, match="protection"):
        casting.choose_targets([emrakul])


def test_a_colorless_spell_can_target_it():
    scenario = _board("Spatial Contortion")
    emrakul = scenario.creature(_EMRAKUL, "bob")

    casting = scenario.cast("Spatial Contortion", username="alice")
    casting.choose_targets([emrakul])
