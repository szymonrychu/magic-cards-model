""" "Tap any number of untapped creatures you control. When you do, shuffle
target `<restriction>` into its owner's library, where X is the number of
creatures tapped this way." - Invasion of New Phyrexia // Teferi Akosa of
Zhalfir's own `-3`.

Every CR number here was looked up with `mise run rules:find` in the session
that wrote this file:

- **CR 107.1c** - "'Any number' means 'a non-negative number,'" so tapping
  zero creatures is a legal (if usually pointless) choice.
- **CR 603.12** - a resolving ability may "allow or instruct a player to take
  an action and create a triggered ability that triggers 'when [a player]
  [does or doesn't] take that action'" - a *reflexive* triggered ability,
  announcing its own target only once it goes on the stack (CR 603.3d), never
  the parent ability's.
- **CR 701.24a/701.24c/701.24d** - to shuffle is to randomize a library, and
  "shuffle a set of objects into a library" still shuffles that library even
  with zero objects in the set.
- **CR 608.2b** - a target is rechecked as the ability resolves; an illegal
  target is refused when it is chosen at all (`Game.choose_trigger_targets`).

`machines/effects._parse_shuffle_target_cards_into_library_clause` already
reads CR 701.24a's "shuffle target `<phrase>` into its owner's library" off a
targeted *graveyard card* (Wand of Vertebrae: "Shuffle up to five target
cards from your graveyard into your library."). Teferi Akosa's own `-3`
targets a battlefield *permanent* instead - the same shuffle-into-library
verb, a different origin zone - which is why this needed its own sibling
parser (`_parse_shuffle_target_permanent_into_library_clause`) sharing the
same CR 701.24a effect rather than a second copy of it, plus a new top-level
"tap any number ... when you do" reflexive reader
(`_parse_tap_any_number_of_untapped_creatures_when_you_do_clause`) generic
over whatever consequence text follows - Teferi Akosa is the only real
Modern/Pioneer/Standard-legal printing of "tap any number of untapped
creatures you control" as a resolving ability's own instruction (verified by
Scryfall search); Rishadan Pawnshop shares the shuffle-into-library verb but
is Legacy/Vintage-only, so it is not used as a pool fixture. Generality is
instead proven the way the file's own conventions already prove a
targeting-restriction shape: `target nonland permanent ... with mana value N
or less` is `machines/targeting.py`'s ordinary reading, already exercised by
several unrelated cards in this pool, not a bespoke check for this one.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

TEFERI = "Invasion of New Phyrexia // Teferi Akosa of Zhalfir"
MINUS_THREE = 2  # [+1, -2, -3] - the ability index `activate` takes.


def _teferi_board(**kwargs) -> Scenario:
    scenario = (
        Scenario()
        .player("alice", hand=[TEFERI], **kwargs)
        .player(
            "bob",
            battlefield=["Grizzly Bears", "Hill Giant"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    card = scenario.find("Invasion of New Phyrexia", Zone.HAND, "alice")
    teferi = scenario.game.put_onto_battlefield(card, "alice", transformed=True)
    return scenario, teferi


def test_tapping_two_creatures_shuffles_a_mana_value_two_permanent_away():
    """X = 2 creatures tapped, so "mana value X or less" admits Grizzly
    Bears (mana value 2) but not Hill Giant (mana value 4)."""
    scenario, teferi = _teferi_board(battlefield=["Runeclaw Bear", "Watchwolf"])
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "bob")

    scenario.activate(teferi, index=MINUS_THREE, username="alice")
    scenario.will_choose_cards(
        *scenario.creatures("Runeclaw Bear", "Watchwolf", username="alice"), username="alice"
    )
    scenario.pass_until_resolved()  # the loyalty ability: tap the two creatures
    assert scenario.stack_names() == ["Teferi Akosa of Zhalfir's triggered ability"]
    scenario.will_choose_targets(bears, source="Teferi Akosa of Zhalfir", username="alice")
    scenario.pass_until_resolved()  # the reflexive ability: shuffle Bears away

    assert bears.zone is Zone.LIBRARY
    bear = scenario.creature("Runeclaw Bear", "alice")
    wolf = scenario.creature("Watchwolf", "alice")
    assert bear.tapped
    assert wolf.tapped


def test_a_too_expensive_permanent_is_refused_as_the_target():
    """CR 608.2b/601.2c: Hill Giant's mana value (4) is over X (2), so it is
    not a legal target for the reflexive ability's own restriction - read
    off the exact text `create_reflexive_trigger` put on the stack, with X
    already written in as the real count (`_carry_count`), the same
    `TargetingProfile.check` real resolution uses (CR 601.2c/603.3d)."""
    from magic_cards_model.machines.targeting import profile_for_text

    scenario, teferi = _teferi_board(battlefield=["Runeclaw Bear", "Watchwolf"])
    giant = scenario.find("Hill Giant", Zone.BATTLEFIELD, "bob")

    scenario.activate(teferi, index=MINUS_THREE, username="alice")
    scenario.will_choose_cards(
        *scenario.creatures("Runeclaw Bear", "Watchwolf", username="alice"), username="alice"
    )
    scenario.pass_until_resolved()  # the loyalty ability: tap the two creatures
    (reflexive,) = scenario.game.stack
    profile = profile_for_text(reflexive.ability.text)

    with pytest.raises(ValueError, match="mana value"):
        profile.check([giant], caster="alice", game=scenario.game)


def test_tapping_zero_creatures_still_creates_the_reflexive_ability():
    """CR 107.1c/603.12: "any number" includes zero, and the instruction (no
    "you may") always happens, so "when you do" still fires with X = 0 -
    proven here because Grizzly Bears (mana value 2) and Hill Giant (mana
    value 4) both fail "mana value 0 or less" (CR 603.3d: a mandatory target
    with none legal removes the ability from the stack before it can be
    seen there), so the only visible trace of it having fired at all is the
    `NO_LEGAL_TARGET` notice with the real, substituted "0" written in."""
    scenario, teferi = _teferi_board()

    scenario.activate(teferi, index=MINUS_THREE, username="alice")
    scenario.pass_until_resolved()  # the loyalty ability: no creatures to tap

    (notice,) = scenario.game.targeting_notices
    assert notice.source_name == "Teferi Akosa of Zhalfir"
    assert "mana value 0 or less" in notice.text
