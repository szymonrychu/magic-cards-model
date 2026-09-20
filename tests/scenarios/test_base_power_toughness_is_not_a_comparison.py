"""Scenario: "target creature has base power and toughness N/N" (CR 613.4b)
is a resolving *effect*, not a "with power/toughness N" target *restriction*
(CR 202.3, CR 208.1/208.2).

Multiply by Zero reads "Target creature has base power and toughness 0/0
until end of turn." - `machines/targeting.py`'s `_extract_comparison`
tokenizes "0/0" losing the "/" (each digit becomes its own word), which left
"toughness" directly in front of a bare "0" - exactly `_COMPARISON_CLAUSE`'s
own shape for a real "target creature with toughness 0" restriction. So the
parser misread the card's own effect as an announcement-time requirement
that the target *already* have toughness 0, which a normal creature never
does - Multiply by Zero could not legally target anything. Perfected
Theory's two modes ("has base power and toughness 1/1"/"4/5") misread the
identical way, turning "target creature" into "target creature with
toughness 1"/"target creature with toughness 4".

Fixed by `_SETS_BASE_POWER_TOUGHNESS_EFFECT`, stripped out of the phrase's
tail before the comparison scan ever sees it - the same "read this clause out
of the way first" treatment `_COLORS_OF_MANA_SPENT_CONDITION` already gets
for an unrelated lookalike.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.targeting import spell_profile_for_text
from magic_cards_model.models import Zone

from .harness import Scenario


def test_multiply_by_zero_profile_carries_no_comparison():
    profile = spell_profile_for_text(
        "Target creature has base power and toughness 0/0 until end of turn."
    )
    assert profile.understood
    (requirement,) = profile.requirements
    assert requirement.comparison_attribute is None


def test_multiply_by_zero_can_target_an_ordinary_creature():
    """The reported misread: a 2/2 with nonzero toughness used to be refused
    as illegal because the parser thought "toughness 0" was a requirement on
    the *target*, not the effect it was about to apply."""
    scenario = (
        Scenario()
        .player("alice", hand=["Multiply by Zero"], battlefield=["Swamp", "Swamp"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    sources = scenario.untapped_sources("Swamp", "Swamp")

    scenario.cast_and_resolve("Multiply by Zero", *sources, targets=[bears])

    assert bears.power == 0
    assert bears.toughness == 0
    assert bears.zone is Zone.GRAVEYARD  # CR 704.5f: 0 toughness


def test_perfected_theory_mode_one_can_target_a_four_toughness_creature():
    """Mode one sets base power and toughness 1/1 - the old misread would
    have refused any target whose toughness was not already 1."""
    scenario = (
        Scenario()
        .player("alice", hand=["Perfected Theory"], battlefield=["Island"])
        .player("bob", battlefield=["Fog Bank"])  # 0/4
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    fog_bank = scenario.creature("Fog Bank", "bob")
    (source,) = scenario.untapped_sources("Island")

    casting = scenario.cast("Perfected Theory", username="alice")
    casting.choose_modes([1])
    casting.choose_targets([fog_bank])
    payment = casting.begin_paying()
    scenario.pay_with(payment, source)
    scenario.put_on_stack(casting)
    scenario.pass_until_resolved()

    assert fog_bank.power == 1
    assert fog_bank.toughness == 1


def test_perfected_theory_mode_two_can_target_a_two_toughness_creature():
    """Mode two sets base power and toughness 4/5 - the old misread required
    toughness 4 already, refusing a 2/2 outright."""
    scenario = (
        Scenario()
        .player("alice", hand=["Perfected Theory"], battlefield=["Island"])
        .player("bob", battlefield=["Grizzly Bears"])  # 2/2
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    (source,) = scenario.untapped_sources("Island")

    casting = scenario.cast("Perfected Theory", username="alice")
    casting.choose_modes([2])
    casting.choose_targets([bears])
    payment = casting.begin_paying()
    scenario.pay_with(payment, source)
    scenario.put_on_stack(casting)
    scenario.pass_until_resolved()

    assert bears.power == 4
    assert bears.toughness == 5


# -- off-set proof: a different card, an unbound X rather than a printed --
# -- number, an activated ability rather than a spell, and a "you control" --
# -- controller restriction ahead of the effect verb -----------------------


def test_minsc_profile_reads_the_controller_restriction_with_no_comparison():
    """Minsc, Beloved Ranger's activated ability: "{X}: Until end of turn,
    target creature you control has base power and toughness X/X and becomes
    a Giant in addition to its other types." Proves the fix generalises past
    a printed N/N to an unbound X/X, and that the effect-verb strip runs
    *after* a genuine "you control" restriction rather than eating it too."""
    profile = spell_profile_for_text(
        "Until end of turn, target creature you control has base power and "
        "toughness X/X and becomes a Giant in addition to its other types."
    )
    assert profile.understood
    (requirement,) = profile.requirements
    assert requirement.comparison_attribute is None
    from magic_cards_model.machines.targeting import ControllerRestriction

    assert requirement.controller is ControllerRestriction.YOU
