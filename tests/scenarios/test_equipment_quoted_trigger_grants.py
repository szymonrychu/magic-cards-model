"""Scenario: FRA S9's Equipment-granted triggered abilities, and the missing
"it gains ..." self-referential effect shape they exposed.

- **Medic's Kitesail** (Reality Fracture), "Equipped creature gets +1/+0 and
  has flying and "Whenever this creature attacks, you gain 1 life."" -
  `_ATTACHED_CREATURE_STATIC_RE`'s "gets P/T[ and has keywords]" branch had no
  room for a trailing quoted ability riding along with a bare keyword, so the
  pump-and-flying half worked and the quoted trigger grant was silently
  dropped. `_ATTACHED_CREATURE_PUMP_AND_QUOTED_RE` fixes the parse; nothing
  about *executing* the granted trigger needed to change; `quoted_ability_
  grants`/`sync_granted_ability_texts`/`granted_triggered_abilities_of`
  already make a granted "Whenever ..." line a real, resolving trigger the
  same way they already did for a granted *activated* ability (Ygra, Eater of
  All, `test_qualified_anthems.py`).

- **Hunter's Axe** (Reality Fracture), "Equipped creature gets +2/+0 and has
  "Whenever this creature attacks, it gains your choice of trample or
  deathtouch until end of turn."" - the same parse fix, but resolving the
  granted trigger surfaced a second, deeper gap: nothing in `machines/
  effects.py` read a no-target triggered ability's own "it gains <keyword>
  until end of turn." effect clause at all (CR 601.2c's "it" reaching back to
  the ability's source), because `create_continuous_effect_of_ability`
  derives what to parse from the *permanent's full printed text*, not from
  the already trigger-condition-stripped effect clause `trigger_effect_for`
  is actually handed - so the "Whenever X, it gains Y" shape can never reach
  `parsed_layer_effects` by that route. Fixed with two hand-built resolution
  effects (`_parse_self_keyword_grant_until_eot_clause`), the same escape
  hatch Wild Mongrel's chosen-colour pump already uses, one plain and one
  reading a CR 608.2d "of your choice" through `DecisionKind.CHOOSE_A_
  QUALITY`.

- **Primaris Chaplain** (off-set, a real card with no relation to either FRA
  card or to equipment at all: "Whenever this creature attacks, it gains
  indestructible until end of turn.") proves the "it gains X" fix is the
  mechanic, not a Hunter's-Axe-shaped patch - it was silently broken before
  this file and is fixed by the same two clause parsers with no FRA card in
  sight.

The rules these rest on:

- **CR 113.10a** - "An effect that adds an activated ability may include
  activation instructions for that ability. These instructions become part of
  the ability that's added to the object" - and CR 113's own ability
  categories treat a granted triggered ability's instructions the same way.
- **CR 301.5a/301.5f** - "equipped creature", read off `CardState.
  attached_to` rather than the board (attachment is not a characteristic).
- **CR 601.2c**/**CR 608.2d** - a resolving ability's own pronoun reaches back
  to its subject, and a choice an effect offers ("of your choice") is made
  when the ability resolves, not before.
- **CR 611.2a** - "until end of turn" (CR 611.2's one-shot effect), which is
  why every grant here is `Duration.UNTIL_END_OF_TURN`, not a permanent
  static ability.

Every CR number here was looked up with `knowledge_search(q="...",
type="rules")` in the session that wrote it, and every card's text with
`resolve_cards` or straight off its fixture.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.keywords import equip_activation
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario, mana_from


def equip(scenario: Scenario, equipment_name: str, target, *, sources: tuple[str, ...]):
    equipment = scenario.find(equipment_name, Zone.BATTLEFIELD, "alice")
    activation = equip_activation(scenario.game, equipment, target, "alice")
    payment = activation.begin_paying()
    for source in scenario.untapped_sources(*sources, username="alice"):
        payment.tap_for_mana(source, mana_from(source))
    payment.pay()
    activation.activate()
    scenario.game.put_triggers_on_stack()
    scenario.pass_priority("alice")
    scenario.pass_priority("bob")


# --------------------------------------------------------------------------
# Medic's Kitesail: pump, flying, and a quoted lifegain-on-attack trigger.
# --------------------------------------------------------------------------


def test_medics_kitesail_grants_pump_flying_and_the_quoted_trigger():
    scenario = (
        Scenario()
        .player(
            "alice", battlefield=["Medic's Kitesail", "Grizzly Bears", "Plains", "Plains"], life=20
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    equip(scenario, "Medic's Kitesail", bears, sources=("Plains", "Plains"))

    assert scenario.game.characteristics_of(bears).power_toughness == (3, 2)
    assert scenario.game.characteristics_of(bears).has_ability("Flying")

    scenario.attack_with(bears, defending="bob")
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == ["Grizzly Bears's triggered ability"]

    alice = scenario.player("alice")
    life_before = alice.life
    scenario.pass_priority("alice")
    scenario.pass_priority("bob")

    assert alice.life == life_before + 1


def test_medics_kitesail_grant_leaves_with_the_equipment():
    """CR 604.2 / CR 613.1f: unequipping takes the granted trigger back off,
    the same way any other layer 6 grant would."""
    scenario = (
        Scenario()
        .player(
            "alice", battlefield=["Medic's Kitesail", "Grizzly Bears", "Plains", "Plains"], life=20
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    equip(scenario, "Medic's Kitesail", bears, sources=("Plains", "Plains"))
    assert scenario.game.characteristics_of(bears).has_ability("Flying")

    kitesail = scenario.find("Medic's Kitesail", Zone.BATTLEFIELD, "alice")
    kitesail.unattach()

    assert not scenario.game.characteristics_of(bears).has_ability("Flying")


# --------------------------------------------------------------------------
# Hunter's Axe: pump and a quoted choice-of-keyword attack trigger.
# --------------------------------------------------------------------------


def test_hunters_axe_grants_the_pump_and_the_chosen_keyword():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Hunter's Axe", "Grizzly Bears", "Forest", "Forest"], life=20)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    equip(scenario, "Hunter's Axe", bears, sources=("Forest", "Forest"))

    assert scenario.game.characteristics_of(bears).power_toughness == (4, 2)

    scenario.will_choose("Deathtouch", source="Grizzly Bears")
    scenario.attack_with(bears, defending="bob")
    scenario.game.put_triggers_on_stack()
    scenario.pass_priority("alice")
    scenario.pass_priority("bob")

    assert scenario.game.characteristics_of(bears).has_ability("Deathtouch")
    assert not scenario.game.characteristics_of(bears).has_ability("Trample")


def test_hunters_axe_grants_whichever_keyword_is_chosen():
    """The same trigger, the other answer - proves the choice is actually
    read, not a hardcoded first option."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Hunter's Axe", "Grizzly Bears", "Forest", "Forest"], life=20)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    equip(scenario, "Hunter's Axe", bears, sources=("Forest", "Forest"))

    scenario.will_choose("Trample", source="Grizzly Bears")
    scenario.attack_with(bears, defending="bob")
    scenario.game.put_triggers_on_stack()
    scenario.pass_priority("alice")
    scenario.pass_priority("bob")

    assert scenario.game.characteristics_of(bears).has_ability("Trample")
    assert not scenario.game.characteristics_of(bears).has_ability("Deathtouch")


def test_hunters_axe_grant_expires_at_end_of_turn():
    """CR 611.2a: "until end of turn" - a one-shot grant, not a static one."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Hunter's Axe", "Grizzly Bears", "Forest", "Forest"], life=20)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    equip(scenario, "Hunter's Axe", bears, sources=("Forest", "Forest"))

    scenario.will_choose("Trample", source="Grizzly Bears")
    scenario.attack_with(bears, defending="bob")
    scenario.game.put_triggers_on_stack()
    scenario.pass_priority("alice")
    scenario.pass_priority("bob")
    assert scenario.game.characteristics_of(bears).has_ability("Trample")

    scenario.start_at(Step.END_STEP)
    scenario.advance()

    assert not scenario.game.characteristics_of(bears).has_ability("Trample")


# --------------------------------------------------------------------------
# Primaris Chaplain (off-set): the plain "it gains X until end of turn."
# shape with no equipment, no choice, and no FRA card anywhere.
# --------------------------------------------------------------------------


def test_primaris_chaplain_gains_indestructible_when_it_attacks_off_set():
    scenario = Scenario().player("alice", battlefield=["Primaris Chaplain"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    chaplain = scenario.creature("Primaris Chaplain", "alice")
    assert not scenario.game.characteristics_of(chaplain).has_ability("Indestructible")

    scenario.attack_with(chaplain, defending="bob")
    scenario.game.put_triggers_on_stack()
    # CR 702.91a: its printed Battle cry is a second attack trigger.
    assert scenario.stack_names() == ["Primaris Chaplain's triggered ability"] * 2
    for _ in range(2):
        scenario.pass_priority("alice")
        scenario.pass_priority("bob")

    assert scenario.game.characteristics_of(chaplain).has_ability("Indestructible")


def test_primaris_chaplain_loses_it_again_at_end_of_turn():
    scenario = Scenario().player("alice", battlefield=["Primaris Chaplain"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    chaplain = scenario.creature("Primaris Chaplain", "alice")

    scenario.attack_with(chaplain, defending="bob")
    scenario.game.put_triggers_on_stack()
    for _ in range(2):  # Rosarius and Battle cry (CR 702.91a)
        scenario.pass_priority("alice")
        scenario.pass_priority("bob")
    assert scenario.game.characteristics_of(chaplain).has_ability("Indestructible")

    scenario.start_at(Step.END_STEP)
    scenario.advance()

    assert not scenario.game.characteristics_of(chaplain).has_ability("Indestructible")
