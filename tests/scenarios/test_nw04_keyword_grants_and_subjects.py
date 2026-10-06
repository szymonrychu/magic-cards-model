"""Scenario: until-end-of-turn grants whose subject or keyword the layer reader
did not read - a subtype-qualified group, toxic N, a target phrase with a
qualifier after its noun, a counted target that can't be blocked, and an
anaphoric grant printed duration-first after a control change.

Reported cards (NW-04 T2): Vampiric Fury ("Vampire creatures you control get
+2/+0 and gain first strike until end of turn."), Aspirant's Ascent ("gains
flying and toxic 1"), Executioner's Swing ("Target creature that dealt damage
this turn gets -5/-5 until end of turn."), Open into Wonder ("X target
creatures can't be blocked this turn. Until end of turn, those creatures gain
"..."") and Furnace Reins ("... Untap that creature. Until end of turn, it
gains haste and "..."").

Second printings (legal in Modern, Pioneer or Standard, in no deck under
`magic-cards-model-api/decks/`): Ezuri, Renegade Leader (an Elf group from an
activated ability), Plague Nurse ("Each other creature you control with toxic
gains toxic 1 until end of turn."), Spire Mangler and Slimy Dualleech (target
phrases "you control with flying" / "with power 2 or less" from triggers),
Ghostform ("Up to two target creatures can't be blocked this turn.") and
Shackles of Treachery (the same control-change chain, a different quote).

Every CR number below was looked up with `mise run rules:find`:

- **CR 205.3m** - creature types; **CR 611.2c** - the group is fixed as the
  effect begins.
- **CR 702.7b** - first strike deals combat damage in its own step.
- **CR 702.164a/b/c** - toxic: combat damage to a player also gives poison
  counters equal to the creature's total toxic value, the sum of all its toxic
  instances.
- **CR 601.2c** - targets are chosen as the spell is cast; a creature that
  dealt no damage this turn is not a legal target for Executioner's Swing.
- **CR 509.1b** - a creature that can't be blocked can't be declared blocked.
- **CR 608.2c** - "those creatures"/"it" are what the earlier instruction named.
- **CR 613.1b** - control-changing effects (layer 2); **CR 302.6** - haste
  lets a creature that just came under its controller's control attack.
- **CR 603.3a** - a triggered ability's controller is the controller of its
  source when it triggered, so the Treasure goes to the stealing player.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import Keyword, has_keyword
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from magic_cards_model.support import HANDLED, classify_clauses
from tests.cards import card
from tests.scenarios.harness import Scenario


def computed(scenario):
    return scenario.game.continuous_effects.board(scenario.game.battlefield)


def notices(scenario) -> list[object]:
    game = scenario.game
    found: list[object] = list(game.continuous_effects.layer_notices)
    for name in type(game).model_fields:
        if name.endswith("_notices"):
            found.extend(getattr(game, name))
    return found


def _resolve_stack(scenario) -> None:
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()


def _board(*, hand=(), alice=(), bob=("Runeclaw Bear",), lands=()):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=list(hand),
            battlefield=[*alice, *lands],
            library=["Forest"] * 10,
        )
        .player("bob", battlefield=list(bob), library=["Forest"] * 10)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    for permanent in scenario.game.battlefield:
        permanent.summoning_sick = False
    return scenario


def _attack_unblocked(scenario, *attackers) -> None:
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(*attackers)
    _resolve_stack(scenario)
    scenario.start_at(Step.DECLARE_BLOCKERS)
    scenario.no_blocks()
    scenario.combat_damage()
    _resolve_triggers(scenario)


def _resolve_triggers(scenario) -> None:
    """Put any pending trigger on the stack and resolve it, without passing
    into the next step when there is none."""
    if scenario.game.pending_triggers or not scenario.game.stack_is_empty:
        scenario.pass_until_resolved()
    _resolve_stack(scenario)


@pytest.mark.parametrize(
    "name",
    [
        "Vampiric Fury",
        "Aspirant's Ascent",
        "Executioner's Swing",
        "Open into Wonder",
        "Furnace Reins",
        "Ezuri, Renegade Leader",
        "Plague Nurse",
        "Spire Mangler",
        "Slimy Dualleech",
        "Ghostform",
        "Shackles of Treachery",
    ],
)
def test_every_card_is_handled(name: str) -> None:
    clauses = [c for c in classify_clauses(card(name)) if c.text]
    assert {c.category for c in clauses} == {HANDLED}, [(c.category, c.text) for c in clauses]


# -- "<Subtype> creatures you control" -----------------------------------------


def test_vampiric_fury_pumps_only_vampires() -> None:
    scenario = _board(
        hand=["Vampiric Fury"],
        alice=["Vampire Nighthawk", "Bloodghast", "Grizzly Bears"],
        lands=["Mountain", "Mountain"],
    )
    scenario.cast_and_resolve("Vampiric Fury", auto=True)
    nighthawk = scenario.creature("Vampire Nighthawk")
    bloodghast = scenario.creature("Bloodghast")
    bears = scenario.creature("Grizzly Bears")

    board = computed(scenario)
    assert board.of(nighthawk).power == 4
    assert board.of(bloodghast).power == 4
    assert board.of(bears).power == 2, "CR 205.3m: a Bear is no Vampire"
    assert has_keyword(nighthawk, Keyword.FIRST_STRIKE, scenario.game)
    assert has_keyword(bloodghast, Keyword.FIRST_STRIKE, scenario.game)
    assert not has_keyword(bears, Keyword.FIRST_STRIKE, scenario.game)
    assert notices(scenario) == []


def test_a_vampire_entering_after_the_fury_is_not_pumped() -> None:
    """CR 611.2c."""
    scenario = _board(
        hand=["Vampiric Fury", "Bloodghast"],
        alice=["Vampire Nighthawk"],
        lands=["Mountain", "Mountain"],
    )
    scenario.cast_and_resolve("Vampiric Fury", auto=True)
    bloodghast = scenario.put_onto_battlefield("Bloodghast", "alice")

    assert computed(scenario).of(bloodghast).power == 2
    assert not has_keyword(bloodghast, Keyword.FIRST_STRIKE, scenario.game)


def test_an_opponents_vampire_is_not_pumped() -> None:
    scenario = _board(
        hand=["Vampiric Fury"],
        alice=["Vampire Nighthawk"],
        bob=["Bloodghast"],
        lands=["Mountain", "Mountain"],
    )
    scenario.cast_and_resolve("Vampiric Fury", auto=True)
    bobs = scenario.creature("Bloodghast", "bob")

    assert computed(scenario).of(bobs).power == 2


def test_first_strike_kills_a_blocker_before_it_strikes_back() -> None:
    """CR 702.7b."""
    scenario = _board(
        hand=["Vampiric Fury"],
        alice=["Bloodghast"],
        bob=["Runeclaw Bear"],
        lands=["Mountain", "Mountain"],
    )
    bloodghast = scenario.creature("Bloodghast")
    runeclaw = scenario.creature("Runeclaw Bear", "bob")
    scenario.cast_and_resolve("Vampiric Fury", auto=True)

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(bloodghast)
    _resolve_stack(scenario)
    scenario.start_at(Step.DECLARE_BLOCKERS)
    scenario.block(bloodghast, runeclaw)
    scenario.combat_damage()
    scenario.state_based_actions()
    scenario.combat_damage()
    scenario.state_based_actions()

    assert runeclaw.zone is Zone.GRAVEYARD
    assert bloodghast.zone is Zone.BATTLEFIELD


def test_ezuri_pumps_every_elf_you_control() -> None:
    scenario = _board(
        alice=["Ezuri, Renegade Leader", "Llanowar Elves", "Grizzly Bears"],
        lands=["Forest"] * 5,
    )
    ezuri = scenario.creature("Ezuri, Renegade Leader")
    elves = scenario.creature("Llanowar Elves")
    bears = scenario.creature("Grizzly Bears")
    index = next(
        i
        for i, ability in enumerate(scenario.game.activated_abilities(ezuri))
        if "Elf creatures" in ability.effect
    )

    scenario.activate(ezuri, *scenario.untapped_sources(*["Forest"] * 5), index=index)
    _resolve_stack(scenario)

    board = computed(scenario)
    assert (board.of(elves).power, board.of(elves).toughness) == (4, 4)
    assert (board.of(ezuri).power, board.of(ezuri).toughness) == (5, 5), "Ezuri is an Elf"
    assert (board.of(bears).power, board.of(bears).toughness) == (2, 2)
    assert has_keyword(elves, Keyword.TRAMPLE, scenario.game)
    assert not has_keyword(bears, Keyword.TRAMPLE, scenario.game)
    assert notices(scenario) == []


# -- toxic N ---------------------------------------------------------------------


def test_aspirants_ascent_gives_flying_and_a_poison_counter_on_damage() -> None:
    scenario = _board(hand=["Aspirant's Ascent"], alice=["Grizzly Bears"], lands=["Island"])
    bears = scenario.creature("Grizzly Bears")
    scenario.cast_and_resolve("Aspirant's Ascent", auto=True, targets=[bears])

    board = computed(scenario).of(bears)
    assert (board.power, board.toughness) == (3, 5)
    assert has_keyword(bears, Keyword.FLYING, scenario.game)
    assert notices(scenario) == []

    _attack_unblocked(scenario, bears)

    assert scenario.player("bob").life == 17
    assert scenario.player("bob").counters[Counter.POISON] == 1


def test_granted_toxic_adds_to_printed_toxic() -> None:
    """CR 702.164c: the total toxic value sums every instance."""
    scenario = _board(hand=["Aspirant's Ascent"], alice=["Plague Nurse"], lands=["Island"])
    nurse = scenario.creature("Plague Nurse")
    scenario.cast_and_resolve("Aspirant's Ascent", auto=True, targets=[nurse])

    _attack_unblocked(scenario, nurse)

    assert scenario.player("bob").counters[Counter.POISON] == 3


def test_granted_toxic_ends_in_the_cleanup_step() -> None:
    scenario = _board(hand=["Aspirant's Ascent"], alice=["Grizzly Bears"], lands=["Island"])
    bears = scenario.creature("Grizzly Bears")
    scenario.cast_and_resolve("Aspirant's Ascent", auto=True, targets=[bears])

    scenario.start_at(Step.END_STEP)
    scenario.advance()  # cleanup

    assert not has_keyword(bears, Keyword.FLYING, scenario.game)
    assert computed(scenario).of(bears).toughness == 2


def test_plague_nurse_grants_toxic_only_to_other_toxic_creatures() -> None:
    scenario = _board(
        hand=["Plague Nurse"],
        alice=["Plague Nurse", "Grizzly Bears"],
        lands=["Forest"] * 3,
    )
    nurse = scenario.creature("Plague Nurse")
    bears = scenario.creature("Grizzly Bears")
    second = scenario.put_onto_battlefield("Plague Nurse", "alice")
    second.summoning_sick = False

    scenario.activate(nurse, *scenario.untapped_sources(*["Forest"] * 3))
    _resolve_stack(scenario)
    assert notices(scenario) == []

    _attack_unblocked(scenario, second, bears)

    # The second Nurse: printed toxic 2 + granted toxic 1. The Bears had no
    # toxic, so it gained none. The activating Nurse is not "other".
    assert scenario.player("bob").counters[Counter.POISON] == 3


# -- a target phrase with a qualifier after its noun ----------------------------


def test_executioners_swing_kills_a_creature_that_dealt_damage() -> None:
    scenario = _board(
        hand=["Executioner's Swing"],
        alice=["Grizzly Bears"],
        lands=["Plains", "Swamp"],
    )
    bears = scenario.creature("Grizzly Bears")
    _attack_unblocked(scenario, bears)
    scenario.start_at(Step.POSTCOMBAT_MAIN)

    scenario.cast_and_resolve("Executioner's Swing", auto=True, targets=[bears])
    scenario.state_based_actions()

    assert bears.zone is Zone.GRAVEYARD
    assert notices(scenario) == []


@pytest.mark.xfail(
    strict=True,
    reason="machines/targeting.py does not yet enforce the active 'that dealt damage this "
    "turn' restriction (only the passive 'that was dealt damage'); NW-04 T1 owns targeting.py",
)
def test_executioners_swing_cannot_target_a_creature_that_dealt_no_damage() -> None:
    """CR 601.2c."""
    scenario = _board(
        hand=["Executioner's Swing"],
        alice=["Grizzly Bears"],
        lands=["Plains", "Swamp"],
    )
    runeclaw = scenario.creature("Runeclaw Bear", "bob")

    with pytest.raises(ValueError):
        scenario.cast("Executioner's Swing", targets=[runeclaw])


def test_spire_mangler_pumps_a_flier_you_control() -> None:
    scenario = _board(alice=["Vampire Nighthawk"], hand=["Spire Mangler"], lands=["Swamp"] * 3)
    nighthawk = scenario.creature("Vampire Nighthawk")
    scenario.cast_and_resolve("Spire Mangler", auto=True)
    scenario.choose_trigger_targets("Spire Mangler", [nighthawk])
    _resolve_stack(scenario)

    assert computed(scenario).of(nighthawk).power == 4
    assert notices(scenario) == []


def test_slimy_dualleech_pumps_and_grants_deathtouch_at_beginning_of_combat() -> None:
    scenario = _board(alice=["Slimy Dualleech", "Llanowar Elves"])
    elves = scenario.creature("Llanowar Elves")

    scenario.will_choose_targets(elves)
    scenario.advance()  # beginning of combat: the trigger goes on the stack
    _resolve_stack(scenario)

    assert computed(scenario).of(elves).power == 2
    assert has_keyword(elves, Keyword.DEATHTOUCH, scenario.game)
    assert notices(scenario) == []


# -- a counted target that can't be blocked -------------------------------------


def _cast_open_into_wonder(scenario, targets):
    x = len(targets)
    casting = scenario.cast("Open into Wonder")
    casting.choose_modes([], x_value=x)
    casting.choose_targets(list(targets))
    casting.determine_cost(x_value=x)
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources(*["Island"] * (x + 2)))
    scenario.put_on_stack(casting)
    scenario.resolve_top()


def test_open_into_wonder_makes_each_target_unblockable_and_a_card_drawer() -> None:
    scenario = _board(
        hand=["Open into Wonder"],
        alice=["Grizzly Bears", "Savannah Lions", "Llanowar Elves"],
        lands=["Island"] * 4,
    )
    bears = scenario.creature("Grizzly Bears")
    lions = scenario.creature("Savannah Lions")
    elves = scenario.creature("Llanowar Elves")
    runeclaw = scenario.creature("Runeclaw Bear", "bob")
    _cast_open_into_wonder(scenario, [bears, lions])
    assert notices(scenario) == []
    hand_before = len(scenario.player().hand)

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(bears, lions, elves)
    _resolve_stack(scenario)
    scenario.start_at(Step.DECLARE_BLOCKERS)
    with pytest.raises(ValueError):
        scenario.block(bears, runeclaw)  # CR 509.1b
    scenario.block(elves, runeclaw)
    scenario.combat_damage()
    _resolve_triggers(scenario)

    assert scenario.player("bob").life == 16
    assert len(scenario.player().hand) == hand_before + 2, "only the two targets draw"


def test_the_open_into_wonder_grant_ends_at_cleanup() -> None:
    scenario = _board(hand=["Open into Wonder"], alice=["Grizzly Bears"], lands=["Island"] * 3)
    bears = scenario.creature("Grizzly Bears")
    _cast_open_into_wonder(scenario, [bears])

    scenario.start_at(Step.END_STEP)
    scenario.advance()  # cleanup

    assert (
        not computed(scenario)
        .of(bears)
        .has_ability("Whenever this creature deals combat damage to a player, draw a card.")
    )


def test_ghostform_makes_up_to_two_targets_unblockable() -> None:
    scenario = _board(
        hand=["Ghostform"], alice=["Grizzly Bears", "Savannah Lions"], lands=["Island"] * 2
    )
    bears = scenario.creature("Grizzly Bears")
    lions = scenario.creature("Savannah Lions")
    runeclaw = scenario.creature("Runeclaw Bear", "bob")
    scenario.cast_and_resolve("Ghostform", auto=True, targets=[bears, lions])
    assert notices(scenario) == []

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(bears, lions)
    _resolve_stack(scenario)
    scenario.start_at(Step.DECLARE_BLOCKERS)
    for attacker in (bears, lions):
        with pytest.raises(ValueError):
            scenario.block(attacker, runeclaw)


def test_ghostform_with_a_single_target() -> None:
    scenario = _board(
        hand=["Ghostform"], alice=["Grizzly Bears", "Savannah Lions"], lands=["Island"] * 2
    )
    bears = scenario.creature("Grizzly Bears")
    lions = scenario.creature("Savannah Lions")
    runeclaw = scenario.creature("Runeclaw Bear", "bob")
    scenario.cast_and_resolve("Ghostform", auto=True, targets=[bears])

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(bears, lions)
    _resolve_stack(scenario)
    scenario.start_at(Step.DECLARE_BLOCKERS)
    scenario.block(lions, runeclaw)  # the untargeted Lions can still be blocked
    with pytest.raises(ValueError):
        scenario.block(bears, runeclaw)


# -- a control change, an untap, then "Until end of turn, it gains ..." ---------


def _steal(spell, *, bob=("Grizzly Bears",)):
    scenario = _board(hand=[spell], bob=list(bob), lands=["Mountain"] * 3)
    stolen = scenario.creature(bob[0], "bob")
    stolen.tap()
    scenario.cast_and_resolve(spell, auto=True, targets=[stolen])
    return scenario, stolen


def test_furnace_reins_steals_untaps_and_hastes() -> None:
    scenario, bears = _steal("Furnace Reins")

    assert bears.controller == "alice"
    assert not bears.tapped
    assert has_keyword(bears, Keyword.HASTE, scenario.game)
    assert (
        computed(scenario)
        .of(bears)
        .has_ability(
            "Whenever this creature deals combat damage to a player or battle, create a Treasure "
            "token."
        )
    )
    assert notices(scenario) == []


def test_the_stolen_creature_makes_its_new_controller_a_treasure() -> None:
    """CR 603.3a: the trigger is controlled by the creature's controller."""
    scenario, bears = _steal("Furnace Reins")

    _attack_unblocked(scenario, bears)

    assert scenario.player("bob").life == 18
    treasures = [p for p in scenario.game.battlefield if p.name.startswith("Treasure")]
    assert [t.controller for t in treasures] == ["alice"]


def test_the_stolen_creature_returns_at_end_of_turn() -> None:
    scenario, bears = _steal("Furnace Reins")

    scenario.start_at(Step.END_STEP)
    scenario.advance()  # cleanup

    assert bears.controller == "bob"
    assert not has_keyword(bears, Keyword.HASTE, scenario.game)


def test_shackles_of_treachery_grants_its_own_quote() -> None:
    scenario, bears = _steal("Shackles of Treachery")

    assert bears.controller == "alice"
    assert has_keyword(bears, Keyword.HASTE, scenario.game)
    assert (
        computed(scenario)
        .of(bears)
        .has_ability(
            "Whenever this creature deals damage, destroy target Equipment attached to it."
        )
    )
    assert notices(scenario) == []
