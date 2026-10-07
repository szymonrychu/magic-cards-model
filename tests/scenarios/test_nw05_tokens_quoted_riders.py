"""NW-05 T3: token sentences carrying a quoted ability, toxic N, a "tapped and
attacking" entry, an "and"-joined keyword list or an anaphoric rider.

Listed cards: Burn Down the House (mode 2), Charge of the Mites (mode 2),
Maestros Diabolist, Purphoros's Intervention (mode 1). Proof printings on the
same templates: Pugnacious Pugilist (the quoted Devil, NW05-T6's card),
Basilica Shepherd and Stinging Hivemaster (toxic 1 and a quoted ability),
Hungry for More ("trample, lifelink, and haste. Sacrifice it at the beginning of
the next end step."), Shock Brigade (mobilize, the existing tapped-and-attacking path).

Rules, each looked up with `mise run rules:find`:

- CR 111.3 / CR 111.4: the creating effect defines the token's characteristics
  and abilities, so a quoted ability is the token's own text.
- CR 702.164a / CR 120.3g: toxic N - combat damage to a player also gives
  that many poison counters.
- CR 608.2c: "They gain haste" and "Sacrifice it" name exactly the tokens the
  earlier sentence of the same instruction created.
- CR 603.7a: "Sacrifice it at the beginning of the next end step" is a delayed
  triggered ability about that one token.
- CR 508.4: a token put onto the battlefield tapped and attacking is attacking
  but, for trigger events and effects, never "attacked", so no attack trigger
  fires.
- CR 603.4: an intervening "if" is checked on trigger and on resolution.
- CR 107.3a: X is the announced value, read from the cast record.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import Keyword, has_keyword, total_toxic_value
from magic_cards_model.machines.effects import parse_mixed_effect
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Type
from magic_cards_model.models.token import TokenDefinition, create_tokens
from magic_cards_model.support import card_support
from tests.cards import card
from tests.scenarios.harness import Scenario


def _tokens(scenario, subtype, username="alice"):
    return [
        state
        for state in scenario.game.permanents_controlled_by(username)
        if state.token and subtype in state.subtypes
    ]


def _cast_mode(scenario, name, mode, *, lands, x_value=None):
    casting = scenario.cast(name)
    if x_value is None:
        casting.choose_modes([mode])
    else:
        casting.choose_modes([mode], x_value=x_value)
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources(*lands))
    scenario.put_on_stack(casting)
    return scenario.resolve_top()


def _outcomes(name):
    return {
        clause.text: clause.outcome
        for clause in card_support(card(name)).clauses
        if clause.kind != "keyword"
    }


def _to_the_end_step(scenario):
    scenario.start_at(Step.POSTCOMBAT_MAIN)
    scenario.advance()  # the end step begins (CR 513.1)
    assert scenario.step is Step.END_STEP


def _poison(scenario, username):
    return sum(
        count
        for kind, count in scenario.player(username).counters.items()
        if "poison" in str(kind).lower()
    )


@pytest.mark.parametrize(
    "name",
    [
        "Burn Down the House",
        "Charge of the Mites",
        "Maestros Diabolist",
        "Purphoros's Intervention",
        "Pugnacious Pugilist",
        "Basilica Shepherd",
        "Stinging Hivemaster",
        "Hungry for More",
    ],
)
def test_every_clause_of_the_card_reads_handled(name):
    outcomes = _outcomes(name)
    assert outcomes, name
    assert set(outcomes.values()) == {"handled"}, outcomes


# -- Burn Down the House, mode 2: quoted death trigger, then "They gain haste" -----


def _burn_board():
    return (
        Scenario()
        .player(
            "alice",
            hand=["Burn Down the House"],
            battlefield=["Mountain"] * 5 + ["Grizzly Bears"],
        )
        .player("bob", battlefield=["Hill Giant"])
        .build()
    )


def test_burn_down_the_house_makes_three_devils_with_haste_this_turn():
    scenario = _burn_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _cast_mode(scenario, "Burn Down the House", 2, lands=["Mountain"] * 5)

    devils = _tokens(scenario, "Devil")
    assert len(devils) == 3
    for devil in devils:
        assert (devil.power, devil.toughness) == (1, 1)
        assert has_keyword(devil, Keyword.HASTE, scenario.game)


def test_the_haste_goes_to_the_devils_only():
    """CR 608.2c: "They" is the three tokens, not every creature alice has."""
    scenario = _burn_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    _cast_mode(scenario, "Burn Down the House", 2, lands=["Mountain"] * 5)

    assert not has_keyword(bears, Keyword.HASTE, scenario.game)
    assert all(has_keyword(d, Keyword.HASTE, scenario.game) for d in _tokens(scenario, "Devil"))


def test_the_haste_is_until_end_of_turn_only():
    scenario = _burn_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _cast_mode(scenario, "Burn Down the House", 2, lands=["Mountain"] * 5)
    devil = _tokens(scenario, "Devil")[0]

    scenario.start_at(Step.END_STEP)
    scenario.advance()
    scenario.advance()
    assert devil.zone is Zone.BATTLEFIELD
    assert not has_keyword(devil, Keyword.HASTE, scenario.game)


def test_a_devil_dying_deals_one_damage_to_any_target():
    scenario = _burn_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _cast_mode(scenario, "Burn Down the House", 2, lands=["Mountain"] * 5)
    devil = _tokens(scenario, "Devil")[0]

    scenario.will_choose_targets("bob", username="alice")
    scenario.game.destroy(devil)
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()

    assert scenario.player("bob").life == 19


def test_burn_down_the_house_mode_one_still_reads():
    scenario = _burn_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "bob")
    _cast_mode(scenario, "Burn Down the House", 1, lands=["Mountain"] * 5)
    scenario.state_based_actions()

    assert bears.zone is Zone.GRAVEYARD
    assert giant.zone is Zone.GRAVEYARD


# -- Charge of the Mites, mode 2: toxic 1 and a quoted "can't block" ---------------


def _mites_board():
    return (
        Scenario()
        .player("alice", hand=["Charge of the Mites"], battlefield=["Plains"] * 3)
        .player("bob", battlefield=["Hill Giant"])
        .build()
    )


def test_charge_of_the_mites_makes_two_toxic_mites():
    scenario = _mites_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _cast_mode(scenario, "Charge of the Mites", 2, lands=["Plains"] * 3)

    mites = _tokens(scenario, "Mite")
    assert len(mites) == 2
    for mite in mites:
        assert (mite.power, mite.toughness) == (1, 1)
        assert Type.ARTIFACT in mite.types
        assert total_toxic_value(mite, scenario.game) == 1


def test_a_toxic_mite_gives_a_poison_counter_with_its_combat_damage():
    """CR 702.164a / CR 120.3g: toxic 1 on the token works in combat."""
    scenario = _mites_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _cast_mode(scenario, "Charge of the Mites", 2, lands=["Plains"] * 3)
    mite = _tokens(scenario, "Mite")[0]
    scenario.start_at(Step.DECLARE_ATTACKERS)
    mite.summoning_sick = False
    scenario.attack_with(mite)
    scenario.advance()
    scenario.no_blocks()
    scenario.advance()

    assert _poison(scenario, "bob") == 1


def test_the_mites_quoted_ability_stops_them_blocking():
    """CR 111.3: "This token can't block." is the Mite's own text. Bob
    attacks; alice answers with Charge of the Mites, and only her Grizzly
    Bears - not a Mite - can block the attacker."""
    scenario = (
        Scenario()
        .player("bob", battlefield=["Hill Giant"])
        .player(
            "alice",
            hand=["Charge of the Mites"],
            battlefield=["Plains"] * 3 + ["Grizzly Bears"],
        )
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    giant = scenario.creature("Hill Giant", "bob")
    giant.summoning_sick = False
    scenario.attack_with(giant, defending="alice")
    scenario.pass_priority("bob")
    casting = scenario.cast("Charge of the Mites", "alice")
    casting.choose_modes([2])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources(*["Plains"] * 3, username="alice"))
    scenario.put_on_stack(casting)
    scenario.resolve_top()
    mite = _tokens(scenario, "Mite")[0]
    bears = scenario.creature("Grizzly Bears", "alice")

    assert scenario.game.can_block(bears, giant)
    assert not scenario.game.can_block(mite, giant)


# -- Basilica Shepherd / Stinging Hivemaster: the same template on other printings -


def test_basilica_shepherd_enters_with_two_toxic_mites():
    scenario = Scenario().player("alice", hand=["Basilica Shepherd"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.put_onto_battlefield("Basilica Shepherd", "alice")
    scenario.pass_until_resolved()

    mites = _tokens(scenario, "Mite")
    assert len(mites) == 2
    assert all(total_toxic_value(m, scenario.game) == 1 for m in mites)


def test_stinging_hivemaster_leaves_a_toxic_mite_when_it_dies():
    scenario = Scenario().player("alice", battlefield=["Stinging Hivemaster"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.destroy(scenario.creature("Stinging Hivemaster", "alice"))
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()

    mites = _tokens(scenario, "Mite")
    assert len(mites) == 1
    assert total_toxic_value(mites[0], scenario.game) == 1


# -- Maestros Diabolist: tapped and attacking Devil, only without a Devil token ----


def _maestros_board(extra=()):
    return (
        Scenario()
        .player("alice", battlefield=["Maestros Diabolist", *extra])
        .player("bob", battlefield=["Hill Giant"])
        .build()
    )


def _attack(scenario, *names):
    scenario.start_at(Step.DECLARE_ATTACKERS)
    attackers = [scenario.creature(name, "alice") for name in names]
    for attacker in attackers:
        attacker.summoning_sick = False
    scenario.attack_with(*attackers)
    scenario.game.put_triggers_on_stack()
    return attackers


def test_maestros_attack_creates_a_tapped_attacking_devil():
    scenario = _maestros_board()
    (maestros,) = _attack(scenario, "Maestros Diabolist")
    scenario.resolve_top()

    devils = _tokens(scenario, "Devil")
    assert len(devils) == 1
    devil = devils[0]
    assert devil.tapped
    attacks = {a.attacker_id: a.defender for a in scenario.game.combat.attacks}
    assert devil.id in attacks, "the Devil is attacking"
    assert attacks[devil.id] == attacks[maestros.id], "same player as the source (CR 508.4)"


def test_the_devil_was_never_declared_as_an_attacker():
    """CR 508.4: the Devil is attacking but never "attacked", so nothing
    triggers off it entering."""
    scenario = _maestros_board()
    _attack(scenario, "Maestros Diabolist")
    scenario.resolve_top()

    devil = _tokens(scenario, "Devil")[0]
    assert scenario.game.stack_is_empty
    assert scenario.game.combat.attack_by(devil.id) is not None


def test_maestros_makes_no_devil_while_you_control_a_devil_token():
    """CR 603.4: the intervening "if you don't control a Devil token"."""
    scenario = _maestros_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    create_tokens(
        scenario.game,
        TokenDefinition(subtypes=("Devil",), power=1, toughness=1),
        "alice",
    )
    assert len(_tokens(scenario, "Devil")) == 1
    _attack(scenario, "Maestros Diabolist")

    assert scenario.game.stack_is_empty, "the trigger never goes on the stack"
    assert len(_tokens(scenario, "Devil")) == 1


def test_the_condition_is_checked_again_on_resolution():
    """Two attackers trigger together with no Devil in play; the first Devil
    made makes the other trigger do nothing (CR 603.4)."""
    scenario = _maestros_board(extra=["Pugnacious Pugilist"])
    _attack(scenario, "Maestros Diabolist", "Pugnacious Pugilist")
    scenario.resolve_top()
    scenario.resolve_top()

    assert len(_tokens(scenario, "Devil")) == 1


def test_a_maestros_devil_dying_pings_any_target():
    scenario = _maestros_board()
    _attack(scenario, "Maestros Diabolist")
    scenario.resolve_top()
    devil = _tokens(scenario, "Devil")[0]

    scenario.will_choose_targets("bob", username="alice")
    scenario.game.destroy(devil)
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()

    assert scenario.player("bob").life == 19


def test_pugnacious_pugilist_makes_the_same_attacking_devil():
    scenario = Scenario().player("alice", battlefield=["Pugnacious Pugilist"]).player("bob").build()
    (pugilist,) = _attack(scenario, "Pugnacious Pugilist")
    scenario.resolve_top()

    devil = _tokens(scenario, "Devil")[0]
    attacks = {a.attacker_id: a.defender for a in scenario.game.combat.attacks}
    assert devil.tapped and attacks[devil.id] == attacks[pugilist.id]


def test_pugnacious_pugilist_attack_trigger_reads_handled():
    """NW05-T6's card: its attack trigger is the same template."""
    outcomes = _outcomes("Pugnacious Pugilist")
    attack = [o for text, o in outcomes.items() if text.startswith("Whenever this creature")]
    assert attack == ["handled"]


# -- Purphoros's Intervention, mode 1: X/1, trample and haste, sacrificed ----------


def _purphoros_board(lands=5):
    return (
        Scenario()
        .player("alice", hand=["Purphoros's Intervention"], battlefield=["Mountain"] * lands)
        .player("bob")
        .build()
    )


def test_purphoros_makes_an_x_over_one_elemental_with_trample_and_haste():
    scenario = _purphoros_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _cast_mode(scenario, "Purphoros's Intervention", 1, lands=["Mountain"] * 4, x_value=3)

    elementals = _tokens(scenario, "Elemental")
    assert len(elementals) == 1
    token = elementals[0]
    assert (token.power, token.toughness) == (3, 1), "X is the announced 3 (CR 107.3a)"
    assert has_keyword(token, Keyword.TRAMPLE, scenario.game)
    assert has_keyword(token, Keyword.HASTE, scenario.game)


def test_purphoros_token_is_sacrificed_at_the_next_end_step_and_not_before():
    scenario = _purphoros_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _cast_mode(scenario, "Purphoros's Intervention", 1, lands=["Mountain"] * 5, x_value=4)
    token = _tokens(scenario, "Elemental")[0]
    assert (token.power, token.toughness) == (4, 1)

    scenario.start_at(Step.POSTCOMBAT_MAIN)
    assert token.zone is Zone.BATTLEFIELD
    scenario.advance()
    assert len(scenario.game.stack) == 1, "one delayed trigger, about this token (CR 603.7a)"
    scenario.resolve_top()
    assert _tokens(scenario, "Elemental") == []


def test_purphoros_sacrifice_names_only_its_own_token():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Purphoros's Intervention"],
            battlefield=["Mountain"] * 3 + ["Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    _cast_mode(scenario, "Purphoros's Intervention", 1, lands=["Mountain"] * 3, x_value=2)
    _to_the_end_step(scenario)
    scenario.resolve_top()

    assert _tokens(scenario, "Elemental") == []
    assert bears.zone is Zone.BATTLEFIELD


# -- Hungry for More: a non-modal spell with the same sentence pair ------------------


def test_hungry_for_more_makes_a_vampire_that_is_sacrificed_at_end_step():
    scenario = (
        Scenario()
        .player("alice", hand=["Hungry for More"], battlefield=["Mountain", "Swamp"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve("Hungry for More", *scenario.untapped_sources("Mountain", "Swamp"))

    token = _tokens(scenario, "Vampire")[0]
    assert (token.power, token.toughness) == (3, 1)
    for keyword in (Keyword.TRAMPLE, Keyword.LIFELINK, Keyword.HASTE):
        assert has_keyword(token, keyword, scenario.game)
    _to_the_end_step(scenario)
    scenario.resolve_top()
    assert token.zone is not Zone.BATTLEFIELD


# -- The reader refuses what it cannot read whole ----------------------------------


@pytest.mark.parametrize(
    "rider",
    [
        "They gain frobnicate until the sun explodes.",
        "If you do, they gain haste until end of turn.",
    ],
)
def test_an_unreadable_or_conditional_rider_is_never_dropped(rider):
    """The rider's own condition (or an unknown word) keeps the whole text
    unread rather than reading the token and silently ignoring the rest."""
    text = (
        'Create a 1/1 red Devil creature token with "When this token dies, it deals 1 damage '
        f'to any target." {rider}'
    )
    assert parse_mixed_effect(text) is None


def test_a_conditional_keyword_token_sentence_is_not_swallowed():
    """The widened "and"-list reader keeps a trailing condition unread."""
    text = (
        "Create a 3/1 red Elemental creature token with trample and haste if you control a Devil."
    )
    assert parse_mixed_effect(text) is None


def test_a_token_followed_by_an_unreadable_rider_is_not_half_read():
    """CR 608.2c has no notion of running half an instruction."""
    text = (
        'Create a 1/1 red Devil creature token with "When this token dies, it deals 1 damage '
        'to any target." They gain frobnicate until the sun explodes.'
    )
    assert parse_mixed_effect(text) is None


# -- Shock Brigade: the existing tapped-and-attacking token path is unchanged ------


def test_shock_brigade_mobilize_still_creates_a_tapped_attacking_warrior():
    scenario = Scenario().player("alice", battlefield=["Shock Brigade"]).player("bob").build()
    _attack(scenario, "Shock Brigade")
    scenario.resolve_top()

    warriors = _tokens(scenario, "Warrior")
    assert len(warriors) == 1 and warriors[0].tapped
