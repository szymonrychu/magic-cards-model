"""Scenario: tapping an already-tapped permanent (CR 701.26a), and its untap
twin (CR 701.26b, CR 122.1d).

Before this file, every effect-side tap called `CardState.tap`, which is
strict - correct for a cost (CR 118.3) or a declared attacker (CR 508.1f),
wrong for a resolving spell or ability, which simply leaves an already-tapped
permanent as it is (CR 701.26a: "Only untapped permanents can be tapped.").
Frost Breath on a tapped Grizzly Bears raised `ValueError: Grizzly Bears is
already tapped` mid-resolution instead of doing nothing to the tap and still
applying the rest of the sentence.

`CardState.tap_if_untapped` is the effect-side verb: CR 701.26a itself, with
no error and no event for a permanent that was already tapped. `CardState.tap`
stays strict for costs and attack declaration (`machines/cost.py`,
`machines/combat.py:674`, both untouched by this file).

The untap twin: CR 701.26b, "Only tapped permanents can be untapped." CR
122.1d's stun-counter replacement - "If a permanent with a stun counter on it
would become untapped, instead remove a stun counter from it" - only applies
where there is a "would become untapped" event to replace. An untapped
permanent was never going to untap, so nothing "would become untapped" and no
counter is spent; a tapped one still loses one instead of untapping, exactly
as before.

Every rule cited here was read whole this session with `mise run rules:find`:

- **CR 701.26a** - "To tap a permanent, turn it sideways from an upright
  position. Only untapped permanents can be tapped."
- **CR 701.26b** - "To untap a permanent, turn it from a sideways position to
  an upright position. Only tapped permanents can be untapped."
- **CR 122.1d** - "One or more stun counters on a permanent create a single
  replacement effect that stops the permanent from untapping. That effect is
  'If a permanent with a stun counter on it would become untapped, instead
  remove a stun counter from it.'"

Every printing here is a real Scryfall printing from `tests/fixtures/cards`
(`src/magic_cards_model/data/printings`). Gigadrowse and Vizier of Tumbling
Sands are legal in Modern (Vizier in Pioneer too). Hammers of Moradin,
Hapatra, the Desert Frost and Infinite Coursework are off the deck pool and
off every one of Modern/Pioneer/Standard - Hammers is a Commander Legends:
Battle for Baldur's Gate exclusive, legal only in legacy, vintage, commander,
oathbreaker, duel and tlr (Scryfall legalities checked this session; it is
*not* Modern- or Pioneer-legal despite carrying the plain "for each opponent,
tap" template `_parse_for_each_opponent_tap_clause` reads). Hapatra and
Infinite Coursework are kept off-format only because each is already this
codebase's own canonical example for the template its parser reads
(`_parse_for_each_opponent_tap_then_stun_clause`'s and
`_parse_tap_enchanted_then_unprepared_clause`'s own docstrings), so no
in-format printing carries either shape.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.delayed import anaphoric_delayed_trigger
from magic_cards_model.models.card_state import Counter
from tests.cards import card

from .harness import Scenario

# -- guard: the legality claims this file's docstring makes must be true ---
# A prior version of this file claimed Hammers of Moradin was Modern- and
# Pioneer-legal; it is a Commander Legends: Battle for Baldur's Gate
# exclusive (legal only in legacy/vintage/commander/oathbreaker/duel/tlr, per
# Scryfall, checked this session). This pins the corrected claim to the
# fixture data itself so it cannot drift back to being wrong unnoticed.


def test_legality_claims_in_this_files_docstring_are_accurate():
    gigadrowse = card("Gigadrowse").legalities
    vizier = card("Vizier of Tumbling Sands").legalities
    hammers = card("Hammers of Moradin").legalities

    assert gigadrowse.modern == "legal"
    assert vizier.modern == "legal"
    assert vizier.pioneer == "legal"
    assert hammers.modern != "legal", "Hammers of Moradin is not Modern-legal"
    assert hammers.pioneer != "legal", "Hammers of Moradin is not Pioneer-legal"
    assert hammers.standard != "legal", "Hammers of Moradin is not Standard-legal"


# -- (h) CardState.tap_if_untapped itself, on a real board -----------------


def test_tap_if_untapped_taps_an_untapped_permanent_and_reports_true():
    scenario = Scenario().player("alice", battlefield=["Grizzly Bears"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    assert not bears.tapped

    assert bears.tap_if_untapped() is True
    assert bears.tapped


def test_tap_if_untapped_leaves_a_tapped_permanent_alone_and_reports_false():
    scenario = Scenario().player("alice", battlefield=["Grizzly Bears"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    bears.tapped = True

    assert bears.tap_if_untapped() is False
    assert bears.tapped


def test_tap_refuses_an_already_tapped_permanent_as_a_cost_still():
    """`CardState.tap` keeps CR 118.3's strict refusal - only
    `tap_if_untapped` is the new, permissive effect-side verb."""
    scenario = Scenario().player("alice", battlefield=["Grizzly Bears"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    bears.tapped = True

    try:
        bears.tap()
    except ValueError as exc:
        assert "already tapped" in str(exc)
    else:
        raise AssertionError("CardState.tap must still refuse a tapped permanent")


# -- (a) Frost Breath: `_parse_tap_target_then_no_untap_clause`, spell path -


def test_frost_breath_taps_an_already_tapped_target_and_an_untapped_one():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Frost Breath"],
            battlefield=["Island", "Island", "Island", "Grizzly Bears", "Goblin Guide"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    goblin = scenario.creature("Goblin Guide", "alice")
    bears.tapped = True
    assert not goblin.tapped

    sources = scenario.untapped_sources("Island", "Island", "Island")
    scenario.cast_and_resolve("Frost Breath", *sources, targets=[bears, goblin])

    assert bears.tapped, "CR 701.26a: already tapped, left as it is"
    assert goblin.tapped, "the untapped target is tapped as normal"
    assert bears.exerted, "the withheld-untap half of the sentence still lands"
    assert goblin.exerted

    scenario.game.untap_step()
    assert bears.tapped, "still doesn't untap during alice's next untap step"
    assert goblin.tapped

    scenario.game.untap_step()
    assert not bears.tapped, "the exert expired, so this untap step untaps it"
    assert not goblin.tapped


# -- (b) Tamiyo, Compleated Sage's +1: the same reader, ability path -------


def test_tamiyo_compleated_sage_plus_one_on_an_already_tapped_target():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Tamiyo, Compleated Sage"],
            battlefield=["Forest", "Forest", "Island", "Island", "Island", "Goblin Guide"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    goblin = scenario.creature("Goblin Guide", "alice")
    goblin.tapped = True

    sources = scenario.untapped_sources("Forest", "Forest", "Island", "Island", "Island")
    tamiyo = scenario.cast_and_resolve("Tamiyo, Compleated Sage", *sources)

    scenario.activate(tamiyo, targets=[goblin])
    scenario.resolve_top()

    assert goblin.tapped, "CR 701.26a: was already tapped, stays tapped"
    assert goblin.exerted, "the withheld-untap half still lands"
    assert tamiyo.counters["loyalty"] == 6


# -- (c) Hapatra, the Desert Frost: tap-then-stun on an already tapped target


def test_hapatra_desert_frost_stun_lands_on_an_already_tapped_target():
    scenario = (
        Scenario()
        .player("alice", hand=["Hapatra, the Desert Frost"], battlefield=["Island"] * 4)
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    bears.tapped = True
    scenario.choose_trigger_targets("Hapatra, the Desert Frost", [bears])

    scenario.cast_and_resolve(
        "Hapatra, the Desert Frost",
        *scenario.untapped_sources("Island", "Island", "Island", "Island"),
    )
    scenario.resolve_top()  # the enters trigger

    assert bears.tapped, "CR 701.26a: already tapped, left as it is"
    assert bears.counters["stun"] == 1, "the stun counter still lands"


# -- (d) tap_ability_targets and _parse_for_each_opponent_tap_clause -------


def test_gigadrowse_taps_an_already_tapped_target():
    """`tap_ability_targets` - Gigadrowse's plain "Tap target permanent.\""""
    scenario = (
        Scenario()
        .player("alice", hand=["Gigadrowse"], battlefield=["Island"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    bears.tapped = True

    (island,) = scenario.untapped_sources("Island")
    scenario.cast_and_resolve("Gigadrowse", island, targets=[bears])

    assert bears.tapped, "CR 701.26a: already tapped, left as it is"


def test_hammers_of_moradin_attack_trigger_taps_an_already_tapped_target():
    """`_parse_for_each_opponent_tap_clause` - Hammers of Moradin's own
    "Whenever this creature attacks, for each opponent, tap up to one target
    creature that player controls." Targets are chosen before the attack is
    declared: the trigger goes straight onto the stack as part of declaring
    attackers (CR 508.1e), so the choice has to be in place before then, the
    same way every other trigger-target scenario in this pool stages it
    ahead of the event that fires the trigger."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Hammers of Moradin"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    hammers = scenario.creature("Hammers of Moradin", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    bears.tapped = True

    scenario.choose_trigger_targets("Hammers of Moradin", [bears])
    scenario.attack_with(hammers, defending="bob")
    while scenario.game.stack:
        scenario.resolve_top()

    assert bears.tapped, "CR 701.26a: already tapped, left as it is"


# -- (e) Infinite Coursework: tap-enchanted template ------------------------


def test_infinite_coursework_taps_an_already_tapped_enchanted_creature():
    """`_parse_tap_enchanted_then_unprepared_clause` - "When this Aura enters,
    tap enchanted creature. It becomes unprepared." """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Infinite Coursework"],
            battlefield=["Grizzly Bears", "Plains", "Island", "Island"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears")
    bears.tapped = True

    scenario.cast_and_resolve(
        "Infinite Coursework",
        *scenario.untapped_sources("Plains", "Island", "Island"),
        targets=[bears],
    )
    scenario.pass_until_resolved()  # the Aura's own "When this Aura enters" trigger

    assert bears.tapped, "CR 701.26a: already tapped, left as it is"


# -- (f) a delayed TapSubject whose subject is already tapped --------------


def test_delayed_tap_subject_on_an_already_tapped_permanent():
    """`machines/delayed.TapSubject` - staged directly, the same way
    `test_delayed_trigger_round_trip.test_tap_subject_survives_a_round_trip`
    stages it: no printing in the pool exercises this anaphoric verb alone."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Grizzly Bears", "Mountain"])
        .player("bob", battlefield=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    bears.tapped = True
    trigger = anaphoric_delayed_trigger(
        "Tap it at the beginning of the next turn's upkeep.",
        subject=bears,
        controller="alice",
        source_id=None,
        source_name="a resolving spell",
    )
    assert trigger is not None
    scenario.game.create_delayed_trigger(trigger)

    while scenario.step is not Step.UPKEEP:
        scenario.advance()
        while not scenario.game.stack_is_empty:
            scenario.resolve_top()

    assert bears.tapped, "CR 701.26a: already tapped, left as it is - no ValueError"


# -- (g) the untap twin: CR 701.26b / CR 122.1d -----------------------------


def _vizier_board() -> Scenario:
    return (
        Scenario()
        .player("alice", battlefield=["Vizier of Tumbling Sands", "Grizzly Bears"])
        .player("bob")
    )


def test_vizier_does_not_spend_a_stun_counter_on_an_already_untapped_target():
    """CR 701.26b: only a tapped permanent can be untapped, so an untapped
    stunned permanent has no "would become untapped" event for CR 122.1d to
    replace, and CR 122.1d never fires."""
    scenario = _vizier_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    vizier = scenario.creature("Vizier of Tumbling Sands", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    assert not bears.tapped
    bears.add_counters(Counter.STUN, 1)

    scenario.activate(vizier, targets=[bears])
    scenario.resolve_top()

    assert not bears.tapped, "was never tapped to begin with"
    assert bears.counter_count(Counter.STUN) == 1, "no event to replace, no counter spent"


def test_vizier_still_spends_a_stun_counter_on_a_tapped_target():
    """The untap twin's existing behaviour, unaffected by this fix: a tapped
    stunned permanent still loses one counter instead of untapping."""
    scenario = _vizier_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    vizier = scenario.creature("Vizier of Tumbling Sands", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    bears.tapped = True
    bears.add_counters(Counter.STUN, 1)

    scenario.activate(vizier, targets=[bears])
    scenario.resolve_top()

    assert bears.tapped, "CR 122.1d replaced the untap"
    assert bears.counter_count(Counter.STUN) == 0, "and spent one counter doing it"


def test_untap_step_does_not_spend_a_stun_counter_on_an_already_untapped_permanent():
    """Same twin, through the untap step itself rather than an effect."""
    scenario = Scenario().player("alice", battlefield=["Grizzly Bears"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    assert not bears.tapped
    bears.add_counters(Counter.STUN, 1)

    scenario.game.untap_step()

    assert not bears.tapped
    assert bears.counter_count(Counter.STUN) == 1, "no event to replace, no counter spent"


def test_untap_step_still_spends_a_stun_counter_on_a_tapped_permanent():
    """The documented CR 122.1d gap, unaffected by this fix: a tapped
    stunned permanent still loses one counter instead of untapping."""
    scenario = Scenario().player("alice", battlefield=["Grizzly Bears"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    bears.tapped = True
    bears.add_counters(Counter.STUN, 1)

    scenario.game.untap_step()

    assert bears.tapped, "CR 122.1d replaced the untap"
    assert bears.counter_count(Counter.STUN) == 0, "and spent one counter doing it"
