"""Damage-combo templates: a spell that pairs its own damage with a second,
independent effect (a draw, an exile, a life swing, or a reveal-choose-
discard sequence), and an X-cost enchantment whose own ETB trigger deals
damage equal to the X its caster announced.

Verified this session with `knowledge_search(q="...", type="rules")` and
cross-checked with `mise run rules:find` (on-disk CR effective 2026-09-25):

- **CR 119.2 / 120.3a** - damage to a player, and life loss it causes.
- **CR 107.3a** - "While a spell ... with a value of X in its cost is on the
  stack, X is considered to be the number that player chose."
- **CR 107.3m** - a triggered ability of the permanent an X-cost spell
  became "uses the same value of X as the spell", if the ability's own text
  doesn't independently define X.
- **CR 701.15a** - to discard a card.
- **CR 613.1f** - a static ability granting a keyword in layer 6.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import Keyword, has_keyword
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_cast_away_doubt_draws_two_and_damages_each_player() -> None:
    """ "Draw two cards. Cast Away Doubt deals 2 damage to each player." -
    two independent CR 608.2c instructions in printed order; both players,
    caster included, take the damage.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Cast Away Doubt"],
            battlefield=["Swamp", "Swamp", "Swamp"],
            library=["Opt", "Opt"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice_life_before = scenario.game.player("alice").life
    bob_life_before = scenario.game.player("bob").life
    hand_before = len(scenario.game.player("alice").hand)

    scenario.cast_and_resolve(
        "Cast Away Doubt", *scenario.untapped_sources("Swamp", "Swamp", "Swamp")
    )

    assert len(scenario.game.player("alice").hand) == hand_before - 1 + 2
    assert scenario.game.player("alice").life == alice_life_before - 2
    assert scenario.game.player("bob").life == bob_life_before - 2


def test_extended_absence_exiles_and_drains_each_opponent() -> None:
    """ "Exile target creature or planeswalker. Extended Absence deals 1
    damage to each opponent and you gain 1 life." - three instructions:
    exile, damage, and a life gain not itself tied to the damage dealt.
    """
    scenario = (
        Scenario()
        .player(
            "alice", hand=["Extended Absence"], battlefield=["Swamp", "Swamp", "Swamp", "Swamp"]
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    alice_life_before = scenario.game.player("alice").life
    bob_life_before = scenario.game.player("bob").life

    scenario.cast_and_resolve(
        "Extended Absence",
        *scenario.untapped_sources("Swamp", "Swamp", "Swamp", "Swamp"),
        targets=[bears],
    )

    assert bears.zone is Zone.EXILE
    assert scenario.game.player("bob").life == bob_life_before - 1
    assert scenario.game.player("alice").life == alice_life_before + 1


def test_stinging_vitriol_damages_then_reveals_and_discards_a_chosen_nonland_card() -> None:
    """ "Stinging Vitriol deals 2 damage to target opponent. That player
    reveals their hand. You choose a nonland card from it. They discard that
    card." - the damage-target and the discard-target are the same player,
    read back by anaphora ("that player"), not re-targeted.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Stinging Vitriol"], battlefield=["Swamp", "Mountain"])
        .player("bob", hand=["Grizzly Bears", "Opt"], battlefield=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bob_life_before = scenario.game.player("bob").life
    bears_in_hand = scenario.find("Grizzly Bears", Zone.HAND, "bob")
    scenario.will_choose_cards(bears_in_hand, source="Stinging Vitriol")

    scenario.cast_and_resolve(
        "Stinging Vitriol", *scenario.untapped_sources("Swamp", "Mountain"), targets=["bob"]
    )

    assert scenario.game.player("bob").life == bob_life_before - 2
    bob_hand_names = [card.name for card in scenario.game.player("bob").hand]
    assert "Grizzly Bears" not in bob_hand_names
    assert "Opt" in bob_hand_names
    assert any(card.name == "Grizzly Bears" for card in scenario.game.player("bob").graveyard)


def test_aunties_sentence_off_set_reveals_and_discards_a_chosen_nonland_permanent_card() -> None:
    """Auntie's Sentence (not in this pool, not the reported card): mode
    one, "Target opponent reveals their hand. You choose a nonland permanent
    card from it. That player discards that card." - the identical reveal-
    choose-discard shape Solve for Disappointment's own S1 Empower Jace
    report handed over, restricted to a permanent card specifically
    (Grizzly Bears, not Opt).

    Solve for Disappointment itself prints the same sentence, but as one
    paragraph beside its own "Empower Jace 1." line (CR-unlisted -
    `knowledge_search`/`mise run rules:find` turned up nothing under
    "Empower" at all) - a second, independent ability this session does not
    build, and reading the whole card's printed text as one CR 608.2c
    instruction sequence fails it closed rather than running the discard and
    silently dropping the rest. Auntie's Sentence is a genuine off-set proof
    of the discard shape alone, free of that complication.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Auntie's Sentence"], battlefield=["Swamp", "Swamp"])
        .player("bob", hand=["Grizzly Bears", "Opt"], battlefield=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears_in_hand = scenario.find("Grizzly Bears", Zone.HAND, "bob")
    scenario.will_choose_cards(bears_in_hand, source="Auntie's Sentence")

    casting = scenario.cast("Auntie's Sentence")
    casting.choose_modes([1])
    casting.choose_targets(["bob"])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Swamp", "Swamp"))
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    bob_hand_names = [card.name for card in scenario.game.player("bob").hand]
    assert "Grizzly Bears" not in bob_hand_names
    assert "Opt" in bob_hand_names
    assert any(card.name == "Grizzly Bears" for card in scenario.game.player("bob").graveyard)


def test_ajanis_anguish_deals_x_damage_and_grants_trample() -> None:
    """ "When this enchantment enters, it deals X damage to any target.
    Creatures you control have trample." - CR 107.3m's own X substitution
    (this session's fix) into an ETB trigger, plus an unrelated static
    keyword grant on the same card.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Ajani's Anguish"],
            battlefield=["Mountain", "Mountain", "Mountain", "Mountain", "Grizzly Bears"],
        )
        .player("bob", battlefield=["Serra Angel"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.creature("Serra Angel", "bob")
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.choose_trigger_targets("Ajani's Anguish", [angel])

    casting = scenario.cast("Ajani's Anguish")
    casting.x_value = 3
    payment = casting.begin_paying()
    scenario.pay_with(
        payment, *scenario.untapped_sources("Mountain", "Mountain", "Mountain", "Mountain")
    )
    scenario.put_on_stack(casting)
    scenario.resolve_top()  # the enchantment resolves onto the battlefield,
    # queuing the enters trigger with its target already chosen above
    scenario.resolve_top()  # the enters trigger

    assert angel.damage == 3
    assert has_keyword(bears, Keyword.TRAMPLE, scenario.game)
