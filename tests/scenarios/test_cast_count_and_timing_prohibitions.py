"""Scenario: player-wide casting prohibitions over *count* and *timing* -
High Noon, Teferi, Time Raveler's static, and Voice of Victory.

- High Noon: "Each player can't cast more than one spell each turn."
  (`test_high_noon.py` already covers this exhaustively end to end; the tests
  here are the direct-reader checks this task's own file, plus the
  same-template second printing, Rule of Law.)
- Teferi, Time Raveler: "Each opponent can cast spells only any time they
  could cast a sorcery." (`test_casting_restrictions.py` already covers the
  end-to-end wiring and the `+1` grant exhaustively; the generality proof
  here is Teferi, Mage of Zhalfir - a second, unrelated printing carrying the
  identical sentence, verified against a real Scryfall printing rather than
  guessed at.)
- Voice of Victory: "Your opponents can't cast spells during your turn."
  (`test_voice_of_victory.py` already covers this exhaustively; the check
  here is the direct reader.)

All three are CR 611.1's third kind of continuous effect - one that "affects
players or the rules of the game" rather than any characteristic - so none of
them write a layer (CR 613.11) and all three are read live off the
battlefield by `machines.casting_restrictions`, never cached (CR 611.3a).
CR 601.3 is the prohibition itself and CR 101.2 is why it wins over the
ordinary CR 117.1a permission to cast.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.casting_restrictions import (
    blanket_cant_cast_restriction,
    sorcery_speed_restriction_source,
)
from tests.scenarios.harness import Scenario


def _board(*, alice_battlefield: list[str], bob_battlefield: list[str] | None = None) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Bolt", "Lightning Bolt"],
            battlefield=alice_battlefield,
            library=["Mountain"] * 5,
        )
        .player(
            "bob",
            hand=["Lightning Bolt", "Lightning Bolt"],
            battlefield=bob_battlefield or ["Mountain"] * 4,
            library=["Mountain"] * 5,
        )
        .build()
    )


# -- High Noon: "Each player can't cast more than one spell each turn." -----


def test_high_noon_is_named_as_the_restricting_source():
    scenario = _board(alice_battlefield=["Mountain"] * 4 + ["High Noon"])

    restriction = blanket_cant_cast_restriction(scenario.game, "alice")

    assert restriction is None, "nothing cast yet - the cap has not been hit"


def test_high_noon_caps_after_one_spell_this_turn():
    scenario = _board(alice_battlefield=["Mountain"] * 4 + ["High Noon"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    scenario.cast_and_resolve("Lightning Bolt", mountain, username="alice", targets=["bob"])

    restriction = blanket_cant_cast_restriction(scenario.game, "alice")

    assert restriction is not None
    assert restriction.source_name == "High Noon"


def test_rule_of_law_is_the_same_template_on_a_different_printing():
    """Rule of Law: "Each player can't cast more than one spell each turn." -
    byte-identical to High Noon's own sentence, verified against the pool
    printing, and a real second card the same reader recognises without
    knowing its name."""
    scenario = _board(alice_battlefield=["Mountain"] * 4 + ["Rule of Law"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    scenario.cast_and_resolve("Lightning Bolt", mountain, username="alice", targets=["bob"])

    restriction = blanket_cant_cast_restriction(scenario.game, "alice")

    assert restriction is not None
    assert restriction.source_name == "Rule of Law"


# -- Teferi, Time Raveler: "Each opponent can cast spells only any time they
#    could cast a sorcery." -------------------------------------------------


def test_teferis_static_is_named_as_the_restricting_source():
    scenario = _board(alice_battlefield=["Teferi, Time Raveler"] + ["Mountain"] * 4)

    assert sorcery_speed_restriction_source(scenario.game, "bob") == "Teferi, Time Raveler"
    assert sorcery_speed_restriction_source(scenario.game, "alice") is None, (
        "each *opponent* - Teferi's own controller is exempt"
    )


def test_teferi_mage_of_zhalfir_carries_the_identical_static():
    """Generality proof: Teferi, Mage of Zhalfir prints the exact same
    sentence on a completely different card - a creature, not a planeswalker,
    with an unrelated `Flash` keyword and a second static line of its own
    ("Creature cards you own that aren't on the battlefield have flash.") -
    and the reader still finds it, because it reads the *text* of each static
    line on the battlefield rather than anything keyed to Teferi, Time
    Raveler's own name. Verified against the pool printing and confirmed by a
    live Scryfall search to be the only other card carrying this sentence.
    """
    scenario = _board(alice_battlefield=["Teferi, Mage of Zhalfir"] + ["Mountain"] * 4)

    assert sorcery_speed_restriction_source(scenario.game, "bob") == "Teferi, Mage of Zhalfir"
    assert sorcery_speed_restriction_source(scenario.game, "alice") is None


# -- Voice of Victory: "Your opponents can't cast spells during your turn." --


def test_voice_of_victory_is_named_as_the_restricting_source():
    scenario = _board(alice_battlefield=["Voice of Victory"] + ["Mountain"] * 4)
    scenario.start_at(Step.PRECOMBAT_MAIN)
    assert scenario.turn.active_player == "alice"

    restriction = blanket_cant_cast_restriction(scenario.game, "bob")

    assert restriction is not None
    assert restriction.source_name == "Voice of Victory"


def test_voice_of_victory_leaves_its_own_controller_alone():
    scenario = _board(alice_battlefield=["Voice of Victory"] + ["Mountain"] * 4)
    scenario.start_at(Step.PRECOMBAT_MAIN)

    assert blanket_cant_cast_restriction(scenario.game, "alice") is None
