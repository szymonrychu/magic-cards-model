"""Enter as a copy, bounded by the mana spent to cast the entering creature.

Mockingbird (Bloomburrow, legal in Modern, Pioneer and Standard - verified
against Scryfall this session): "You may have this creature enter as a copy of
any creature on the battlefield with mana value less than or equal to the
amount of mana spent to cast this creature, except it's a Bird in addition to
its other types and it has flying." Its mana cost is {X}{U}.

The rules this file walks through:

- CR 614.1c - "[This permanent] enters as . . ." is a replacement effect, and
  CR 614.12a makes its choice before the permanent enters.
- CR 601.2h - the total cost is paid, and that payment is the mana "spent to
  cast" it. The Mockingbird ruling (2024-07-26): "Mockingbird's second ability
  counts all mana spent to cast Mockingbird, not just mana spent on {X}."
- CR 202.3 - mana value is the total amount of mana in the mana cost; an {X}
  in the cost of a permanent counts as 0 (the Mockingbird ruling "If the
  copied creature has {X} in its mana cost, X is 0").
- No spell, no spend: a Mockingbird put onto the battlefield without being
  cast had no mana spent to cast it, so the bound is 0.
- CR 707.2 - copiable values are the printed values "as modified by other copy
  effects", so a creature that is itself a copy is copied as what it copies.
- CR 707.9a / CR 707.9b - the Bird type and flying are part of the copy's
  copiable values, so a Clone copying Mockingbird-as-X keeps both.

No mocks: every card is a real printing from the pool.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import DecisionKind
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.cards import card
from tests.scenarios.harness import Scenario


def _cast_mockingbird(scenario, x_value, *source_names, username="alice"):
    """Cast Mockingbird for `x_value`, paying with the named untapped lands."""
    sources = scenario.untapped_sources(*source_names, username=username)
    casting = scenario.cast("Mockingbird", username)
    casting.determine_cost(x_value=x_value)
    payment = casting.begin_paying()
    scenario.pay_with(payment, *sources)
    scenario.put_on_stack(casting)
    return scenario.resolve_top()


def _copy_questions(scenario, source="Mockingbird"):
    return [
        decision
        for decision in scenario.questions_asked()
        if decision.kind is DecisionKind.CHOOSE_CARDS and decision.source == source
    ]


def test_mockingbird_cast_for_two_copies_a_two_drop_and_is_a_flying_bird():
    """X=1: {1}{U}, two mana spent. Grizzly Bears (mana value 2) is offered,
    Serra Angel (mana value 5) is not. The copy is a 2/2 Bear with Bird added
    and flying granted (CR 707.9a, CR 707.9b)."""
    scenario = (
        Scenario()
        .player("alice", hand=["Mockingbird"], battlefield=["Island", "Island", "Grizzly Bears"])
        .player("bob", battlefield=["Serra Angel"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    angel = scenario.creature("Serra Angel", "bob")
    scenario.will_choose_cards(bears, username="alice", source="Mockingbird")

    bird = _cast_mockingbird(scenario, 1, "Island", "Island")

    (question,) = _copy_questions(scenario)
    assert bears.id in question.cards
    assert angel.id not in question.cards
    characteristics = scenario.game.characteristics_of(bird)
    assert characteristics.name == "Grizzly Bears"
    assert (characteristics.power, characteristics.toughness) == (2, 2)
    assert card("Grizzly Bears").type_line.endswith("Bear")
    assert "Bear" in characteristics.subtypes
    assert "Bird" in characteristics.subtypes
    assert "Bard" not in characteristics.subtypes
    assert "Flying" in characteristics.abilities
    assert characteristics.mana_value == 2
    assert scenario.game.unreadable_copy_exception_notices == []


def test_the_bound_is_inclusive_and_counts_every_mana_spent_not_only_x():
    """X=4: {4}{U}, five mana spent - "less than or equal to" admits Serra
    Angel's mana value 5 exactly, which X alone (4) would not."""
    scenario = (
        Scenario()
        .player("alice", hand=["Mockingbird"], battlefield=["Island"] * 5)
        .player("bob", battlefield=["Serra Angel"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.creature("Serra Angel", "bob")
    scenario.will_choose_cards(angel, username="alice", source="Mockingbird")

    bird = _cast_mockingbird(scenario, 4, *["Island"] * 5)

    (question,) = _copy_questions(scenario)
    assert angel.id in question.cards
    characteristics = scenario.game.characteristics_of(bird)
    assert characteristics.name == "Serra Angel"
    assert (characteristics.power, characteristics.toughness) == (4, 4)
    assert "Angel" in characteristics.subtypes and "Bird" in characteristics.subtypes
    # The copy is controlled by alice, not by the copied creature's controller.
    assert bird.controller == "alice"


def test_a_creature_above_the_bound_is_never_offered_and_mockingbird_enters_as_itself():
    """X=0: {U}, one mana spent. Grizzly Bears (2) is out of reach, so there is
    nothing to choose and no question at all - Mockingbird is a 1/1 Bird Bard
    with flying."""
    scenario = (
        Scenario()
        .player("alice", hand=["Mockingbird"], battlefield=["Island", "Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    bird = _cast_mockingbird(scenario, 0, "Island")

    assert _copy_questions(scenario) == []
    characteristics = scenario.game.characteristics_of(bird)
    assert characteristics.name == "Mockingbird"
    assert (characteristics.power, characteristics.toughness) == (1, 1)
    assert characteristics.subtypes == ("Bird", "Bard")


def test_a_mana_value_zero_creature_is_in_reach_of_a_one_mana_mockingbird():
    """X=0 still spends one mana, and Memnite's mana value is 0."""
    scenario = (
        Scenario()
        .player("alice", hand=["Mockingbird"], battlefield=["Island", "Memnite", "Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    memnite = scenario.creature("Memnite", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.will_choose_cards(memnite, username="alice", source="Mockingbird")

    bird = _cast_mockingbird(scenario, 0, "Island")

    (question,) = _copy_questions(scenario)
    assert set(question.cards) == {memnite.id}
    assert bears.id not in question.cards
    characteristics = scenario.game.characteristics_of(bird)
    assert characteristics.name == "Memnite"
    assert "Construct" in characteristics.subtypes and "Bird" in characteristics.subtypes
    assert "Flying" in characteristics.abilities


def test_put_onto_the_battlefield_without_casting_it_the_bound_is_zero():
    """No spell became this permanent, so no mana was spent to cast it: only a
    mana value 0 creature can be copied."""
    scenario = (
        Scenario()
        .player("alice", hand=["Mockingbird"], battlefield=["Memnite", "Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    memnite = scenario.creature("Memnite", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.will_choose_cards(memnite, username="alice", source="Mockingbird")

    bird = scenario.put_onto_battlefield("Mockingbird", "alice")

    (question,) = _copy_questions(scenario)
    assert memnite.id in question.cards
    assert bears.id not in question.cards
    assert scenario.game.characteristics_of(bird).name == "Memnite"


def test_put_onto_the_battlefield_with_only_nonzero_creatures_enters_as_itself():
    scenario = (
        Scenario()
        .player("alice", hand=["Mockingbird"], battlefield=["Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    bird = scenario.put_onto_battlefield("Mockingbird", "alice")

    assert _copy_questions(scenario) == []
    assert scenario.game.characteristics_of(bird).name == "Mockingbird"


def test_declining_the_copy_leaves_a_one_one_flying_bird_bard():
    """The ruling: "You can choose not to have Mockingbird enter as a copy of
    another creature. If you do, it will just be a 1/1 Bird Bard creature with
    flying"."""
    scenario = (
        Scenario()
        .player("alice", hand=["Mockingbird"], battlefield=["Island", "Island", "Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_take_the_may(False, username="alice", source="Mockingbird")

    bird = _cast_mockingbird(scenario, 1, "Island", "Island")

    assert _copy_questions(scenario) == []
    characteristics = scenario.game.characteristics_of(bird)
    assert characteristics.name == "Mockingbird"
    assert (characteristics.power, characteristics.toughness) == (1, 1)
    assert "Flying" in characteristics.abilities


def test_the_copy_does_not_copy_counters_or_tapped_status():
    """CR 707.2: "Other effects ..., status, counters, and stickers are not
    copied." A tapped Memnite with two +1/+1 counters is copied as a plain,
    untapped 1/1."""
    scenario = (
        Scenario()
        .player("alice", hand=["Mockingbird"], battlefield=["Island", "Memnite"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    memnite = scenario.creature("Memnite", "alice")
    memnite.counters.add(Counter.PLUS_ONE, 2)
    memnite.tapped = True
    scenario.will_choose_cards(memnite, username="alice", source="Mockingbird")

    bird = _cast_mockingbird(scenario, 0, "Island")

    assert scenario.game.characteristics_of(bird).name == "Memnite"
    assert bird.tapped is False
    assert bird.counters[Counter.PLUS_ONE] == 0
    assert (scenario.game.power_of(bird), scenario.game.toughness_of(bird)) == (1, 1)


def test_a_copied_enters_with_x_counters_reads_mockingbirds_x_of_zero():
    """Walking Ballista's mana value is 0 on the battlefield (CR 202.3: {X} is
    0 there), so a one-mana Mockingbird reaches it. Its copied "enters with X
    +1/+1 counters" reads CR 107.3m's X of the spell that became this
    permanent - Mockingbird's own X, 0 - so it enters a 0/0 and CR 704.5f puts
    it into the graveyard."""
    scenario = (
        Scenario()
        .player("alice", hand=["Mockingbird"], battlefield=["Island", "Walking Ballista"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ballista = scenario.creature("Walking Ballista", "alice")
    ballista.counters.add(Counter.PLUS_ONE, 2)
    scenario.will_choose_cards(ballista, username="alice", source="Mockingbird")

    bird = _cast_mockingbird(scenario, 0, "Island")

    assert bird.zone is Zone.GRAVEYARD
    assert ballista.zone is Zone.BATTLEFIELD


def test_a_copied_enters_with_x_counters_uses_mockingbirds_own_x():
    """The ruling: "Any 'as [this creature] enters' or '[this creature] enters
    with' abilities of the copied creature will also work." Mockingbird cast
    with X=2 as a copy of Walking Ballista enters with two +1/+1 counters -
    CR 107.3m's X is the value chosen for the spell that became the object."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Mockingbird"],
            battlefield=["Island", "Island", "Island", "Walking Ballista"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ballista = scenario.creature("Walking Ballista", "alice")
    ballista.counters.add(Counter.PLUS_ONE, 1)
    scenario.will_choose_cards(ballista, username="alice", source="Mockingbird")

    bird = _cast_mockingbird(scenario, 2, "Island", "Island", "Island")

    assert bird.zone is Zone.BATTLEFIELD
    assert scenario.game.characteristics_of(bird).name == "Walking Ballista"
    assert bird.counters[Counter.PLUS_ONE] == 2
    assert scenario.game.power_of(bird) == 2


def test_mockingbird_copying_a_clone_copies_what_the_clone_copied():
    """CR 707.2: copiable values are "as modified by other copy effects". The
    ruling: "If the copied creature is copying something else, then Mockingbird
    enters as whatever that creature copied". A Clone-as-Grizzly Bears has
    mana value 2 on the battlefield, not Clone's 4, and Mockingbird becomes
    Grizzly Bears, not Clone."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Clone", "Mockingbird"],
            battlefield=["Island"] * 6 + ["Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.will_choose_cards(bears, username="alice", source="Clone")
    clone = scenario.cast_and_resolve(
        "Clone", *scenario.untapped_sources(*["Island"] * 4, username="alice"), username="alice"
    )
    assert scenario.game.characteristics_of(clone).name == "Grizzly Bears"
    scenario.will_choose_cards(clone, username="alice", source="Mockingbird")

    bird = _cast_mockingbird(scenario, 1, "Island", "Island")

    (question,) = _copy_questions(scenario)
    assert clone.id in question.cards
    characteristics = scenario.game.characteristics_of(bird)
    assert characteristics.name == "Grizzly Bears"
    assert "Bird" in characteristics.subtypes


def test_a_clone_of_mockingbird_as_bears_keeps_bird_and_flying():
    """CR 707.9a and CR 707.9b: the Bird type and flying are part of
    Mockingbird-as-Bears' copiable values, so a Clone copying it gets both."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Mockingbird", "Clone"],
            battlefield=["Island"] * 6 + ["Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.will_choose_cards(bears, username="alice", source="Mockingbird")
    bird = _cast_mockingbird(scenario, 1, "Island", "Island")
    scenario.will_choose_cards(bird, username="alice", source="Clone")

    clone = scenario.cast_and_resolve(
        "Clone", *scenario.untapped_sources(*["Island"] * 4, username="alice"), username="alice"
    )

    characteristics = scenario.game.characteristics_of(clone)
    assert characteristics.name == "Grizzly Bears"
    assert "Bear" in characteristics.subtypes and "Bird" in characteristics.subtypes
    assert "Flying" in characteristics.abilities
    # The real Grizzly Bears is untouched: the exception is the copy's own.
    assert "Bird" not in scenario.game.characteristics_of(bears).subtypes
    assert "Flying" not in scenario.game.characteristics_of(bears).abilities
