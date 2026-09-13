"""Additional costs on a spell cast during resolution (CR 608.2g, 601.2b, 601.2f).

CR 601.2b: "If the spell has alternative or additional costs that will be paid
as it's being cast such as buyback or kicker costs (see rules 118.8 and
118.9), the player announces their intentions to pay any or all of those
costs". CR 601.2f: "The total cost is the mana cost or alternative cost (as
determined in rule 601.2b), plus all additional costs and cost increases".
"Without paying its mana cost" is an alternative cost (CR 118.9), so a kicker
(CR 702.33a: "You may pay an additional [cost] as you cast this spell") is
still offered on top of it, and a mandatory additional cost (CR 118.8) still
has to be paid - CR 118.3: "A player can't pay a cost without having the
necessary resources to pay it fully", so a spell whose mandatory cost cannot
be paid cannot be cast at all.

Every cast here is a cascade hit (`Game.cast_during_resolution`). The optional
family is each shape the engine announces: kicker (Burst Lightning), offspring
(Thundertrap Trainer, CR 702.175a), gift (Crumb and Get It, CR 702.174a),
blight (Requiting Hex, CR 701.68a), replicate (Gigadrowse, CR 702.56a) and
escalate (Collective Brutality, CR 702.120a); the mandatory one is Fling's
sacrifice. Crumb and Get It, Gigadrowse, Collective Brutality and Fling are
off the deck pool; Burst Lightning, Thundertrap Trainer and Requiting Hex are
pool cards.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import DecisionKind
from magic_cards_model.machines.modes import modal_profile
from magic_cards_model.models import Zone
from tests.cards import card
from tests.scenarios.harness import Scenario


def elf_board(hit: str, *, extra: tuple[str, ...] = (), battlefield: tuple[str, ...] = (), hand=()):
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Bloodbraid Elf", *hand],
            library=[hit],
            battlefield=["Forest", "Mountain", "Forest", "Mountain", *extra, *battlefield],
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )


def cast_elf(scenario):
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_take_the_may(True, source="Bloodbraid Elf")
    first_four = scenario.untapped_sources("Forest", "Mountain", "Forest", "Mountain")
    scenario.cast_onto_stack("Bloodbraid Elf", *first_four)
    return first_four


def spell(scenario, name):
    return next(state for state in scenario.game.stack if getattr(state, "name", None) == name)


def asked(scenario, kind, source):
    return [q for q in scenario.questions_asked() if q.kind is kind and q.source == source]


# -- kicker (CR 702.33a) -------------------------------------------------------


def test_the_kicker_is_offered_and_paid_on_a_cascaded_burst_lightning():
    scenario = elf_board("Burst Lightning", extra=("Mountain",) * 4)
    cast_elf(scenario)
    scenario.will_take_the_may(True, source="Burst Lightning")
    scenario.will_choose_targets("bob", source="Burst Lightning")

    scenario.resolve_top()  # the cascade trigger

    bolt = spell(scenario, "Burst Lightning")
    assert scenario.game.cast_record_of(bolt).kicked == 1
    assert all(land.tapped for land in scenario.game.battlefield if land.card.is_land)
    scenario.resolve_top()
    assert scenario.player("bob").life == 16


def test_declining_the_kicker_casts_it_unkicked_for_nothing():
    scenario = elf_board("Burst Lightning", extra=("Mountain",) * 4)
    cast_elf(scenario)
    scenario.will_take_the_may(False, source="Burst Lightning")
    scenario.will_choose_targets("bob", source="Burst Lightning")

    scenario.resolve_top()

    bolt = spell(scenario, "Burst Lightning")
    assert scenario.game.cast_record_of(bolt).kicked == 0
    assert len(scenario.untapped_sources(*["Mountain"] * 4)) == 4
    scenario.resolve_top()
    assert scenario.player("bob").life == 18


def test_a_kicker_the_caster_cannot_pay_is_offered_as_an_illegal_yes():
    """CR 118.3 and CR 608.2d: with no mana left the "yes" is impossible, so
    the unscripted caster casts it unkicked rather than failing the cast."""
    scenario = elf_board("Burst Lightning")
    cast_elf(scenario)
    scenario.will_choose_targets("bob", source="Burst Lightning")

    scenario.resolve_top()

    (question,) = asked(scenario, DecisionKind.MAY, "Burst Lightning")
    assert question.affirmative_is_legal is False
    assert scenario.game.cast_record_of(spell(scenario, "Burst Lightning")).kicked == 0


# -- the rest of the optional family ------------------------------------------


def test_offspring_is_offered_on_a_cast_during_resolution():
    scenario = elf_board("Thundertrap Trainer", extra=("Island",) * 4)
    cast_elf(scenario)
    scenario.will_take_the_may(True, source="Thundertrap Trainer")

    scenario.resolve_top()

    trainer = spell(scenario, "Thundertrap Trainer")
    assert scenario.game.cast_record_of(trainer).offspring_paid is True
    assert not scenario.untapped_sources()


def test_a_gift_is_promised_to_the_only_opponent():
    scenario = elf_board("Crumb and Get It", battlefield=("Llanowar Elves",))
    elves = scenario.find("Llanowar Elves", Zone.BATTLEFIELD, "alice")
    cast_elf(scenario)
    scenario.will_take_the_may(True, source="Crumb and Get It")
    scenario.will_choose_targets(elves, source="Crumb and Get It")

    scenario.resolve_top()

    record = scenario.game.cast_record_of(spell(scenario, "Crumb and Get It"))
    assert record.gift_promised is True
    assert record.gift_chosen_player == "bob"


def test_blight_puts_the_counter_on_the_chosen_creature():
    scenario = elf_board("Requiting Hex", battlefield=("Llanowar Elves",))
    elves = scenario.find("Llanowar Elves", Zone.BATTLEFIELD, "alice")
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "bob")
    cast_elf(scenario)
    scenario.will_take_the_may(True, source="Requiting Hex")
    scenario.will_choose_cards(elves, source="Requiting Hex")
    scenario.will_choose_targets(bears, source="Requiting Hex")

    scenario.resolve_top()

    assert scenario.game.cast_record_of(spell(scenario, "Requiting Hex")).blight_paid is True
    scenario.state_based_actions()
    assert elves.zone is Zone.GRAVEYARD, "a 1/1 with a -1/-1 counter (CR 704.5f)"
    scenario.resolve_top()
    assert bears.zone is Zone.GRAVEYARD
    assert scenario.player("alice").life == 22


def test_replicate_is_paid_as_many_times_as_the_caster_can():
    """CR 702.56a's "any number of times", bounded by CR 118.3: two spare
    Islands pay {U} twice, and a third "yes" would be impossible."""
    scenario = elf_board("Gigadrowse", extra=("Island", "Island"))
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "bob")
    cast_elf(scenario)
    scenario.will_choose_targets(bears, source="Gigadrowse", times=None)

    scenario.resolve_top()

    assert scenario.game.cast_record_of(spell(scenario, "Gigadrowse")).replicated == 2
    offers = asked(scenario, DecisionKind.MAY, "Gigadrowse")
    assert [q.affirmative_is_legal for q in offers[:3]] == [True, True, False]


def test_escalate_is_charged_for_each_mode_beyond_the_first():
    modes = [mode.text for mode in modal_profile(card("Collective Brutality")).modes]
    scenario = elf_board("Collective Brutality", hand=("Island",))
    island = scenario.find("Island", Zone.HAND, "alice")
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "bob")
    cast_elf(scenario)
    scenario.will_choose_mode(modes[1], source="Collective Brutality")
    scenario.will_choose_mode(modes[2], source="Collective Brutality")
    scenario.will_choose_cards(island, source="Collective Brutality")
    scenario.will_choose_targets(bears, source="Collective Brutality")
    scenario.will_choose_targets("bob", source="Collective Brutality")

    scenario.resolve_top()

    assert island.zone is Zone.GRAVEYARD
    brutality = spell(scenario, "Collective Brutality")
    assert scenario.game.cast_record_of(brutality).modes == [2, 3]
    scenario.resolve_top()
    assert scenario.player("bob").life == 18


# -- a mandatory additional cost (CR 118.8) ------------------------------------


def outburst_board(*battlefield: str):
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Violent Outburst"],
            library=["Fling"],
            battlefield=["Forest", "Mountain", "Forest", *battlefield],
        )
        .player("bob")
        .build()
    )


def cast_outburst(scenario, *, take: bool = True):
    scenario.start_at(Step.PRECOMBAT_MAIN)
    if take:
        scenario.will_take_the_may(True, source="Violent Outburst")
    scenario.cast_onto_stack(
        "Violent Outburst", *scenario.untapped_sources("Forest", "Mountain", "Forest")
    )


def test_flings_sacrifice_is_chosen_while_the_cascade_resolves():
    scenario = outburst_board("Grizzly Bears")
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice")
    cast_outburst(scenario)
    scenario.will_choose_cards(bears, source="Fling")
    scenario.will_choose_targets("bob", source="Fling")

    scenario.resolve_top()

    assert bears.zone is Zone.GRAVEYARD
    assert scenario.stack_names() == ["Violent Outburst", "Fling"]
    scenario.resolve_top()
    assert scenario.player("bob").life == 18


def test_fling_with_nothing_to_sacrifice_cannot_be_cast_and_goes_to_the_bottom():
    """CR 118.3: the mandatory sacrifice cannot be paid, so casting it is not
    an option (CR 608.2d) and it "weren't cast" (CR 702.85a)."""
    scenario = outburst_board()
    cast_outburst(scenario, take=False)

    scenario.resolve_top()

    (question,) = asked(scenario, DecisionKind.MAY, "Violent Outburst")
    assert question.affirmative_is_legal is False
    fling = scenario.find("Fling", Zone.LIBRARY, "alice")
    assert scenario.player("alice").library[-1] is fling
    assert scenario.stack_names() == ["Violent Outburst"]
