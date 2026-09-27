"""CR 701.68c: "the blighted creature" - the object CR 701.68a's blight was
actually performed on, referenced later in the same sentence.

Grub, Notorious Auntie: "Whenever Grub attacks, you may blight 1. If you do,
create a tapped and attacking token that's a copy of the blighted creature,
except it has 'At the beginning of the end step, sacrifice this token.'"
Reuses `token_copy_of` (`models/token.py`) and the "except it has '<ability>'"
reader every other token-copy-with-exceptions clause in this pool already
shares (sos-T7's own family in `machines/effects.py`), plus CR 508.4's "put
onto the battlefield already attacking" (`_put_onto_the_battlefield_attacking`,
`_defender_of_controllers_attack`).

Every CR number here was read with `mise run rules:find` in the session that
wrote this file.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def _grub_notorious_auntie(scenario: Scenario):
    """Grub, Storied Matriarch, staged and flipped to its own back face -
    `.transform()` directly, the technique `test_activated_ability_effects.
    py`'s own Avatar Roku already uses for a back-face-only ability."""
    grub = scenario.creature("Grub, Storied Matriarch", "alice")
    grub.transform()
    grub.summoning_sick = False
    return grub


def test_blighting_creates_a_tapped_attacking_copy_of_the_blighted_creature():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Grub, Storied Matriarch", "Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.BEGINNING_OF_COMBAT)
    grub = _grub_notorious_auntie(scenario)
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.will_take_the_may(True, username="alice")
    scenario.will_choose_cards(bears, username="alice")
    scenario.attack_with(grub)
    scenario.pass_until_resolved()

    assert bears.counters[Counter.MINUS_ONE] == 1
    tokens = [
        state
        for state in scenario.game.permanents_controlled_by("alice")
        if state.name == "Grizzly Bears" and state.id != bears.id
    ]
    assert len(tokens) == 1
    token = tokens[0]
    assert token.token is True
    assert token.tapped is True
    assert token in scenario.attackers()
    assert token.zone is Zone.BATTLEFIELD
    # CR 707.9a's added ability becomes part of the copy's own copiable text,
    # not a grant on top of it - a plain string match on its own printed
    # oracle text is the honest way to check it landed, since it is not a
    # keyword `has_keyword` reads.
    assert "sacrifice this token" in (token.card.oracle_text or "").lower()


def test_the_token_sacrifices_itself_at_the_beginning_of_the_end_step():
    """The added ability itself doing something, not just being printed."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Grub, Storied Matriarch", "Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.BEGINNING_OF_COMBAT)
    grub = _grub_notorious_auntie(scenario)
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.will_take_the_may(True, username="alice")
    scenario.will_choose_cards(bears, username="alice")
    scenario.attack_with(grub)
    scenario.pass_until_resolved()
    token = next(
        state
        for state in scenario.game.permanents_controlled_by("alice")
        if state.name == "Grizzly Bears" and state.id != bears.id
    )

    scenario.no_blocks()
    scenario.combat_damage()
    # `attack_with`/`no_blocks`/`combat_damage` drive combat directly and do
    # not move `TurnMachine.step` on their own - it is still sitting at
    # `BEGINNING_OF_COMBAT` from `start_at`, so every combat step still has
    # to be walked through on the way to the end step.
    scenario.advance()  # beginning of combat -> declare attackers
    scenario.advance()  # declare attackers -> declare blockers
    scenario.advance()  # declare blockers -> combat damage
    scenario.advance()  # combat damage -> end of combat
    scenario.advance()  # end of combat -> postcombat main
    scenario.advance()  # postcombat main -> end step
    scenario.pass_until_resolved()

    assert token.zone is Zone.GRAVEYARD


def test_declining_to_blight_creates_no_copy():
    """CR 608.2d: declining the "you may" means no creature is blighted and
    no token is created."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Grub, Storied Matriarch", "Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.BEGINNING_OF_COMBAT)
    grub = _grub_notorious_auntie(scenario)
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.will_take_the_may(False, username="alice")
    scenario.attack_with(grub)
    scenario.pass_until_resolved()

    assert bears.counters[Counter.MINUS_ONE] == 0
    assert [
        state
        for state in scenario.game.permanents_controlled_by("alice")
        if state.name == "Grizzly Bears"
    ] == [bears]
