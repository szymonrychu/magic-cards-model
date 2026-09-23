"""Scenario: a search or a look-at bounded by a sacrificed permanent's mana
value - "mana value equal to N plus the sacrificed `<type>`'s mana value" and
"mana value X or less, where X is N plus the sacrificed `<type>`'s mana
value" - wherever the sacrifice was paid: a spell's additional cost
(Eldritch Evolution), an activated ability's cost (Prime Speaker
Vannifar), or a "you may sacrifice ... If you do, ..." choice made while the
ability resolves (Enigmatic Incarnation, Birthing Ritual).

Every CR number below was looked up with `mise run rules:find` in the
session that wrote this file:

- **CR 608.2h** - "If the effect requires information from a specific
  object ... if it's no longer in that zone ... the effect uses the object's
  last known information." The sacrificed permanent's mana value is the one
  it had on the battlefield: a Clone copying Memnite was a 0, not the 4 its
  own card prints, and a token that has since ceased to exist still had one.
- **CR 202.3** - "The mana value of an object is a number equal to the total
  amount of mana in its mana cost, regardless of color."
- **CR 707.2** - a copy's copiable values include the mana cost, so a Clone
  copying Memnite has Memnite's mana cost on the battlefield.
- **CR 111.7** / **CR 704.5d** - a token in a zone other than the battlefield
  ceases to exist, before the spell or ability ever resolves.
- **CR 118.8a** - an additional cost is announced and paid as the spell is
  cast.
- **CR 701.23a** - a search finds "a card that matches the given
  description"; a card outside the bound is never offered.
- **CR 701.24a** - the shuffle.
- **CR 608.2d** - the "you may" choices, made while the effect applies.
- **CR 603.4** - Birthing Ritual's intervening "if you control a creature".
- **CR 401.4** - "in a random order" is nobody's arrangement.

Eldritch Evolution and Birthing Ritual are the reported cards and the only
two printings of the "X or less, where X is N plus the sacrificed ..." bound.
Prime Speaker Vannifar (the activated-cost form, an equality bound) and
Enigmatic Incarnation (the resolve-time "you may sacrifice another
enchantment. If you do, ..." form, a *non-creature* sacrificed type) are the
off-pool proofs that the reader is the template, not either card.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import DecisionKind
from magic_cards_model.models import Color, Zone
from magic_cards_model.models.token import TokenDefinition, create_tokens
from tests.scenarios.harness import PlayedScenario, Scenario

SOLDIER = TokenDefinition(subtypes=("Soldier",), colors=(Color.WHITE,), power=1, toughness=1)


def _offered(scenario: PlayedScenario, source: str) -> list[str]:
    """The names of the cards the last `CHOOSE_CARDS` question from `source`
    offered - what CR 701.23a's description let the player find."""
    questions = [
        question
        for question in scenario.questions_asked()
        if question.kind is DecisionKind.CHOOSE_CARDS and question.source == source
    ]
    assert questions, f"{source} asked no CHOOSE_CARDS question"
    offered = set(questions[-1].cards)
    return sorted(state.name for state in scenario.all_card_states() if state.id in offered)


def _library_card(scenario: PlayedScenario, name: str, username: str = "alice"):
    return next(state for state in scenario.player(username).library if state.name == name)


# --------------------------------------------------------------------------
# Eldritch Evolution: "X or less, where X is 2 plus ...", additional cost
# --------------------------------------------------------------------------


def _eldritch(*library: str, battlefield: tuple[str, ...] = ("Grizzly Bears",)) -> PlayedScenario:
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Eldritch Evolution"],
            battlefield=["Forest", "Forest", "Forest", *battlefield],
            library=list(library),
        )
        .player("bob", library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_eldritch_evolution_finds_a_creature_up_to_two_more_than_the_sacrificed_one():
    scenario = _eldritch("Serra Angel", "Hill Giant", "Gray Ogre", "Island")
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = _library_card(scenario, "Hill Giant")
    scenario.will_choose_cards(giant, username="alice", source="Eldritch Evolution")
    shuffles = scenario.game.shuffles_performed
    forests = scenario.untapped_sources("Forest", "Forest", "Forest")

    spell = scenario.cast_and_resolve("Eldritch Evolution", *forests, sacrificing=[bears])

    assert giant.zone is Zone.BATTLEFIELD and giant.controller == "alice"
    assert bears.zone is Zone.GRAVEYARD
    assert _offered(scenario, "Eldritch Evolution") == ["Gray Ogre", "Hill Giant"], (
        "X = 2 + 2: a 4 and a 3 qualify, the 5-drop Serra Angel does not (CR 701.23a)"
    )
    assert scenario.game.shuffles_performed > shuffles, "CR 701.24a: then shuffle"
    assert spell.zone is Zone.EXILE, "Exile Eldritch Evolution - never its graveyard"
    assert all(state.name != "Eldritch Evolution" for state in scenario.player().graveyard)


def test_eldritch_evolution_may_find_nothing_and_still_shuffles_and_exiles_itself():
    """CR 701.23b: a search for a stated quality may fail to find. The
    shuffle and the self-exile are still done."""
    scenario = _eldritch("Hill Giant", "Island")
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.will_choose_cards(username="alice", source="Eldritch Evolution")
    shuffles = scenario.game.shuffles_performed
    forests = scenario.untapped_sources("Forest", "Forest", "Forest")

    spell = scenario.cast_and_resolve("Eldritch Evolution", *forests, sacrificing=[bears])

    assert {state.name for state in scenario.player().library} == {"Hill Giant", "Island"}
    assert scenario.game.shuffles_performed > shuffles
    assert spell.zone is Zone.EXILE


def test_eldritch_evolution_reads_a_token_s_mana_value_after_it_ceased_to_exist():
    """CR 111.7/704.5d: the sacrificed Soldier token is gone before the spell
    resolves - there is nothing left to look at. CR 608.2h: its last known
    mana value (0) still sets X = 2, so Grizzly Bears qualifies and Gray Ogre
    does not."""
    scenario = _eldritch("Gray Ogre", "Grizzly Bears", battlefield=())
    (soldier,) = create_tokens(scenario.game, SOLDIER, "alice")
    bears = _library_card(scenario, "Grizzly Bears")
    scenario.will_choose_cards(bears, username="alice", source="Eldritch Evolution")
    forests = scenario.untapped_sources("Forest", "Forest", "Forest")

    scenario.cast_and_resolve("Eldritch Evolution", *forests, sacrificing=[soldier])

    assert scenario.game.find_by_id(soldier.id) is None, "CR 704.5d: the token is gone"
    assert bears.zone is Zone.BATTLEFIELD
    assert _offered(scenario, "Eldritch Evolution") == ["Grizzly Bears"]


def test_eldritch_evolution_reads_a_copy_s_mana_value_as_it_last_existed():
    """CR 707.2/608.2h: a Clone that entered as a copy of Memnite had
    Memnite's mana cost - mana value 0 - on the battlefield. Its own card
    prints {3}{U} (mana value 4), which would have let a 6-drop through;
    X is 2 + 0 = 2 instead."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Eldritch Evolution", "Clone"],
            battlefield=["Memnite", "Island", "Island", "Island", "Island"]
            + ["Forest", "Forest", "Forest"],
            library=["Primeval Titan", "Gray Ogre", "Grizzly Bears"],
        )
        .player("bob", library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    memnite = scenario.creature("Memnite", "alice")
    scenario.will_take_the_may(True, username="alice", source="Clone")
    scenario.will_choose_targets(memnite, username="alice", source="Clone")
    scenario.will_choose_cards(memnite, username="alice", source="Clone")
    islands = scenario.untapped_sources("Island", "Island", "Island", "Island")
    clone = scenario.cast_and_resolve("Clone", *islands)
    assert clone.zone is Zone.BATTLEFIELD
    assert scenario.game.characteristics_of(clone).mana_value == 0, "CR 707.2: Memnite's cost"

    bears = _library_card(scenario, "Grizzly Bears")
    scenario.will_choose_cards(bears, username="alice", source="Eldritch Evolution")
    forests = scenario.untapped_sources("Forest", "Forest", "Forest")
    scenario.cast_and_resolve("Eldritch Evolution", *forests, sacrificing=[clone])

    assert bears.zone is Zone.BATTLEFIELD
    assert _offered(scenario, "Eldritch Evolution") == ["Grizzly Bears"], (
        "X = 2 + 0 from the copy's last known mana value, not 2 + 4 from the Clone card"
    )


# --------------------------------------------------------------------------
# Prime Speaker Vannifar: equality bound, sacrificed as an activation cost
# --------------------------------------------------------------------------


def _vannifar(*library: str, battlefield: tuple[str, ...] = ("Llanowar Elves",)) -> PlayedScenario:
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Prime Speaker Vannifar", *battlefield],
            library=list(library),
        )
        .player("bob", library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_vannifar_finds_a_creature_exactly_one_more_than_the_sacrificed_one():
    scenario = _vannifar("Gray Ogre", "Grizzly Bears", "Savannah Lions", "Wall of Omens")
    vannifar = scenario.creature("Prime Speaker Vannifar", "alice")
    elves = scenario.creature("Llanowar Elves", "alice")
    bears = _library_card(scenario, "Grizzly Bears")
    scenario.will_choose_cards(bears, username="alice", source="Prime Speaker Vannifar")
    shuffles = scenario.game.shuffles_performed

    scenario.activate(vannifar, sacrificing=[elves])
    scenario.pass_until_resolved()

    assert bears.zone is Zone.BATTLEFIELD
    assert elves.zone is Zone.GRAVEYARD
    assert _offered(scenario, "Prime Speaker Vannifar") == ["Grizzly Bears", "Wall of Omens"], (
        "equal to 1 + 1: exactly mana value 2 - neither the 1 nor the 3 qualifies"
    )
    assert scenario.game.shuffles_performed > shuffles


def test_vannifar_reads_a_sacrificed_token_s_last_known_mana_value():
    """CR 608.2h through an activation cost (CR 602.2b pays it before the
    ability exists): the token is gone by resolution, and its mana value of 0
    still makes the bound exactly 1."""
    scenario = _vannifar("Grizzly Bears", "Llanowar Elves", battlefield=())
    vannifar = scenario.creature("Prime Speaker Vannifar", "alice")
    (soldier,) = create_tokens(scenario.game, SOLDIER, "alice")
    elves = _library_card(scenario, "Llanowar Elves")
    scenario.will_choose_cards(elves, username="alice", source="Prime Speaker Vannifar")

    scenario.activate(vannifar, sacrificing=[soldier])
    scenario.pass_until_resolved()

    assert elves.zone is Zone.BATTLEFIELD
    assert _offered(scenario, "Prime Speaker Vannifar") == ["Llanowar Elves"]


# --------------------------------------------------------------------------
# Enigmatic Incarnation: "you may sacrifice another enchantment. If you do,"
# --------------------------------------------------------------------------


def _to_end_step(scenario: PlayedScenario) -> None:
    while scenario.step is not Step.END_STEP:
        scenario.advance()
    scenario.game.put_triggers_on_stack()


def _incarnation(*battlefield: str) -> PlayedScenario:
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Enigmatic Incarnation", *battlefield],
            library=["Hill Giant", "Gray Ogre", "Serra Angel", "Island"],
        )
        .player("bob", library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_enigmatic_incarnation_trades_an_enchantment_for_a_creature_one_mana_value_up():
    scenario = _incarnation("Glorious Anthem")
    anthem = scenario.find("Glorious Anthem", Zone.BATTLEFIELD, "alice")
    giant = _library_card(scenario, "Hill Giant")
    scenario.will_take_the_may(True, username="alice", source="Enigmatic Incarnation")
    scenario.will_choose_cards(anthem, username="alice", source="Enigmatic Incarnation")
    scenario.will_choose_cards(giant, username="alice", source="Enigmatic Incarnation")
    _to_end_step(scenario)

    scenario.pass_until_resolved()

    assert anthem.zone is Zone.GRAVEYARD
    assert giant.zone is Zone.BATTLEFIELD
    assert _offered(scenario, "Enigmatic Incarnation") == ["Hill Giant"], (
        "equal to 1 + 3 (Glorious Anthem): exactly 4"
    )


def test_enigmatic_incarnation_declined_searches_nothing():
    scenario = _incarnation("Glorious Anthem")
    anthem = scenario.find("Glorious Anthem", Zone.BATTLEFIELD, "alice")
    scenario.will_take_the_may(False, username="alice", source="Enigmatic Incarnation")
    shuffles = scenario.game.shuffles_performed
    _to_end_step(scenario)

    scenario.pass_until_resolved()

    assert anthem.zone is Zone.BATTLEFIELD
    assert len(scenario.player().library) == 4
    assert scenario.game.shuffles_performed == shuffles, "no search, so no shuffle"


def test_enigmatic_incarnation_cannot_sacrifice_itself():
    """ "another enchantment": with no other enchantment, saying yes is not a
    legal answer (CR 608.2d) and nothing is sacrificed or searched."""
    scenario = _incarnation()
    _to_end_step(scenario)

    scenario.pass_until_resolved()

    incarnation = scenario.find("Enigmatic Incarnation", Zone.BATTLEFIELD, "alice")
    assert incarnation.zone is Zone.BATTLEFIELD
    assert len(scenario.player().library) == 4
    mays = [
        question
        for question in scenario.questions_asked()
        if question.kind is DecisionKind.MAY and question.source == "Enigmatic Incarnation"
    ]
    assert all(not question.affirmative_is_legal for question in mays)


# --------------------------------------------------------------------------
# Birthing Ritual: look at seven, may sacrifice, may put X or less
# --------------------------------------------------------------------------

_SEVEN = [
    "Gray Ogre",
    "Hill Giant",
    "Grizzly Bears",
    "Llanowar Elves",
    "Island",
    "Serra Angel",
    "Opt",
]


def _ritual(*battlefield: str, library: list[str] | None = None) -> PlayedScenario:
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Birthing Ritual", *battlefield],
            library=list(library if library is not None else [*_SEVEN, "Forest", "Forest"]),
        )
        .player("bob", library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_birthing_ritual_sacrifices_and_puts_a_creature_up_to_one_more():
    scenario = _ritual("Grizzly Bears")
    bears = scenario.creature("Grizzly Bears", "alice")
    ogre = _library_card(scenario, "Gray Ogre")
    scenario.will_take_the_may(True, username="alice", source="Birthing Ritual")
    scenario.will_choose_cards(bears, username="alice", source="Birthing Ritual")
    scenario.will_choose_cards(ogre, username="alice", source="Birthing Ritual")
    _to_end_step(scenario)

    scenario.pass_until_resolved()

    alice = scenario.player("alice")
    assert bears.zone is Zone.GRAVEYARD
    assert ogre.zone is Zone.BATTLEFIELD
    assert _offered(scenario, "Birthing Ritual") == [
        "Gray Ogre",
        "Grizzly Bears",
        "Llanowar Elves",
    ], "X = 1 + 2: creature cards with mana value 3 or less among the seven"
    assert [state.name for state in alice.library[:2]] == ["Forest", "Forest"], (
        "the six others went to the bottom, under the two cards that were never looked at"
    )
    assert sorted(state.name for state in alice.library[2:]) == sorted(
        name for name in _SEVEN if name != "Gray Ogre"
    )


def test_birthing_ritual_declining_the_sacrifice_bottoms_all_seven():
    scenario = _ritual("Grizzly Bears")
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.will_take_the_may(False, username="alice", source="Birthing Ritual")
    _to_end_step(scenario)

    scenario.pass_until_resolved()

    alice = scenario.player("alice")
    assert bears.zone is Zone.BATTLEFIELD
    assert [state.name for state in alice.library[:2]] == ["Forest", "Forest"]
    assert sorted(state.name for state in alice.library[2:]) == sorted(_SEVEN)
    assert not any(
        question.kind is DecisionKind.CHOOSE_CARDS and question.source == "Birthing Ritual"
        for question in scenario.questions_asked()
    ), "no sacrifice, so nothing is ever put: the second choice is never offered"


def test_birthing_ritual_may_sacrifice_and_then_put_nothing():
    scenario = _ritual("Grizzly Bears")
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.will_take_the_may(True, username="alice", source="Birthing Ritual")
    scenario.will_choose_cards(bears, username="alice", source="Birthing Ritual")
    scenario.will_choose_cards(username="alice", source="Birthing Ritual")
    _to_end_step(scenario)

    scenario.pass_until_resolved()

    alice = scenario.player("alice")
    assert bears.zone is Zone.GRAVEYARD
    assert sorted(state.name for state in alice.library[2:]) == sorted(_SEVEN)
    assert not any(state.zone is Zone.BATTLEFIELD for state in alice.library), (
        "every looked-at card is back in the library"
    )


def test_birthing_ritual_reads_a_sacrificed_token_s_last_known_mana_value():
    """A 0-mana-value token makes X = 1: Llanowar Elves only."""
    scenario = _ritual()
    (soldier,) = create_tokens(scenario.game, SOLDIER, "alice")
    elves = _library_card(scenario, "Llanowar Elves")
    scenario.will_take_the_may(True, username="alice", source="Birthing Ritual")
    scenario.will_choose_cards(soldier, username="alice", source="Birthing Ritual")
    scenario.will_choose_cards(elves, username="alice", source="Birthing Ritual")
    _to_end_step(scenario)

    scenario.pass_until_resolved()

    assert elves.zone is Zone.BATTLEFIELD
    assert _offered(scenario, "Birthing Ritual") == ["Llanowar Elves"]


def test_birthing_ritual_does_not_trigger_without_a_creature():
    """CR 603.4: "if you control a creature" is checked as the end step
    begins; with none, the ability never triggers."""
    scenario = _ritual()
    _to_end_step(scenario)

    assert not scenario.stack_names()
    assert [state.name for state in scenario.player().library[:7]] == _SEVEN


def test_birthing_ritual_with_a_short_library_looks_at_what_there_is():
    scenario = _ritual("Grizzly Bears", library=["Gray Ogre", "Island"])
    bears = scenario.creature("Grizzly Bears", "alice")
    ogre = _library_card(scenario, "Gray Ogre")
    scenario.will_take_the_may(True, username="alice", source="Birthing Ritual")
    scenario.will_choose_cards(bears, username="alice", source="Birthing Ritual")
    scenario.will_choose_cards(ogre, username="alice", source="Birthing Ritual")
    _to_end_step(scenario)

    scenario.pass_until_resolved()

    assert ogre.zone is Zone.BATTLEFIELD
    assert [state.name for state in scenario.player().library] == ["Island"]
