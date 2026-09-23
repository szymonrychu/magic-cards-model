"""Scenario: `machines/layers.py`'s target-subject qualifier slot ("target
<qualifier> creature") admits a hyphenated or multi-word creature type, not
just one bare word.

CR 205.3m (looked up this session with `mise run rules:find 205.3m`): "One
creature type is two words long: Time Lord. All other creature types are one
word long: ... Assembly-Worker, ..." - so a creature-type qualifier is either
a single plain word (Human), a single *hyphenated* word (Assembly-Worker), or
the one two-word exception (Time Lord). `_SUBJECT` (both its "target ..." and
"another target ..." branches), `_PLURAL_TARGET_SUBJECT`, and
`_TARGET_AND_SAME_NAME_PUMP_RE` all read that slot as `(?: [a-z]+)?` - one
optional bare word, no hyphen - so "Target Assembly-Worker creature gets
+1/+1 until end of turn." (Mishra's Factory's own third ability, and Assembly-
Worker's only one) never matched at all: CR 601.2c/608.2b targeting had
already settled that the ability's target was legal (`machines/targeting.py`
reads the computed subtype fine, per
`test_targeting_computed_supertype_subtype_historic.py`), but the *magnitude*
parser in this file had no way to read past "Target " to "creature" with a
hyphenated word in between, so the ability resolved and did nothing.

Fight as One's second mode - "Target non-Human creature you control gets
+1/+1 and gains indestructible until end of turn." - is the same gap for a
*modal spell*: mode one ("Target Human creature ...") already matched the old
regex, because "Human" has no hyphen, so the card's own "notice" status
before this fix comes from mode two alone (`Game.mode_notices` non-empty,
CR 700.2a's "the effect of only the chosen mode is applied" meaning the
un-parsed mode silently does nothing while its sibling mode still resolves).

Targeting legality itself is not this file's business - it was already
correct before this fix and stays exactly as it was; only the magnitude
parser's own qualifier slot is widened here.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.keywords import is_indestructible

from .harness import Scenario


def computed(scenario: Scenario):
    """The board with static abilities and stored durational effects applied."""
    return scenario.game.continuous_effects.board(scenario.game.battlefield)


# --------------------------------------------------------------------------
# (a) Mishra's Factory: animate it, then its tap ability on another animated
# Factory (an Assembly-Worker, CR 613.1d's granted creature type) gives
# +1/+1 until end of turn.
# --------------------------------------------------------------------------


def test_mishras_factory_pumps_another_animated_factory():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Mishra's Factory", "Mishra's Factory", "Forest", "Forest"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    factory1, factory2, forest1, forest2 = scenario.creatures(
        "Mishra's Factory", "Mishra's Factory", "Forest", "Forest", username="alice"
    )

    # "{1}: This land becomes a 2/2 Assembly-Worker artifact creature until
    # end of turn. It's still a land." - Mishra's Factory's own second
    # ability (index 1), animating both copies.
    scenario.activate(factory1, forest1, index=1)
    scenario.resolve_top()
    scenario.activate(factory2, forest2, index=1)
    scenario.resolve_top()

    # "{T}: Target Assembly-Worker creature gets +1/+1 until end of turn." -
    # Mishra's Factory's own third ability (index 2), factory1 targeting the
    # now-animated factory2.
    scenario.activate(factory1, index=2, targets=[factory2])
    scenario.resolve_top()

    assert computed(scenario).of(factory2).power_toughness == (3, 3), (
        "the animated 2/2 plus the pump's +1/+1"
    )


# --------------------------------------------------------------------------
# (b) The Assembly-Worker printing's own identical ability does the same,
# with no animation needed - it is already a creature.
# --------------------------------------------------------------------------


def test_assembly_workers_own_printing_pumps_another_assembly_worker():
    scenario = (
        Scenario().player("alice", battlefield=["Assembly-Worker", "Assembly-Worker"]).build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    worker1, worker2 = scenario.creatures("Assembly-Worker", "Assembly-Worker", username="alice")

    scenario.activate(worker1, index=0, targets=[worker2])
    scenario.resolve_top()

    assert computed(scenario).of(worker2).power_toughness == (3, 3), (
        "the printed 2/2 plus the pump's +1/+1"
    )


# --------------------------------------------------------------------------
# (c) Fight as One's second mode on a non-Human creature: +1/+1 and
# indestructible until end of turn. Both modes chosen apply to their
# respective targets, and the card's own notice becomes handled.
# --------------------------------------------------------------------------


def test_fight_as_one_pumps_and_grants_indestructible_to_both_chosen_targets():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Fight as One"],
            battlefield=["Plains", "Abzan Falconer", "Grizzly Bears"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    human = scenario.creature("Abzan Falconer", "alice")  # Creature - Human Soldier
    non_human = scenario.creature("Grizzly Bears", "alice")  # Creature - Bear
    plains = scenario.untapped_sources("Plains")

    casting = scenario.cast("Fight as One")
    casting.choose_modes([1, 2])
    casting.choose_targets([human, non_human])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *plains)
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    board = computed(scenario)
    assert board.of(human).power_toughness == (3, 4), "the printed 2/3 plus mode one's +1/+1"
    assert is_indestructible(human, scenario.game)
    assert board.of(non_human).power_toughness == (3, 3), "the printed 2/2 plus mode two's +1/+1"
    assert is_indestructible(non_human, scenario.game)
    assert scenario.game.mode_notices == [], "both chosen modes read, neither left a notice"


# --------------------------------------------------------------------------
# (d) The effects end at cleanup (CR 514.2, CR 703.4p: "until end of turn").
# --------------------------------------------------------------------------


def test_fight_as_one_effects_end_at_cleanup():
    scenario = (
        Scenario()
        .player("alice", hand=["Fight as One"], battlefield=["Plains", "Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    plains = scenario.untapped_sources("Plains")

    casting = scenario.cast("Fight as One")
    casting.choose_modes([2])
    casting.choose_targets([bears])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *plains)
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    scenario.start_at(Step.END_STEP)
    assert computed(scenario).of(bears).power_toughness == (3, 3), "still up in the end step"
    assert is_indestructible(bears, scenario.game)

    scenario.advance()  # cleanup

    board = computed(scenario)
    assert board.of(bears).power_toughness == (2, 2)
    assert not is_indestructible(bears, scenario.game)
