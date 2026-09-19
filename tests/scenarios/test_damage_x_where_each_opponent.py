"""Untargeted "deals X damage to each ..." reads a trailing ", where X is
<expr>" (CR 608.2h), the same way a fixed printed number already does -
Cavalier of Flame's own death trigger: "it deals X damage to each opponent
and each planeswalker they control, where X is the number of land cards in
your graveyard."

Every CR number below was read in full from `.rules/MagicCompRules.txt` with
`mise run rules:find` in the session that wrote this file.

- **CR 608.2h** - "If an effect requires information from the game ..., the
  answer is determined only once, when the effect is applied. If the effect
  requires information from a specific object, including the source of the
  ability itself, the effect uses the current information of that object if
  it's in the public zone it was expected to be in; if it's no longer in that
  zone, ... the effect uses the object's last known information." This is why
  the magnitude is read once, at resolution, and why the source - already in
  the graveyard by the time this trigger resolves - is still found and named.
- **CR 113.7a** - the source of a triggered ability can be gone by the time it
  resolves; the ability still checks its information (here, nothing about the
  source itself - the graveyard it counts is its controller's), and the
  source can still perform the action ("it deals ... damage") even though it
  no longer exists on the battlefield.
- **CR 119.2** - "Damage dealt to a player normally causes that player to
  lose that much life."
- **CR 120.3a** - "Damage dealt to a player by a source without infect causes
  that player to lose that much life."
- **CR 120.3c** - "Damage dealt to a planeswalker causes that many loyalty
  counters to be removed from that planeswalker."
- **CR 102.2** - "each opponent" is every other player in the game, not a
  single chosen one - the reason two opponents are used below, one with a
  planeswalker and one without, rather than just one.
- **CR 107.2** - "If anything needs to use a number that can't be determined
  ..., it uses 0 instead" - an empty graveyard of lands is X = 0, not an
  error.
- **CR 205.2a** - the fifteen card types, land among them, which is what
  "land cards in your graveyard" counts and a nonland card never is.

`docs/engine-coverage.md`'s effect-registry gap survey has nothing to say
about this specific shape; it closes with this file and
`machines/effects.py`'s `_DAMAGE_EACH_FILTERED_RE`/`_DAMAGE_EACH_OPPONENT_RE`/
`_DAMAGE_EACH_CREATURE_RE`, extended to read the literal word "X" plus its own
"where X is <expr>" definition the same general way the fixed-number shape
already read.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

CAVALIER = "Cavalier of Flame"


def _cavalier_scenario(*, alice_graveyard: list[str]) -> Scenario:
    """Alice's Cavalier of Flame and her own planeswalker, against two
    opponents - bob with a planeswalker of his own, carol with none - so
    "each opponent" is genuinely exercised against more than one player and
    the "and each planeswalker they control" filter is proven against both a
    controller who has one and one who does not.
    """
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=[CAVALIER, "Karn, the Great Creator"],
            graveyard=alice_graveyard,
        )
        .player(
            "bob",
            hand=["Murderous Rider"],
            battlefield=["Kaito, Bane of Nightmares", "Swamp", "Swamp", "Swamp"],
        )
        .player("carol")
        .build()
    )


def _kill_cavalier_with_swift_end(scenario) -> None:
    """Bob casts Murderous Rider's adventure half, Swift End - "Destroy target
    creature or planeswalker. You lose 2 life." - a real, unconditional
    destroy spell, at Cavalier of Flame. Once it resolves the death trigger is
    a pending ability (CR 603.3), put on the stack and resolved by hand.
    """
    scenario.start_at(Step.UPKEEP)
    cavalier = scenario.creature(CAVALIER, "alice")

    scenario.pass_priority("alice")  # CR 117.3d's APNAP order: alice, then bob

    casting = scenario.cast("Murderous Rider", username="bob")
    casting.cast_as_adventure()
    casting.choose_targets([cavalier])
    scenario.pay_with(
        casting.begin_paying(),
        *scenario.untapped_sources("Swamp", "Swamp", "Swamp", username="bob"),
    )
    scenario.put_on_stack(casting)
    scenario.resolve_top()  # Swift End: destroy, bob loses 2 life

    assert cavalier.zone is Zone.GRAVEYARD, "Swift End's own destroy"
    assert scenario.player("bob").life == 18, "Swift End's own rider (CR 119.3)"

    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()


def test_cavalier_of_flame_deals_damage_equal_to_lands_in_graveyard():
    """Three land cards in alice's graveyard: X = 3. Bob (with a planeswalker)
    and carol (without one) each lose 3 life; Kaito loses 3 loyalty. Alice and
    her own Karn, the Great Creator are untouched - CR 102.2's "opponent"
    never includes the ability's own controller.
    """
    scenario = _cavalier_scenario(alice_graveyard=["Mountain", "Forest", "Island"])
    karn = scenario.find("Karn, the Great Creator", Zone.BATTLEFIELD, "alice")
    kaito = scenario.find("Kaito, Bane of Nightmares", Zone.BATTLEFIELD, "bob")
    assert kaito.loyalty == 4, "Kaito, Bane of Nightmares' own printed loyalty"

    _kill_cavalier_with_swift_end(scenario)

    assert scenario.player("bob").life == 15, "18 minus 3 (CR 120.3a)"
    assert scenario.player("carol").life == 17, "20 minus 3 - CR 102.2's plural 'each opponent'"
    assert scenario.player("alice").life == 20, "never her own controller"
    assert kaito.loyalty == 1, "4 minus 3 (CR 120.3c)"
    assert karn.loyalty == 5, "alice's own planeswalker, untouched"


def test_zero_lands_in_the_graveyard_deals_zero_damage():
    """CR 107.2: an empty count is X = 0, and 0 damage is dealt (nothing
    marked, nothing lost) rather than the trigger being refused or erroring.
    """
    scenario = _cavalier_scenario(alice_graveyard=[])
    kaito = scenario.find("Kaito, Bane of Nightmares", Zone.BATTLEFIELD, "bob")

    _kill_cavalier_with_swift_end(scenario)

    assert scenario.player("bob").life == 18, "unchanged by 0 damage, only Swift End's own rider"
    assert scenario.player("carol").life == 20
    assert kaito.loyalty == 4, "unchanged: 0 loyalty removed"


def test_only_land_cards_in_the_graveyard_count():
    """CR 205.2a: "land" is one specific card type. A nonland card sitting in
    the same graveyard as the lands does not add to X - one land and one
    instant is X = 1, not 2.
    """
    scenario = _cavalier_scenario(alice_graveyard=["Mountain", "Lightning Bolt"])
    kaito = scenario.find("Kaito, Bane of Nightmares", Zone.BATTLEFIELD, "bob")

    _kill_cavalier_with_swift_end(scenario)

    assert scenario.player("bob").life == 17, "18 minus 1 - the Bolt in the yard never counted"
    assert kaito.loyalty == 3, "4 minus 1"


# -- generality: two different real printings, neither Cavalier of Flame ---


def test_chandra_legacy_of_fire_deals_x_damage_where_x_is_planeswalkers_controlled():
    """Chandra, Legacy of Fire: "At the beginning of your end step, Chandra
    deals X damage to each opponent, where X is the number of planeswalkers
    you control." A different card, a different trigger condition (a step
    trigger, not a death trigger), a different count expression ("planeswalkers
    you control", `_COUNT_YOU_CONTROL_RE`'s branch of `count_expression`
    rather than the graveyard branch), and the plain `_DAMAGE_EACH_OPPONENT_RE`
    shape with no "and each ... they control" filter at all.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Chandra, Legacy of Fire", "Karn, the Great Creator"])
        .player("bob")
        .build()
    )
    assert scenario.turn.active_player == "alice"
    # CR 500.6/603.3: a "beginning of" trigger fires as the turn machine
    # actually steps into that step, which `Game.advance` runs and
    # `Scenario.start_at`'s own raw pointer jump does not - so this walks
    # every step in order rather than jumping straight to `Step.END_STEP`.
    while scenario.step != Step.END_STEP:
        scenario.advance()

    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert scenario.player("bob").life == 18, "20 minus 2 - X = 2 planeswalkers alice controls"
    assert scenario.player("alice").life == 20, "never her own controller"


def test_gates_ablaze_deals_x_damage_to_each_creature_where_x_is_gates_controlled():
    """Gates Ablaze: "Gates Ablaze deals X damage to each creature, where X
    is the number of Gates you control." A spell rather than an ability
    (`damage_each_creature_spell`, `for_spell=True`), a subtype count
    (`_COUNT_YOU_CONTROL_RE`'s subtype branch, "Gates" -> CR 205.3m) rather
    than a card-type count, and the `_DAMAGE_EACH_CREATURE_RE` shape rather
    than `_DAMAGE_EACH_OPPONENT_RE` or the filtered one.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Gates Ablaze"],
            battlefield=["Azorius Guildgate", "Azorius Guildgate", "Mountain"],
        )
        .player("bob", battlefield=["Craw Wurm"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    wurm = scenario.creature("Craw Wurm", "bob")

    scenario.cast_and_resolve("Gates Ablaze", auto=True)

    assert wurm.damage == 2, "X = 2 Gates alice controls (CR 120.3e: marked, 6/4 survives)"
