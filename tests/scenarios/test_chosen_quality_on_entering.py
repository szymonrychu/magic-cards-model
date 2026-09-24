""" "As [this] enters, choose a color/card name/creature type." (CR 614.1c,
CR 614.12a).

CR 614.1c: "Effects that read '... As [this permanent] enters ...' are
replacement effects." CR 614.12a: "If a replacement effect that modifies how
a permanent enters the battlefield requires a choice, that choice is made
before the permanent enters the battlefield."

Before this file, `machines/replacement._self_enters_modifiers` performed
exactly one `AS_ENTERS` shape - the shockland's pay-life-or-tapped choice -
and every other `AS_ENTERS` effect fell out of the loop unperformed, silently.
Nothing on `CardState` stored a chosen color, name, or type, and
`DecisionKind` had no kind for asking. Seven pool cards print this shape and
only three of them choose a color, which is why `CardState.choice` is generic
over `ChoiceKind` rather than a color-only field: a color-only fix would leave
the other four (Runed Halo, Pithing Needle, Disruptor Flute, Cavern of Souls)
exactly as broken as before.

This file covers the choice itself - it is asked, it is answered, it is
recorded before the permanent enters, and a card whose consumer this wave does
not build fails closed with a notice instead of silently doing nothing. The
one consumer this wave *does* build end to end - the mana clause - is
`test_mana_adding_triggers.py`'s file, not this one.
"""

from uuid import uuid4

from magic_cards_model.machines import Step
from magic_cards_model.machines.replacement import UnwiredChoiceNotice
from magic_cards_model.models import Color, Zone
from magic_cards_model.models.card_state import Choice, ChoiceKind
from tests.scenarios.harness import Scenario


def test_a_color_choice_is_recorded_before_the_aura_enters():
    """Utopia Sprawl: the reported card. `Choice.value` is blue's letter code,
    deliberately not green - the Aura sits on a Forest, and a fix that quietly
    defaulted to the enchanted land's own color would still make a
    green-choosing scenario look right.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Utopia Sprawl"], battlefield=["Forest", "Forest"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    payer, forest = scenario.untapped_sources("Forest", "Forest", username="alice")
    scenario.will_choose(Color.BLUE.value, source="Utopia Sprawl")

    sprawl = scenario.cast_and_resolve("Utopia Sprawl", payer, targets=[forest])

    assert sprawl.zone is Zone.BATTLEFIELD
    assert sprawl.choice == Choice(kind=ChoiceKind.COLOR, value=Color.BLUE.value)


def test_a_card_name_choice_is_recorded_before_the_artifact_enters():
    """Pithing Needle: the card-name-choosing shape, unrelated to color."""
    scenario = (
        Scenario()
        .player("alice", hand=["Pithing Needle"], battlefield=["Forest"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (forest,) = scenario.untapped_sources("Forest", username="alice")
    scenario.will_choose("Lightning Bolt", source="Pithing Needle")

    needle = scenario.cast_and_resolve("Pithing Needle", forest)

    assert needle.zone is Zone.BATTLEFIELD
    assert needle.choice == Choice(kind=ChoiceKind.CARD_NAME, value="Lightning Bolt")


def test_a_creature_type_choice_is_recorded_before_the_land_enters():
    """Cavern of Souls: a land, played rather than cast, and the third of the
    three `ChoiceKind`s - proof the choice is not color-shaped underneath.
    """
    scenario = Scenario().player("alice", hand=["Cavern of Souls"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_choose("Zombie", source="Cavern of Souls")

    cavern = scenario.play_land("Cavern of Souls")

    assert cavern.zone is Zone.BATTLEFIELD
    assert cavern.choice == Choice(kind=ChoiceKind.CREATURE_TYPE, value="Zombie")


def test_an_unanswered_color_choice_still_gets_a_legal_answer():
    """CR 608.2d: the player can't choose an option that's illegal or
    impossible, but also can't decline to choose at all - CR 614.12a's choice
    is mandatory. An unscripted scenario still has to end up with *some*
    color recorded rather than nothing.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Utopia Sprawl"], battlefield=["Forest", "Forest"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    payer, forest = scenario.untapped_sources("Forest", "Forest", username="alice")

    sprawl = scenario.cast_and_resolve("Utopia Sprawl", payer, targets=[forest])

    assert sprawl.choice is not None
    assert sprawl.choice.kind is ChoiceKind.COLOR
    assert sprawl.choice.value in {c.value for c in Color}


def test_choosing_a_color_outside_the_five_is_refused():
    """`Game.ask` enforces CR 608.2d's "can't choose an option that's illegal
    or impossible" against `Decision.options` - a color choice is scripted
    against the five colors' letter codes, and anything else is refused
    loudly rather than silently recorded.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Utopia Sprawl"], battlefield=["Forest", "Forest"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    payer, forest = scenario.untapped_sources("Forest", "Forest", username="alice")
    scenario.will_choose("purple", source="Utopia Sprawl")

    try:
        scenario.cast_and_resolve("Utopia Sprawl", payer, targets=[forest])
    except ValueError as error:
        assert "purple" in str(error)
    else:
        raise AssertionError("choosing an illegal color should have raised")


def test_runed_halos_protection_grant_is_not_silently_dropped():
    """Runed Halo: "You have protection from the chosen card name." grants
    protection to a *player*, which `machines/layers.py`'s static-ability
    sweep never reads for any permanent (it is permanent-targeted only) - this
    wave records `UnwiredChoiceNotice` instead of the card doing nothing with
    no trace. See `UnwiredChoiceNotice` for why this consumer is out of scope.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Runed Halo"], battlefield=["Plains", "Plains"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Plains", "Plains", username="alice")
    scenario.will_choose("Lightning Bolt", source="Runed Halo")

    halo = scenario.cast_and_resolve("Runed Halo", *sources)

    assert halo.choice == Choice(kind=ChoiceKind.CARD_NAME, value="Lightning Bolt")
    notices = scenario.game.unwired_choice_notices
    assert any(
        notice.source_id == halo.id and "protection" in notice.text.lower() for notice in notices
    )


def test_pithing_needles_activation_restriction_is_wired_not_noticed():
    """Pithing Needle: "Activated abilities of sources with the chosen name
    can't be activated unless they're mana abilities." used to be recorded as
    an unwired choice; `Game.activation_prohibition` now reads it against the
    recorded name on every activation (CR 602.5), so it is no longer noticed -
    `test_activation_prohibitions.py` is where it is shown doing its job.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Pithing Needle"], battlefield=["Forest"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (forest,) = scenario.untapped_sources("Forest", username="alice")
    scenario.will_choose("Sol Ring", source="Pithing Needle")

    needle = scenario.cast_and_resolve("Pithing Needle", forest)

    assert needle.choice is not None and needle.choice.value == "Sol Ring"
    assert not [
        notice for notice in scenario.game.unwired_choice_notices if notice.source_id == needle.id
    ]


def test_disruptor_flutes_chosen_name_lines_are_both_wired():
    """Disruptor Flute prints *two* lines that read back the chosen name, and
    both are wired now: the cost increase - "Spells with the chosen name cost
    {3} more to cast." - through `CostModifierKind.NAMED_INCREASE`, and the
    activation prohibition through `Game.activation_prohibition`. Neither is
    noticed; a notice for a consumer that works is a false alarm.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Disruptor Flute"], battlefield=["Forest", "Forest"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Forest", "Forest", username="alice")
    scenario.will_choose("Sol Ring", source="Disruptor Flute")

    flute = scenario.cast_and_resolve("Disruptor Flute", *sources)

    assert not [
        notice for notice in scenario.game.unwired_choice_notices if notice.source_id == flute.id
    ]
    # Nor does the wired line come back as an unreadable cost modifier on the
    # other list (DDR#978's own fail-closed record).
    assert not [
        notice for notice in scenario.game.cost_modifier_notices if notice.source_id == flute.id
    ]


def test_cavern_of_souls_restricted_mana_grant_is_not_silently_dropped():
    """Cavern of Souls: "Spend this mana only to cast a creature spell of the
    chosen type, and that spell can't be countered." restricts what a floating
    mana symbol may pay for and grants an uncounterable quality besides -
    `models/mana.ManaPool` carries neither, so this is recorded rather than
    silently dropped.
    """
    scenario = Scenario().player("alice", hand=["Cavern of Souls"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_choose("Zombie", source="Cavern of Souls")

    cavern = scenario.play_land("Cavern of Souls")

    notices = scenario.game.unwired_choice_notices
    assert any(notice.source_id == cavern.id for notice in notices)


def test_voice_of_alls_own_protection_grant_is_wired_with_no_notice():
    """Voice of All: "This creature has protection from the chosen color." is
    permanent-targeted, unlike Runed Halo's player-targeted grant. It used to
    fail closed with a `LayerNotice`; `machines/layers.py`'s
    `_SELF_PROTECTION_FROM_CHOSEN_COLOR_RE` now reads it as a layer 6 grant
    (CR 613.1f) of "Protection from <the chosen colour>", so neither notice
    list carries it - `test_protection_from_chosen_colour.py` covers what the
    protection then does.
    """
    scenario = (
        Scenario()
        .player(
            "alice", hand=["Voice of All"], battlefield=["Plains", "Plains", "Plains", "Plains"]
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Plains", "Plains", "Plains", "Plains", username="alice")
    scenario.will_choose(Color.BLUE.value, source="Voice of All")

    voice = scenario.cast_and_resolve("Voice of All", *sources)
    scenario.state_based_actions()  # force a static-effects recompute

    assert voice.choice == Choice(kind=ChoiceKind.COLOR, value=Color.BLUE.value)
    assert not any(notice.source_id == voice.id for notice in scenario.game.unwired_choice_notices)
    assert not any(
        notice.source_id == voice.id for notice in scenario.game.continuous_effects.layer_notices
    )
    assert scenario.game.characteristics_of(voice).has_ability("Protection from blue")


def test_the_mana_clauses_own_choice_never_gets_an_unwired_notice():
    """Utopia Sprawl's trigger line is the one consumer this wave *does*
    build, and reads "the chosen color" too - it must never show up in
    `unwired_choice_notices` just because the phrase appears on the card.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Utopia Sprawl"], battlefield=["Forest", "Forest"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    payer, forest = scenario.untapped_sources("Forest", "Forest", username="alice")
    scenario.will_choose(Color.BLUE.value, source="Utopia Sprawl")

    sprawl = scenario.cast_and_resolve("Utopia Sprawl", payer, targets=[forest])

    assert not any(notice.source_id == sprawl.id for notice in scenario.game.unwired_choice_notices)


def test_the_chosen_color_mana_ability_never_gets_an_unwired_notice():
    """Room of Refuge's own "{T}: Add one mana of the chosen color." is the
    second consumer this wave builds end to end (`ManaAbility.uses_chosen_
    color`, bound against `CardState.choice`) - it must never show up in
    `unwired_choice_notices` just because the phrase appears on the card,
    the identical false positive `test_the_mana_clauses_own_choice_never_
    gets_an_unwired_notice` already guards for Utopia Sprawl's own "adds an
    additional" shape.
    """
    scenario = Scenario().player("alice", hand=["Room of Refuge"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_choose("R", source="Room of Refuge")

    land = scenario.play_land("Room of Refuge", "alice")

    assert land.choice == Choice(kind=ChoiceKind.COLOR, value="R")
    assert not any(notice.source_id == land.id for notice in scenario.game.unwired_choice_notices)


def test_sunken_citadels_own_chosen_color_mana_abilities_never_get_an_unwired_notice():
    """Off-set proof: Sunken Citadel, real, non-fra, not the reported card,
    printing the identical shape on *two* mana abilities at once (a plain
    "Add one mana of the chosen color" and a restricted "Add two mana of the
    chosen color. Spend this mana only to activate abilities of land
    sources.") - both must stay clear of the notice list."""
    scenario = Scenario().player("alice", hand=["Sunken Citadel"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_choose("G", source="Sunken Citadel")

    land = scenario.play_land("Sunken Citadel", "alice")

    assert land.choice == Choice(kind=ChoiceKind.COLOR, value="G")
    assert not any(notice.source_id == land.id for notice in scenario.game.unwired_choice_notices)


def test_unwired_choice_notice_is_importable_and_shaped_as_documented():
    """A narrow smoke test on the notice's own shape, so a refactor that
    silently drops a field is caught here rather than only in the assertions
    above that read `.text`.
    """
    notice = UnwiredChoiceNotice(
        source_id=uuid4(),
        source_name="Runed Halo",
        text="You have protection from the chosen card name.",
    )
    assert notice.source_name == "Runed Halo"
    assert "chosen card name" in notice.text
