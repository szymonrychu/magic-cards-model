"""Scenario: the riders that follow "Create a token that's a copy of <target>".

Chrome Dome, Cogwork Assembler, Orthion, Flamerush Rider and Thousand-Faced
Shadow all create a token copy (CR 707.2, CR 111.2) and then say something
about *the token just made* (CR 608.2c), never the targeted original:

- "That token gains haste." / "It gains haste." / "They gain haste." - a
  layer 6 grant (CR 613.1f) on the new objects only;
- "Sacrifice it/them" / "Exile it at the beginning of the next end step." -
  CR 603.7a's delayed trigger, created during resolution;
- "Exile the token at end of combat." - the same primitive, at CR 511.2's
  end of combat step;
- "...that's tapped and attacking" / "The token enters tapped and
  attacking." - CR 508.4: put onto the battlefield attacking, never
  declared as an attacker, so CR 508.4c's declaration rules and CR 508.3a's
  "whenever [a creature] attacks" triggers never see it.

Every CR number was looked up with `mise run rules:find`.

Generality (target the template, not the card): Memnite, Sliver Construct,
Grizzly Bears and Alaborn Cavalier stand in as the copied objects; none of
them appears in a card in this file's names.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.keywords import ninjutsu_activation
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

DOME = "Chrome Dome"
ASSEMBLER = "Cogwork Assembler"
ORTHION = "Orthion, Hero of Lavabrink"
RIDER = "Flamerush Rider"
SHADOW = "Thousand-Faced Shadow"


def _resolve_everything(scenario):
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()


def _tokens_named(scenario, name):
    return [p for p in scenario.game.battlefield if p.token and p.name == name]


def _chars(scenario, permanent):
    return scenario.game.computed_board().of(permanent)


def _to_step(scenario, step):
    while scenario.step is not step:
        _resolve_everything(scenario)
        scenario.advance()
    _resolve_everything(scenario)


# -- Chrome Dome: haste, attack, sacrifice at the end step -------------------


def _dome_board():
    return (
        Scenario()
        .player(
            "alice",
            battlefield=[DOME, "Memnite", *["Mountain"] * 5],
            library=["Island"] * 5,
        )
        .player("bob", library=["Island"] * 5)
        .build()
    )


def test_chrome_dome_token_gains_haste_attacks_and_is_sacrificed_at_the_end_step():
    scenario = _dome_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    dome = scenario.find(DOME, Zone.BATTLEFIELD, "alice")
    memnite = scenario.creature("Memnite", "alice")

    scenario.activate(dome, *scenario.untapped_sources(*["Mountain"] * 5), targets=[memnite])
    _resolve_everything(scenario)

    (token,) = _tokens_named(scenario, "Memnite")
    assert token.id != memnite.id, "a new object (CR 707.2)"
    assert "Haste" in _chars(scenario, token).abilities, "That token gains haste"
    assert _chars(scenario, token).power == 2, "Chrome Dome's +1/+0 reaches the copy"

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(token)
    assert scenario.game.is_attacking(token), "a copy that entered this turn may attack"

    _to_step(scenario, Step.COMBAT_DAMAGE)
    assert scenario.player("bob").life == 20 - 2

    _to_step(scenario, Step.POSTCOMBAT_MAIN)
    assert len(_tokens_named(scenario, "Memnite")) == 1, "CR 603.7a: not before the end step"
    _to_step(scenario, Step.END_STEP)
    assert _tokens_named(scenario, "Memnite") == []
    assert memnite.zone is Zone.BATTLEFIELD, "the token goes, never the original"


def test_the_haste_belongs_to_the_token_only():
    scenario = _dome_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    dome = scenario.find(DOME, Zone.BATTLEFIELD, "alice")
    memnite = scenario.creature("Memnite", "alice")

    scenario.activate(dome, *scenario.untapped_sources(*["Mountain"] * 5), targets=[memnite])
    _resolve_everything(scenario)

    assert "Haste" not in _chars(scenario, memnite).abilities


# -- Cogwork Assembler: exile, an opponent's artifact ------------------------


def test_cogwork_assembler_exiles_the_token_copy_of_an_opponents_artifact_at_the_end_step():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[ASSEMBLER, *["Mountain"] * 7],
            library=["Island"] * 5,
        )
        .player("bob", battlefield=["Sliver Construct"], library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    assembler = scenario.find(ASSEMBLER, Zone.BATTLEFIELD, "alice")
    theirs = scenario.creature("Sliver Construct", "bob")

    scenario.activate(assembler, *scenario.untapped_sources(*["Mountain"] * 7), targets=[theirs])
    _resolve_everything(scenario)

    (token,) = _tokens_named(scenario, "Sliver Construct")
    assert scenario.game.controller_of(token).username == "alice", "CR 111.2"
    assert "Haste" in _chars(scenario, token).abilities

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(token)
    _to_step(scenario, Step.POSTCOMBAT_MAIN)
    assert len(_tokens_named(scenario, "Sliver Construct")) == 1
    _to_step(scenario, Step.END_STEP)

    assert _tokens_named(scenario, "Sliver Construct") == []
    assert theirs.zone is Zone.BATTLEFIELD


# -- Orthion: one copy, then five ---------------------------------------------


def _orthion_board():
    return (
        Scenario()
        .player(
            "alice",
            battlefield=[ORTHION, "Grizzly Bears", *["Mountain"] * 9],
            library=["Island"] * 5,
        )
        .player("bob", library=["Island"] * 5)
        .build()
    )


def test_orthion_single_copy_has_haste_and_is_sacrificed_at_the_end_step():
    scenario = _orthion_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    orthion = scenario.find(ORTHION, Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.activate(
        orthion, *scenario.untapped_sources(*["Mountain"] * 2), index=0, targets=[bears]
    )
    _resolve_everything(scenario)

    (token,) = _tokens_named(scenario, "Grizzly Bears")
    assert "Haste" in _chars(scenario, token).abilities
    assert "Haste" not in _chars(scenario, bears).abilities
    assert orthion.tapped

    _to_step(scenario, Step.END_STEP)
    assert _tokens_named(scenario, "Grizzly Bears") == []
    assert bears.zone is Zone.BATTLEFIELD


def test_orthion_five_copies_all_gain_haste_attack_and_are_all_sacrificed():
    scenario = _orthion_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    orthion = scenario.find(ORTHION, Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.activate(
        orthion, *scenario.untapped_sources(*["Mountain"] * 9), index=1, targets=[bears]
    )
    _resolve_everything(scenario)

    tokens = _tokens_named(scenario, "Grizzly Bears")
    assert len(tokens) == 5
    assert all("Haste" in _chars(scenario, t).abilities for t in tokens), "They gain haste"

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(*tokens)
    _to_step(scenario, Step.COMBAT_DAMAGE)
    assert scenario.player("bob").life == 20 - 5 * 2

    _to_step(scenario, Step.POSTCOMBAT_MAIN)
    assert len(_tokens_named(scenario, "Grizzly Bears")) == 5
    _to_step(scenario, Step.END_STEP)
    assert _tokens_named(scenario, "Grizzly Bears") == []
    assert bears.zone is Zone.BATTLEFIELD, "only the tokens are sacrificed"


# -- Flamerush Rider: tapped and attacking, exiled at end of combat ----------


def _rider_board():
    return (
        Scenario()
        .player(
            "alice",
            battlefield=[RIDER, "Grizzly Bears", "Alaborn Cavalier"],
            library=["Island"] * 5,
        )
        .player("bob", library=["Island"] * 5)
        .build()
    )


def test_flamerush_rider_token_enters_tapped_and_attacking_and_is_exiled_at_end_of_combat():
    scenario = _rider_board()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    rider = scenario.find(RIDER, Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.attack_with(rider, bears)
    scenario.choose_trigger_targets(RIDER, [bears])
    _resolve_everything(scenario)

    (token,) = _tokens_named(scenario, "Grizzly Bears")
    assert token.tapped, "tapped"
    assert scenario.game.is_attacking(token), "and attacking (CR 508.4)"
    assert token.id != bears.id

    _to_step(scenario, Step.COMBAT_DAMAGE)
    assert scenario.player("bob").life == 20 - 3 - 2 - 2, "the copy deals its damage"
    assert len(_tokens_named(scenario, "Grizzly Bears")) == 1, "still there before end of combat"

    _to_step(scenario, Step.END_OF_COMBAT)
    assert _tokens_named(scenario, "Grizzly Bears") == [], "Exile the token at end of combat"
    assert bears.zone is Zone.BATTLEFIELD
    assert token.zone is not Zone.BATTLEFIELD


def test_an_attacking_token_copy_was_never_declared_so_no_attack_triggers_fire():
    """CR 508.4c / CR 508.3a: the copy of Alaborn Cavalier (whenever this
    creature attacks, ...) is attacking without having been declared."""
    scenario = _rider_board()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    rider = scenario.find(RIDER, Zone.BATTLEFIELD, "alice")
    cavalier = scenario.creature("Alaborn Cavalier", "alice")
    scenario.attack_with(rider, cavalier)
    scenario.game.put_triggers_on_stack()
    # Only the Rider's and the declared Cavalier's own triggers exist.
    assert sorted(scenario.stack_names()) == sorted(
        [f"{RIDER}'s triggered ability", "Alaborn Cavalier's triggered ability"]
    )
    _resolve_everything(scenario)

    tokens = _tokens_named(scenario, "Alaborn Cavalier")
    assert len(tokens) <= 1
    for token in tokens:
        assert scenario.game.is_attacking(token)
    assert not any(
        getattr(item, "source_name", None) == "Alaborn Cavalier"
        and getattr(item, "source_id", None) in {t.id for t in tokens}
        for item in scenario.game.stack
    )


# -- Thousand-Faced Shadow: ninjutsu, enters from hand attacking ------------


def _shadow_board():
    return (
        Scenario()
        .player(
            "alice",
            hand=[SHADOW],
            battlefield=["Grizzly Bears", "Memnite", *["Island"] * 4],
            library=["Island"] * 5,
        )
        .player("bob", library=["Island"] * 5)
        .build()
    )


def _ninjutsu(scenario, card, returning):
    activation = ninjutsu_activation(scenario.game, card, returning, "alice")
    activation.begin_paying()
    activation.payment.auto_tap(scenario.game.permanents_controlled_by("alice"))
    activation.payment.pay()
    activation.activate()
    activation.resolve()


def test_thousand_faced_shadow_copies_another_attacker_tapped_and_attacking():
    scenario = _shadow_board()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    bears = scenario.creature("Grizzly Bears", "alice")
    memnite = scenario.creature("Memnite", "alice")
    scenario.attack_with(bears, memnite)
    scenario.start_at(Step.DECLARE_BLOCKERS)
    scenario.no_blocks()
    shadow = scenario.find(SHADOW, Zone.HAND, "alice")

    _ninjutsu(scenario, shadow, memnite)
    assert shadow.zone is Zone.BATTLEFIELD and scenario.game.is_attacking(shadow)
    scenario.choose_trigger_targets(SHADOW, [bears])
    _resolve_everything(scenario)

    (token,) = _tokens_named(scenario, "Grizzly Bears")
    assert token.tapped
    assert scenario.game.is_attacking(token)
    assert token.id != bears.id
    assert [p for p in scenario.game.battlefield if p.token] == [token], "one token, no more"


def test_thousand_faced_shadow_needs_to_be_attacking_when_it_enters_from_hand():
    """The intervening "if it's attacking" (CR 603.4): cast normally from hand
    it enters, but not attacking, and nothing is copied."""
    scenario = _shadow_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    shadow = scenario.find(SHADOW, Zone.HAND, "alice")
    scenario.put_onto_battlefield(SHADOW, "alice")
    scenario.game.put_triggers_on_stack()
    _resolve_everything(scenario)

    assert not scenario.game.is_attacking(shadow)
    assert [p for p in scenario.game.battlefield if p.token] == []
