"""Two templates Jacob Frye prints, each read generically:

1. The batched trigger "Whenever one or more `<description>` you control deal
   combat damage to a player" - one trigger per combat damage step, however
   many of the described creatures connected.
2. "exile up to one target `<quality>` card from your graveyard. [If you do,
   copy it. | and copy it.] You may cast the copy." - a copy of a card, cast
   while the ability resolves, *paying* its costs (no "without paying its mana
   cost").

Every CR number below was looked up with `mise run rules:find` in the session
that wrote this file.

- **CR 603.2c** - "An ability triggers only once each time its trigger event
  occurs. However, it can trigger repeatedly if one event contains multiple
  occurrences." "One or more ... deal combat damage" names the whole step's
  damage as the event, so two Assassins connecting trigger it once.
- **CR 510.2** - "all combat damage that's been assigned is dealt
  simultaneously" - which is what makes one combat damage step one event.
- **CR 707.12** - "An effect that instructs a player to cast a copy of an
  object (and not just copy a spell) follows the rules for casting spells,
  except that the copy is created in the same zone the object is in and then
  cast while another spell or ability is resolving." The copy is made in
  exile, and its mana cost is paid.
- **CR 707.10a** - "If a copy of a card is in any zone other than the stack or
  the battlefield, it ceases to exist." - a copy not cast does not linger.
- **CR 707.10f** - "Some effects copy a permanent spell. As that copy
  resolves, it ceases being a copy of a spell and becomes a token permanent."

Jacob Frye is the reported card. The off-pool proofs (both Modern-legal, not
in the api deck pool) are Invasion Tactics ("Whenever one or more Allies you
control deal combat damage to a player, draw a card." - a different subtype
and effect, on an enchantment) and Nashi, Moon's Legacy ("Whenever Nashi
attacks, exile up to one target legendary or Rat card from your graveyard and
copy it. You may cast the copy." - a different trigger, a different quality,
and "and copy it" instead of "If you do, copy it").
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.targeting import profile_for_text
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _jacob_board(*, battlefield: list[str], graveyard: list[str], library: list[str] | None = None):
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=battlefield,
            graveyard=graveyard,
            library=library or ["Island", "Island", "Island"],
        )
        .player("bob", library=["Swamp", "Swamp", "Swamp"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    return scenario


def _to_damage(scenario, *attackers) -> None:
    scenario.attack_with(*attackers)
    scenario.game.put_triggers_on_stack()
    scenario.no_blocks()
    scenario.combat_damage()


def _evie_tokens(scenario):
    return [
        state
        for state in scenario.game.battlefield
        if state.name == "Evie Frye" and getattr(state, "token", False)
    ]


def test_two_assassins_connecting_trigger_jacob_once_and_the_copy_is_cast_paying_its_cost():
    scenario = _jacob_board(
        battlefield=["Jacob Frye", "Vein Ripper", "Island", "Island"],
        graveyard=["Evie Frye"],
    )
    jacob = scenario.creature("Jacob Frye", "alice")
    ripper = scenario.creature("Vein Ripper", "alice")
    evie = scenario.find("Evie Frye", Zone.GRAVEYARD, "alice")
    bob = scenario.player("bob")

    scenario.will_choose_targets(evie, username="alice")
    scenario.will_take_the_may(True, username="alice")
    scenario.will_pay_the_mana_cost(True, username="alice")
    _to_damage(scenario, jacob, ripper)

    assert bob.life == 20 - 3 - 6
    # CR 603.2c: one event for the whole step, so exactly one Jacob trigger.
    assert scenario.stack_names() == ["Jacob Frye's triggered ability"]
    scenario.pass_until_resolved()  # Jacob's trigger: exile, copy, cast the copy

    assert evie.zone is Zone.EXILE, "the original is exiled, never cast"
    assert scenario.stack_names() == ["Evie Frye"], "the copy was cast (CR 707.12)"
    assert all(land.tapped for land in scenario.game.battlefield if land.name == "Island"), (
        "the copy's {1}{U} was paid - no 'without paying its mana cost' here"
    )
    scenario.pass_until_resolved()

    # CR 707.10f: a copy of a permanent spell resolves into a token.
    assert len(_evie_tokens(scenario)) == 1


def test_a_non_assassin_connecting_alone_does_not_trigger_jacob():
    scenario = _jacob_board(
        battlefield=["Jacob Frye", "Grizzly Bears", "Island", "Island"],
        graveyard=["Evie Frye"],
    )
    bears = scenario.creature("Grizzly Bears", "alice")

    _to_damage(scenario, bears)

    assert scenario.player("bob").life == 18
    assert scenario.stack_names() == []
    assert not scenario.game.pending_triggers


def test_opponents_assassins_do_not_trigger_jacob():
    """ "Assassins you control": bob's Assassin hitting alice is not alice's
    event."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Vein Ripper"], library=["Swamp"] * 3)
        .player("bob", battlefield=["Jacob Frye"], graveyard=["Evie Frye"], library=["Swamp"] * 3)
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    ripper = scenario.creature("Vein Ripper", "alice")

    _to_damage(scenario, ripper)

    assert scenario.player("bob").life == 14
    assert scenario.stack_names() == []


def test_declining_to_cast_the_copy_leaves_no_copy_behind():
    """CR 707.10a: the copy made in exile and not cast ceases to exist; the
    original card stays exiled."""
    scenario = _jacob_board(
        battlefield=["Jacob Frye", "Island", "Island"],
        graveyard=["Evie Frye"],
    )
    jacob = scenario.creature("Jacob Frye", "alice")
    evie = scenario.find("Evie Frye", Zone.GRAVEYARD, "alice")

    scenario.will_choose_targets(evie, username="alice")
    scenario.will_take_the_may(False, username="alice")
    _to_damage(scenario, jacob)
    scenario.pass_until_resolved()

    assert evie.zone is Zone.EXILE
    exiled_evies = [state for state in scenario.game.exile if state.name == "Evie Frye"]
    assert exiled_evies == [evie], "only the original remains; the uncast copy is gone"
    assert scenario.stack_names() == []
    assert not any(land.tapped for land in scenario.game.battlefield if land.name == "Island")


def test_the_copy_cannot_be_cast_when_its_cost_cannot_be_paid():
    """CR 601.2h: with no mana to pay {1}{U}, the cast is illegal and rewound;
    the copy then ceases to exist (CR 707.10a)."""
    scenario = _jacob_board(battlefield=["Jacob Frye"], graveyard=["Evie Frye"])
    jacob = scenario.creature("Jacob Frye", "alice")
    evie = scenario.find("Evie Frye", Zone.GRAVEYARD, "alice")

    scenario.will_choose_targets(evie, username="alice")
    scenario.will_take_the_may(True, username="alice")
    scenario.will_pay_the_mana_cost(True, username="alice")
    _to_damage(scenario, jacob)
    scenario.pass_until_resolved()

    assert evie.zone is Zone.EXILE
    assert scenario.stack_names() == []
    assert [state for state in scenario.game.exile if state.name == "Evie Frye"] == [evie]


def test_jacob_cannot_target_a_non_assassin_card():
    """ "target Assassin card or card with freerunning": Grizzly Bears is
    neither, so the only candidate is none - "up to one" lets the trigger go
    on the stack with no target, and it then does nothing."""
    scenario = _jacob_board(
        battlefield=["Jacob Frye", "Island", "Island"],
        graveyard=["Grizzly Bears"],
    )
    jacob = scenario.creature("Jacob Frye", "alice")
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")

    _to_damage(scenario, jacob)
    assert scenario.stack_names() == ["Jacob Frye's triggered ability"]
    scenario.pass_until_resolved()

    assert bears.zone is Zone.GRAVEYARD
    assert scenario.stack_names() == []


def test_invasion_tactics_draws_once_for_two_allies_connecting():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Invasion Tactics", "Great Divide Guide", "Momo, Friendly Flier"],
            library=["Island", "Island", "Island"],
        )
        .player("bob", library=["Swamp"] * 3)
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    alice = scenario.player("alice")
    guide = scenario.creature("Great Divide Guide", "alice")
    momo = scenario.creature("Momo, Friendly Flier", "alice")
    hand_before = len(alice.hand)

    _to_damage(scenario, guide, momo)
    assert scenario.stack_names() == ["Invasion Tactics's triggered ability"], (
        "CR 603.2c: one batched trigger"
    )
    scenario.pass_until_resolved()

    assert len(alice.hand) == hand_before + 1


def test_invasion_tactics_ignores_non_allies():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Invasion Tactics", "Grizzly Bears"],
            library=["Island", "Island", "Island"],
        )
        .player("bob", library=["Swamp"] * 3)
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    bears = scenario.creature("Grizzly Bears", "alice")

    _to_damage(scenario, bears)
    assert scenario.stack_names() == []


def test_nashi_exiles_a_rat_card_and_casts_the_copy_paying_its_cost():
    scenario = _jacob_board(
        battlefield=["Nashi, Moon's Legacy", "Swamp"],
        graveyard=["Sewer Rats"],
    )
    nashi = scenario.creature("Nashi, Moon's Legacy", "alice")
    rats = scenario.find("Sewer Rats", Zone.GRAVEYARD, "alice")
    (swamp,) = scenario.untapped_sources("Swamp")

    scenario.will_choose_targets(rats, username="alice")
    scenario.will_take_the_may(True, username="alice")
    scenario.will_pay_the_mana_cost(True, username="alice")
    scenario.attack_with(nashi)
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == ["Nashi, Moon's Legacy's triggered ability"]
    scenario.pass_until_resolved()

    assert rats.zone is Zone.EXILE
    assert scenario.stack_names() == ["Sewer Rats"]
    assert swamp.tapped
    scenario.pass_until_resolved()
    tokens = [
        state
        for state in scenario.game.battlefield
        if state.name == "Sewer Rats" and getattr(state, "token", False)
    ]
    assert len(tokens) == 1


def test_nashi_legendary_or_rat_is_a_disjunction():
    """ "legendary or Rat card" is a legendary card *or* a Rat card: Evie
    Frye (legendary, not a Rat) is a legal target, Grizzly Bears (neither)
    is not."""
    scenario = _jacob_board(
        battlefield=["Nashi, Moon's Legacy", "Island", "Island"],
        graveyard=["Evie Frye", "Grizzly Bears"],
    )
    nashi = scenario.creature("Nashi, Moon's Legacy", "alice")
    evie = scenario.find("Evie Frye", Zone.GRAVEYARD, "alice")
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")
    requirement = profile_for_text(nashi.oracle_text).requirements[0]
    assert requirement.rejects(bears, "alice", scenario.game) is not None
    assert requirement.rejects(evie, "alice", scenario.game) is None

    scenario.will_choose_targets(evie, username="alice")
    scenario.will_take_the_may(True, username="alice")
    scenario.will_pay_the_mana_cost(True, username="alice")
    scenario.attack_with(nashi)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert evie.zone is Zone.EXILE
    assert scenario.stack_names() == ["Evie Frye"]


def test_jacob_target_reads_card_with_freerunning_as_its_own_alternative():
    """ "target Assassin card or card with freerunning": the second item is a
    card described only by a keyword ability (CR 702.173), read as its own
    alternative rather than merged into "Assassin"."""
    scenario = _jacob_board(battlefield=["Jacob Frye"], graveyard=["Grizzly Bears"])
    jacob = scenario.creature("Jacob Frye", "alice")
    (requirement,) = profile_for_text(jacob.oracle_text).requirements
    assert requirement.minimum == 0 and requirement.count == 1, "up to one"
    assert requirement.required_subtypes == {"assassin"}
    assert [alt.required_keyword for alt in requirement.alternatives] == ["freerunning"]
