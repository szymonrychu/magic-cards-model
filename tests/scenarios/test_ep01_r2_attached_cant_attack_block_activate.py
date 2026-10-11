"""EP-01 R2 T4: Aura and Equipment restrictions read off the attachment
(CR 508.1c, 509.1b, 602.5, 502.3, 701.27, 702.122).

- "Enchanted creature can't attack, block, or crew Vehicles." (Revoke
  Privileges) and the permanent forms that add "its activated abilities can't
  be activated unless they're mana abilities" in one sentence (Bound in Gold)
  or as a second sentence (Intercessor's Arrest)
- "Enchanted creature can't attack, block, or transform." (Bound by Moonsilver)
- "Enchanted creature's activated abilities can't be activated." (Detainment
  Spell) - no mana-ability exemption
- "Enchanted permanent doesn't untap during its controller's untap step and
  its activated abilities can't be activated." (Encrust, Stuck in Summoner's
  Sanctum)
- "Enchanted creature can't be blocked and has shroud." (Protective Bubble),
  "Equipped creature can't be blocked and has shroud." (Whispersilk Cloak),
  "During your turn, equipped creature has hexproof and can't be blocked."
  (Bilbo's Ring), "Enchanted creature can't be blocked as long as you control
  a Gate." (Way of the Thief)
- "As long as enchanted permanent is a creature, it gets -1/-1 and can't
  block." (Clawing Torment)
- "Enchanted creature gets +4/+1 and blocks each combat if able." (Spirespine)

Each is proven both ways: the attachment's subject is refused, a bystander is
not, and the restriction ends when the attachment leaves.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.keywords import crew_activation
from magic_cards_model.models import Zone

from .harness import Scenario

BOLT = "Lightning Bolt"


def _attack_world(aura, victim="Grizzly Bears", extra=()):
    scenario = (
        Scenario()
        .player("alice", battlefield=[aura, victim, "Hill Giant", *extra])
        .player("bob", battlefield=["Serra Angel"])
        .build()
    )
    enchanted = scenario.creature(victim, "alice")
    scenario.find(aura, Zone.BATTLEFIELD, "alice").attach_to(enchanted)
    scenario.start_at(Step.DECLARE_ATTACKERS)
    return scenario, enchanted


def _block_world(aura, victim="Grizzly Bears"):
    scenario = (
        Scenario()
        .player("alice", battlefield=["Hill Giant"])
        .player("bob", battlefield=[aura, victim])
        .build()
    )
    enchanted = scenario.creature(victim, "bob")
    scenario.find(aura, Zone.BATTLEFIELD, "bob").attach_to(enchanted)
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(scenario.creature("Hill Giant", "alice"), defending="bob")
    return scenario, enchanted


CANT_ATTACK_BLOCK_CREW = ["Revoke Privileges", "Bound in Gold", "Intercessor's Arrest"]


@pytest.mark.parametrize("aura", [*CANT_ATTACK_BLOCK_CREW, "Bound by Moonsilver"])
def test_enchanted_creature_cant_attack(aura):
    scenario, enchanted = _attack_world(aura)
    assert scenario.can_attack(enchanted) is False
    assert scenario.can_attack(scenario.creature("Hill Giant")) is True
    with pytest.raises(ValueError, match="can't attack"):
        scenario.attack_with(enchanted)


@pytest.mark.parametrize("aura", [*CANT_ATTACK_BLOCK_CREW, "Bound by Moonsilver"])
def test_enchanted_creature_cant_block(aura):
    scenario, enchanted = _block_world(aura)
    with pytest.raises(ValueError, match="can't block"):
        scenario.block(scenario.creature("Hill Giant", "alice"), enchanted)


def _crew(aura, *, enchant):
    scenario = (
        Scenario()
        .player("alice", battlefield=[aura, "Grizzly Bears", "Hill Giant", "Smuggler's Copter"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    copter = scenario.creature("Smuggler's Copter", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "alice")
    if enchant:
        scenario.find(aura, Zone.BATTLEFIELD, "alice").attach_to(bears)
    return scenario, copter, bears, giant


@pytest.mark.parametrize("aura", CANT_ATTACK_BLOCK_CREW)
def test_enchanted_creature_cant_crew_vehicles(aura):
    scenario, copter, bears, giant = _crew(aura, enchant=True)
    with pytest.raises(ValueError, match=r"can't crew|crew Vehicles"):
        crew_activation(scenario.game, copter, [bears], "alice")
    crew_activation(scenario.game, copter, [giant], "alice")


@pytest.mark.parametrize("aura", CANT_ATTACK_BLOCK_CREW)
def test_an_unenchanted_creature_crews_freely(aura):
    scenario, copter, bears, _giant = _crew(aura, enchant=False)
    crew_activation(scenario.game, copter, [bears], "alice")


# -- can't transform (Bound by Moonsilver) -----------------------------------


def _delver(*, enchant):
    scenario = (
        Scenario()
        .player("alice", battlefield=["Bound by Moonsilver", "Delver of Secrets", "Hill Giant"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    delver = scenario.creature("Delver of Secrets", "alice")
    aura = scenario.find("Bound by Moonsilver", Zone.BATTLEFIELD, "alice")
    if enchant:
        aura.attach_to(delver)
    return scenario, delver, aura


def test_the_enchanted_creature_cant_transform():
    _scenario, delver, _aura = _delver(enchant=True)
    before = delver.up_face_name
    delver.transform()
    assert delver.up_face_name == before


def test_an_unenchanted_creature_transforms():
    _scenario, delver, _aura = _delver(enchant=False)
    before = delver.up_face_name
    delver.transform()
    assert delver.up_face_name != before


def test_transforming_works_again_once_the_aura_moves_off():
    scenario, delver, aura = _delver(enchant=True)
    aura.attach_to(scenario.creature("Hill Giant", "alice"))
    before = delver.up_face_name
    delver.transform()
    assert delver.up_face_name != before


# -- activated abilities ------------------------------------------------------


def _activation_world(aura, creature):
    scenario = (
        Scenario()
        .player("alice", battlefield=[aura, creature, "Forest", "Forest"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    target = scenario.creature(creature, "alice")
    return scenario, target, scenario.find(aura, Zone.BATTLEFIELD, "alice")


@pytest.mark.parametrize("aura", ["Bound in Gold", "Intercessor's Arrest"])
def test_enchanted_permanents_nonmana_abilities_are_refused(aura):
    scenario, rootwalla, source = _activation_world(aura, "Basking Rootwalla")
    assert scenario.why_cannot_activate(rootwalla, 0, "alice") is None
    source.attach_to(rootwalla)
    reason = scenario.why_cannot_activate(rootwalla, 0, "alice")
    assert reason is not None and "activated abilities can't be activated" in reason
    assert aura in reason and "CR 602.5" in reason


@pytest.mark.parametrize("aura", ["Bound in Gold", "Intercessor's Arrest"])
def test_the_mana_ability_exemption_is_read(aura):
    scenario, elves, source = _activation_world(aura, "Llanowar Elves")
    source.attach_to(elves)
    assert scenario.why_cannot_activate(elves, 0, "alice") is None


def test_detainment_spell_stops_every_activated_ability_mana_included():
    scenario, elves, source = _activation_world("Detainment Spell", "Llanowar Elves")
    assert scenario.why_cannot_activate(elves, 0, "alice") is None
    source.attach_to(elves)
    reason = scenario.why_cannot_activate(elves, 0, "alice")
    assert reason is not None and "Detainment Spell" in reason and "CR 602.5" in reason


def test_detainment_spell_leaves_other_creatures_alone():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Detainment Spell", "Llanowar Elves", "Basking Rootwalla"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.find("Detainment Spell", Zone.BATTLEFIELD, "alice").attach_to(
        scenario.creature("Llanowar Elves", "alice")
    )
    rootwalla = scenario.creature("Basking Rootwalla", "alice")
    assert scenario.why_cannot_activate(rootwalla, 0, "alice") is None


# -- doesn't untap + activated abilities (Encrust, Stuck in Summoner's Sanctum) -


@pytest.mark.parametrize("aura", ["Encrust", "Stuck in Summoner's Sanctum"])
def test_the_enchanted_permanent_stays_tapped_and_cant_activate(aura):
    scenario, elves, source = _activation_world(aura, "Llanowar Elves")
    source.attach_to(elves)
    elves.tapped = True
    scenario.game.untap_step()
    assert elves.tapped, "doesn't untap during its controller's untap step"
    reason = scenario.why_cannot_activate(elves, 0, "alice")
    assert reason is not None and aura in reason and "CR 602.5" in reason


@pytest.mark.parametrize("aura", ["Encrust", "Stuck in Summoner's Sanctum"])
def test_without_the_aura_the_permanent_untaps_and_activates(aura):
    scenario, elves, source = _activation_world(aura, "Llanowar Elves")
    elves.tapped = True
    scenario.game.untap_step()
    assert not elves.tapped
    assert scenario.why_cannot_activate(elves, 0, "alice") is None


def test_encrust_enchants_an_artifact_too():
    scenario, ring, source = _activation_world("Encrust", "Sol Ring")
    source.attach_to(ring)
    ring.tapped = True
    scenario.game.untap_step()
    assert ring.tapped
    assert scenario.why_cannot_activate(ring, 0, "alice") is not None


# -- can't be blocked (+ shroud / hexproof / Gate) -----------------------------


def _evasion_world(attachment, *, host="Grizzly Bears", mine=(), theirs=("Hill Giant",)):
    scenario = (
        Scenario()
        .player("alice", battlefield=[attachment, host, *mine])
        .player("bob", battlefield=list(theirs))
        .build()
    )
    attacker = scenario.creature(host, "alice")
    scenario.find(attachment, Zone.BATTLEFIELD, "alice").attach_to(attacker)
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(attacker, defending="bob")
    return scenario, attacker


def _blocked(scenario, attacker):
    try:
        scenario.block(attacker, scenario.creature("Hill Giant", "bob"))
    except ValueError as error:
        return str(error)
    return None


@pytest.mark.parametrize("attachment", ["Protective Bubble", "Whispersilk Cloak"])
def test_cant_be_blocked_and_has_shroud_the_blocker_is_refused(attachment):
    scenario, attacker = _evasion_world(attachment)
    refusal = _blocked(scenario, attacker)
    assert refusal is not None and "can't be blocked" in refusal and "CR 509.1b" in refusal


def _bolt_world(attachment, *, enchant):
    scenario = (
        Scenario()
        .player("alice", battlefield=[attachment, "Grizzly Bears", "Mountain"], hand=[BOLT])
        .player("bob")
        .build()
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    if enchant:
        scenario.find(attachment, Zone.BATTLEFIELD, "alice").attach_to(bears)
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario, bears


@pytest.mark.parametrize("attachment", ["Protective Bubble", "Whispersilk Cloak"])
def test_cant_be_blocked_and_has_shroud_the_creature_is_untargetable(attachment):
    scenario, bears = _bolt_world(attachment, enchant=True)
    with pytest.raises(ValueError, match=r"shroud|can't be the target"):
        scenario.cast(BOLT, "alice", targets=[bears])


@pytest.mark.parametrize("attachment", ["Protective Bubble", "Whispersilk Cloak"])
def test_without_the_attachment_the_creature_is_targetable(attachment):
    scenario, bears = _bolt_world(attachment, enchant=False)
    scenario.cast(BOLT, "alice", targets=[bears])


@pytest.mark.parametrize("attachment", ["Protective Bubble", "Whispersilk Cloak"])
def test_the_blocker_is_free_once_the_attachment_moves(attachment):
    scenario, attacker = _evasion_world(attachment, mine=("Hill Giant",))
    scenario.find(attachment, Zone.BATTLEFIELD, "alice").attach_to(
        scenario.creature("Hill Giant", "alice")
    )
    assert _blocked(scenario, attacker) is None


def test_way_of_the_thief_needs_a_gate():
    with_gate, attacker = _evasion_world("Way of the Thief", mine=("Azorius Guildgate",))
    refusal = _blocked(with_gate, attacker)
    assert refusal is not None and "can't be blocked" in refusal
    assert with_gate.game.power_of(attacker) == 4, "and the +2/+2 still applies"


def test_way_of_the_thief_without_a_gate_is_blockable():
    scenario, attacker = _evasion_world("Way of the Thief")
    assert _blocked(scenario, attacker) is None
    assert scenario.game.power_of(attacker) == 4


def test_way_of_the_thief_a_gate_the_opponent_controls_does_not_count():
    scenario, attacker = _evasion_world(
        "Way of the Thief", theirs=("Hill Giant", "Dimir Guildgate")
    )
    assert _blocked(scenario, attacker) is None


def test_bilbos_ring_on_its_controllers_turn_cant_be_blocked():
    scenario, attacker = _evasion_world("Bilbo's Ring")
    refusal = _blocked(scenario, attacker)
    assert refusal is not None and "can't be blocked" in refusal


def test_bilbos_ring_hexproof_only_during_its_controllers_turn():
    def world(first):
        scenario = Scenario().manual_turn_based_actions()
        for name in (first, "bob" if first == "alice" else "alice"):
            scenario = scenario.player(
                name,
                battlefield=(
                    ["Bilbo's Ring", "Grizzly Bears"] if name == "alice" else ["Mountain"]
                ),
                hand=[BOLT] if name == "bob" else [],
            )
        played = scenario.build()
        ring = played.find("Bilbo's Ring", Zone.BATTLEFIELD, "alice")
        ring.attach_to(played.creature("Grizzly Bears", "alice"))
        played.start_at(Step.PRECOMBAT_MAIN)
        return played

    on_my_turn = world("alice")
    with pytest.raises(ValueError, match=r"hexproof|can't be the target"):
        on_my_turn.cast(BOLT, "bob", targets=[on_my_turn.creature("Grizzly Bears", "alice")])
    on_theirs = world("bob")
    on_theirs.cast(BOLT, "bob", targets=[on_theirs.creature("Grizzly Bears", "alice")])


# -- Clawing Torment ------------------------------------------------------------


def test_clawing_torment_on_a_creature_shrinks_it_and_stops_it_blocking():
    scenario, enchanted = _block_world("Clawing Torment", victim="Hill Giant")
    assert scenario.game.power_of(enchanted) == 2
    assert scenario.game.toughness_of(enchanted) == 2
    with pytest.raises(ValueError, match="can't block"):
        scenario.block(scenario.creature("Hill Giant", "alice"), enchanted)


def test_clawing_torment_on_a_noncreature_artifact_does_nothing():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Clawing Torment", "Sol Ring"])
        .player("bob")
        .build()
    )
    ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "alice")
    scenario.find("Clawing Torment", Zone.BATTLEFIELD, "alice").attach_to(ring)
    chars = scenario.game.characteristics_of(ring)
    assert chars.power_toughness == (None, None)


# -- Spirespine ------------------------------------------------------------------


def test_spirespine_bestowed_makes_the_enchanted_creature_block_if_able():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Hill Giant"])
        .player("bob", battlefield=["Spirespine", "Grizzly Bears", "Serra Angel"])
        .build()
    )
    bears = scenario.creature("Grizzly Bears", "bob")
    spirespine = scenario.find("Spirespine", Zone.BATTLEFIELD, "bob")
    spirespine.attach_to(bears)
    scenario.start_at(Step.DECLARE_ATTACKERS)
    giant = scenario.creature("Hill Giant", "alice")
    scenario.attack_with(giant, defending="bob")
    assert scenario.game.power_of(bears) == 6
    with pytest.raises(ValueError, match="CR 509.1c"):
        scenario.block(giant, scenario.creature("Serra Angel", "bob"))
    scenario.block(giant, bears, spirespine)
