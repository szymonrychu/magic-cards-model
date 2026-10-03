"""Scenario: "Whenever you attack with creatures with total power N or
greater for the first time each turn, untap all attacking creatures. After
this phase, there is an additional combat phase." - Desert Were-Worm's own
attack trigger.

Two new pieces of machinery, both read generically by shape:

- `machines/triggers.total_power_attack_threshold` - a subject-less CR
  508.3d "you attack" declaration event (the same one "you attack with one
  or more `<description>`" already batches), qualified instead by the
  computed (CR 613.5) sum of every attacker's own power this declaration
  just made, not a per-attacker description.
- `machines/abilities._strip_condition_once_per_turn_trailer` - the printed
  condition's own trailing "for the first time each turn" (CR 603.2h), read
  the same way the trailing effect-side sentence "This ability triggers only
  once each turn." already is, so `TriggeredAbility.once_per_turn` gates a
  second firing in the same turn.
- `machines/effects._parse_untap_all_attacking_clause` / `_parse_
  additional_combat_phase_only_clause` - "untap all attacking creatures."
  and "After this phase, there is an additional combat phase." (CR 500.8),
  proven generic on a second, real, differently-worded printing: Hellkite
  Charger's "you may pay {5}{R}{R}. If you do, untap all attacking creatures
  and after this phase, there is an additional combat phase." - the same two
  clauses joined by "and" inside a CR 118.12 optional payment, rather than
  printed as their own two sentences.

CR 508.3d ("[a]n ability that reads 'Whenever [a player] attacks, . . .'
triggers if one or more creatures that player controls are declared as
attackers"), CR 603.2h (the once-each-turn trigger restriction), and CR 500.8
(adding phases) were all verified with `mise run rules:find` in the session
that wrote this file - see `machines/triggers.py`'s and `machines/effects.py`'s
own docstrings for the exact wording each already cites.

No legal printing anywhere in this session's Scryfall snapshot (checked both
`oracle-cards.jsonl` and a live Scryfall search) carries the exact "you
attack with creatures with total power N or greater[ for the first time each
turn]" trigger-condition wording outside Desert Were-Worm itself - every
other "total power" attack condition in the pool is either Formidable's
static "creatures you control have total power N or greater" (an intervening
*if*, a different grammar already read elsewhere) or Pack tactics' own past-
tense "if you attacked with creatures with total power N or greater this
combat" (also a different, pre-existing shape). This is recorded, not
asserted around - see the dated MEMORY.md line - and the condition reader's
own generality is instead exercised here across two different thresholds and
board shapes (a single creature meeting it alone, and two creatures only
meeting it together), while the *effect* clauses are proven on the real
second printing above.
"""

from magic_cards_model.machines import Step

from .harness import Scenario


def test_two_attackers_whose_combined_power_crosses_the_threshold_trigger_it():
    """Neither Desert Were-Worm (power 10 with five Mountains) nor Grizzly
    Bears (power 2) alone reaches 12, but attacking together they do - CR
    613.5's computed sum across the whole declaration, not a per-attacker
    check."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Desert Were-Worm", "Grizzly Bears"] + ["Mountain"] * 5)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    worm = scenario.creature("Desert Were-Worm")
    bears = scenario.creature("Grizzly Bears")
    assert scenario.game.power_of(worm) == 10
    assert scenario.game.power_of(bears) == 2

    scenario.attack_with(worm, bears)
    assert worm.tapped and bears.tapped, "attacking taps them (CR 508.1f)"

    scenario.resolve_top()

    assert not worm.tapped, "untapped by the trigger despite having attacked"
    assert not bears.tapped

    # CR 500.8's "directly after the [current] phase": the extra combat
    # phase's own steps run *before* the rest of the original combat phase
    # (declare blockers, combat damage, end of combat) rather than after -
    # `TurnMachine.insert_extra_phase`'s own `resume_index` is exactly where
    # the interrupted phase picks back up once the extra one drains its
    # queue, and it is captured while still sitting in the middle of this
    # phase's own declare-attackers step. CR 506.4b: untapping an already
    # declared attacker doesn't remove it from combat, so neither creature
    # is eligible to be *declared* an attacker again here - both are still
    # attacking from the paused original combat, which is what the extra
    # phase itself proves, not a second declaration.
    step = scenario.advance()
    while step is not Step.DECLARE_ATTACKERS:
        step = scenario.advance()

    assert scenario.step is Step.DECLARE_ATTACKERS, "the additional combat phase (CR 500.8)"
    assert scenario.game.combat.attack_by(worm.id) is None, (
        "the original combat phase ended first (CR 500.8, CR 511.3): the additional "
        "phase begins after it, not in the middle of it"
    )


def test_a_single_attacker_at_the_threshold_alone_also_triggers_it():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Desert Were-Worm"] + ["Mountain"] * 6)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    worm = scenario.creature("Desert Were-Worm")
    assert scenario.game.power_of(worm) == 12

    scenario.attack_with(worm)
    scenario.resolve_top()

    assert not worm.tapped


def test_below_the_threshold_nothing_happens():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Desert Were-Worm"] + ["Mountain"] * 5)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    worm = scenario.creature("Desert Were-Worm")
    assert scenario.game.power_of(worm) == 10

    scenario.attack_with(worm)

    assert scenario.game.stack == [], "power 10 never reaches the printed threshold of 12"
    assert worm.tapped, "still just an ordinary attack"


def test_the_trigger_does_not_fire_a_second_time_in_the_same_turn():
    """ "[F]or the first time each turn" (CR 603.2h): Desert Were-Worm's own
    copy of the ability, once fired, does not fire a second time off a
    *later*, genuinely new "you attack" declaration in the same turn - even
    one that also meets the threshold.

    Desert Were-Worm itself cannot be the one making that second
    declaration: CR 506.4b means it is still attacking from the paused
    original combat (see the test above) and cannot be redeclared, so two
    held-back Wurmcoil Engines (6 power each, never declared in the first
    attack) are what makes a genuinely new, separately-qualifying
    declaration possible at all once the extra combat's own declare-
    attackers step arrives.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Desert Were-Worm", "Wurmcoil Engine", "Wurmcoil Engine"]
            + ["Mountain"] * 6,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    worm = scenario.creature("Desert Were-Worm")
    engine_one, engine_two = scenario.creatures("Wurmcoil Engine", "Wurmcoil Engine")
    assert scenario.game.power_of(worm) == 12
    assert scenario.game.power_of(engine_one) == 6
    ability_text = (
        "Whenever you attack with creatures with total power 12 or greater "
        "for the first time each turn, untap all attacking creatures. After "
        "this phase, there is an additional combat phase."
    )
    key = f"{worm.id}:{ability_text}"

    scenario.attack_with(worm)
    scenario.resolve_top()
    assert not worm.tapped, "the first attack's own untap"
    assert scenario.game.once_per_turn_triggers.get(key) == 1

    step = scenario.advance()
    while step is not Step.DECLARE_ATTACKERS:
        step = scenario.advance()
    assert scenario.step is Step.DECLARE_ATTACKERS, "the one extra combat phase (CR 500.8)"

    scenario.attack_with(engine_one, engine_two)  # combined power 12, the threshold again

    assert scenario.game.stack == [], "once_per_turn (CR 603.2h) refuses the second trigger"
    assert scenario.game.once_per_turn_triggers.get(key) == 1, "still just the one use"
    assert engine_one.tapped and engine_two.tapped, "an ordinary attack, nothing untapped them"


# -- the *effect* clauses, proven generic on a second real printing ---------


def test_hellkite_charger_untaps_and_inserts_an_extra_combat_too():
    """Hellkite Charger: "Flying, haste\\nWhenever this creature attacks, you
    may pay {5}{R}{R}. If you do, untap all attacking creatures and after
    this phase, there is an additional combat phase." - the same two effect
    clauses as Desert Were-Worm's own, worded and joined differently (one
    "and" rather than two sentences, wrapped in a CR 118.12 optional
    payment) and printed on a real, modern-legal card, not gated by any
    total-power threshold at all."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Hellkite Charger"] + ["Mountain"] * 7)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    charger = scenario.creature("Hellkite Charger")

    scenario.will_pay_the_mana_cost(True, username="alice")
    scenario.attack_with(charger)
    assert charger.tapped, "attacking taps it (CR 508.1f) even with haste"
    scenario.resolve_top()

    assert not charger.tapped, "untapped by the trigger despite having attacked"

    step = scenario.advance()
    while step is not Step.DECLARE_ATTACKERS:
        step = scenario.advance()

    assert scenario.step is Step.DECLARE_ATTACKERS, "the additional combat phase (CR 500.8)"
    assert scenario.game.combat.attack_by(charger.id) is None, (
        "the original combat phase ended first (CR 500.8, CR 511.3)"
    )


def test_hellkite_charger_declining_the_payment_does_neither():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Hellkite Charger"] + ["Mountain"] * 7)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    charger = scenario.creature("Hellkite Charger")

    scenario.will_pay_the_mana_cost(False, username="alice")
    scenario.attack_with(charger)
    scenario.resolve_top()

    assert charger.tapped, "declined the payment, so nothing untapped it"
