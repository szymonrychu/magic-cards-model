"""Scenario: every `ContinuousEffect` selector/modification/count/condition
union member, round-tripped through `Game.model_dump(mode="json")` /
`model_validate`.

This is the acceptance test for the engine-stateless-library plan's headline
fix: `Game.model_dump(mode="json")` used to raise `PydanticSerializationError:
Unable to serialize unknown type: <class 'function'>` for any game where a
pump spell or an "until end of turn" effect had resolved, because
`ContinuousEffect.selector`/`.modification`/`.condition` were plain Python
closures. `machines/layers.py` now stores each as a frozen,
`kind`-discriminated pydantic model instead, and this file is the proof: one
real printing per union member, resolved through the real engine, dumped,
decoded back into a fresh `Game`, and recomputed - the resulting
`ComputedBoard.characteristics` and `Journal.applied` order must be identical
to the pre-dump game, because the design's whole argument is that a decoded
game is byte-for-byte the same machine as the one that made it, not merely one
that looks the same.

Every union member is covered somewhere in this file, but not every member
gets its own test function - a real card often produces several members in one
resolution (Elesh Norn alone produces `OtherCreaturesControlledBy` and
`CreaturesControlledByOpponentsOf`; Mishra's Factory alone produces
`SetTypesAndSubtypes` and `SetPowerToughness`), and each docstring below names
every member the test exercises.

`ReplaceText` is the one member with no real printing behind it: nothing in
this pool's parser wires CR 612's text-changing effects into it (`grep
replace_text\\(` finds no caller at all), so `tests/test_layers.py`'s own
`test_replace_text_round_trips_at_the_model_level` covers it at the bare-model
level instead - see that test's docstring for why a scenario is not possible
for this one member.

Most of the board setups here are lifted from an existing, already-CR-verified
scenario file (named in each docstring) rather than invented fresh, so this
file adds no new claim about what a card's text means - only that the engine
still agrees with itself about it after a round trip.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.keywords import crew_activation
from magic_cards_model.models import Zone
from magic_cards_model.models.game import Game
from tests.scenarios.harness import PlayedScenario, Scenario


def assert_decodes_identically(scenario: Scenario | PlayedScenario) -> None:
    """Dump `scenario.game`, decode it back, and check the two things a
    decoded `ContinuousEffect` must reproduce exactly for this design to be
    sound at all: the computed board, and the order effects applied in.

    `before` is *computed*, not merely read, so `ContinuousEffects.entered`
    and `.clock` are baked into the snapshot exactly as a real game leaves
    them - the same reason `Game.computed_board`'s own docstring gives for why
    a graveyard-reading CDA needs the board computed before it is trusted.

    If `after.journal.applied` ever differs from `before.journal.applied`,
    that means some effect's behaviour depended on Python object identity or
    closure state the pydantic model does not capture - the design's own
    stop-and-report case, not something to paper over here.
    """
    game = scenario.game
    before = game.computed_board()
    dumped = game.model_dump(mode="json")
    restored = Game.model_validate(dumped)
    after = restored.computed_board()

    assert after.characteristics == before.characteristics
    assert after.journal.applied == before.journal.applied


# --------------------------------------------------------------------------
# Resolution effects (CR 611.2): OnlyThisIncarnation, ModifyPowerToughness,
# SameNameAs, SwitchPowerToughness, SetController, BecomeACopy
# --------------------------------------------------------------------------


def test_giant_growth_round_trips():
    """`OnlyThisIncarnation` + `ModifyPowerToughness` - the headline fix this
    whole task exists for: this exact shape used to make `model_dump(mode=
    "json")` raise.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Giant Growth"], battlefield=["Grizzly Bears", "Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    (forest,) = scenario.untapped_sources("Forest")
    scenario.cast_and_resolve("Giant Growth", forest, targets=[bears])

    assert scenario.game.computed_board().of(bears).power_toughness == (5, 5)
    assert_decodes_identically(scenario)


def test_echoing_courage_round_trips():
    """`SameNameAs` - "target creature and all other creatures with the same
    name as that creature get +2/+2 until end of turn", against two identical
    Grizzly Bears.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Echoing Courage"],
            battlefield=["Grizzly Bears", "Grizzly Bears", "Forest", "Forest"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    target, other = scenario.creatures("Grizzly Bears", "Grizzly Bears", username="alice")
    forests = scenario.untapped_sources("Forest", "Forest")
    scenario.cast_and_resolve("Echoing Courage", *forests, targets=[target])

    board = scenario.game.computed_board()
    assert board.of(target).power_toughness == (4, 4)
    assert board.of(other).power_toughness == (4, 4), "same name, not the same target"
    assert_decodes_identically(scenario)


def test_twisted_image_round_trips():
    """`SwitchPowerToughness` (sublayer 7d) on a Ragavan (2/1)."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Twisted Image"],
            library=["Forest"],
            battlefield=["Ragavan, Nimble Pilferer", "Island"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ragavan = scenario.creature("Ragavan, Nimble Pilferer", "alice")
    islands = scenario.untapped_sources("Island")
    scenario.cast_and_resolve("Twisted Image", *islands, targets=[ragavan])

    assert scenario.game.computed_board().of(ragavan).power_toughness == (1, 2)
    assert_decodes_identically(scenario)


def test_threaten_round_trips():
    """`SetController` + `GrantAbility` ("gains haste"), on an opponent's
    creature - the only shape in this file that changes who controls a
    permanent.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Threaten"], battlefield=["Mountain", "Mountain", "Mountain"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    mountains = scenario.untapped_sources("Mountain", "Mountain", "Mountain")
    scenario.cast_and_resolve("Threaten", *mountains, targets=[bears])

    board = scenario.game.computed_board()
    assert board.of(bears).controller == "alice"
    assert board.of(bears).has_ability("Haste")
    assert_decodes_identically(scenario)


def test_mother_of_runes_round_trips():
    """`Only` (built by hand in `effects.py`, not through the text-driven
    registry) + `GrantAbility`, with the granted text itself fixed at
    resolution (the chosen colour), not re-derived on decode.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Mother of Runes", "Forest"])
        .player("bob", battlefield=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    runes = scenario.creature("Mother of Runes", "alice")
    scenario.will_choose("R", source="Mother of Runes")
    scenario.activate(runes, targets=[runes])
    scenario.resolve_top()

    board = scenario.game.computed_board()
    assert board.of(runes).has_ability("Protection from red")
    assert_decodes_identically(scenario)


def test_the_mycosynth_gardens_round_trips():
    """`BecomeACopy` - the land's computed characteristics become Sol Ring's,
    stored as resolved values rather than a live reference to Sol Ring's own
    `CardState`.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["The Mycosynth Gardens", "Forest", "Sol Ring"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    gardens = scenario.find("The Mycosynth Gardens", Zone.BATTLEFIELD)
    sol_ring = scenario.find("Sol Ring", Zone.BATTLEFIELD)
    (forest,) = scenario.untapped_sources("Forest")
    scenario.activate(gardens, forest, index=2, targets=[sol_ring], x_value=1)
    scenario.resolve_top()

    characteristics = scenario.game.characteristics_of(gardens)
    assert characteristics.name == "Sol Ring"
    assert_decodes_identically(scenario)


def test_mishras_factory_round_trips():
    """`SetTypesAndSubtypes` + `SetPowerToughness` - one activated ability
    landing in two layers at once (CR 613.6).
    """
    scenario = (
        Scenario().player("alice", battlefield=["Mishra's Factory", "Mishra's Factory"]).build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    factory, other = scenario.creatures("Mishra's Factory", "Mishra's Factory", username="alice")
    scenario.activate(factory, other, index=1)
    scenario.resolve_top()

    board = scenario.game.computed_board()
    assert board.of(factory).is_creature
    assert board.of(factory).power_toughness == (2, 2)
    assert_decodes_identically(scenario)


def test_wild_mongrels_pump_round_trips():
    """`ModifyPowerToughness` + `SetColors`, both built by hand in
    `effects.py` (the chosen-colour shape, not the text-driven registry).
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Grizzly Bears"], battlefield=["Wild Mongrel", "Forest", "Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mongrel = scenario.creature("Wild Mongrel", "alice")
    bears = scenario.find("Grizzly Bears", Zone.HAND, "alice")
    scenario.will_choose("U", source="Wild Mongrel")
    scenario.activate(mongrel, discarding=[bears])
    scenario.resolve_top()

    board = scenario.game.computed_board()
    assert board.of(mongrel).power_toughness == (3, 3)
    assert "U" in board.of(mongrel).colors
    assert_decodes_identically(scenario)


# --------------------------------------------------------------------------
# Static abilities (CR 611.3): rebuilt fresh from the decoded battlefield -
# the round trip proves the decoded `CardState`s still drive the parser to
# the identical builder.
# --------------------------------------------------------------------------


def test_humility_round_trips():
    """`EveryCreature` + `LoseAllAbilities` + `SetPowerToughness`."""
    scenario = Scenario().player("alice", battlefield=["Humility", "Grizzly Bears"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    board = scenario.game.computed_board()
    bears = scenario.creature("Grizzly Bears", "alice")
    assert board.of(bears).power_toughness == (1, 1)
    assert board.of(bears).abilities == ()
    assert_decodes_identically(scenario)


def test_opalescence_round_trips():
    """`OtherNonAuraEnchantments` + `AddType` + `SetPowerToughnessToManaValue`."""
    scenario = Scenario().player("alice", battlefield=["Opalescence", "Glorious Anthem"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    board = scenario.game.computed_board()
    anthem = scenario.find("Glorious Anthem", Zone.BATTLEFIELD)
    assert board.of(anthem).is_creature
    assert_decodes_identically(scenario)


def test_glorious_anthem_round_trips():
    """`CreaturesControlledBy` (the plain anthem, no qualifiers)."""
    scenario = Scenario().player("alice", battlefield=["Glorious Anthem", "Grizzly Bears"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    bears = scenario.creature("Grizzly Bears", "alice")
    assert scenario.game.computed_board().of(bears).power_toughness == (3, 3)
    assert_decodes_identically(scenario)


def test_elesh_norn_round_trips():
    """`OtherCreaturesControlledBy` + `CreaturesControlledByOpponentsOf`, both
    from the one card's two anthem sentences.

    The two sentences share one timestamp (both static, both off the same
    permanent) and select disjoint sets, so CR 613.8a finds no dependency
    between them and CR 613 does not order them against each other - but the
    engine still has to pick something stable (`ContinuousEffect.order`, the
    order the sentences are written on the card), so `Journal.applied` order
    is asserted exactly, decode or no decode.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Elesh Norn, Grand Cenobite", "Grizzly Bears"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    board = scenario.game.computed_board()
    mine = scenario.creature("Grizzly Bears", "alice")
    theirs = scenario.creature("Grizzly Bears", "bob")
    assert board.of(mine).power_toughness == (4, 4)
    assert board.of(theirs).power_toughness == (0, 0)

    game = scenario.game
    before = game.computed_board()
    restored = Game.model_validate(game.model_dump(mode="json"))
    after = restored.computed_board()
    assert after.characteristics == before.characteristics
    assert after.journal.applied == before.journal.applied


def test_ygra_round_trips():
    """`OtherCreatures` + `AddTypesAndSubtype` + `GrantAbility` (quoted)."""
    scenario = (
        Scenario().player("alice", battlefield=["Ygra, Eater of All", "Grizzly Bears"]).build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    board = scenario.game.computed_board()
    bears = scenario.creature("Grizzly Bears", "alice")
    ygra = scenario.creature("Ygra, Eater of All", "alice")
    assert "Food" in board.of(bears).subtypes
    assert "Food" not in board.of(ygra).subtypes, 'Ygra excludes herself ("other")'
    assert_decodes_identically(scenario)


def test_dryad_of_the_ilysian_grove_round_trips():
    """`LandsControlledBy` + `AddBasicLandTypes`."""
    scenario = (
        Scenario().player("alice", battlefield=["Dryad of the Ilysian Grove", "Mountain"]).build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    mountain = scenario.find("Mountain", Zone.BATTLEFIELD)
    board = scenario.game.computed_board()
    assert "Island" in board.of(mountain).subtypes
    assert_decodes_identically(scenario)


def test_blood_moon_round_trips():
    """`NonbasicLands` + `SetBasicLandType`."""
    scenario = Scenario().player("alice", battlefield=["Blood Moon", "Tinder Farm"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    farm = scenario.find("Tinder Farm", Zone.BATTLEFIELD)
    board = scenario.game.computed_board()
    assert board.of(farm).subtypes == ("Mountain",)
    assert_decodes_identically(scenario)


def test_urborg_round_trips():
    """`EveryLand` + `AddSubtype`."""
    scenario = (
        Scenario().player("alice", battlefield=["Urborg, Tomb of Yawgmoth", "Mountain"]).build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    mountain = scenario.find("Mountain", Zone.BATTLEFIELD)
    board = scenario.game.computed_board()
    assert "Swamp" in board.of(mountain).subtypes
    assert_decodes_identically(scenario)


def test_fecund_greenshells_gate_round_trips():
    """`QualifiedCreatures`, exercising `gate_card_type`/`gate_threshold`."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Fecund Greenshell", "Grizzly Bears"] + ["Forest"] * 10)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    bears = scenario.creature("Grizzly Bears", "alice")
    board = scenario.game.computed_board()
    assert board.of(bears).power_toughness == (4, 4)
    assert_decodes_identically(scenario)


def test_leyline_of_the_guildpact_round_trips():
    """`AllPermanentsControlledBy` + `SetColors` (its second line - the first
    line's `LandsControlledBy` + `AddBasicLandTypes` is already exercised by
    `test_dryad_of_the_ilysian_grove_round_trips`, the identical sentence).
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Leyline of the Guildpact", "Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    bears = scenario.creature("Grizzly Bears", "alice")
    board = scenario.game.computed_board()
    assert len(board.of(bears).colors) == 5
    assert_decodes_identically(scenario)


def test_toph_round_trips():
    """`PermanentsControlledBy` + `AddType`."""
    scenario = (
        Scenario().player("alice", battlefield=["Toph, the First Metalbender", "Sol Ring"]).build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    sol_ring = scenario.find("Sol Ring", Zone.BATTLEFIELD)
    board = scenario.game.computed_board()
    assert board.of(sol_ring).is_land
    assert_decodes_identically(scenario)


def test_stormscale_scion_round_trips():
    """`CreaturesControlledByWithSubtype`."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Stormscale Scion", "Archive Dragon", "Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    dragon = scenario.creature("Archive Dragon", "alice")
    board = scenario.game.computed_board()
    assert board.of(dragon).power_toughness == (5, 7)
    assert_decodes_identically(scenario)


def test_scion_of_draco_round_trips():
    """`CreaturesControlledByWithColor`.

    Scion of Draco's five colour clauses share one timestamp and select
    disjoint, non-dependent sets (CR 613.8a never pairs them), so CR 613 does
    not order them against each other at all - `_apply_group`'s tiebreak for
    that case is `ContinuousEffect.order`, the order the five clauses are
    written in the card's own oracle text, so `Journal.applied` order is
    identical however many times the board is recomputed, decode or no
    decode.
    """
    scenario = Scenario().player("alice", battlefield=["Scion of Draco", "Savannah Lions"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    lions = scenario.creature("Savannah Lions", "alice")
    board = scenario.game.computed_board()
    assert board.of(lions).has_ability("Vigilance")

    game = scenario.game
    before = game.computed_board()
    restored = Game.model_validate(game.model_dump(mode="json"))
    after = restored.computed_board()
    assert after.characteristics == before.characteristics
    assert after.journal.applied == before.journal.applied


def test_innkeepers_talent_round_trips():
    """`PermanentsControlledByWithCounters` + `GrantAbilityInstance` (ward,
    which never deduplicates - CR 702.21a, CR 113.2c).
    """
    scenario = (
        Scenario().player("alice", battlefield=["Innkeeper's Talent", "Grizzly Bears"]).build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    talent = scenario.find("Innkeeper's Talent", Zone.BATTLEFIELD)
    talent.class_level = 2
    bears = scenario.creature("Grizzly Bears", "alice")
    bears.add_counters("+1/+1", 1)

    board = scenario.game.computed_board()
    assert board.of(bears).abilities.count("Ward {1}") == 1
    assert_decodes_identically(scenario)


def test_tarmogoyf_round_trips():
    """`Only` + `DefinePowerToughness` + `FixedCount`."""
    scenario = (
        Scenario().player("alice", battlefield=["Tarmogoyf"], graveyard=["Lightning Bolt"]).build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    goyf = scenario.creature("Tarmogoyf", "alice")
    board = scenario.game.computed_board()
    assert board.of(goyf).power_toughness == (1, 2)
    assert_decodes_identically(scenario)


def test_nighthawk_scavenger_round_trips():
    """`DefinePower` + a second `FixedCount` (power only, toughness stays
    the printed value).
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Nighthawk Scavenger"])
        .player("bob", graveyard=["Lightning Bolt", "Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scavenger = scenario.creature("Nighthawk Scavenger", "alice")
    board = scenario.game.computed_board()
    assert board.of(scavenger).power == 3  # 1 + two card types (instant, creature)
    assert board.of(scavenger).toughness == 3, "printed, not a CDA"
    assert_decodes_identically(scenario)


def test_allosaurus_rider_round_trips():
    """`DefinePowerToughness` + `CountLandsControlledBy`."""
    scenario = (
        Scenario().player("alice", battlefield=["Allosaurus Rider", "Forest", "Forest"]).build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    rider = scenario.creature("Allosaurus Rider", "alice")
    board = scenario.game.computed_board()
    assert board.of(rider).power_toughness == (3, 3)
    assert_decodes_identically(scenario)


def test_territorial_kavu_round_trips():
    """`DefinePowerToughness` + `CountBasicLandTypesAmongLandsControlledBy`."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Territorial Kavu", "Mountain", "Plains", "Blood Crypt"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    kavu = scenario.creature("Territorial Kavu", "alice")
    board = scenario.game.computed_board()
    assert board.of(kavu).power_toughness == (3, 3)
    assert_decodes_identically(scenario)


def test_relentless_rats_round_trips():
    """`ModifyPowerToughnessPer` + `CountOtherCreaturesNamed`."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Relentless Rats", "Relentless Rats", "Relentless Rats"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    rats = scenario.creatures(
        "Relentless Rats", "Relentless Rats", "Relentless Rats", username="alice"
    )
    board = scenario.game.computed_board()
    for rat in rats:
        assert board.of(rat).power_toughness == (4, 4)
    assert_decodes_identically(scenario)


def test_urzas_saga_construct_round_trips():
    """A second `ModifyPowerToughnessPer` shape, counted with
    `CountPermanentsControlledBy` instead of by name.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Urza's Saga"], battlefield=["Sol Ring"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    saga = scenario.play_land("Urza's Saga")
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()
    scenario.game.saga_lore_step()
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()

    (sol_ring,) = scenario.untapped_sources("Sol Ring")
    scenario.activate(saga, sol_ring, index=1)
    scenario.resolve_top()

    (construct,) = [p for p in scenario.game.battlefield if p.name == "Construct Token"]
    board = scenario.game.computed_board()
    assert board.of(construct).power_toughness == (2, 2)
    assert_decodes_identically(scenario)


def test_vehicle_crew_round_trips():
    """`Only` + `AddType`, built in `machines/keywords.py` rather than
    `machines/layers.py` - the same models, a different caller.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[
                "Consulate Dreadnought",
                "Grizzly Bears",
                "Grizzly Bears",
                "Grizzly Bears",
            ],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    vehicle = scenario.find("Consulate Dreadnought", Zone.BATTLEFIELD)
    bears = scenario.creatures("Grizzly Bears", "Grizzly Bears", "Grizzly Bears", username="alice")
    activation = crew_activation(scenario.game, vehicle, list(bears), "alice")
    activation.begin_paying()
    activation.payment.pay()
    activation.activate()
    activation.resolve()

    board = scenario.game.computed_board()
    assert board.of(vehicle).is_creature
    assert_decodes_identically(scenario)


def test_rancor_round_trips():
    """`Only` (an attached creature's static, not the target-fixed
    incarnation-scoped kind) + `ModifyPowerToughness` + `GrantAbility`.
    """
    scenario = (
        Scenario().player("alice", hand=["Rancor"], battlefield=["Grizzly Bears", "Forest"]).build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    (forest,) = scenario.untapped_sources("Forest")
    scenario.cast_and_resolve("Rancor", forest, targets=[bears])

    board = scenario.game.computed_board()
    assert board.of(bears).power_toughness == (4, 2)
    assert board.of(bears).has_ability("Trample")
    assert_decodes_identically(scenario)


def test_tishanas_tidebinder_round_trips():
    """`RemainsOnBattlefield` - the one `Condition` member, and the reason
    `Condition.holds_in` takes a `Game`: the decoded effect has to look the
    Tidebinder up by id in the *decoded* game, not hold a reference to the
    game that dumped it.
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Vampiric Rites", "Swamp", "Swamp"])
        .player("bob", battlefield=["Tishana's Tidebinder"])
        .build()
    )
    tidebinder = scenario.creature("Tishana's Tidebinder", "bob")
    rites = scenario.creature("Vampiric Rites", "alice")
    ward_text = "{1}{B}, Sacrifice a creature: You gain 1 life and draw a card."
    # `ContinuousEffects.create` mints the effect's own id with no `Game`
    # method's `_id_allocator_scope` open around it here.
    with scenario.game._id_allocator_scope():  # noqa: SLF001
        scenario.game.continuous_effects.create(tidebinder, targets=[rites], game=scenario.game)

    before = scenario.game.computed_board()
    assert not before.of(rites).has_ability(ward_text)
    assert_decodes_identically(scenario)

    dumped = scenario.game.model_dump(mode="json")
    restored = Game.model_validate(dumped)
    restored.destroy(restored.find_by_id(tidebinder.id))
    after = restored.computed_board()
    assert after.of(restored.find_by_id(rites.id)).has_ability(ward_text), (
        "the duration stops running the moment the decoded game's own "
        "Tidebinder leaves - it must not still be reading the id off the "
        "game that was dumped"
    )


def test_same_timestamp_static_effects_apply_in_the_same_order_every_time():
    """`_apply_group`'s tiebreak after timestamp must be stable across a
    repeated `computed_board()` call on one live game - no dump, no decode,
    nothing but calling it twice.

    Scion of Draco's five colour-conditioned grants, and Elesh Norn, Grand
    Cenobite's two anthem lines, are both a static ability generating several
    `ContinuousEffect`s off the same permanent at the same timestamp
    (CR 613.7a: one static ability's whole set of effects shares the
    permanent's timestamp). CR 613.8a finds no dependency between them
    (disjoint selectors), so CR 613.7/613.8 never orders them against each
    other - but the engine still owes a *stable* answer, because
    `Journal.applied` order is part of what a faithful, replayable engine
    reports, not an implementation detail free to vary.

    Before the fix, `_apply_group` tie-broke on `str(effect.id)`, and every
    static effect is minted fresh (a new random id) on every `computed_board()`
    call (CR 613.5 recomputes the whole board from scratch each time) - so
    calling it twice on the *same, unchanged* game, with no serialization
    anywhere in between, produced two different `Journal.applied` orders.
    This asserts the order is identical, as an ordered list, both times.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[
                "Scion of Draco",
                "Elesh Norn, Grand Cenobite",
                "Savannah Lions",
            ],
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    game = scenario.game
    first = game.computed_board()
    second = game.computed_board()
    third = game.computed_board()

    assert second.journal.applied == first.journal.applied
    assert third.journal.applied == first.journal.applied
    assert second.characteristics == first.characteristics
    assert third.characteristics == first.characteristics
