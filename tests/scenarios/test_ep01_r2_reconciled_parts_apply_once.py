"""Once-only guards for the parts EP-01 round 2 built twice in parallel tasks.

The integration kept one reader per printed shape and deleted the other; a
second reader of the same line would apply the same effect twice - two granted
ability instances, a permanent untapped twice, two cast options. Each test
below pins "exactly once" for one reconciled part:

- "Untap all <group> you control during each other player's untap step."
  (Seedborn Muse, Murkfiend Liege) - `untap_statics.other_players_untap_of_line`
  (CR 502.3);
- "You may choose not to untap this <permanent> during your untap step." -
  `untap_statics.is_may_choose_not_to_untap_line`, asked once (CR 502.3);
- the soulbond pair's quoted grant (Galvanic Alchemist) - `conditional_statics`
  (CR 702.95a, CR 613.1f);
- group quoted-ability grants (Scuttling Sliver; Mishra's "Permanents you
  control have ...") - `quoted_grants` (CR 113.10a, CR 613.1f);
- graveyard unearth grants (Mishra, Sedris) - `zone_grants` (CR 702.84a);
- the zone scavenge grant (Varolz) - `spell_grants` (CR 702.97a);
- "Creatures [your opponents] control can't have <kind> counters put on
  them." (Blightbeetle, Melira) - `game_rule_statics` (CR 101.2, CR 122.6);
- a spell keyword grant both `spell_grants` and `zone_grants` read (Sami's
  affinity, CR 702.41a).
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.keywords import off_zone_abilities
from magic_cards_model.machines.zone_grants import effective_card
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def _build(alice: dict, bob: dict | None = None):
    scenario = (
        Scenario()
        .player("alice", library=["Island"] * 10, **alice)
        .player("bob", library=["Island"] * 10, **(bob or {}))
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _advance(scenario) -> None:
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.pass_until_resolved()
        scenario.game.put_triggers_on_stack()
    scenario.advance()


def _through_untap_step_of(scenario, username: str) -> None:
    game = scenario.game
    start = game.turn.turns_taken
    while not (game.turn.active_player == username and game.turn.turns_taken > start):
        _advance(scenario)
    while game.turn.step is Step.UNTAP:
        _advance(scenario)


def _activated(scenario, state, text: str):
    return [a for a in scenario.game.activated_abilities(state) if a.raw.strip() == text]


def _computed(scenario, state) -> list[str]:
    return list(scenario.game.characteristics_of(state).abilities)


def test_overlapping_other_player_untap_statics_untap_each_permanent_once():
    scenario = _build({"battlefield": ["Seedborn Muse", "Murkfiend Liege", "Grizzly Bears"]})
    bears = scenario.creature("Grizzly Bears", "alice")
    bears.tapped = True
    untapping = scenario.game._other_players_untapping("bob")  # noqa: SLF001
    assert [state.name for state in untapping].count("Grizzly Bears") == 1
    _through_untap_step_of(scenario, "bob")
    assert not bears.tapped


def test_choose_not_to_untap_is_asked_once():
    scenario = _build({"battlefield": ["Deserter's Quarters"]})
    quarters = scenario.find("Deserter's Quarters", Zone.BATTLEFIELD, "alice")
    quarters.tapped = True
    _through_untap_step_of(scenario, "bob")
    _through_untap_step_of(scenario, "alice")
    asked = [d for d in scenario.questions_asked() if d.source == "Deserter's Quarters"]
    assert len(asked) == 1
    assert not quarters.tapped, "an unscripted player declines, so it untaps"


ALCHEMIST_UNTAP = "{2}{U}: Untap this creature."


def test_a_soulbond_partner_gets_one_instance_of_the_quoted_ability():
    from magic_cards_model.machines import soulbond

    scenario = _build({"battlefield": ["Galvanic Alchemist", "Grizzly Bears"]})
    alchemist = scenario.creature("Galvanic Alchemist")
    bears = scenario.creature("Grizzly Bears")
    soulbond.pair(scenario.game, alchemist, bears)
    scenario.state_based_actions()
    for state in (alchemist, bears):
        assert len(_activated(scenario, state, ALCHEMIST_UNTAP)) == 1
        assert _computed(scenario, state).count(ALCHEMIST_UNTAP) == 1


def test_a_sliver_gets_one_instance_of_the_group_quoted_ability():
    scenario = _build({"battlefield": ["Scuttling Sliver", "Cautery Sliver"]})
    cautery = scenario.creature("Cautery Sliver")
    assert len(_activated(scenario, cautery, "{2}: Untap this creature.")) == 1
    assert _computed(scenario, cautery).count("{2}: Untap this creature.") == 1


def test_mishra_grants_each_permanent_one_ward_line():
    scenario = _build({"battlefield": ["Mishra, Tamer of Mak Fawa", "Grizzly Bears", "Forest"]})
    for name in ("Grizzly Bears", "Forest"):
        permanent = scenario.find(name, Zone.BATTLEFIELD, "alice")
        assert _computed(scenario, permanent).count("Ward—Sacrifice a permanent.") == 1


def _offered(scenario, state) -> list[str]:
    """The off-zone entries the legal-action path builds for `state`."""
    game = scenario.game
    return [entry.family for entry in off_zone_abilities(effective_card(game, state), state, game)]


def test_mishra_offers_one_unearth_for_an_artifact_card():
    scenario = _build({"battlefield": ["Mishra, Tamer of Mak Fawa"], "graveyard": ["Sol Ring"]})
    ring = scenario.find("Sol Ring", Zone.GRAVEYARD, "alice")
    assert _offered(scenario, ring) == ["unearth"]


def test_sedris_offers_one_unearth_for_a_creature_card():
    scenario = _build({"battlefield": ["Sedris, the Traitor King"], "graveyard": ["Grizzly Bears"]})
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")
    assert _offered(scenario, bears) == ["unearth"]


def test_varolz_offers_one_scavenge_for_a_creature_card():
    scenario = _build({"battlefield": ["Varolz, the Scar-Striped"], "graveyard": ["Hill Giant"]})
    giant = scenario.find("Hill Giant", Zone.GRAVEYARD, "alice")
    assert _offered(scenario, giant) == ["scavenge"]


def test_counter_prohibitions_reach_the_side_their_line_names():
    scenario = _build(
        {"battlefield": ["Blightbeetle", "Melira, Sylvok Outcast", "Grizzly Bears"]},
        {"battlefield": ["Grizzly Bears"]},
    )
    mine, theirs = (scenario.creature("Grizzly Bears", u) for u in ("alice", "bob"))
    game = scenario.game
    game.add_counters(theirs, Counter.PLUS_ONE, 1)
    game.add_counters(mine, Counter.PLUS_ONE, 1)
    game.add_counters(mine, Counter.MINUS_ONE, 1)
    game.add_counters(theirs, Counter.MINUS_ONE, 1)
    assert theirs.counter_count(Counter.PLUS_ONE) == 0, "Blightbeetle: opponents' creatures"
    assert mine.counter_count(Counter.PLUS_ONE) == 1
    assert mine.counter_count(Counter.MINUS_ONE) == 0, "Melira: her controller's creatures"
    assert theirs.counter_count(Counter.MINUS_ONE) == 1


def test_a_granted_affinity_reduces_the_cost_once():
    """ "Spells you cast have affinity for artifacts." (Sami) is read by both
    `spell_grants` and `zone_grants`' spell subjects; one instance of affinity
    (CR 702.41a) takes {1} off per artifact - two artifacts make Serra Angel
    {3}{W}{W} cost {1}{W}{W}, not {W}{W}."""
    from magic_cards_model.models.mana import ManaCost

    scenario = _build(
        {
            "hand": ["Serra Angel"],
            "battlefield": ["Sami, Wildcat Captain", "Ornithopter", "Memnite", "Plains"],
        }
    )
    assert scenario.cast("Serra Angel").total_cost.mana == ManaCost.parse("{1}{W}{W}")
