"""Disturb (CR 702.146): casting a double-faced card transformed from its
owner's graveyard.

CR 702.146a: "Disturb is an ability found on the front face of some
double-faced cards ... 'Disturb [cost]' means 'You may cast this card
transformed from your graveyard by paying [cost] rather than its mana cost.'
See rule 712.8c." CR 702.146b: "A resolving double-faced spell that was cast
using its disturb ability enters the battlefield with its back face up."
(CR 702.146 has only those two subrules.)

Three things follow, and each has its own block below:

- **the permission** - a graveyard zone (CR 601.3) and an alternative cost
  (CR 118.9), offered only from the graveyard: the front face cast from the
  graveyard, or disturb announced from the hand, is refused in the engine's
  own words;
- **the face** - CR 712.11a/712.8c: the spell is put on the stack back face
  up with only its back face's characteristics, and its mana value is the
  front face's; CR 702.146b: it enters back face up. An Aura back face
  (Twinblade Invocation) targets as it is cast (CR 712.11c, CR 303.4a);
- **the exile** - every disturb back face prints "If <this> would be put into
  a graveyard from anywhere, exile it instead." It applies on the stack (a
  countered disturbed spell) and on the battlefield (a disturbed creature
  that dies, an Aura put into the graveyard by CR 704.5m), and it does not
  apply to a bounce: back in the hand, the card has only its front face
  (CR 712.8a) and is an ordinary card again.

Proof printings: the listed disturb cards Beloved Beggar // Generous Soul,
Galedrifter // Waildrifter, Devoted Grafkeeper // Departed Soulkeeper, Lunarch
Veteran // Luminous Phantom and Twinblade Geist // Twinblade Invocation -
different costs, colours, back-face types (creature and Aura) and triggers.
"""

import pytest

from magic_cards_model.machines import Step, legal_actions
from magic_cards_model.machines.casting import keyword_cast_options, why_cannot_cast_from
from magic_cards_model.machines.combat import Keyword, has_keyword
from magic_cards_model.models import ActionKind, Zone
from magic_cards_model.support import card_support
from tests.cards import card
from tests.scenarios.harness import Scenario

BEGGAR = "Beloved Beggar"
GALEDRIFTER = "Galedrifter"
GRAFKEEPER = "Devoted Grafkeeper"
VETERAN = "Lunarch Veteran"
TWINBLADE = "Twinblade Geist"


def board(alice: dict, bob: dict | None = None) -> Scenario:
    return (
        Scenario().manual_turn_based_actions().player("alice", **alice).player("bob", **(bob or {}))
    )


def _disturb(scenario, name: str, *lands: str, targets=None):
    """Announce `name` from the graveyard with disturb, pay with `lands`, put
    it on the stack - the CR 601.2 path a player takes."""
    sources = scenario.untapped_sources(*lands)
    casting = scenario.cast(name, from_zone=Zone.GRAVEYARD)
    casting.use_keyword("Disturb")
    if targets is not None:
        casting.choose_targets(targets)
    scenario.pay_with(casting.begin_paying(), *sources)
    return scenario.put_on_stack(casting)


# -- what the keyword offers ------------------------------------------------


@pytest.mark.parametrize(
    ("name", "cost"),
    [
        (BEGGAR, "{4}{W}{W}"),
        (GALEDRIFTER, "{4}{U}"),
        (GRAFKEEPER, "{1}{W}{U}"),
        (TWINBLADE, "{2}{W}"),
    ],
)
def test_disturb_offers_a_graveyard_cast_for_the_disturb_cost(name, cost):
    (option,) = [o for o in keyword_cast_options(card(name)) if o.keyword == "Disturb"]

    assert option.zone is Zone.GRAVEYARD
    assert option.pays_mana_cost is False
    assert option.casts_transformed is True
    assert str(option.cost) == cost


@pytest.mark.parametrize("name", [BEGGAR, GALEDRIFTER, GRAFKEEPER, VETERAN, TWINBLADE])
def test_the_disturb_cards_read_fully_handled(name):
    support = card_support(card(name))

    assert support.status == "handled", [c for c in support.clauses if c.status != "handled"]


# -- casting it: the face ---------------------------------------------------


def test_a_disturbed_spell_is_on_the_stack_back_face_up_with_the_front_mana_value():
    """CR 712.11a / 712.8c: back face up, only the back face's
    characteristics, the front face's mana value ({1}{W} = 2)."""
    scenario = board({"graveyard": [BEGGAR], "battlefield": ["Plains"] * 6}).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    spell = _disturb(scenario, BEGGAR, *["Plains"] * 6)

    assert spell.zone is Zone.STACK
    assert spell.transformed
    assert spell.name == "Generous Soul"
    assert spell.mana_value == 2


def test_a_disturbed_creature_enters_back_face_up():
    """CR 702.146b: it enters with its back face up - Generous Soul, flying
    and vigilance, not Beloved Beggar."""
    scenario = board({"graveyard": [BEGGAR], "battlefield": ["Plains"] * 6}).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    spell = _disturb(scenario, BEGGAR, *["Plains"] * 6)
    scenario.resolve_top()

    assert spell.zone is Zone.BATTLEFIELD
    assert spell.transformed
    assert spell.name == "Generous Soul"
    assert has_keyword(spell, Keyword.FLYING, scenario.game)
    assert has_keyword(spell, Keyword.VIGILANCE, scenario.game)


def test_a_second_printing_disturbs_for_its_own_cost():
    """Galedrifter's {4}{U}: blue, five mana, a different back face."""
    scenario = board({"graveyard": [GALEDRIFTER], "battlefield": ["Island"] * 5}).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    spell = _disturb(scenario, GALEDRIFTER, *["Island"] * 5)
    scenario.resolve_top()

    assert spell.zone is Zone.BATTLEFIELD
    assert spell.name == "Waildrifter"
    assert spell.mana_value == 4


def test_the_disturb_cost_is_paid_not_the_mana_cost():
    """CR 118.9: {1}{W}{U}, not Devoted Grafkeeper's own {W}{U} - two lands
    cannot pay it."""
    scenario = board({"graveyard": [GRAFKEEPER], "battlefield": ["Plains", "Island"]}).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    sources = scenario.untapped_sources("Plains", "Island")
    casting = scenario.cast(GRAFKEEPER, from_zone=Zone.GRAVEYARD)
    casting.use_keyword("Disturb")

    assert str(casting.total_cost.mana) == "{1}{W}{U}"
    with pytest.raises(ValueError):
        scenario.pay_with(casting.begin_paying(), *sources)


def test_cast_from_hand_it_is_the_front_face():
    """CR 712.11: front face up by default."""
    scenario = board({"hand": [BEGGAR], "battlefield": ["Plains"] * 2}).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    beggar = scenario.cast_and_resolve(BEGGAR, *scenario.untapped_sources("Plains", "Plains"))

    assert beggar.zone is Zone.BATTLEFIELD
    assert not beggar.transformed
    assert beggar.name == BEGGAR


def test_a_disturb_trigger_on_the_front_face_does_not_exist_on_the_back():
    """Lunarch Veteran's "Whenever another creature you control enters, you
    gain 1 life" is the front face's; disturbed it is Luminous Phantom, whose
    trigger is "leaves the battlefield" instead (CR 712.8e)."""
    scenario = board(
        {"graveyard": [VETERAN], "battlefield": ["Plains", "Plains", "Grizzly Bears"]}
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    phantom = _disturb(scenario, VETERAN, "Plains", "Plains")
    scenario.resolve_top()

    assert phantom.name == "Luminous Phantom"
    assert has_keyword(phantom, Keyword.FLYING, scenario.game)
    assert scenario.player("alice").life == 20


# -- permission, and what has none ------------------------------------------


def test_the_front_face_cannot_be_cast_from_the_graveyard():
    """CR 601.3: disturb is the only permission, and it casts the card
    transformed - an announcement that never claims it is refused."""
    scenario = board({"graveyard": [BEGGAR], "battlefield": ["Plains"] * 2}).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast(BEGGAR, from_zone=Zone.GRAVEYARD)
    scenario.pay_with(casting.begin_paying(), *scenario.untapped_sources("Plains", "Plains"))
    with pytest.raises(ValueError, match="Disturb") as refused:
        casting.cast()
    assert "CR 702.146a" in str(refused.value)
    casting.cancel()
    assert scenario.find(BEGGAR, Zone.GRAVEYARD).zone is Zone.GRAVEYARD


def test_disturb_cannot_be_used_from_the_hand():
    """CR 702.146a: "from your graveyard" - from the hand there is nothing to
    disturb, and the engine says why."""
    scenario = board({"hand": [BEGGAR], "battlefield": ["Plains"] * 6}).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast(BEGGAR)
    with pytest.raises(ValueError, match="(?i)graveyard"):
        casting.use_keyword("Disturb")


def test_a_card_in_another_players_graveyard_cannot_be_disturbed():
    """CR 702.146a: "your graveyard"."""
    scenario = board({"battlefield": ["Plains"] * 6}, {"graveyard": [BEGGAR]}).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    beggar = scenario.find(BEGGAR, Zone.GRAVEYARD, "bob")
    (option,) = [o for o in keyword_cast_options(beggar.card) if o.keyword == "Disturb"]

    assert "owner" in option.why_not(beggar, "alice", scenario.game)
    assert option.why_not(beggar, "bob", scenario.game) is None
    assert why_cannot_cast_from(beggar, "bob", Zone.GRAVEYARD, scenario.game) is None


def test_legal_actions_offer_the_disturb_cast_from_the_graveyard():
    scenario = board({"graveyard": [GALEDRIFTER], "battlefield": ["Island"] * 5}).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    drifter = scenario.find(GALEDRIFTER, Zone.GRAVEYARD)

    casts = [
        action
        for action in legal_actions(scenario.game, "alice")
        if action.card_id == drifter.id and action.kind is ActionKind.CAST
    ]

    assert casts
    assert all(action.from_zone is Zone.GRAVEYARD for action in casts)
    assert any(action.keyword == "Disturb" for action in casts)


def test_disturb_is_sorcery_speed_for_a_creature_back_face():
    """CR 307.1/302.1: Waildrifter is a creature spell, so not in combat."""
    scenario = board({"graveyard": [GALEDRIFTER], "battlefield": ["Island"] * 5}).build()
    scenario.start_at(Step.BEGINNING_OF_COMBAT)

    with pytest.raises(ValueError, match="(?i)main phase"):
        casting = scenario.cast(GALEDRIFTER, from_zone=Zone.GRAVEYARD)
        casting.use_keyword("Disturb")
        scenario.pay_with(casting.begin_paying(), *scenario.untapped_sources(*["Island"] * 5))
        casting.cast()


@pytest.mark.parametrize("step", [Step.END_STEP, Step.BEGINNING_OF_COMBAT, Step.UPKEEP])
def test_flashback_keeps_the_sorcerys_own_timing(step):
    """CR 702.34a: flashback changes the zone and the cost, never the timing -
    Faithless Looting is still a sorcery (CR 307.1, CR 117.1a), so it is not
    cast outside its controller's main phase."""
    scenario = board({"graveyard": ["Faithless Looting"], "battlefield": ["Mountain"] * 3}).build()
    scenario.start_at(step)
    looting = scenario.find("Faithless Looting", Zone.GRAVEYARD)

    assert not [
        action
        for action in legal_actions(scenario.game, "alice")
        if action.card_id == looting.id and action.kind is ActionKind.CAST
    ]
    with pytest.raises(ValueError, match="(?i)main phase"):
        casting = scenario.cast("Faithless Looting", from_zone=Zone.GRAVEYARD)
        casting.use_keyword("Flashback")
        scenario.pay_with(casting.begin_paying(), *scenario.untapped_sources(*["Mountain"] * 3))
        casting.cast()


def test_flashback_keeps_its_timing_beside_a_sorcery_timed_grant():
    """CR 117.1a follows the option the cast actually uses. Kess, Dissident
    Mage grants a graveyard cast of a sorcery that carries sorcery timing of
    its own; its presence must not lend that answer to flashback (CR 702.34a),
    which keeps Faithless Looting's own sorcery timing in beginning of combat."""
    scenario = board(
        {
            "graveyard": ["Faithless Looting"],
            "battlefield": ["Kess, Dissident Mage", *["Mountain"] * 3],
        }
    ).build()
    scenario.start_at(Step.BEGINNING_OF_COMBAT)

    with pytest.raises(ValueError, match="(?i)main phase"):
        casting = scenario.cast("Faithless Looting", from_zone=Zone.GRAVEYARD)
        casting.use_keyword("Flashback")
        scenario.pay_with(casting.begin_paying(), *scenario.untapped_sources(*["Mountain"] * 3))
        casting.cast()


def test_flashback_beside_a_sorcery_timed_grant_in_the_main_phase():
    """The positive half: in its controller's main phase, flashback casts
    Faithless Looting from the graveyard with Kess on the battlefield."""
    scenario = board(
        {
            "graveyard": ["Faithless Looting"],
            "battlefield": ["Kess, Dissident Mage", *["Mountain"] * 3],
        }
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Faithless Looting", from_zone=Zone.GRAVEYARD)
    casting.use_keyword("Flashback")
    scenario.pay_with(casting.begin_paying(), *scenario.untapped_sources(*["Mountain"] * 3))
    assert scenario.put_on_stack(casting).zone is Zone.STACK


def test_escape_keeps_the_creatures_own_timing():
    """CR 702.138a: escape is a permission to cast from the graveyard; Uro is
    a creature spell (CR 302.1, CR 117.1a), so not in the end step."""
    filler = ["Grizzly Bears"] * 5
    scenario = board(
        {
            "graveyard": ["Uro, Titan of Nature's Wrath", *filler],
            "battlefield": ["Forest", "Forest", "Island", "Island"],
        }
    ).build()
    scenario.start_at(Step.END_STEP)
    fuel = [c for c in scenario.player("alice").graveyard if c.name == "Grizzly Bears"]

    with pytest.raises(ValueError, match="(?i)main phase"):
        casting = scenario.cast("Uro, Titan of Nature's Wrath", from_zone=Zone.GRAVEYARD)
        casting.use_keyword("Escape", choosing=fuel)
        scenario.pay_with(
            casting.begin_paying(),
            *scenario.untapped_sources("Forest", "Forest", "Island", "Island"),
        )
        casting.cast()


def test_flashback_on_an_instant_is_still_instant_speed():
    """CR 304.1: Faithful Mending is an instant, so flashback casts it in the
    end step exactly as it could be cast from the hand."""
    lands = ("Plains", "Island", "Island")
    scenario = board({"graveyard": ["Faithful Mending"], "battlefield": list(lands)}).build()
    scenario.start_at(Step.END_STEP)

    casting = scenario.cast("Faithful Mending", from_zone=Zone.GRAVEYARD)
    casting.use_keyword("Flashback")
    scenario.pay_with(casting.begin_paying(), *scenario.untapped_sources(*lands))
    assert scenario.put_on_stack(casting).zone is Zone.STACK


# -- the exile --------------------------------------------------------------


def test_a_disturbed_creature_that_dies_is_exiled():
    scenario = board(
        {"graveyard": [BEGGAR], "battlefield": ["Plains"] * 6},
        {"hand": ["Go for the Throat"], "battlefield": ["Swamp", "Swamp"]},
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    soul = _disturb(scenario, BEGGAR, *["Plains"] * 6)
    scenario.resolve_top()
    scenario.pass_priority("alice")

    swamps = scenario.untapped_sources("Swamp", "Swamp", username="bob")
    scenario.cast_and_resolve("Go for the Throat", *swamps, username="bob", targets=[soul])

    assert soul.zone is Zone.EXILE
    assert soul not in scenario.player("alice").graveyard


def test_a_countered_disturbed_spell_is_exiled():
    scenario = board(
        {"graveyard": [GALEDRIFTER], "battlefield": ["Island"] * 5},
        {"hand": ["Essence Scatter"], "battlefield": ["Island", "Island"]},
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    spell = _disturb(scenario, GALEDRIFTER, *["Island"] * 5)
    scenario.pass_priority("alice")

    islands = scenario.untapped_sources("Island", "Island", username="bob")
    scenario.cast_and_resolve("Essence Scatter", *islands, username="bob", targets=[spell])

    assert spell.zone is Zone.EXILE
    assert scenario.stack_names() == []


def test_a_bounced_disturbed_creature_returns_to_hand_as_its_front_face():
    """Only "put into a graveyard" is replaced; in the hand the card has
    only its front face (CR 712.8a) and casts normally again."""
    scenario = board(
        {"graveyard": [GALEDRIFTER], "battlefield": ["Island"] * 5},
        {"hand": ["Unsummon"], "battlefield": ["Island"]},
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    drifter = _disturb(scenario, GALEDRIFTER, *["Island"] * 5)
    scenario.resolve_top()
    scenario.pass_priority("alice")

    (island,) = scenario.untapped_sources("Island", username="bob")
    scenario.cast_and_resolve("Unsummon", island, username="bob", targets=[drifter])

    assert drifter.zone is Zone.HAND
    assert not drifter.transformed
    assert drifter.name == GALEDRIFTER


def test_a_front_face_that_dies_goes_to_the_graveyard_and_can_be_disturbed():
    """The exile is the back face's: Beloved Beggar cast from the hand dies
    into the graveyard like any creature - and is then disturbable."""
    scenario = board(
        {"hand": [BEGGAR], "battlefield": ["Plains"] * 8},
        {"hand": ["Go for the Throat"], "battlefield": ["Swamp", "Swamp"]},
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    beggar = scenario.cast_and_resolve(BEGGAR, *scenario.untapped_sources("Plains", "Plains"))
    scenario.pass_priority("alice")

    swamps = scenario.untapped_sources("Swamp", "Swamp", username="bob")
    scenario.cast_and_resolve("Go for the Throat", *swamps, username="bob", targets=[beggar])
    assert beggar.zone is Zone.GRAVEYARD

    soul = _disturb(scenario, BEGGAR, *["Plains"] * 6)
    scenario.resolve_top()
    assert soul.zone is Zone.BATTLEFIELD
    assert soul.name == "Generous Soul"


# -- an Aura back face ------------------------------------------------------


def test_a_disturbed_aura_targets_and_grants_its_ability():
    """Twinblade Invocation: "Enchant creature / Enchanted creature has double
    strike." Cast transformed it is an Aura spell (CR 712.11c, CR 303.4a)."""
    scenario = board(
        {"graveyard": [TWINBLADE], "battlefield": ["Plains"] * 3 + ["Grizzly Bears"]}
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears")

    aura = _disturb(scenario, TWINBLADE, *["Plains"] * 3, targets=[bears])
    scenario.resolve_top()

    assert aura.zone is Zone.BATTLEFIELD
    assert aura.name == "Twinblade Invocation"
    assert aura.attached_to == bears.id
    assert has_keyword(bears, Keyword.DOUBLE_STRIKE, scenario.game)


def test_a_disturbed_aura_whose_creature_dies_is_exiled():
    """CR 704.5m puts the unattached Aura into the graveyard - exiled
    instead."""
    scenario = board(
        {"graveyard": [TWINBLADE], "battlefield": ["Plains"] * 3 + ["Grizzly Bears"]},
        {"hand": ["Go for the Throat"], "battlefield": ["Swamp", "Swamp"]},
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears")
    aura = _disturb(scenario, TWINBLADE, *["Plains"] * 3, targets=[bears])
    scenario.resolve_top()
    scenario.pass_priority("alice")

    swamps = scenario.untapped_sources("Swamp", "Swamp", username="bob")
    scenario.cast_and_resolve("Go for the Throat", *swamps, username="bob", targets=[bears])

    assert bears.zone is Zone.GRAVEYARD
    assert aura.zone is Zone.EXILE
