"""EP-01 round 1 integration: seven abilities the behavioural sweep could not
stage, each proven here by playing the real event through the engine."""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _main(**players) -> "object":
    builder = Scenario()
    for username, kwargs in players.items():
        builder = builder.player(username, **kwargs)
    scenario = builder.build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _trigger_names(scenario) -> list[str]:
    scenario.game.put_triggers_on_stack()
    return scenario.stack_names()


def test_bioessence_hydra_grows_when_loyalty_counters_go_on_a_planeswalker():
    scenario = _main(alice={"battlefield": ["Bioessence Hydra", "Jace Beleren"]})
    walker = scenario.find("Jace Beleren", Zone.BATTLEFIELD)
    scenario.game.add_counters(walker, "loyalty", 2, putter="alice")
    assert _trigger_names(scenario) == ["Bioessence Hydra's triggered ability"]
    scenario.resolve_top()
    hydra = scenario.find("Bioessence Hydra", Zone.BATTLEFIELD)
    assert hydra.counter_count("+1/+1") == 2


def test_nine_lives_exiles_itself_at_nine_incarnation_counters():
    scenario = _main(alice={"battlefield": ["Nine Lives"]})
    lives = scenario.find("Nine Lives", Zone.BATTLEFIELD)
    scenario.game.add_counters(lives, "incarnation", 8, putter="alice")
    assert _trigger_names(scenario) == []
    scenario.game.add_counters(lives, "incarnation", 1, putter="alice")
    assert _trigger_names(scenario) == ["Nine Lives's triggered ability"]


def _end_step_triggers(*auras: str) -> list[str]:
    scenario = _main(alice={"battlefield": ["Kitsune Mystic", *auras]})
    mystic = scenario.creature("Kitsune Mystic", "alice")
    for aura in auras:
        scenario.find(aura, Zone.BATTLEFIELD).attach_to(mystic)
    while scenario.step is not Step.END_STEP:
        scenario.advance()
    return _trigger_names(scenario)


def test_kitsune_mystic_flips_at_end_step_with_two_auras():
    assert _end_step_triggers("Rancor", "Writ of Passage") == ["Kitsune Mystic's triggered ability"]


def test_kitsune_mystic_stays_put_with_one_aura():
    assert _end_step_triggers("Rancor") == []


REIDANE = "Reidane, God of the Worthy // Valkmira, Protector's Shield"


def _valkmira_in_play(**bob):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[REIDANE],
            battlefield=["Plains"] * 4 + ["Grizzly Bears"],
        )
        .player("bob", **bob)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    casting = scenario.cast(REIDANE, "alice")
    casting.cast_as_split_half("Valkmira, Protector's Shield")
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources(*["Plains"] * 4, username="alice"))
    scenario.put_on_stack(casting)
    scenario.resolve_top()
    return scenario


def test_valkmira_counters_a_bolt_aimed_at_its_controllers_other_permanent():
    scenario = _valkmira_in_play(hand=["Lightning Bolt"], battlefield=["Mountain"])
    scenario.pass_priority("alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.cast_onto_stack(
        "Lightning Bolt",
        *scenario.untapped_sources("Mountain", username="bob"),
        username="bob",
        targets=[bears],
    )
    assert scenario.stack_names() == [
        "Lightning Bolt",
        "Valkmira, Protector's Shield's triggered ability",
    ]


def test_valkmira_also_answers_a_spell_aimed_at_its_controller():
    scenario = _valkmira_in_play(hand=["Lightning Bolt"], battlefield=["Mountain"])
    scenario.pass_priority("alice")
    scenario.cast_onto_stack(
        "Lightning Bolt",
        *scenario.untapped_sources("Mountain", username="bob"),
        username="bob",
        targets=["alice"],
    )
    assert scenario.stack_names() == [
        "Lightning Bolt",
        "Valkmira, Protector's Shield's triggered ability",
    ]


def _tentacle_on_bobs_turn():
    """The Watcher's own first trigger makes the Tentacle: alice draws on bob's
    turn (CR 603.2)."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["The Watcher in the Water", "Kraken of the Straits"],
            library=["Forest"] * 6,
        )
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain"], library=["Forest"] * 6)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    while scenario.game.active_player.username != "bob" or scenario.step is not Step.PRECOMBAT_MAIN:
        scenario.game.put_triggers_on_stack()
        while scenario.game.stack:
            scenario.resolve_top()
        scenario.advance()
    scenario.draw(1, "alice")
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()
    return scenario


def test_the_watchers_tentacle_dying_triggers_its_untap_and_stun():
    scenario = _tentacle_on_bobs_turn()
    tentacle = scenario.creature("Tentacle Token", "alice")
    scenario.game.destroy(tentacle)
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == ["The Watcher in the Water's triggered ability"]


def test_the_watchers_tentacle_needs_the_draw_to_be_yours_on_their_turn():
    scenario = (
        Scenario()
        .player("alice", battlefield=["The Watcher in the Water"], library=["Forest"] * 6)
        .player("bob", library=["Forest"] * 6)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    assert scenario.game.active_player.username == "alice"
    scenario.draw(1, "alice")
    scenario.draw(1, "bob")
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == []


def _mimeoplasm_with_an_exiled_creature():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Mimeoplasm, Revered One"],
            graveyard=["Serra Angel"],
            battlefield=["Island", "Swamp", "Forest", "Forest", "Island", "Mountain"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    casting = scenario.cast("Mimeoplasm, Revered One")
    casting.determine_cost(x_value=1)
    scenario.will_choose_cards(
        *scenario.player("alice").graveyard[:1], source="Mimeoplasm, Revered One"
    )
    scenario.auto_pay(casting.begin_paying(), username="alice")
    scenario.put_on_stack(casting)
    scenario.resolve_top()
    return scenario


def test_mimeoplasm_becomes_a_copy_of_the_creature_card_exiled_with_it():
    scenario = _mimeoplasm_with_an_exiled_creature()
    mimeoplasm = scenario.find("Mimeoplasm, Revered One", Zone.BATTLEFIELD, "alice")
    angel = scenario.find("Serra Angel", Zone.EXILE)
    scenario.activate(mimeoplasm, auto=True, targets=[angel])
    scenario.resolve_top()
    chars = scenario.game.characteristics_of(mimeoplasm)
    assert chars.name == "Serra Angel"
    assert (chars.power, chars.toughness) == (3, 3)


def _rivendell_scry_available(*battlefield: str) -> bool:
    scenario = _main(alice={"battlefield": ["Rivendell", "Island", *battlefield]})
    rivendell = scenario.find("Rivendell", Zone.BATTLEFIELD)
    return scenario.why_cannot_activate(rivendell, 1) is None


def test_rivendell_scry_needs_a_legendary_creature():
    assert _rivendell_scry_available("Kor Firewalker", "Thrasta, Tempest's Roar")
    assert not _rivendell_scry_available("Grizzly Bears")


def test_valkmira_ignores_a_spell_aimed_at_the_opponents_own_permanent():
    scenario = _valkmira_in_play(hand=["Lightning Bolt"], battlefield=["Mountain", "Grizzly Bears"])
    scenario.pass_priority("alice")
    scenario.cast_onto_stack(
        "Lightning Bolt",
        *scenario.untapped_sources("Mountain", username="bob"),
        username="bob",
        targets=[scenario.creature("Grizzly Bears", "bob")],
    )
    assert scenario.stack_names() == ["Lightning Bolt"]
