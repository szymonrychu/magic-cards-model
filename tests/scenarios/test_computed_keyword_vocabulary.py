"""Reading keywords off the computed board when they share a comma line.

A printing writes its keyword abilities on one line: Emrakul, the Promised End
says "Flying, trample, protection from instants". CR 613.5 - "The application
of continuous effects as described by the layer system is continually and
automatically performed by the game" - means the answer to "does this permanent
have flying" comes off that computed line, not off the printing's own Scryfall
`keywords` field, because a layer 6 effect may have taken the line away or put
one there.

`machines/combat.py::has_keyword` reads that line with a vocabulary. The
vocabulary used to be nothing but the keywords combat itself has rules for, and
`machines/abilities.py::_parse_keywords` is deliberately all-or-nothing: one
token it cannot match discards the whole line, which is what keeps
"Flying creatures you control get +1/+1." from reading as flying. Put those two
together and `protection from instants` - a keyword combat has no rule for -
took flying and trample down with it. Emrakul lost CR 702.9b's evasion (a 3/3
ground creature could block a 13/13 flier) and CR 702.19b's trample (a 4-toughness
blocker ate all 13 damage and the defending player took none).

The fix is the vocabulary, not the all-or-nothing rule: the permanent's own
keyword abilities join it, so `protection` is a word the reader knows and the
line parses whole. The all-or-nothing rule has to stay: a line half of which
is not a keyword (Nevinyrral's "Hexproof from artifacts, creatures, and
enchantments") must not hand out the half that is. A station symbol's line
("5+ | Flying, trample", CR 721.2a) is no longer such a line - it is read as
the station static ability it is (`layers._station_symbol_effects`). What a line the reader still
cannot take whole gets now is a `KeywordLineNotice` - the same "unreadable is
not the same as no effect" record `EvasionNotice` and `UndefinedPowerNotice`
keep - instead of vanishing with nothing said.

CR 708.2 stays untouched: a face-down permanent has "no characteristics other
than those listed by the ability or rules that allowed the spell or permanent
to be face down", so it has no line to read and none of these keywords.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import has_keyword
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

#: Every printing in the pool whose keyword line mixes a combat keyword with a
#: keyword combat has no rule for, and the keyword that used to vanish with it.
SHARED_LINES = [
    ("Emrakul, the Promised End", "flying"),
    ("Emrakul, the Promised End", "trample"),
    ("Ketramose, the New Dawn", "menace"),
    ("Ketramose, the New Dawn", "lifelink"),
    ("Ancient Adamantoise", "vigilance"),
    ("Colossal Skyturtle", "flying"),
    ("Miirym, Sentinel Wyrm", "flying"),
    ("Ureni, the Song Unending", "flying"),
]


@pytest.mark.parametrize(("name", "keyword"), SHARED_LINES)
def test_a_shared_keyword_line_keeps_every_keyword_on_it(name: str, keyword: str):
    """CR 702.1: the printing "lists only the name of the ability as a keyword",
    and a comma-separated list of them is still each of those abilities."""
    scenario = Scenario().player("alice", battlefield=[name]).build()
    permanent = scenario.creature(name)

    assert has_keyword(permanent, keyword), f"{name} prints {keyword}"
    assert has_keyword(permanent, keyword, scenario.game), (
        f"CR 613.5: {name} still has {keyword} on the computed board"
    )


def test_one_line_gives_the_same_answer_whichever_keyword_is_asked_about():
    """Ketramose, the New Dawn: "Menace, lifelink, indestructible".

    The three are one line, so no board state can leave the permanent with one
    of them and not the others. Before the fix, asking about indestructible put
    the word into the vocabulary and the line parsed, while asking about menace
    did not and the whole line was discarded - the same card, the same board,
    the same line, two contradictory answers.
    """
    scenario = Scenario().player("alice", battlefield=["Ketramose, the New Dawn"]).build()
    ketramose = scenario.creature("Ketramose, the New Dawn")

    answers = {
        keyword: has_keyword(ketramose, keyword, scenario.game)
        for keyword in ("menace", "lifelink", "indestructible")
    }

    assert answers == {"menace": True, "lifelink": True, "indestructible": True}


def test_a_ground_creature_cannot_block_emrakul():
    """CR 702.9b: "A creature with flying can't be blocked except by creatures
    with flying and/or reach." """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Emrakul, the Promised End"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)

    emrakul = scenario.creature("Emrakul, the Promised End", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.attack_with(emrakul)

    assert not scenario.game.can_block(bears, emrakul)
    assert scenario.game.why_cannot_block(bears, emrakul) == (
        "Emrakul, the Promised End has flying and Grizzly Bears has neither flying nor reach"
    )


def test_emrakul_tramples_over_a_reach_blocker():
    """CR 702.19b: "Once all those blocking creatures are assigned lethal
    damage, any excess damage is assigned as its controller chooses among those
    blocking creatures and the player ... the creature is attacking."

    Giant Spider is a 2/4 with reach, so the block is legal (CR 702.17b). Four
    of Emrakul's thirteen are lethal for it and the other nine reach bob.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Emrakul, the Promised End"])
        .player("bob", battlefield=["Giant Spider"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)

    emrakul = scenario.creature("Emrakul, the Promised End", "alice")
    spider = scenario.creature("Giant Spider", "bob")
    scenario.attack_with(emrakul)
    scenario.block(emrakul, spider)
    scenario.combat_damage()

    assert spider.zone is Zone.GRAVEYARD
    assert scenario.player("bob").life == 11, "CR 702.19b: 13 - 4 lethal for the Spider"


def test_a_face_down_permanent_has_none_of_the_line():
    """CR 708.2 / CR 708.2a: a face-down permanent is "a 2/2 face-down creature
    with no text", so there is no keyword line to read at all - and the fix must
    not reach past the computed board to the printing to find one."""
    scenario = Scenario().player("alice", battlefield=["Colossal Skyturtle"]).build()
    turtle = scenario.creature("Colossal Skyturtle")
    assert has_keyword(turtle, "flying", scenario.game)

    turtle.turn_face_down()

    assert not has_keyword(turtle, "flying", scenario.game)
    assert not has_keyword(turtle, "ward", scenario.game)
    assert (turtle.power, turtle.toughness) == (2, 2)


def test_a_station_line_grants_nothing_below_its_threshold_and_is_read():
    """Extinguisher Battleship: "5+ | Flying, trample".

    CR 721.2a: "{N+}[abilities]" means "As long as this permanent has N or more
    charge counters on it, it has [abilities]." With no charge counters the
    Battleship has neither keyword - the station symbol is never read as an
    unconditional keyword line - and, since the line is now read as the
    station static ability it is (`tests/scenarios/test_station.py` covers it
    at five), no `KeywordLineNotice` claims it went unread.
    """
    scenario = Scenario().player("alice", battlefield=["Extinguisher Battleship"]).build()
    battleship = scenario.find("Extinguisher Battleship", Zone.BATTLEFIELD)

    assert not has_keyword(battleship, "trample", scenario.game), "CR 721.2a: only at 5+"
    assert not has_keyword(battleship, "flying", scenario.game)

    assert not scenario.game.keyword_line_notices


def test_a_hexproof_from_list_is_not_read_and_says_so():
    """Nevinyrral, Urborg Tyrant: "Hexproof from artifacts, creatures, and
    enchantments".

    CR 702.11f: "Hexproof from [quality A] and from [quality B]" is shorthand
    for two separate hexproof abilities. The comma list is the same shorthand
    with three, and reading only the first would leave the permanent hexproof
    from artifacts alone - a narrower ability than it has. Dropped whole, and
    recorded.
    """
    scenario = Scenario().player("alice", battlefield=["Nevinyrral, Urborg Tyrant"]).build()
    nevinyrral = scenario.creature("Nevinyrral, Urborg Tyrant")

    assert not has_keyword(nevinyrral, "hexproof", scenario.game)

    (notice,) = scenario.game.keyword_line_notices
    assert notice.source_name == "Nevinyrral, Urborg Tyrant"
    assert notice.unread == ("creatures", "and enchantments")


def test_prose_lines_record_nothing():
    """`_parse_keywords`'s all-or-nothing rule is still doing its job: a line
    where nothing matches is prose, not a keyword line with unread tokens, and
    the notice list must not fill up with every sentence on the board.

    Ketramose, the New Dawn is the fixture because its other two lines are both
    prose - a "can't attack or block unless" restriction and a triggered
    ability - sitting next to a keyword line that now reads whole.
    """
    scenario = Scenario().player("alice", battlefield=["Ketramose, the New Dawn"]).build()
    ketramose = scenario.creature("Ketramose, the New Dawn")

    assert has_keyword(ketramose, "menace", scenario.game)

    assert scenario.game.keyword_line_notices == []
