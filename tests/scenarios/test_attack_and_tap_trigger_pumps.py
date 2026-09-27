"""Combat triggers whose own effect names a target by a bare creature type
instead of "creature" (CR 205.3m's own templating convention, revived by
Lorwyn Eclipsed) - "target attacking Goblin you control", "another target Elf
you control", "another target Merfolk you control" - plus CR 506.5's "attacks
alone" read into a dynamic pump.

`machines/layers.py`'s own hand-rolled `_SUBJECT`/`_SUBJECT_NOUN` grammar (used
by `_PUMP_RE` and over a dozen sibling regexes) only ever accepted "creature",
"permanent", or "creature or planeswalker" as a target's noun - a bare
capitalised creature type standing in for it, the way real Lorwyn-block Oracle
text prints it, matched nothing at all, so every one of these was silent.
`_SUBTYPE_TARGET_PUMP_RE` is the new, narrow, additive sibling that recognises
just this shape (subtype validated with `canonical_subtype`) and hands off to
the very same `_pump_and_keyword_builder` "target creature" already uses -
`machines/layers.py`'s own shared `_SUBJECT` is never touched, so nothing that
already matched it can regress.

- **Boggart Prankster** - "Whenever you attack, target attacking Goblin you
  control gets +1/+0 until end of turn." CR 508.3d: one trigger for the whole
  declaration (`event.subject_id is None`), already read generically by
  `machines/triggers.py`; the target is restricted to attacking Goblins by
  `machines/targeting.py`'s own general grammar at announcement.
- **Vinebred Brawler** - "Whenever this creature attacks, another target Elf
  you control gets +2/+1 until end of turn." CR 508.3a's plain self-attack
  trigger, "another" excluding the source.
- **Tributary Vaulter** - "Whenever this creature becomes tapped, another
  target Merfolk you control gets +2/+0 until end of turn." CR 701.26a's tap
  event, already read generically for the self-referential form.
- **Thoughtweft Imbuer** - "Whenever a creature you control attacks alone, it
  gets +X/+X until end of turn, where X is the number of Kithkin you
  control." CR 506.5's defining shape, already read generically
  (`event.attacking_alone`); the new piece is the dynamic-X anaphor pump
  (`_parse_it_dynamic_x_pump_clause`, `machines/effects.py`), which resolves
  "it" to the triggering attacker (`_referent_of_it`) rather than to the
  ability's own source the way `_attack_trigger_pump_subject`'s "Whenever
  this creature attacks, it gets ..." sibling does. **Akroan Hoplite**
  (proof printing, Modern/Pioneer-legal, not a listed card, not in any
  `decks/*.txt`) proves two things past Thoughtweft Imbuer's own printing at
  once: "it gets +X/+0" (only power is dynamic, toughness a literal "+0" -
  `_IT_GETS_DYNAMIC_X_PUMP_RE`'s power/toughness are read independently) and
  "the number of attacking creatures you control" (`count_expression`'s own
  widened `_COUNT_YOU_CONTROL_RE`, which also gained "attacking" as a status
  alongside tapped/untapped for Kinscaer Sentry's own dynamic mana-value cap).

CR numbers verified this session with `mise run rules:find`:

- **CR 508.3a** - "Whenever [a creature] attacks, ..." triggers once per
  declared attacker.
- **CR 508.3d** - "Whenever [a player] attacks, ..." triggers once per
  declaration, for one or more attackers.
- **CR 506.5** - a creature attacks alone if it is the only creature declared
  as an attacker in the declare attackers step.
- **CR 701.26a** - "To tap a permanent, turn it sideways ...".
"""

from magic_cards_model.machines import Step
from tests.scenarios.harness import Scenario


def _pt(scenario, state):
    return scenario.game.power_of(state), scenario.game.toughness_of(state)


# -- Boggart Prankster: "whenever you attack" batched trigger, target ---------
# -- restricted by combat state + subtype -------------------------------------


def test_boggart_prankster_pumps_a_target_attacking_goblin():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Boggart Prankster", "Boggart Ram-Gang"])
        .player("bob")
        .build()
    )
    prankster = scenario.creature("Boggart Prankster", "alice")
    ram_gang = scenario.creature("Boggart Ram-Gang", "alice")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    # CR 601.2c: the target is announced as the ability goes on the stack,
    # which `Game.declare_attackers` does itself right after registering the
    # whole attacking party - so the answer has to be queued before the
    # attack is declared, for the `CHOOSE_TARGETS` question that firing asks.
    scenario.will_choose_targets(ram_gang)
    scenario.attack_with(prankster, ram_gang)
    scenario.pass_until_resolved()

    assert _pt(scenario, ram_gang) == (4, 3), "3/3 Ram-Gang +1/+0"


def test_boggart_prankster_cannot_target_a_non_attacking_goblin():
    """CR 601.2c: an illegal target (not attacking) is never offered - the
    ability fires (CR 508.3d, one or more attackers) but has nothing legal
    to name if the only Goblin around never attacked."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Boggart Prankster", "Boggart Ram-Gang"])
        .player("bob")
        .build()
    )
    prankster = scenario.creature("Boggart Prankster", "alice")
    ram_gang = scenario.creature("Boggart Ram-Gang", "alice")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(prankster)  # Ram-Gang stays home, so it never attacked
    scenario.pass_until_resolved()

    assert _pt(scenario, ram_gang) == (3, 3), "never a legal target - unpumped"


def test_boggart_prankster_can_target_itself_while_attacking():
    scenario = Scenario().player("alice", battlefield=["Boggart Prankster"]).player("bob").build()
    prankster = scenario.creature("Boggart Prankster", "alice")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.will_choose_targets(prankster)
    scenario.attack_with(prankster)
    scenario.pass_until_resolved()

    assert _pt(scenario, prankster) == (2, 3), "1/3 Prankster +1/+0"


# -- Vinebred Brawler: self attack trigger, "another target" -----------------


def test_vinebred_brawler_pumps_another_target_elf():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Vinebred Brawler", "Llanowar Elves"])
        .player("bob")
        .build()
    )
    brawler = scenario.creature("Vinebred Brawler", "alice")
    elves = scenario.creature("Llanowar Elves", "alice")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.will_choose_targets(elves)
    scenario.attack_with(brawler)
    scenario.pass_until_resolved()

    assert _pt(scenario, elves) == (3, 2), "1/1 Llanowar Elves +2/+1"
    assert _pt(scenario, brawler) == (4, 2), "brawler itself is unaffected"


# -- Tributary Vaulter: a tap trigger, not an attack trigger ------------------


def test_tributary_vaulter_pumps_another_target_merfolk_when_it_becomes_tapped():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Tributary Vaulter", "Ambassador Laquatus"])
        .player("bob")
        .build()
    )
    vaulter = scenario.creature("Tributary Vaulter", "alice")
    prophet = scenario.creature("Ambassador Laquatus", "alice")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.will_choose_targets(prophet)
    scenario.attack_with(vaulter)  # tapping it to attack is CR 701.26a's tap
    scenario.pass_until_resolved()

    assert _pt(scenario, prophet) == (3, 3), "1/3 Ambassador Laquatus +2/+0"


def test_tributary_vaulter_does_not_trigger_from_an_untap():
    """CR 701.26b: untapping is the opposite event - this reads only
    `TriggerEvent.BECOMES_TAPPED`, so an untap step never fires it."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Tributary Vaulter", "Ambassador Laquatus"])
        .player("bob")
        .build()
    )
    vaulter = scenario.creature("Tributary Vaulter", "alice")
    vaulter.tap()
    scenario.start_at(Step.UNTAP)
    scenario.turn_based_actions()

    assert not vaulter.tapped
    assert scenario.stack_names() == []


# -- Thoughtweft Imbuer: CR 506.5 "attacks alone", dynamic X -------------------


def test_thoughtweft_imbuer_pumps_the_lone_attacker_by_kithkin_count():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Thoughtweft Imbuer", "Goldmeadow Dodger", "Goldmeadow Harrier"],
        )
        .player("bob")
        .build()
    )
    dodger = scenario.creature("Goldmeadow Dodger", "alice")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(dodger)  # Thoughtweft Imbuer itself stays home
    scenario.pass_until_resolved()

    # Thoughtweft Imbuer, Goldmeadow Dodger, and Goldmeadow Harrier are all
    # Kithkin - three of them, so the lone attacker gets +3/+3.
    assert _pt(scenario, dodger) == (4, 4), "1/1 Goldmeadow Dodger +3/+3"


def test_thoughtweft_imbuer_does_not_trigger_when_two_creatures_attack():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Thoughtweft Imbuer", "Goldmeadow Dodger", "Hill Giant"])
        .player("bob")
        .build()
    )
    dodger = scenario.creature("Goldmeadow Dodger", "alice")
    giant = scenario.creature("Hill Giant", "alice")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(dodger, giant)
    scenario.pass_until_resolved()

    assert _pt(scenario, dodger) == (1, 1), "not alone - CR 506.5"
    assert _pt(scenario, giant) == (3, 3)


# -- Akroan Hoplite: off-pool proof, mixed X/literal pump, attacking count ----


def test_akroan_hoplite_off_pool_proof_pumps_power_only_by_attacker_count():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Akroan Hoplite", "Goldmeadow Dodger", "Hill Giant"])
        .player("bob")
        .build()
    )
    hoplite = scenario.creature("Akroan Hoplite", "alice")
    dodger = scenario.creature("Goldmeadow Dodger", "alice")
    giant = scenario.creature("Hill Giant", "alice")

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(hoplite, dodger, giant)
    scenario.pass_until_resolved()

    # Three attacking creatures -> +3/+0, toughness untouched.
    assert _pt(scenario, hoplite) == (4, 2), "1/2 Akroan Hoplite +3/+0"
    assert _pt(scenario, dodger) == (1, 1), "not itself - unaffected"
