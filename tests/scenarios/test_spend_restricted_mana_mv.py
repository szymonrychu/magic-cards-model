"""CR 106.6's "Spend this mana only to ..." restriction, narrowed by CR
202.3's mana value rather than by a card type - Ashling, Rimebound's own
"Whenever this creature transforms into Ashling, Rimebound and at the
beginning of your first main phase, add two mana of any one color. Spend
this mana only to cast spells with mana value 4 or greater."

`test_mana_spend_restrictions.py` already proves `SpendClause.min_mana_value`
against Helga, Skittish Seer's own "creature spells with mana value 4 or
greater" (a *typed* restriction). Ashling's own restriction narrows by mana
value alone, with no card-type qualifier at all - `models/mana._spend_clause`
already reads an empty quality list as "ask nothing" for type/subtype, so
this is the same machinery, just proving the untyped shape actually refuses
and actually pays for real spells rather than only asserting on the parsed
`SpendClause` object. Troyan, Gutsy Explorer (Modern/Pioneer/Standard-legal,
outside this pool): "{T}: Add {G}{U}. Spend this mana only to cast spells
with mana value 5 or greater or spells with {X} in their mana costs." is the
second printing that proves the reader is the general mechanic, not a row
fitted to Ashling's own sentence - a different threshold, a different
mana-producing shape (a plain activated ability rather than a triggered one),
and its own "or spells with {X} in their mana costs" second clause.

Every CR number here was read with `mise run rules:find` in the session that
wrote this file.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.triggers import GameEvent, TriggerEvent
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _fire_ashling_rimebound(scenario: Scenario, ashling) -> None:
    ashling.transform()
    scenario.will_choose("W", source="Ashling, Rimebound", username="alice")
    scenario.game.emit(
        GameEvent(
            event=TriggerEvent.TRANSFORMS,
            subject_id=ashling.id,
            subject_name=ashling.name,
            subject_controller="alice",
            subject_card=ashling.card,
            player="alice",
        )
    )
    scenario.pass_until_resolved()


def test_ashling_rimebounds_mana_casts_a_spell_with_mana_value_4_or_greater():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Colossal Dreadmaw"],
            battlefield=["Ashling, Rekindled", "Forest", "Forest", "Forest", "Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ashling = scenario.creature("Ashling, Rekindled", "alice")
    _fire_ashling_rimebound(scenario, ashling)
    assert scenario.player("alice").mana_pool.total == 2

    sources = scenario.untapped_sources("Forest", "Forest", "Forest", "Forest", username="alice")
    casting = scenario.cast("Colossal Dreadmaw", username="alice")
    payment = casting.begin_paying()
    scenario.pay_with(payment, *sources)
    scenario.put_on_stack(casting)
    scenario.pass_until_resolved()

    assert scenario.find("Colossal Dreadmaw", Zone.BATTLEFIELD, "alice").zone is Zone.BATTLEFIELD
    assert scenario.player("alice").mana_pool.is_empty


def test_ashling_rimebounds_mana_cannot_pay_for_a_low_mana_value_spell():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Bolt"],
            battlefield=["Ashling, Rekindled"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ashling = scenario.creature("Ashling, Rekindled", "alice")
    _fire_ashling_rimebound(scenario, ashling)

    casting = scenario.cast("Lightning Bolt", username="alice", targets=["bob"])
    payment = casting.begin_paying()

    assert payment.shortfall is True
    with pytest.raises(ValueError, match="Spend this mana only to cast spells"):
        payment.pay()

    # CR 733.1: nothing was spent, so the mana is still there, still restricted.
    assert scenario.player("alice").mana_pool.total == 2


def test_troyans_mana_casts_a_spell_with_mana_value_5_or_greater():
    """A second, unrelated printing of "Spend this mana only to cast spells
    with mana value N or greater" - a different threshold, a different
    mana-producing shape (an activated ability, not a triggered one)."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Craw Wurm"],
            battlefield=["Troyan, Gutsy Explorer", "Forest", "Forest", "Forest", "Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    troyan = scenario.creature("Troyan, Gutsy Explorer", "alice")
    troyan.summoning_sick = False
    scenario.game.activate_ability(troyan, 0, "alice")
    assert scenario.player("alice").mana_pool.total == 2

    sources = scenario.untapped_sources("Forest", "Forest", "Forest", "Forest", username="alice")
    casting = scenario.cast("Craw Wurm", username="alice")
    payment = casting.begin_paying()
    scenario.pay_with(payment, *sources)
    scenario.put_on_stack(casting)
    scenario.pass_until_resolved()

    assert scenario.find("Craw Wurm", Zone.BATTLEFIELD, "alice").zone is Zone.BATTLEFIELD
    assert scenario.player("alice").mana_pool.is_empty


def test_troyans_mana_cannot_pay_for_a_low_mana_value_non_x_spell():
    scenario = (
        Scenario()
        .player("alice", hand=["Lightning Bolt"], battlefield=["Troyan, Gutsy Explorer"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    troyan = scenario.creature("Troyan, Gutsy Explorer", "alice")
    troyan.summoning_sick = False
    scenario.game.activate_ability(troyan, 0, "alice")

    casting = scenario.cast("Lightning Bolt", username="alice", targets=["bob"])
    payment = casting.begin_paying()

    assert payment.shortfall is True
    with pytest.raises(ValueError, match="Spend this mana only to cast spells"):
        payment.pay()

    assert scenario.player("alice").mana_pool.total == 2
