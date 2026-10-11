"""EP-01 R2 T4: attack and block restrictions and requirements a creature
states about itself (CR 508.1c, 508.1d, 509.1b, 509.1c, 506.5, 613.1f).

- "can't be blocked as long as it's attacking alone" (Yuan-Ti Malison, Dream
  Prowler)
- "can't attack during extra turns" (Medomai the Ageless)
- "can't attack if defending player controls <description>" (Orgg)
- "can't attack unless you sacrifice two Islands" (Leviathan)
- "can't be blocked unless all creatures defending player controls block it"
  (Tromokratis)
- "As long as <condition>, this creature has hexproof and can't be blocked."
  (Slippery Scoundrel's city's blessing, Ratonhnhake's "hasn't dealt damage
  yet", Futurist Operative's tapped form) and the keyword-only twins
  (Karakyk Guardian, Palladia-Mors), "has hexproof unless it's attacking or
  blocking" (Tromokratis)
- "As long as this creature has a +1/+1 counter on it, it can attack as
  though it didn't have defender" (Skyclave Sentinel, Scuttlegator)
- "target creature defending player controls blocks it this combat if able"
  (Avalanche Tusker, Impetuous Devils, Fighter Class)
- "No more than one creature can attack ~ each combat" on a planeswalker
  (The Eternal Wanderer)
- "can't be blocked by more than one creature each combat this turn"
  (Glorfindel, Dauntless Rescuer's mode)
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter

from .harness import Scenario


def _block(
    attacker: str,
    blockers: list[str],
    *,
    extra_attackers=(),
    mine=(),
    theirs=(),
    setup=None,
):
    """Alice attacks bob with `attacker` (and `extra_attackers`); bob blocks
    the first with `blockers`. The refusal message, or None when it is legal."""
    scenario = (
        Scenario()
        .player("alice", battlefield=[attacker, *extra_attackers, *mine])
        .player("bob", battlefield=[*blockers, *theirs])
        .build()
    )
    attacking = scenario.creature(attacker, "alice")
    if setup is not None:
        setup(scenario, attacking)
    scenario.start_at(Step.DECLARE_ATTACKERS)
    others = [scenario.creature(name, "alice") for name in extra_attackers]
    scenario.attack_with(attacking, *others, defending="bob")
    try:
        scenario.block(attacking, *[scenario.creature(name, "bob") for name in blockers])
    except ValueError as error:
        return str(error)
    return None


# -- "can't be blocked as long as it's attacking alone" ----------------------


@pytest.mark.parametrize("name", ["Yuan-Ti Malison", "Dream Prowler"])
def test_unblockable_while_attacking_alone(name):
    refusal = _block(name, ["Hill Giant"])
    assert refusal is not None and "can't be blocked" in refusal and "CR 509.1b" in refusal


@pytest.mark.parametrize("name", ["Yuan-Ti Malison", "Dream Prowler"])
def test_blockable_when_another_creature_attacks_too(name):
    assert _block(name, ["Hill Giant"], extra_attackers=["Grizzly Bears"]) is None


def test_the_other_attacker_is_not_unblockable_either():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Yuan-Ti Malison", "Grizzly Bears"])
        .player("bob", battlefield=["Hill Giant"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    malison = scenario.creature("Yuan-Ti Malison", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.attack_with(malison, bears, defending="bob")
    scenario.block(bears, scenario.creature("Hill Giant", "bob"))


# -- Medomai: "can't attack during extra turns" ------------------------------


def test_medomai_attacks_on_an_ordinary_turn():
    scenario = Scenario().player("alice", battlefield=["Medomai the Ageless"]).player("bob").build()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    medomai = scenario.creature("Medomai the Ageless", "alice")
    assert scenario.can_attack(medomai) is True


def test_medomai_cannot_attack_during_an_extra_turn():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Medomai the Ageless", "Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.game.turn.taking_extra_turn = True
    medomai = scenario.creature("Medomai the Ageless", "alice")
    assert scenario.can_attack(medomai) is False
    assert scenario.can_attack(scenario.creature("Grizzly Bears", "alice")) is True
    with pytest.raises(ValueError, match=r"CR 508\.1c"):
        scenario.attack_with(medomai)


# -- Orgg: "can't attack if defending player controls ..." -------------------


def _orgg(*theirs, tap=()):
    scenario = Scenario().player("alice", battlefield=["Orgg"]).player("bob", battlefield=theirs)
    played = scenario.build()
    played.start_at(Step.DECLARE_ATTACKERS)
    for name in tap:
        played.creature(name, "bob").tapped = True
    return played


def test_orgg_cannot_attack_into_an_untapped_creature_with_power_three():
    scenario = _orgg("Hill Giant")
    orgg = scenario.creature("Orgg", "alice")
    assert scenario.can_attack(orgg) is False
    with pytest.raises(ValueError, match=r"CR 508\.1c"):
        scenario.attack_with(orgg)


def test_orgg_attacks_when_the_big_creature_is_tapped_or_small():
    tapped = _orgg("Hill Giant", tap=["Hill Giant"])
    assert tapped.can_attack(tapped.creature("Orgg", "alice")) is True
    small = _orgg("Grizzly Bears")
    assert small.can_attack(small.creature("Orgg", "alice")) is True


def test_orgg_cannot_block_a_power_three_attacker_but_blocks_a_small_one():
    scenario = (
        Scenario().player("alice", battlefield=["Hill Giant"]).player("bob", battlefield=["Orgg"])
    ).build()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(scenario.creature("Hill Giant", "alice"), defending="bob")
    with pytest.raises(ValueError, match=r"CR 509\.1b"):
        scenario.block(scenario.attackers()[0], scenario.creature("Orgg", "bob"))


# -- Leviathan: "can't attack unless you sacrifice two Islands" --------------


def _leviathan(islands: int, *, copies: int = 1):
    scenario = (
        Scenario()
        .player("alice", battlefield=["Leviathan"] * copies + ["Island"] * islands)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    for leviathan in scenario.creatures(*["Leviathan"] * copies, username="alice"):
        leviathan.tapped = False
    return scenario


def _islands_left(scenario) -> int:
    return sum(1 for p in scenario.game.permanents_controlled_by("alice") if p.name == "Island")


def test_leviathan_sacrifices_two_islands_to_attack():
    scenario = _leviathan(3)
    leviathan = scenario.creature("Leviathan", "alice")
    scenario.attack_with(leviathan, defending="bob")
    assert scenario.attackers() == [leviathan]
    assert _islands_left(scenario) == 1
    assert sum(1 for c in scenario.game.player("alice").graveyard if c.name == "Island") == 2


def test_leviathan_with_one_island_cannot_attack():
    scenario = _leviathan(1)
    leviathan = scenario.creature("Leviathan", "alice")
    assert scenario.can_attack(leviathan) is False
    with pytest.raises(ValueError, match=r"CR 508\.1c"):
        scenario.attack_with(leviathan, defending="bob")
    assert _islands_left(scenario) == 1


def test_leviathan_does_not_sacrifice_when_it_stays_home():
    scenario = _leviathan(2)
    scenario.attack_with(defending="bob")
    assert _islands_left(scenario) == 2


def test_two_leviathans_need_four_islands():
    short = _leviathan(3, copies=2)
    first, second = short.creatures("Leviathan", "Leviathan", username="alice")
    with pytest.raises(ValueError, match=r"CR 508\.1c"):
        short.attack_with(first, second, defending="bob")
    enough = _leviathan(4, copies=2)
    first, second = enough.creatures("Leviathan", "Leviathan", username="alice")
    enough.attack_with(first, second, defending="bob")
    assert _islands_left(enough) == 0


# -- Tromokratis ------------------------------------------------------------


def test_tromokratis_is_blocked_only_by_all_of_the_defenders_creatures():
    both = ["Hill Giant", "Grizzly Bears"]
    refusal = _block("Tromokratis", ["Hill Giant"], theirs=["Grizzly Bears"])
    assert refusal is not None and "CR 509.1b" in refusal
    assert _block("Tromokratis", both) is None


def test_tromokratis_can_be_blocked_by_a_lone_defender():
    assert _block("Tromokratis", ["Hill Giant"]) is None


def test_tromokratis_unblocked_is_not_a_violation():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Tromokratis"])
        .player("bob", battlefield=["Hill Giant", "Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(scenario.creature("Tromokratis", "alice"), defending="bob")
    scenario.no_blocks()


def test_tromokratis_has_hexproof_unless_attacking_or_blocking():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Tromokratis"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    kraken = scenario.creature("Tromokratis", "alice")
    assert scenario.game.characteristics_of(kraken).has_ability("Hexproof")
    scenario.attack_with(kraken, defending="bob")
    assert not scenario.game.characteristics_of(kraken).has_ability("Hexproof")


def test_tromokratis_loses_hexproof_while_blocking():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Hill Giant"])
        .player("bob", battlefield=["Tromokratis"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    kraken = scenario.creature("Tromokratis", "bob")
    assert scenario.game.characteristics_of(kraken).has_ability("Hexproof")
    scenario.attack_with(scenario.creature("Hill Giant", "alice"), defending="bob")
    scenario.block(scenario.attackers()[0], kraken)
    assert not scenario.game.characteristics_of(kraken).has_ability("Hexproof")


# -- gated "has hexproof and can't be blocked" -------------------------------


def test_slippery_scoundrel_with_the_citys_blessing_is_hexproof_and_unblockable():
    def bless(scenario, attacking):
        scenario.game.player("alice").has_citys_blessing = True

    refusal = _block("Slippery Scoundrel", ["Hill Giant"], setup=bless)
    assert refusal is not None and "can't be blocked" in refusal

    scenario = Scenario().player("alice", battlefield=["Slippery Scoundrel"]).player("bob").build()
    scoundrel = scenario.creature("Slippery Scoundrel", "alice")
    assert not scenario.game.characteristics_of(scoundrel).has_ability("Hexproof")
    scenario.game.player("alice").has_citys_blessing = True
    assert scenario.game.characteristics_of(scoundrel).has_ability("Hexproof")


def test_slippery_scoundrel_without_the_blessing_is_blockable():
    assert _block("Slippery Scoundrel", ["Hill Giant"]) is None


def test_the_blessing_is_the_controllers_not_the_opponents():
    def bless_bob(scenario, attacking):
        scenario.game.player("bob").has_citys_blessing = True

    assert _block("Slippery Scoundrel", ["Hill Giant"], setup=bless_bob) is None


def test_ratonhnhaketon_is_untouchable_until_it_deals_damage():
    scenario = Scenario().player("alice", battlefield=["Ratonhnhaké꞉ton"]).player("bob").build()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    assassin = scenario.creature("Ratonhnhaké꞉ton", "alice")
    assert scenario.game.characteristics_of(assassin).has_ability("Hexproof")
    scenario.attack_with(assassin, defending="bob")
    scenario.no_blocks()
    scenario.combat_damage()
    assert not scenario.game.characteristics_of(assassin).has_ability("Hexproof")


def test_ratonhnhaketon_cannot_be_blocked_before_it_has_dealt_damage():
    refusal = _block("Ratonhnhaké꞉ton", ["Hill Giant"])
    assert refusal is not None and "can't be blocked" in refusal


@pytest.mark.parametrize("name", ["Karakyk Guardian", "Palladia-Mors, the Ruiner"])
def test_hexproof_ends_once_the_creature_has_dealt_damage(name):
    scenario = Scenario().player("alice", battlefield=[name]).player("bob").build()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    dragon = scenario.creature(name, "alice")
    assert scenario.game.characteristics_of(dragon).has_ability("Hexproof")
    scenario.attack_with(dragon, defending="bob")
    scenario.no_blocks()
    scenario.combat_damage()
    assert not scenario.game.characteristics_of(dragon).has_ability("Hexproof")


def test_damage_dealt_by_another_creature_does_not_end_hexproof():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Karakyk Guardian", "Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    guardian = scenario.creature("Karakyk Guardian", "alice")
    scenario.attack_with(scenario.creature("Grizzly Bears", "alice"), defending="bob")
    scenario.no_blocks()
    scenario.combat_damage()
    assert scenario.game.characteristics_of(guardian).has_ability("Hexproof")


def test_hasnt_dealt_damage_survives_a_new_turn_but_not_leaving_the_battlefield():
    scenario = Scenario().player("alice", battlefield=["Karakyk Guardian"]).player("bob").build()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    guardian = scenario.creature("Karakyk Guardian", "alice")
    scenario.attack_with(guardian, defending="bob")
    scenario.no_blocks()
    scenario.combat_damage()
    assert guardian.has_dealt_damage is True
    scenario.game.return_to_hand(guardian)
    assert guardian.has_dealt_damage is False


# -- Futurist Operative ------------------------------------------------------


def test_futurist_operative_is_a_one_one_unblockable_human_citizen_while_tapped():
    scenario = Scenario().player("alice", battlefield=["Futurist Operative"]).player("bob").build()
    operative = scenario.creature("Futurist Operative", "alice")
    untapped = scenario.game.characteristics_of(operative)
    assert "Human" not in untapped.subtypes or "Citizen" not in untapped.subtypes
    operative.tapped = True
    tapped = scenario.game.characteristics_of(operative)
    assert tapped.subtypes == ("Human", "Citizen")
    assert (scenario.game.power_of(operative), scenario.game.toughness_of(operative)) == (1, 1)


def test_futurist_operative_attacking_taps_it_and_so_it_cannot_be_blocked():
    refusal = _block("Futurist Operative", ["Hill Giant"])
    assert refusal is not None and "can't be blocked" in refusal


# -- defender overridden by a counter ---------------------------------------


@pytest.mark.parametrize("name", ["Skyclave Sentinel", "Scuttlegator"])
def test_a_defender_with_a_plus_one_counter_can_attack(name):
    scenario = Scenario().player("alice", battlefield=[name]).player("bob").build()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    creature = scenario.creature(name, "alice")
    assert scenario.can_attack(creature) is False
    creature.add_counters(Counter.PLUS_ONE, 1)
    assert scenario.can_attack(creature) is True
    scenario.attack_with(creature, defending="bob")
    assert scenario.attackers() == [creature]


@pytest.mark.parametrize("name", ["Skyclave Sentinel", "Scuttlegator"])
def test_a_different_counter_kind_does_not_lift_defender(name):
    scenario = Scenario().player("alice", battlefield=[name]).player("bob").build()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    creature = scenario.creature(name, "alice")
    creature.add_counters(Counter.MINUS_ONE, 1)
    assert scenario.can_attack(creature) is False


# -- "target creature blocks it this combat if able" -------------------------


def _forced_block(attacker: str, *, extra=(), hand_class_level=False):
    scenario = (
        Scenario()
        .player("alice", battlefield=[attacker, *extra])
        .player("bob", battlefield=["Hill Giant", "Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    return scenario


@pytest.mark.parametrize("name", ["Avalanche Tusker", "Impetuous Devils"])
def test_the_attack_trigger_forces_the_chosen_creature_to_block_it(name):
    scenario = _forced_block(name)
    attacker = scenario.creature(name, "alice")
    giant = scenario.creature("Hill Giant", "bob")
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.will_choose_targets(giant)
    scenario.attack_with(attacker, defending="bob")
    scenario.pass_until_resolved()
    with pytest.raises(ValueError, match=r"CR 509\.1c"):
        scenario.no_blocks()
    scenario.block(attacker, giant)
    assert scenario.blockers() == [giant]
    assert bears.id not in [blocker.id for blocker in scenario.blockers()]


@pytest.mark.parametrize("name", ["Avalanche Tusker", "Impetuous Devils"])
def test_the_forced_creature_may_block_something_else_if_it_cannot_block_it(name):
    scenario = _forced_block(name, extra=["Grizzly Bears"])
    attacker = scenario.creature(name, "alice")
    giant = scenario.creature("Hill Giant", "bob")
    scenario.will_choose_targets(giant)
    scenario.attack_with(attacker, scenario.creature("Grizzly Bears", "alice"), defending="bob")
    scenario.pass_until_resolved()
    with pytest.raises(ValueError, match=r"CR 509\.1c"):
        scenario.block(scenario.creature("Grizzly Bears", "alice"), giant)


def test_fighter_class_level_three_makes_the_chosen_creature_block_the_attacker():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Fighter Class", "Grizzly Bears"])
        .player("bob", battlefield=["Hill Giant", "Runeclaw Bear"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.find("Fighter Class", Zone.BATTLEFIELD, "alice").class_level = 3
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "bob")
    scenario.will_choose_targets(giant)
    scenario.attack_with(bears, defending="bob")
    scenario.pass_until_resolved()
    with pytest.raises(ValueError, match=r"CR 509\.1c"):
        scenario.no_blocks()
    scenario.block(bears, giant)
    assert scenario.blockers() == [giant]


# -- planeswalker attack cap -------------------------------------------------


def test_the_eternal_wanderer_can_be_attacked_by_only_one_creature():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Grizzly Bears", "Hill Giant"])
        .player("bob", battlefield=["The Eternal Wanderer"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    wanderer = scenario.find("The Eternal Wanderer", Zone.BATTLEFIELD, "bob")
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "alice")
    with pytest.raises(ValueError, match="CR 508.1c"):
        scenario.game.declare_attackers([(bears, wanderer), (giant, wanderer)])
    scenario.game.declare_attackers([(bears, wanderer), (giant, "bob")])


# -- "<N> target creatures you control that share a creature type can't be
#    blocked this turn" (Secret Tunnel) -------------------------------------


def _tunnel(*mine):
    scenario = (
        Scenario()
        .player(
            "alice", battlefield=["Secret Tunnel", *mine, "Island", "Island", "Island", "Island"]
        )
        .player("bob", battlefield=["Hill Giant"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _activate_tunnel(scenario, *targets):
    tunnel = scenario.find("Secret Tunnel", Zone.BATTLEFIELD, "alice")
    scenario.activate(
        tunnel,
        *scenario.untapped_sources("Island", "Island", "Island", "Island"),
        index=1,
        targets=list(targets),
    )
    scenario.pass_until_resolved()


def test_secret_tunnel_makes_two_creatures_that_share_a_type_unblockable():
    scenario = _tunnel("Grizzly Bears", "Runeclaw Bear")
    bears = scenario.creature("Grizzly Bears", "alice")
    runeclaw = scenario.creature("Runeclaw Bear", "alice")
    _activate_tunnel(scenario, bears, runeclaw)
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(bears, runeclaw, defending="bob")
    with pytest.raises(ValueError, match="CR 509.1b"):
        scenario.block(bears, scenario.creature("Hill Giant", "bob"))
    with pytest.raises(ValueError, match="CR 509.1b"):
        scenario.block(runeclaw, scenario.creature("Hill Giant", "bob"))


def test_secret_tunnel_refuses_two_creatures_that_share_no_type():
    scenario = _tunnel("Grizzly Bears", "Serra Angel")
    with pytest.raises(ValueError, match="share a creature type"):
        _activate_tunnel(
            scenario,
            scenario.creature("Grizzly Bears", "alice"),
            scenario.creature("Serra Angel", "alice"),
        )


def test_secret_tunnel_leaves_a_third_creature_blockable():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[
                "Secret Tunnel",
                "Grizzly Bears",
                "Runeclaw Bear",
                "Goblin Guide",
                "Island",
                "Island",
                "Island",
                "Island",
            ],
        )
        .player("bob", battlefield=["Hill Giant"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    runeclaw = scenario.creature("Runeclaw Bear", "alice")
    guide = scenario.creature("Goblin Guide", "alice")
    _activate_tunnel(scenario, bears, runeclaw)
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(bears, guide, defending="bob")
    scenario.block(guide, scenario.creature("Hill Giant", "bob"))


# -- Glorfindel's mode: "can't be blocked by more than one creature each combat
#    this turn" ------------------------------------------------------------


def _resolve_glorfindel_mode(scenario, text):
    """Resolve one bullet of Glorfindel's "Whenever you scry, choose one"
    trigger as the engine's effect parser reads it (the scry trigger event
    itself is another family's)."""
    from magic_cards_model.machines.abilities import AbilityKind, parse_abilities
    from magic_cards_model.machines.effects import _ability_effect_or_notice
    from magic_cards_model.machines.triggers import AbilityOnStack

    glorfindel = scenario.creature("Glorfindel, Dauntless Rescuer", "alice")
    (trigger,) = [
        ability
        for ability in parse_abilities(glorfindel.card)
        if ability.kind is AbilityKind.TRIGGERED
    ]
    effect = _ability_effect_or_notice(text)
    assert effect is not None
    with scenario.game._id_allocator_scope():
        effect(
            scenario.game,
            AbilityOnStack(
                kind=AbilityKind.TRIGGERED,
                ability=trigger,
                source_id=glorfindel.id,
                source_name=glorfindel.name,
                controller="alice",
            ),
        )
    return glorfindel


def _glorfindel_blocked(modes, blockers):
    scenario = (
        Scenario()
        .player("alice", battlefield=["Glorfindel, Dauntless Rescuer"])
        .player("bob", battlefield=blockers)
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    for text in modes:
        glorfindel = _resolve_glorfindel_mode(scenario, text)
    glorfindel = scenario.creature("Glorfindel, Dauntless Rescuer", "alice")
    scenario.attack_with(glorfindel, defending="bob")
    try:
        scenario.block(glorfindel, *[scenario.creature(name, "bob") for name in blockers])
    except ValueError as error:
        return str(error)
    return None


AT_MOST_ONE = "This creature can't be blocked by more than one creature each combat this turn."


def test_glorfindel_mode_forbids_a_second_blocker_this_turn():
    refusal = _glorfindel_blocked([AT_MOST_ONE], ["Hill Giant", "Grizzly Bears"])
    assert refusal is not None and "more than one creature" in refusal and "CR 509.1b" in refusal


def test_glorfindel_mode_allows_a_single_blocker():
    assert _glorfindel_blocked([AT_MOST_ONE], ["Hill Giant"]) is None


def test_without_the_mode_glorfindel_can_be_double_blocked():
    assert _glorfindel_blocked([], ["Hill Giant", "Grizzly Bears"]) is None
