import re
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any
from uuid import UUID

from ...data.creature_types import creature_types
from ...data.subtypes import canonical_subtype
from ...machines.abilities import (
    self_normalized_effect_text,
    self_reference_names,
)
from ...machines.cost import (
    CardRequirement,
    CostComponent,
    exile_cost,
)
from ...machines.layers import (
    Characteristics,
    ComputedBoard,
    LayerNotice,
)
from ...machines.triggers import (
    AbilityOnStack,
    ExtraTriggerEvent,
    GameEvent,
)
from ...numbers import count_pattern, parse_count
from ..card import (
    Card,
    Color,
    Supertype,
    Type,
)
from ..card_state import (
    CardState,
    Counter,
)
from ..mana import ManaCost
from ..zone import Zone
from .records import KnownCard, KnownCarry, Reveal

if TYPE_CHECKING:
    from . import Game


#: CR 702.16a: "Protection is a static ability, written 'Protection from
#: [quality]'." CR 702.16g makes "protection from A and from B" two abilities,
#: so the qualities are split apart rather than kept as one phrase.
_PROTECTION = re.compile(r"protection from ([^.;\n]+)", re.IGNORECASE)

#: CR 207.2: reminder text is "italicized text within parentheses", which has
#: no effect on game play. It can hold a full stop and a comma, so it is cut
#: out before the quality phrase is read.
_REMINDER_TEXT = re.compile(r"\s*\([^)]*\)")


_UNRESOLVED_PROTECTION_QUALITY = re.compile(
    r"^(?:a |the )?(?:color|colour|card type|quality) of your choice\b", re.IGNORECASE
)


def _qualities_from_text(text: str | None) -> list[str]:
    """Every "protection from [quality]" this text carries, in order (CR 702.16a,
    CR 702.16g). Shared by `protection_qualities`, which reads a printing's own
    oracle text, and `Game._effective_protection_qualities`, which reads the
    same phrase off a *granted* ability line (`machines/layers.py`'s indefinite
    keyword-and-protection grant, Akroma's Memorial) the same way.
    """
    qualities: list[str] = []
    # CR 702.16a's quality ends where the keyword's own reminder text starts:
    # "protection from black (This creature can't be blocked ... by anything
    # black.)" - the parenthesised CR reminder (CR 207.2) is not a quality.
    # Only a keyword line is the object's own protection (CR 702.1: "only the
    # name of the ability"): a sentence that merely mentions the phrase is a
    # static ability granting it elsewhere ("Human creatures you control have
    # protection from ...", "You have protection from each of your
    # opponents."), exactly as `hexproof_abilities_in` reads hexproof.
    keyword_lines = "\n".join(
        line
        for line in _REMINDER_TEXT.sub("", text or "").split("\n")
        if ":" not in line and "." not in line
    )
    for match in _PROTECTION.finditer(keyword_lines):
        # A comma ends the phrase unless another "from" follows it: Emrakul,
        # the Aeons Torn's "protection from spells that are one or more
        # colors, annihilator 6" names one quality, then another keyword.
        pieces = match.group(1).split(", ")
        phrase = pieces[0]
        for piece in pieces[1:]:
            if not piece.lower().startswith(("from ", "and from ")):
                break
            phrase += " and from " + piece.split("from ", 1)[1]
        for part in phrase.split(" and from "):
            quality = part.strip().rstrip(",").strip()
            if not quality or _UNRESOLVED_PROTECTION_QUALITY.match(quality):
                continue
            if quality not in qualities:
                qualities.append(quality)
    return qualities


#: "Exile any number of <colour> cards from your graveyard with <N> or more
#: <colour> mana symbols among their mana costs" - Baron Helmut Zemo's boast
#: cost. A count of mana symbols of one colour across the chosen cards' mana
#: costs (CR 107.4e/107.4f: hybrid and Phyrexian symbols are coloured symbols
#: of every colour they show), read by `_symbol_threshold_exile_component`.
_SYMBOL_THRESHOLD_EXILE_COST = re.compile(
    r"^exile any number of (?P<quality>white|blue|black|red|green) cards from your "
    r"graveyard with (?P<count>\w+) or more (?P<color>white|blue|black|red|green) mana "
    r"symbols among their mana costs\.?$",
    re.IGNORECASE,
)


def symbol_threshold_exile_cost(text: str) -> tuple[Color, Color, int] | None:
    """`_SYMBOL_THRESHOLD_EXILE_COST`'s parts - the cards' colour, the symbols'
    colour, and the threshold - or `None` for any other cost sentence."""
    match = _SYMBOL_THRESHOLD_EXILE_COST.fullmatch(text.strip())
    if match is None:
        return None
    needed = parse_count(match.group("count"))
    if needed is None:
        return None
    return (
        _COLOR_WORDS[match.group("quality").lower()],
        _COLOR_WORDS[match.group("color").lower()],
        needed,
    )


def colored_symbol_count(card: CardState | Card, color: Color) -> int:
    """How many mana symbols of `color` a card's mana cost shows (CR 107.4e/
    107.4f: a hybrid or Phyrexian symbol counts for every colour it shows)."""
    return sum(
        1 for symbol in ManaCost.parse(card.mana_cost or "").symbols if color in symbol.colors
    )


def _symbol_threshold_exile_component(
    text: str, chosen: list[CardState], payer: str
) -> CostComponent | None:
    """`_SYMBOL_THRESHOLD_EXILE_COST`'s cost over the cards `chosen` for it,
    or `None` when `text` is not that shape.

    CR 118.3: the cards chosen must carry the threshold between them, or the
    cost cannot be paid - refused here, as the cost is built, the same way
    `Game.activation_cost` refuses any other cost it cannot build. Each card's
    colour and zone are the `EXILE` component's own checks (a
    `CardRequirement` and `Zone.GRAVEYARD`), made again as it is paid.
    """
    if _SYMBOL_THRESHOLD_EXILE_COST.fullmatch(text.strip()) is None:
        return None
    parts = symbol_threshold_exile_cost(text)
    if parts is None:
        raise ValueError(f"cannot build a cost for {text!r}")
    quality, color, needed = parts
    shown = sum(colored_symbol_count(card, color) for card in chosen)
    if shown < needed:
        raise ValueError(
            f"the {len(chosen)} card(s) chosen show {shown} {color.name.lower()} mana "
            f"symbol(s) among their mana costs, not the {needed} the cost asks for (CR 118.3)"
        )
    component = exile_cost(
        *chosen, payer=payer, required=len(chosen), description=text, zone=Zone.GRAVEYARD
    )
    component.requirement = CardRequirement(
        colors=[quality], description=f"{quality.name.lower()} card"
    )
    return component


#: CR 602.5b's "Activate only if <condition>" restriction, the condition taken
#: to the end of its sentence. A trailing "and only as a sorcery" / "and only
#: once each turn" is a second restriction, read by its own check, and is cut
#: off by `_activation_condition` before the condition is read.
_ACTIVATE_ONLY_IF = re.compile(r"activate only if (?P<condition>[^.]+)", re.IGNORECASE)
_AND_ONLY_TAIL = re.compile(r"\s+and only\b.*$", re.IGNORECASE)


#: The board conditions `Game.condition_holds` reads, shared by "Activate only
#: if ..." (CR 602.5b) and a modal instruction's "If ..., choose N instead"
#: (CR 700.2). Every count is `magic_cards_model.numbers`' `COUNT`, never a
#: table of its own, so "six", "eight" and "20" read the way "three" does -
#: Metalcraft ("you control three or more artifacts"), Shrine of the Forsaken
#: Gods ("seven or more lands"), Kelpie Guide ("eight or more lands").
#: The counted noun is a quality phrase (`_permanent_quality`), so Rimewind
#: Cryomancer's "snow permanents" (CR 205.4a) is read, not dropped.
_CONDITION_CONTROLS_N = re.compile(
    rf"(?P<who>you control|an opponent controls) {count_pattern('count')} or more "
    r"(?P<quality>.+)",
    re.IGNORECASE,
)
#: Fanatic of Rhonas's Ferocious and Bolt Bend's discount: "you control a
#: creature with power 4 or greater."; Baxter Building's "you control a
#: creature with toughness 4 or greater." - one "a(n) <quality> with
#: <power|toughness> N or greater" shape, the quality read by
#: `_permanent_quality` and the stat off the computed characteristics (CR
#: 208.1: power and toughness "can be modified or set ... by effects").
_CONDITION_POWER = re.compile(
    r"you control an? (?P<quality>[a-z' -]+?) with "
    r"(?P<stat>power|toughness) (?P<power>\d+) or greater",
    re.IGNORECASE,
)
#: Flame of Anor's "you control a Wizard", Soul Transfer's "you control an
#: artifact and an enchantment" - one or more "a(n) <quality>" joined by "and".
_CONDITION_CONTROLS_A = re.compile(r"you control (?P<qualities>an? .+)", re.IGNORECASE)
_AND_AN = re.compile(r"\s+and\s+(?=an?\s)", re.IGNORECASE)
_A_QUALITY = re.compile(r"an? (?P<quality>.+)", re.IGNORECASE)
#: Thranduil's Company's own "As long as you control another Elf, you may
#: play an additional land on each of your turns." - CR 305.2's own
#: continuous-effect increase, gated on a board fact that names an object
#: *other than the permanent carrying the ability itself* ("another", not
#: "a"/"an"). `_CONDITION_CONTROLS_A` never reads this shape at all: its own
#: `an? .+` alternative requires the word right after "you control" to be
#: "a"/"an", which "another" is not. `source`, the permanent whose own line
#: this condition sits on, is what "another" excludes.
_CONDITION_CONTROLS_ANOTHER = re.compile(r"you control another (?P<quality>.+)", re.IGNORECASE)
#: Power Plant Worker / Mine Worker / Tower Worker's own shared "you control
#: creatures named `<name>` and `<name>`" - two specific printed names
#: (CR 201.4), not `_CONDITION_CONTROLS_A`'s quality phrase, so it is its own
#: pattern rather than a widening of that one. The plural noun is read too:
#: Scepter, Crown and Throne of Empires print "artifacts named ...", and each
#: named permanent has to be one of those.
_CONDITION_CONTROLS_NAMED_PAIR = re.compile(
    r"you control (?P<kind>creatures|artifacts|enchantments|lands|planeswalkers|permanents) "
    r"named (?P<first>.+?) and (?P<second>.+)",
    re.IGNORECASE,
)
#: Beza, the Bounding Spring's four trailing conditions, Sunset Revelry's three
#: leading ones and Ticket Tortoise's intervening if (CR 603.4): "an opponent
#: controls more lands than you", "an opponent has more life than you", "an
#: opponent controls more creatures than you", "an opponent has more cards in
#: hand than you". "An opponent" is any one of them (CR 102.3), and "more" is
#: strict - a tie is not more. The permanent noun is `_permanent_quality`'s
#: phrase, read off the computed board (CR 613.5) like every other count here.
_CONDITION_OPPONENT_COMPARISON = re.compile(
    r"an opponent (?:controls (?P<direction>more|fewer) (?P<quality>.+?)"
    r"|has (?P<stat_direction>more|fewer) (?P<stat>life|cards in (?:their )?hand)) than you",
    re.IGNORECASE,
)
#: Hydro-Man, Fluid Felon's intervening if, "if Hydro-Man is a creature", and
#: Flywheel Racer's "Activate only if this permanent is a creature" - the
#: condition's own source being a creature right now, on the computed board
#: (CR 613.5): a Vehicle is one only while crewed (CR 301.7), and Hydro-Man is
#: not one while his own ability has made him a land. The subject is the
#: source itself - CR 700.7's "this <something>", "it", or the card's own name
#: (CR 201.5, `self_reference_names`); anything naming some other object
#: ("enchanted creature", "target ...") is not this shape.
_CONDITION_SELF_IS_A_CREATURE = re.compile(
    r"(?!(?:enchanted|equipped|target|that|another|each|an?|the) )"
    r"(?P<subject>[^,.]+?) is (?:still )?an? creature",
    re.IGNORECASE,
)
#: Phoenix Fleet Airship's intervening if and Goblin Blast-Runner's "as long
#: as": "you sacrificed a permanent this turn" (CR 701.21a), read off
#: `permanents_sacrificed_this_turn`, which only `sacrifice` writes and a new
#: turn clears.
_CONDITION_SACRIFICED_THIS_TURN = re.compile(
    r"you sacrificed (?:a permanent|one or more permanents) this turn", re.IGNORECASE
)
#: Diamond City: "two or more creatures entered the battlefield under your
#: control this turn."
_CONDITION_ENTERED_THIS_TURN = re.compile(
    rf"{count_pattern('count')} or more creatures entered the battlefield "
    r"under your control this turn",
    re.IGNORECASE,
)
#: Delirium (CR 207.2c: an ability word, no rules meaning of its own - the
#: whole condition is the sentence): "there are four or more card types among
#: cards in your graveyard", and its "permanent types" sibling (CR 110.4).
#: Happily Ever After widens the pool to "permanents you control and/or cards
#: in your graveyard": one set of types over both (CR 300.1), the permanents'
#: read off the computed board.
_CONDITION_TYPES_AMONG_GRAVEYARD = re.compile(
    rf"there (?:is|are) {count_pattern('count')} or more (?P<kind>card|permanent) types "
    r"among (?P<permanents>permanents you control and/or )?cards in your graveyard",
    re.IGNORECASE,
)
#: Threshold: "there are seven or more cards in your graveyard" (Barbarian
#: Ring), qualified - "six or more creature cards" (Gate to the Afterlife),
#: "eight or more permanent cards" (Uchbenbak) - or "... cards are in your
#: graveyard". Spell mastery (CR 207.2c) prints a two-word quality, "two or
#: more instant and/or sorcery cards in your graveyard" - either type counts.
_CONDITION_GRAVEYARD_CARDS = re.compile(
    rf"(?:there (?:is|are) )?{count_pattern('count')} or more "
    r"(?:(?P<quality>[\w-]+(?: and/or [\w-]+)?) )?"
    r"cards? (?:are |is )?in your graveyard",
    re.IGNORECASE,
)
#: Merfolk Windrobber: "an opponent has eight or more cards in their graveyard."
_CONDITION_OPPONENT_GRAVEYARD_CARDS = re.compile(
    rf"an opponent has {count_pattern('count')} or more cards in their graveyard",
    re.IGNORECASE,
)
#: Resonating Lute: "you have seven or more cards in your hand."
_CONDITION_HAND_CARDS = re.compile(
    rf"you have {count_pattern('count')} or more cards in (?:your )?hand", re.IGNORECASE
)
#: Fleshless Gladiator: "an opponent has three or more poison counters"
#: (CR 122.1f).
_CONDITION_OPPONENT_POISON = re.compile(
    rf"an opponent has {count_pattern('count')} or more poison counters", re.IGNORECASE
)
#: Luminarch Ascension's "this enchantment has four or more quest counters on
#: it" and Oracle's Vault's "there are three or more brick counters on this
#: artifact" - counters on the ability's own source (CR 122.1).
_CONDITION_SELF_COUNTERS = re.compile(
    rf"(?:this \w+ has {count_pattern('count')} or more (?P<kind>[\w+/-]+) counters on it"
    rf"|there (?:is|are) {count_pattern('count2')} or more (?P<kind2>[\w+/-]+) counters? "
    r"on this \w+)",
    re.IGNORECASE,
)
#: "there are twenty-five or more loyalty counters among Jaces you control"
#: - Jace, Reality Sculptor's own `0`. CR 306.5c: loyalty is the number of
#: loyalty counters on a planeswalker, summed here across every permanent
#: `controller` controls that shares the printed name (CR 201.4's own "this
#: spell/permanent" is never how a card names *other* permanents sharing its
#: type - "Jaces" is CR 201.5's plural of the legendary type Jace itself
#: carries, the same way Empower Jace's own "a Jace token you control"
#: reads the name, not a hardcoded lookup).
_CONDITION_LOYALTY_AMONG_NAMED = re.compile(
    rf"there (?:is|are) {count_pattern('count')} or more loyalty counters? among "
    r"(?P<name>[A-Za-z][a-zA-Z' -]*?)s you control",
    re.IGNORECASE,
)


#: CR 702.62b: "A card is 'suspended' if it's in the exile zone, has suspend,
#: and has a time counter on it." Greater Gargadon's own restriction.
_CONDITION_SUSPENDED = re.compile(r"this (?:card|permanent) is suspended", re.IGNORECASE)
#: CR 702.33d/601.4: Inscription of Abundance's own "If this spell was
#: kicked, choose any number instead." - CR 601.4's worked example for this
#: exact card.
_CONDITION_KICKED = re.compile(r"this spell was kicked", re.IGNORECASE)
#: `machines/teamwork.py`'s own optional additional cost - "If this spell
#: was cast using teamwork, ..." (Cruel Alliance and every other Teamwork
#: spell in the pool), the identical shape `_CONDITION_KICKED` already
#: reads for kicker, off `CastRecord.cast_using_teamwork` instead of
#: `.kicked`.
_CONDITION_CAST_USING_TEAMWORK = re.compile(r"this spell was cast using teamwork", re.IGNORECASE)
#: CR 702.174k: "If a spell's controller declares the intention to pay a
#: spell's gift cost, that spell's gift was promised." Crumb and Get It's and
#: Dawn's Truce's own "If the gift was promised, ..." - read off the resolving
#: object's `CastRecord.gift_promised`, the same record `_CONDITION_KICKED`
#: reads, and carried to a permanent by CR 400.7d the same way.
_CONDITION_GIFT_PROMISED = re.compile(r"the gift was promised", re.IGNORECASE)
#: CR 700.11: Molten Collapse's "If you descended this turn, you may choose
#: both instead."
_CONDITION_DESCENDED = re.compile(r"you descended this turn", re.IGNORECASE)
#: Xerex Strobe-Knight: "you've cast two or more spells this turn" - counted
#: off `Game.spells_cast_this_turn`, which already excludes copies (CR 707.10).
_CONDITION_SPELLS_CAST_THIS_TURN = re.compile(
    rf"you(?:'ve| have) cast {count_pattern('count')} or more spells this turn", re.IGNORECASE
)
#: Grim Repriser's own "Activate only if an opponent has been dealt
#: noncombat damage this turn" (CR 120.2a, CR 602.5b) - read off
#: `Game.turn_facts["dealt_noncombat_damage"]`, recorded per recipient in
#: `deal_damage`.
_CONDITION_OPPONENT_NONCOMBAT_DAMAGE_THIS_TURN = re.compile(
    r"an opponent has been dealt noncombat damage this turn", re.IGNORECASE
)
#: Traxos, Academy Guardian: "you've cast a noncreature spell this turn" - the
#: singular "at least one" sibling of `_CONDITION_SPELLS_CAST_THIS_TURN`,
#: qualified by card type/subtype the same way `_CONDITION_GRAVEYARD_CARDS`
#: already is. Bare "you've cast a spell this turn" (no quality) is the same
#: shape with nothing to qualify - `_card_quality(None)` reads that as every
#: spell.
#: Captain Mar-Vell, Space-Born's own "Cosmic Awareness — As long as an
#: opponent has cast a spell this turn, ..." widens the subject to an
#: opponent too, beside the pre-existing "you've cast" reading - the same
#: `Game.spells_cast_this_turn` board fact, asked of every opponent instead
#: of the controller.
_CONDITION_CAST_A_SPELL_THIS_TURN = re.compile(
    r"(?:(?P<opponent>an opponent) (?:has cast|cast)|you(?:'ve| have) cast) "
    r"an? (?:(?P<quality>[\w-]+) )?spell this turn",
    re.IGNORECASE,
)
#: Veil of Summer's own trailing "Draw a card if an opponent has cast a blue
#: or black spell this turn." and Sandstalker Moloch's differently-worded
#: intervening if, "an opponent cast a blue and/or black spell this turn" -
#: the same board fact (CR 105.1's five colors) read off `Game.spells_cast_
#: this_turn`, the identical list `_CONDITION_CAST_A_SPELL_THIS_TURN` above
#: already reads for a *quality* word, now read for one or more *colour*
#: words instead - CR 105.1's "or" is inclusive (a spell that is both
#: still counts), so "blue or black"/"blue and/or black" are the same
#: question asked two different ways: did an opponent cast a spell that
#: was blue, or was black, or both. `(?:has cast|cast)` covers both cards'
#: own tenses without needing two separate patterns.
_CONDITION_OPPONENT_CAST_COLOR = re.compile(
    r"an opponent (?:has cast|cast) an? "
    r"(?P<colors>(?:white|blue|black|red|green)"
    r"(?:(?:,\s*|\s+and/or\s+|\s+or\s+|\s+and\s+)(?:white|blue|black|red|green))*)"
    r" spell this turn",
    re.IGNORECASE,
)
#: Proctor of Potential: "you've scried or surveilled this turn" (CR
#: 701.22a, 701.25a) - read off `Game.turn_facts["scried_or_surveilled"]`
#: (`turn_fact_holds`), recorded in `scry` and `surveil` alike, since the
#: printed condition treats either verb as satisfying it.
_CONDITION_SCRIED_OR_SURVEILLED_THIS_TURN = re.compile(
    r"you(?:'ve| have) scried or surveilled this turn", re.IGNORECASE
)
#: Fblthp, Impossibly Lost's own "your library has no cards in it" (CR
#: 401.1's zone, counted the plain way `_CONDITION_HAND_CARDS`/`_CONDITION_
#: GRAVEYARD_CARDS` already count a player's own zone) - a board fact read
#: fresh every time, not a turn fact, so a card drawn or milled since the
#: library last emptied is read correctly.
_CONDITION_LIBRARY_EMPTY_RE = re.compile(r"your library has no cards in it", re.IGNORECASE)
#: Morbid (an ability word, CR 207.2c): "a creature died this turn" -
#: Brimstone Volley's, Gruesome Discovery's own condition, formerly a private
#: `machines/effects.py` lookup (`_INSTEAD_CONDITIONS`), moved here so every
#: reader that asks `condition_holds` - not only the "instead" shape - reads
#: it the same way.
_CONDITION_CREATURE_DIED_THIS_TURN = re.compile(r"a creature died this turn", re.IGNORECASE)
#: Lagomos, Hand of Hatred's "five or more creatures died this turn" - the
#: counted form of the morbid condition above, over the same per-turn count
#: of CR 700.4 deaths.
_CONDITION_CREATURES_DIED_THIS_TURN = re.compile(
    rf"{count_pattern('count')} or more creatures died this turn", re.IGNORECASE
)
#: Minas Tirith's "you attacked with two or more creatures this turn" and
#: Temple of Civilization's "three or more" - creatures declared as
#: attackers (CR 508.1) this turn, `Game.attacked_this_turn`.
_CONDITION_ATTACKED_WITH_N = re.compile(
    rf"you attacked with {count_pattern('count')} or more creatures this turn", re.IGNORECASE
)
#: Temple of Cyclical Time's "it has no time counters on it" - the source's
#: own counters (CR 122.1), the zero form of `_CONDITION_SELF_COUNTERS`.
_CONDITION_SELF_NO_COUNTERS = re.compile(
    r"(?:it|this \w+) has no (?P<kind>[\w+/-]+) counters on it", re.IGNORECASE
)
#: Twinned Vision's own "this spell wasn't cast from your hand" / "... from
#: hand" - CR 601.2a's own "from where it is to the stack" cast-from zone,
#: read off the resolving spell's own `CastRecord` (`source`). Also moved
#: here from the same former `_INSTEAD_CONDITIONS` table.
_CONDITION_NOT_CAST_FROM_HAND = re.compile(
    r"this spell wasn'?t cast from (?:your )?hand", re.IGNORECASE
)
#: "this spell was cast from a graveyard" - Plunder the Trollshaws', Tidings
#: of War's and Secrets of the Key's flashback rider: CR 601.2a's own "from
#: where it is to the stack" zone, read off the resolving spell's own
#: `CastRecord` (`source`) the same way `_CONDITION_NOT_CAST_FROM_HAND` is. A
#: copy (CR 707.10) is never cast, so it was never cast from a graveyard.
_CONDITION_CAST_FROM_GRAVEYARD = re.compile(
    r"this spell was cast from (?:a|your) graveyard", re.IGNORECASE
)
#: "this spell's additional cost was paid" - Burning Curiosity's "If this
#: spell's additional cost was paid, exile the top three cards instead." and
#: Cinder Strike's "... instead if this spell's additional cost was paid."
#: (CR 118.8b's optional additional cost, read as the instruction resolves,
#: CR 608.2c) - `CastRecord.optional_additional_cost_paid`, which names
#: no keyword, the same reading `machines/effects._parse_if_additional_cost_
#: paid_clause` already gives the non-"instead" form.
_CONDITION_ADDITIONAL_COST_PAID = re.compile(
    r"this spell'?s additional cost was paid", re.IGNORECASE
)
#: "this creature entered this turn" (Moon-Circuit Hacker's "unless" rider),
#: "this land entered this turn" (Mirrex's activation restriction) - the
#: condition's own source, read off `CardState.turn_entered` against the
#: current turn. A source that has since left the battlefield keeps its stamp,
#: which is its last known information (CR 608.2h).
_CONDITION_SELF_ENTERED_THIS_TURN = re.compile(
    r"this (?:creature|permanent|artifact|enchantment|land|planeswalker|battle) entered "
    r"(?:the battlefield )?this turn",
    re.IGNORECASE,
)
#: "you attacked this turn" (Kaito Shizuki's `+1`) - whether the player
#: declared one or more attackers this turn (CR 508.1), recorded as the
#: `turn_facts["attacked"]` fact by `declare_attackers`.
_CONDITION_YOU_ATTACKED_THIS_TURN = re.compile(r"you attacked this turn", re.IGNORECASE)
#: Landfall's "you had a land enter the battlefield under your control this
#: turn" (Searing Blaze; CR 207.2c: the ability word is only a label), read
#: off the `turn_facts["land_entered"]` fact `_announce_entry` records.
_CONDITION_LAND_ENTERED_THIS_TURN = re.compile(
    r"(?:you had a land enter|a land entered) the battlefield under your control this turn",
    re.IGNORECASE,
)


#: Every shape `condition_holds` reads, in the same order it tries them -
#: kept as one tuple, rather than re-deriving it, so `condition_is_readable`
#: below and `condition_holds` itself can never drift apart on which
#: conditions this engine actually understands.
_CONDITION_PATTERNS: tuple[re.Pattern[str], ...] = (
    _CONDITION_POWER,
    _CONDITION_CONTROLS_N,
    _CONDITION_CONTROLS_A,
    _CONDITION_CONTROLS_ANOTHER,
    _CONDITION_CONTROLS_NAMED_PAIR,
    _CONDITION_OPPONENT_COMPARISON,
    _CONDITION_SELF_IS_A_CREATURE,
    _CONDITION_SACRIFICED_THIS_TURN,
    _CONDITION_ENTERED_THIS_TURN,
    _CONDITION_TYPES_AMONG_GRAVEYARD,
    _CONDITION_GRAVEYARD_CARDS,
    _CONDITION_OPPONENT_GRAVEYARD_CARDS,
    _CONDITION_HAND_CARDS,
    _CONDITION_OPPONENT_POISON,
    _CONDITION_SELF_COUNTERS,
    _CONDITION_LOYALTY_AMONG_NAMED,
    _CONDITION_SPELLS_CAST_THIS_TURN,
    _CONDITION_OPPONENT_NONCOMBAT_DAMAGE_THIS_TURN,
    _CONDITION_CAST_A_SPELL_THIS_TURN,
    _CONDITION_OPPONENT_CAST_COLOR,
    _CONDITION_SUSPENDED,
    _CONDITION_KICKED,
    _CONDITION_CAST_USING_TEAMWORK,
    _CONDITION_GIFT_PROMISED,
    _CONDITION_DESCENDED,
    _CONDITION_SCRIED_OR_SURVEILLED_THIS_TURN,
    _CONDITION_LIBRARY_EMPTY_RE,
    _CONDITION_CREATURE_DIED_THIS_TURN,
    _CONDITION_NOT_CAST_FROM_HAND,
    _CONDITION_CAST_FROM_GRAVEYARD,
    _CONDITION_ADDITIONAL_COST_PAID,
    _CONDITION_SELF_ENTERED_THIS_TURN,
    _CONDITION_YOU_ATTACKED_THIS_TURN,
    _CONDITION_LAND_ENTERED_THIS_TURN,
)


def _names_the_source(subject: str, source: CardState) -> bool:
    """Whether a condition's `subject` is its own source: CR 700.7's "this
    `<something>`", a legend's own "he"/"she", or one of the names CR 201.5
    lets its text call itself by (`self_reference_names`). A bare "it" is
    not read as the source - in a rider it is the object an earlier
    instruction named."""
    words = subject.strip().lower()
    if words in ("he", "she") or re.fullmatch(r"this [a-z]+", words):
        return True
    legendary = "legendary" in (source.card.type_line or "").lower()
    return any(
        words == name.lower() for name in self_reference_names(source.name, legendary=legendary)
    )


def condition_is_readable(condition: str) -> bool:
    """Whether `Game.condition_holds` would recognise `condition`'s *shape*
    at all - a regex-only check, with no `Game` (and so no board state) in
    sight, for a parser deciding at *parse* time whether a printed
    conditional clause is one this engine can gate on, before any `Game`
    object exists to ask `condition_holds` itself.

    A parser that skips this and calls `condition_holds` only at resolution
    time has no way to fail closed on an unrecognised condition without
    either guessing it False (silently wrong the moment the condition is
    ever true) or building the whole `Effect` closure speculatively and
    throwing it away - this answers the question up front instead, the same
    way `_targets_understood` lets a targeted-clause parser fail closed on
    an unreadable target phrase before ever building an `Effect`.

    Mirrors `condition_holds` exactly: every pattern it tries is in
    `_CONDITION_PATTERNS`, in the same order, so a `True` here is read the
    same way once resolution actually asks.
    """
    from ...machines import conditions

    text = condition.strip().rstrip(".").strip()
    if (alternatives := _condition_alternatives(text)) is not None:
        return all(condition_is_readable(part) for part in alternatives)
    return builtin_condition_readable(text) or conditions.claims(text)


def builtin_condition_readable(condition: str) -> bool:
    """Whether one of `Game.builtin_condition_holds`' own `_CONDITION_*`
    patterns matches `condition` whole - the built-in half of
    `condition_is_readable`, which `machines/conditions.claims` asks too."""
    text = condition.strip().rstrip(".").strip()
    return any(pattern.fullmatch(text) is not None for pattern in _CONDITION_PATTERNS)


#: "`<condition>` or if `<condition>`" - Gathering Place's own "Activate only
#: if this land entered this turn or if you control a basic land": either
#: half being true is enough.
_CONDITION_OR_IF = re.compile(r"\s+or if\s+", re.IGNORECASE)


def _condition_alternatives(text: str) -> list[str] | None:
    """The halves of an "X or if Y" condition, or `None` for a plain one."""
    parts = _CONDITION_OR_IF.split(text)
    return parts if len(parts) > 1 else None


#: CR 110.4a: "Specifically, it means an artifact, battle, creature,
#: enchantment, land, or planeswalker card."
_PERMANENT_TYPES = frozenset(
    {Type.ARTIFACT, Type.BATTLE, Type.CREATURE, Type.ENCHANTMENT, Type.LAND, Type.PLANESWALKER}
)


def _is_minus_symbol(printed: str) -> bool:
    """Whether a printed loyalty symbol is a negative one (CR 107.7).

    "Negative loyalty symbols point downward and feature a minus sign followed
    by a number or an X." Both the typographic minus WOTC prints (U+2212) and a
    plain hyphen are accepted, since the oracle text this is read from uses the
    former and hand-written text tends to use the latter.
    """
    return printed.strip().startswith(("−", "-"))


def _card_type_named(quality: str) -> Type | None:
    """The card type a protection quality names, or None if it names something else.

    CR 205.2a lists the card types; a protection quality states them in the
    plural ("protection from instants"), so the trailing "s" comes off before
    the lookup.
    """
    word = quality.strip().lower().removesuffix("s")
    try:
        return Type(word)
    except ValueError:
        return None


def _negated_card_type_named(quality: str) -> Type | None:
    """The card type a "non`<type>`" quality names, or `None` for anything
    else - Invasion of Regatha // Disciples of the Inferno's "a noncreature
    source you control", the identical "non" + CR 205.2a card-type-word
    negation `machines/casting_restrictions.py::_matches_type_filter` already
    reads for "noncreature spells" (Soulless Jailer), asked here of a damage
    source's own quality (CR 609.7b/702.16a) instead of a spell's card types."""
    word = quality.strip().lower()
    if not word.startswith("non"):
        return None
    return _card_type_named(word.removeprefix("non"))


def _has_color_quality(wanted: str, colors: Iterable[Color]) -> bool | None:
    """Whether an object of `colors` has the colour quality `wanted` - a
    colour word or a CR 105.2a/105.2b colour count - or `None` when `wanted` is
    neither."""
    color = _COLOR_WORDS.get(wanted)
    if color is not None:
        return color in colors
    count = _COLOR_COUNT_QUALITIES.get(wanted)
    if count is not None:
        return count(len(set(colors)))
    return None


def _permanent_quality(phrase: str) -> Callable[[Characteristics], bool] | None:
    """A counted noun phrase - "artifacts", "lands", "snow permanents", "black
    permanents", "Vampires" - as a test on a permanent's computed
    characteristics (CR 613.5), or None when any word of it is not read.

    The last word is the noun ("permanents" is every permanent, CR 110.4);
    every word before it is a qualifier `_characteristic_word` must read. A
    phrase with a word it cannot read - "creatures with different powers" -
    is refused whole rather than read as its first word.
    """
    words = phrase.strip().split()
    if not words:
        return None
    *qualifiers, noun = words
    tests: list[Callable[[Characteristics], bool]] = []
    if noun.lower() not in ("permanent", "permanents"):
        noun_test = _characteristic_word(noun)
        if noun_test is None:
            return None
        tests.append(noun_test)
    for qualifier in qualifiers:
        qualifier_test = _characteristic_word(qualifier)
        if qualifier_test is None:
            return None
        tests.append(qualifier_test)
    return lambda chars: all(test(chars) for test in tests)


def _card_quality(word: str | None) -> Callable[[CardState], bool] | None:
    """A graveyard card's quality - "creature", "permanent" (CR 110.4a), a
    card type or subtype, or a subtype qualifying a type ("Zombie creature",
    Tomb Tyrant's own "at least three Zombie creature cards in your
    graveyard") - or every card when the text prints none.

    Multiple words each qualify the noun (every word ANDed), the same
    qualifiers-then-noun reading `_permanent_quality` already gives a
    permanent's computed characteristics - not a word list of this
    function's own, just this same one-word reading run once per word. A
    "non" prefix negates a single word ("noncreature"). None when any word
    is not read."""
    if word is None:
        return lambda state: True
    lowered = word.strip().lower()
    if " and/or " in lowered:
        # Spell mastery's "instant and/or sorcery" card: either quality.
        parts = [_card_quality(part.strip()) for part in lowered.split(" and/or ")]
        if any(part is None for part in parts):
            return None
        return lambda state: any(part(state) for part in parts)  # type: ignore[misc]
    words = lowered.split()
    if len(words) > 1:
        tests = [_card_quality(each) for each in words]
        if any(test is None for test in tests):
            return None
        return lambda state: all(test(state) for test in tests)  # type: ignore[misc]
    if lowered.startswith("non") and len(lowered) > 4:
        inner = _card_quality(lowered.removeprefix("non").lstrip("-"))
        if inner is None:
            return None
        return lambda state: not inner(state)
    if lowered == "permanent":
        return lambda state: bool(_PERMANENT_TYPES.intersection(state.types))
    card_type = _card_type_named(lowered)
    if card_type is not None:
        return lambda state: card_type in state.types
    subtype = canonical_subtype(word)
    if subtype is not None:
        return lambda state: any(each.lower() == subtype for each in state.subtypes)
    return None


def _names_match(obj: CardState, chosen: str) -> bool:
    """Whether `obj` has the chosen card name (CR 201.4). A split card has
    both halves' names (CR 201.4b's own premise), so either half matches."""
    name = obj.name
    return chosen == name or chosen in (part.strip() for part in name.split("//"))


class ConditionsMixin:
    def _carry_cast_record(self: "Game", state: CardState, stamp_before: UUID) -> None:
        """Re-key the record of the object `state` was a moment ago onto the
        object it is now, for a move the cast itself makes: a spell re-stated
        onto the stack, or a permanent spell becoming the permanent (CR
        400.7d). Every other move leaves the old key behind, unreadable."""
        record = self.cast_records.pop(stamp_before, None)
        if record is not None:
            self.cast_records[state.zone_change_stamp] = record

    def _forget_counts(self: "Game") -> None:
        self._linked_count = None
        self._linked_counts_by_player = {}
        self._counting_player = None

    @contextmanager
    def counting_for(self: "Game", username: str) -> Iterator[None]:
        """Scope `record_count`/`recorded_count` to one player's own count
        while that player carries out their part of an "each player ..."
        instruction (CR 608.2e)."""
        previous = self._counting_player
        self._counting_player = username
        try:
            yield
        finally:
            self._counting_player = previous

    def record_count(self: "Game", count: int | None) -> None:
        """Record how many objects the resolving object's current instruction
        actually moved, for a later "that many" to read (`_linked_count`) -
        or `None` to clear it ahead of an instruction whose count a later
        "if you do" asks about."""
        self._linked_count = count
        if self._counting_player is not None:
            if count is None:
                self._linked_counts_by_player.pop(self._counting_player, None)
            else:
                self._linked_counts_by_player[self._counting_player] = count

    def recorded_count(self: "Game") -> int | None:
        """The count `record_count` last wrote during this resolution - the
        player's own while `counting_for` names one - or None when no counted
        instruction has run yet."""
        if self._counting_player is not None:
            return self._linked_counts_by_player.get(self._counting_player)
        return self._linked_count

    def revolt_active_for(self: "Game", controller: str) -> bool:
        """Whether Revolt's condition holds for `controller` right now: CR
        207.2c's ability word, printed as "a permanent you controlled left
        the battlefield this turn" (Fatal Push: "...under your control this
        turn"). Checked at resolution, not at announcement - the same instant
        `Game.legal_target`'s CR 608.2b recheck already reads other resolution-
        time conditions from."""
        return self.permanents_left_battlefield_this_turn.get(controller, 0) > 0

    def record_turn_fact(self: "Game", fact: str, player: str) -> None:
        """Note that `fact` happened for `player` this turn - `turn_facts`'
        own write half.

        Idempotent (a `set`, not a counter): a fact that already holds for
        `player` this turn is unchanged by happening again, which is what
        every consumer of this ledger asks - "did you", never "how many
        times"."""
        self.turn_facts.setdefault(fact, set()).add(player)

    def note_last_counter_removed(self: "Game", permanent: CardState, kind: str) -> None:
        """`permanent`'s last `kind` counter was just removed: raise
        `ExtraTriggerEvent.LAST_COUNTER_REMOVED` - CR 310.12b's Siege defeat
        trigger, "When the last defense counter is removed from this
        permanent". `CardState.remove_counters` calls this for every removal
        that empties a kind, whatever did the removing."""
        self.emit(
            GameEvent(
                event=ExtraTriggerEvent.LAST_COUNTER_REMOVED,
                subject_id=permanent.id,
                subject_name=permanent.name,
                subject_card=permanent.card,
                player=self.controller_of(permanent).username,
                counter_kind=kind,
            )
        )

    def _record_shown(
        self: "Game",
        card_state: CardState,
        viewers: list[str] | None,
        source: str | None,
        *,
        library_epoch: int | None = None,
    ) -> CardState:
        """Append the `Reveal` both `reveal` and `look` record.

        The stamp and, for a library card, the owner's library epoch are read
        now, because they are what `known_to` compares later: CR 400.7 for
        the card, CR 701.20d for the order it sat in. `library_epoch` pins a
        library record to a later order instead - `look_at_top_and_split`'s,
        whose caller puts the cards back.
        """
        with self._id_allocator_scope():
            owner = self._seat(card_state.owner)
            in_library = card_state.zone is Zone.LIBRARY and owner is not None
            if in_library and owner and library_epoch is None:
                library_epoch = owner.library_epoch
            self.reveals.append(
                Reveal(
                    card_id=card_state.id,
                    card_name=card_state.name,
                    revealed_by=card_state.owner or "",
                    zone=card_state.zone,
                    source=source,
                    viewers=None if viewers is None else list(viewers),
                    zone_change_stamp=card_state.zone_change_stamp,
                    turn=self._turns_taken(),
                    library_epoch=library_epoch if in_library else None,
                )
            )
            return card_state

    def known_to(self: "Game", viewer: str) -> list[KnownCard]:
        """Every card `viewer` knows from a reveal, a look, or a carry, right now.

        Pure: it reads `reveals` and `known_carries` and changes nothing, so
        asking twice answers the same. A record is live for `viewer` only when
        all of these hold, and anything else - including a record whose shape
        this does not recognise - is left out (fail closed):

        - `viewer` saw it: `Reveal.viewers` is `None` (CR 701.20a, all
          players) or names them (CR 701.20e).
        - The card is still that object: it is in the recorded zone with the
          recorded `zone_change_stamp` (CR 400.7).
        - For a library record, the library is still in that order: the
          owner's `Player.library_epoch` is the recorded one (CR 701.20d,
          CR 701.24a), and `index_from_top` is where the card is now.

        A carry (`KnownCarry`, a knowledge policy rather than a CR rule) is
        live while the card sits in its owner's hand with the stamp it
        arrived with. One entry per card: a later live record replaces an
        earlier one for the same card, so a card revealed again (CR 701.20c)
        is known once, from its newest showing.
        """
        found: dict[UUID, KnownCard] = {}
        for carry in self.known_carries:
            carried = self._live_carry(carry, viewer)
            if carried is not None:
                found[carry.card_id] = carried
        for reveal in self.reveals:
            shown = self._live_reveal(reveal, viewer)
            if shown is not None:
                found[reveal.card_id] = shown
        # "You may look at the top card of your library any time." (Radar
        # Sense, Ka-Zar, Iron Lad, Courser of Kruphix, Augur of Autumn) - a
        # live CR 611.3d grant rather than a one-shot `Reveal` record: this
        # reads the *current* top card fresh every call (`known_to` stays
        # pure), so it tracks a shuffle or a draw with no stale record to
        # ever expire. Only `viewer`'s own library, and only while a
        # permanent they control still grants it.
        viewer_player = self._seat(viewer)
        if (
            viewer_player is not None
            and viewer_player.library
            and self.controls_look_at_top_permission(viewer)
        ):
            top = viewer_player.library[0]
            found[top.id] = KnownCard(
                card_id=top.id,
                card_name=top.name,
                owner=viewer,
                zone=Zone.LIBRARY,
                index_from_top=0,
                source='a static "look at the top card" permission',
                turn=self._turns_taken(),
                carried=False,
            )
        # Shared Fate (and Colfenor's Plans): a face-down card in a pile the
        # viewer's permission lets them look at is known to them.
        from ...machines.casting import may_look_at_linked_exile

        for card in self.exile:
            if (
                not card.face_up
                and card.exile_annotation is not None
                and card.id not in found
                and may_look_at_linked_exile(self, card, viewer)
            ):
                found[card.id] = KnownCard(
                    card_id=card.id,
                    card_name=card.card.name,
                    owner=card.owner or "",
                    zone=Zone.EXILE,
                    index_from_top=None,
                    source="a permission to look at cards exiled with a permanent",
                    turn=self._turns_taken(),
                    carried=False,
                )
        # Lens of Clarity: every face-down creature the viewer does not control
        # is known to them while a permanent they control grants the look.
        if self.looks_at_opposing_face_down_creatures(viewer):
            for permanent in self.battlefield:
                if permanent.face_down and self.controller_of(permanent).username != viewer:
                    found[permanent.id] = KnownCard(
                        card_id=permanent.id,
                        card_name=permanent.card.name,
                        owner=permanent.owner or "",
                        zone=Zone.BATTLEFIELD,
                        index_from_top=None,
                        source="a static look at face-down creatures",
                        turn=self._turns_taken(),
                        carried=False,
                    )
        # "Play with your hand revealed." (Enduring Renewal) - every card in a
        # revealed hand is known to every viewer (CR 701.20a), read fresh like
        # the look-at-the-top permission above.
        for seat in self.players:
            if seat.hand and self.hand_is_revealed(seat.username):
                for held in seat.hand:
                    found[held.id] = KnownCard(
                        card_id=held.id,
                        card_name=held.name,
                        owner=seat.username,
                        zone=Zone.HAND,
                        index_from_top=None,
                        source='a static "play with your hand revealed" grant',
                        turn=self._turns_taken(),
                        carried=False,
                    )
        # "Play with the top card of your library revealed." (Courser of
        # Kruphix, Melek): every seat's top card is public to every viewer
        # while a permanent its owner controls says so (CR 400.2).
        for seat in self.players:
            if seat.library and self.reveals_top_card(seat.username):
                top = seat.library[0]
                found[top.id] = KnownCard(
                    card_id=top.id,
                    card_name=top.name,
                    owner=seat.username,
                    zone=Zone.LIBRARY,
                    index_from_top=0,
                    source='a static "play with the top card revealed" line',
                    turn=self._turns_taken(),
                    carried=False,
                )
        return list(found.values())

    def _live_reveal(self: "Game", reveal: Reveal, viewer: str) -> KnownCard | None:
        if reveal.viewers is not None and viewer not in reveal.viewers:
            return None
        if reveal.zone_change_stamp is None or reveal.turn is None:
            return None
        card_state = self.find_by_id(reveal.card_id)
        if card_state is None or card_state.zone is not reveal.zone:
            return None
        if card_state.zone_change_stamp != reveal.zone_change_stamp:
            return None
        owner = self._seat(card_state.owner)
        if owner is None:
            return None
        index_from_top: int | None = None
        if reveal.zone is Zone.LIBRARY:
            if not self._library_order_holds(
                card_state.id, card_state.zone_change_stamp, owner, reveal.library_epoch
            ):
                return None
            index_from_top = next(
                (index for index, state in enumerate(owner.library) if state is card_state), None
            )
            if index_from_top is None:
                return None
        elif reveal.library_epoch is not None:
            return None
        return KnownCard(
            card_id=reveal.card_id,
            card_name=reveal.card_name,
            owner=owner.username,
            zone=reveal.zone,
            index_from_top=index_from_top,
            source=reveal.source,
            turn=reveal.turn,
            carried=False,
        )

    def _live_carry(self: "Game", carry: KnownCarry, viewer: str) -> KnownCard | None:
        if carry.viewers is not None and viewer not in carry.viewers:
            return None
        card_state = self.find_by_id(carry.card_id)
        owner = self._seat(carry.owner)
        if card_state is None or owner is None or card_state.zone is not Zone.HAND:
            return None
        if card_state.zone_change_stamp != carry.zone_change_stamp:
            return None
        if not any(state is card_state for state in owner.hand):
            return None
        return KnownCard(
            card_id=carry.card_id,
            card_name=carry.card_name,
            owner=carry.owner,
            zone=Zone.HAND,
            index_from_top=None,
            source=carry.source,
            turn=carry.turn,
            carried=True,
        )

    def carry_knowledge_into_hand(
        self: "Game", card_state: CardState, stamp_before: UUID, origin: Zone = Zone.LIBRARY
    ) -> None:
        """Carry every record still live for `card_state` in `origin` into its
        owner's hand, as `KnownCarry` data (a knowledge policy, not a CR rule).

        Called by `Player.add` for a card moving straight from a hidden group
        its owner holds into that owner's hand, after the move, with the stamp
        the card had before it: from the library - a draw (CR 121.1) or any
        effect that makes the same move - or from outside the game, a card
        revealed there (CR 400.11a, CR 701.20a) and then put into the hand
        (Karn, the Great Creator's -2, Burning Wish). A library record the
        epoch had already ended before the move (CR 701.20d) is not live, so
        it is not carried; neither is a record of an earlier object (CR 400.7).
        """
        owner = self._seat(card_state.owner)
        if owner is None:
            return
        for reveal in list(self.reveals):
            if (
                reveal.card_id != card_state.id
                or reveal.zone is not origin
                or reveal.zone_change_stamp is None
                or reveal.zone_change_stamp != stamp_before
                or reveal.turn is None
            ):
                continue
            if origin is Zone.LIBRARY:
                if not self._library_order_holds(
                    card_state.id, stamp_before, owner, reveal.library_epoch
                ):
                    continue
            elif reveal.library_epoch is not None:
                continue
            self.known_carries.append(
                KnownCarry(
                    card_id=card_state.id,
                    card_name=reveal.card_name,
                    owner=owner.username,
                    viewers=None if reveal.viewers is None else list(reveal.viewers),
                    zone_change_stamp=card_state.zone_change_stamp,
                    source=reveal.source,
                    turn=reveal.turn,
                )
            )

    def carry_public_knowledge_into_hand(self: "Game", card_state: CardState, origin: Zone) -> None:
        """Record a card that moved from a public zone into its owner's hand as
        known to every player, as `KnownCarry` data (a knowledge policy, not a
        CR rule).

        CR 400.2 makes the graveyard, battlefield, stack and exile public zones,
        "zones in which all players can see the cards' faces", so every player
        saw this card before it went into the hand - a graveyard return, a
        bounce, a dash return. Called by `Player.add` after the move, so the
        record carries the stamp the card arrived with and ends at its next
        zone change (CR 400.7), exactly like a carried library record. `origin`
        names the zone it came from, for the record's source.
        """
        owner = self._seat(card_state.owner)
        if owner is None:
            return
        self.known_carries.append(
            KnownCarry(
                card_id=card_state.id,
                card_name=card_state.name,
                owner=owner.username,
                viewers=None,
                zone_change_stamp=card_state.zone_change_stamp,
                source=origin.value,
                turn=self._turns_taken(),
            )
        )

    @staticmethod
    def _face_seen_in_public_zone(card_state: CardState) -> bool:
        """Whether every player can see this card's face where it is now.

        CR 400.2: "Public zones are zones in which all players can see the
        cards' faces, except for those cards that some rule or effect
        specifically allow to be face down." CR 406.3 and CR 708.2 are those
        exceptions: a card exiled face down, and a face-down spell or
        permanent."""
        return (
            not card_state.zone.is_hidden
            and not card_state.zone.is_outside_the_game
            and card_state.face_up
            and card_state.face_down_characteristics is None
        )

    def _record_cards_seen_going_into_libraries(
        self: "Game", placed: Sequence[CardState], origins: Mapping[UUID, Zone]
    ) -> None:
        """Record a card every player saw go into a library, at the position it
        went to (a knowledge policy over CR 400.2, the library twin of
        `carry_public_knowledge_into_hand`).

        Only when it is the one card this instruction put into that library:
        CR 401.4, "If an effect puts two or more cards in a specific position
        in a library at the same time, the owner of those cards may arrange
        them in any order. That library's owner doesn't reveal the order in
        which the cards go into the library." Recorded after the placement
        has moved the library epoch, so the record lives until the library is
        next reordered (CR 701.20d) or the card moves (CR 400.7), and a draw
        carries it into the hand (`carry_knowledge_into_hand`)."""
        by_library: dict[str, list[CardState]] = {}
        for card_state in placed:
            if card_state.zone is Zone.LIBRARY and card_state.owner is not None:
                by_library.setdefault(card_state.owner, []).append(card_state)
        for cards in by_library.values():
            if len(cards) != 1:
                continue
            (card_state,) = cards
            origin = origins.get(card_state.id)
            if origin is None:
                continue
            self._record_shown(card_state, None, origin.value)

    def _last_known_stat(self: "Game", card_id: UUID, stat: str) -> int | None:
        """A departed permanent's power or toughness as CR 608.2h reads it:
        `CardState.last_known_power_toughness`. `None`
        for an id nothing finds or a non-numeric (`*`) value."""
        state = self.find_by_id(card_id)
        if state is None:
            return None
        if state.zone is Zone.BATTLEFIELD:
            return getattr(state, stat)
        power, toughness = state.last_known_power_toughness()
        return power if stat == "power" else toughness

    def _last_known_color_count(self: "Game", card_id: UUID) -> int:
        """How many colours a sacrificed permanent had (CR 105.1), the computed
        ones while it is still on the battlefield (CR 613.5) and its own once
        it has left; 0 for an id nothing finds (a token that has ceased to
        exist, CR 704.5d - callers read it while the token is still there)."""
        state = self.find_by_id(card_id)
        if state is None:
            return 0
        if state.zone is Zone.BATTLEFIELD:
            return len(self.characteristics_of(state).colors)
        return len(state.card.colors or ())

    def last_known_mana_value(self: "Game", card: "CardState | UUID") -> float:
        """An object's mana value as CR 608.2h reads it (CR 202.3): the
        computed one while it is still on the battlefield (a copy has the
        copied mana cost, CR 707.2), the snapshot `CardState.last_known_mana_
        value` took as it left when that differed, and otherwise its own.

        An id `find_by_id` no longer finds - a token that has ceased to exist
        (CR 704.5d) - reads 0: a caller that needs such a token's value takes
        it while the token is still there, as `note_cast` and
        `activate_ability` do for the permanents a cost sacrificed.
        """
        state = self.find_by_id(card) if isinstance(card, UUID) else card
        if state is None:
            return 0.0
        if state.zone is Zone.BATTLEFIELD:
            return self.characteristics_of(state).mana_value
        if state.last_known_mana_value is not None:
            return state.last_known_mana_value
        return state.mana_value

    def _player_quality_protects(
        self: "Game", target: CardState, quality: str, source_controller: str | None
    ) -> bool:
        """Whether `quality` is CR 702.16k's player quality and names the
        player controlling the source: "each of your opponents" is every
        opponent of `target`'s controller (CR 702.16i), so a source an
        opponent controls is one it has protection from, and one its own
        controller controls never is. `False` for any other quality, and for a
        source whose controller is not known."""
        if source_controller is None or not _EACH_OPPONENT_PROTECTION_QUALITY.match(
            quality.strip()
        ):
            return False
        return source_controller != self.controller_of(target).username

    def _quality_characteristics_of(
        self: "Game", source: Any
    ) -> tuple[tuple[Color, ...], tuple[Type, ...], tuple[str, ...], tuple[Any, ...], str] | None:
        """The colours, types, subtypes and supertypes CR 702.11d judges
        `source` by, and its name for a refusal message.

        - An `AbilityOnStack` is judged by its source (CR 113.7: "the object
          that generated it"), found by id or, once it has ceased to exist,
          by `source_last_known`.
        - A permanent on the battlefield: its computed characteristics
          (CR 613.5), so a colour or type an effect changed counts.
        - A spell on the stack, or a card about to be cast: the object as it
          is there.
        - An object that has left the battlefield: its last known
          information (CR 113.7a, CR 608.2b) - the `last_known_*` snapshot
          `CardState.remember_last_known_power_toughness` took as it left,
          where a continuous effect made it differ from the printing.
        - A bare `Card`: its printing.
        """
        if isinstance(source, AbilityOnStack):
            ability_name = source.name
            source = source.source_or_last_known(self)
            if source is None:
                return None
            characteristics = self._quality_characteristics_of(source)
            if characteristics is None:
                return None
            return (*characteristics[:4], ability_name)
        if isinstance(source, Card):
            return (
                tuple(source.colors),
                tuple(source.types),
                tuple(source.subtypes),
                tuple(source.supertypes),
                source.name,
            )
        if not isinstance(source, CardState):
            return None
        if source.zone is Zone.BATTLEFIELD:
            computed = self.characteristics_of(source)
            return (
                tuple(computed.colors),
                tuple(computed.types),
                tuple(computed.subtypes),
                tuple(computed.supertypes),
                source.name,
            )
        return (
            source.last_known_colors if source.last_known_colors is not None else source.colors,
            source.last_known_types if source.last_known_types is not None else source.types,
            (
                source.last_known_subtypes
                if source.last_known_subtypes is not None
                else source.subtypes
            ),
            tuple(source.supertypes),
            source.name,
        )

    def source_has_quality_of_card(
        self: "Game",
        source: "Card",
        quality: str,
        *,
        is_spell: bool = False,
        source_state: CardState | None = None,
        source_mana_value: float | None = None,
    ) -> bool:
        """`source_has_quality` for a bare `Card` rather than a `CardState`.

        `source_mana_value` is a spell's mana value on the stack, X as chosen
        (CR 202.3e), for a "mana value 3 or greater" quality - a bare `Card`
        only knows X as 0. A live `source_state` (an ability's permanent) is
        read through `characteristics_of` instead; with neither, the printed
        value.

        The targeting half of CR 702.16b is asked about the *card* behind a
        spell or an ability's source, while the damage half (CR 702.16e) is
        asked about a `CardState`. Both read the same four flavours of
        quality, so the reading lives in one place and this is the adapter.

        `is_spell` is CR 112.1's own "spell" quality: "a card on the stack" -
        unlike a card type (CR 702.16a's own extension reaching a source in
        any zone), never true of a bare `Card`, so it has to be told by the
        caller, which already knows whether the source it read this `Card`
        off was a spell or an ability (`_source_card_of`).

        `source_state` is the live `CardState` behind an *ability's* source
        permanent, when the caller has one - needed for "permanents that were
        cast this turn" (`Game.was_cast_this_turn`), which asks a question a
        bare `Card` has no way to answer (it is not "on the battlefield" or
        "off the battlefield", it is not anything - CR 110.1's permanent is a
        live object, not a print). Never given for a spell: CR 110.1 makes a
        spell on the stack never a permanent in the first place, so this
        quality is always false for one regardless of what card it prints,
        the same way it is always false for a bare `is_spell=True` here.
        """
        wanted = quality.strip().lower()
        if wanted == "everything":
            # CR 702.16j: protection from everything is protection from each
            # object, whatever its characteristics.
            return True
        if _is_spell_quality(wanted):
            return is_spell
        if (spell_colours := _spell_colour_quality(wanted)) is not None:
            return is_spell and spell_colours(source.colors)
        if _is_cast_this_turn_quality(wanted):
            return source_state is not None and self.was_cast_this_turn(source_state)
        card_type = _card_type_named(wanted)
        if card_type is not None:
            return card_type in source.types
        negated = _negated_card_type_named(wanted)
        if negated is not None:
            return negated not in source.types
        colour = _has_color_quality(wanted, source.colors)
        if colour is not None:
            return colour
        test = _characteristic_quality(wanted)
        if test is None:
            return False
        if source_state is not None and source_state.zone is Zone.BATTLEFIELD:
            return test(self.characteristics_of(source_state))
        return test(_card_characteristics(source, source_mana_value))

    def source_has_quality(self: "Game", source: CardState, quality: str) -> bool:
        """Whether a damage source has a named property (CR 609.7b, CR 702.16a).

        CR 702.16a: "This quality is usually a color (as in 'protection from
        black') but can be any characteristic value or information ... If the
        quality is a card type, subtype, or supertype, the ability applies to
        sources that are permanents with that card type, subtype, or supertype
        and to any sources not on the battlefield that are of that card type,
        subtype, or supertype. This is an exception to rule 109.2."

        Colours, CR 105.2a/105.2b's colour counts ("monocolored",
        "multicolored"), card types, CR 112.1's "spell" and CR 400.7d's
        "permanents that were cast this turn" are read; anything else returns
        False rather than being guessed at, and is listed in
        `docs/engine-coverage.md`.

        A permanent's own types and colours are the ones asked about - CR
        613.5's computed board while `source` is still on the battlefield (a
        land animated by earthbend is a creature only there), and the
        printed `CardState` for anything else, which is CR 702.16a's own
        second clause: "any sources not on the battlefield that are of that
        card type" reads the printed characteristics by name.

        A "non`<type>`" quality (Disciples of the Inferno's "a noncreature
        source you control") is CR 205.2a's plain negation of a card type,
        the identical reading `machines/casting_restrictions.py::_matches_
        type_filter` already gives "noncreature spells" - checked only once
        the bare card-type name comes back unrecognised, so it never shadows
        a real (if oddly spelled) positive quality.
        "Spell" is not a card type at all (CR 205.2a never lists it), so that
        second clause never reaches it: a source only carries this quality
        while `source.zone` genuinely `is Zone.STACK` right now - never for
        one sitting in a hand or graveyard the way a card-type quality would
        still read there. Neither is "permanents that were cast this turn" -
        `Game.was_cast_this_turn` is the one place that fact is answered,
        used identically here (CR 702.16e's damage), by `protection_quality_
        against` (CR 702.16c/d/f: enchanting, equipping, blocking - all three
        share this method) and by `source_has_quality_of_card`'s targeting
        half (CR 702.16b), which threads the live source state through
        because a bare `Card` alone cannot answer it.
        """
        wanted = quality.strip().lower()
        if wanted == "everything":
            return True  # CR 702.16j
        if _is_spell_quality(wanted):
            return source.zone is Zone.STACK
        if (spell_colours := _spell_colour_quality(wanted)) is not None:
            return source.zone is Zone.STACK and spell_colours(source.colors)
        if _is_cast_this_turn_quality(wanted):
            return self.was_cast_this_turn(source)
        types, colors = source.types, source.colors
        if source.zone is Zone.BATTLEFIELD:
            chars = self.characteristics_of(source)
            types, colors = chars.types, chars.colors
        card_type = _card_type_named(wanted)
        if card_type is not None:
            return card_type in types
        negated = _negated_card_type_named(wanted)
        if negated is not None:
            return negated not in types
        colour = _has_color_quality(wanted, colors)
        if colour is not None:
            return colour
        test = _characteristic_quality(wanted)
        return test is not None and test(self._protection_characteristics(source))

    def record_combat_damage_to_player(self: "Game", source: CardState, player: str) -> None:
        """Ledger one source's combat damage dealt to `player` (CR 510.2) on
        `combat_damage_to_players_this_turn`, capturing the source's
        controller and computed creature types *now*, as CR 702.76a's "at the
        time it dealt that damage" requires. Called only with damage actually
        dealt (`machines/combat._deal_combat_damage`)."""
        kinds = set(creature_types())
        self.combat_damage_to_players_this_turn.append(
            CombatDamageToPlayer(
                player=player,
                source_id=source.id,
                controller=self.controller_of(source).username,
                creature_types=tuple(
                    kind for kind in self.characteristics_of(source).subtypes if kind in kinds
                ),
            )
        )

    def prowl_condition_holds(self: "Game", caster: str, spell: CardState) -> bool:
        """CR 702.76a: "a player was dealt combat damage this turn by a source
        that, at the time it dealt that damage, was under your control and had
        any of this spell's creature types."

        The spell's creature types are its own (a Kindred type line's, or a
        changeling's every creature type - CR 702.73a), read off its current
        characteristics; the source's side is the record's, captured when the
        damage was dealt."""
        kinds = set(creature_types())
        spell_types = {kind for kind in self.characteristics_of(spell).subtypes if kind in kinds}
        return any(
            record.controller == caster and spell_types.intersection(record.creature_types)
            for record in self.combat_damage_to_players_this_turn
        )

    def spectacle_condition_holds(self: "Game", caster: str) -> bool:
        """CR 702.137a: "'Spectacle [cost]' means 'You may pay [cost] rather
        than pay this spell's mana cost if an opponent lost life this turn.'"

        "An opponent" is read relative to `caster`, the player proposing to
        pay the spectacle cost, the same `players_in_game` exclusion
        `condition_holds`'s own opponent-scoped conditions use.
        `Player.life_lost_this_turn` is already CR 119.2/118.3b/701.12c's
        gross per-turn loss (damage, a life payment, or the losing half of an
        exchange, all routed through `Player.lose_life`), so nothing new is
        recorded here - Light Up the Stage and Skewer the Critics are the
        first readers of it from the casting side."""
        return any(
            player.life_lost_this_turn > 0
            for player in self.players_in_game
            if player.username != caster
        )

    def _record_graveyard_arrival(
        self: "Game",
        card_state: CardState,
        *,
        origin_zone: Zone,
        permanent_types: tuple[Type, ...] | None,
    ) -> None:
        """One ledger entry on `graveyard_arrivals_this_turn` (CR 400.6/400.3).

        The single place every `GraveyardArrival` is actually built, so
        `is_permanent_card` (CR 110.4a) is computed the same way regardless
        of which of the four call sites reached it: `Game.put_into_graveyard`
        (the main one), `Game.enter_the_battlefield`'s two branches where a
        replacement effect (CR 614.6) redirects an entering permanent to a
        graveyard instead, and `machines/keywords.discard`/`.dredge`, neither
        of which goes through `put_into_graveyard` at all - see `Game.
        descended`'s own docstring for why CR 700.11's "from anywhere" needs
        every one of them fed.

        `card_state.types` (not `permanent_types`) is what answers CR
        110.4a's "permanent card" question - the front-face-safe, off-
        battlefield read (`CardState.types`'s own docstring), a fixed
        property of the card itself rather than of whatever it happened to
        be while animated on the battlefield: a land earthbent into a
        creature (CR 701.66a) that dies is already a permanent card for
        being a land, and does not also need to have been a creature at the
        time. This is why `is_permanent_card` is never derived from
        `permanent_types`, which is `None` for an arrival that skipped the
        battlefield and would otherwise silently undercount every discarded,
        milled, or countered permanent card.
        """
        owner = card_state.owner
        if owner is None:
            return
        from ...machines.turn import Phase

        in_combat = self.turn is not None and self.turn.phase is Phase.COMBAT
        self.graveyard_arrivals_this_turn.append(
            GraveyardArrival(
                player=owner,
                origin_zone=origin_zone,
                is_permanent_card=bool(_PERMANENT_TYPES.intersection(card_state.types)),
                permanent_types=permanent_types,
                card_id=card_state.id,
                card_types=tuple(card_state.types),
                combat=(
                    self.turn_count("combat_phases", self.turn.active_player)
                    if in_combat and self.turn is not None
                    else 0
                ),
            )
        )

    def descended(self: "Game", username: str) -> bool:
        """CR 700.11: whether `username` "has descended this turn" - a
        permanent card was put into their graveyard from anywhere this turn.

        Reads `cards_put_into_graveyard_this_turn(username, permanent_only=
        True)` off `graveyard_arrivals_this_turn` - FRA S5's general ledger,
        reconciled at merge in favour of a separate `permanent_cards_to_
        graveyard_this_turn` running count the fu-events line of development
        built independently for the identical CR 700.11 question, per
        `CLAUDE.md`'s "keep one mechanism" rule.
        """
        return self.cards_put_into_graveyard_this_turn(username, permanent_only=True) > 0

    def descend_count(self: "Game", username: str) -> int:
        """CR 700.11: "the number of times [`username`] descended this
        turn" - the number of permanent cards put into their graveyard from
        anywhere this turn (CR 700.11's own count question, The Mycotyrant's
        "X is the number of times you descended this turn"). See
        `descended`'s own docstring for where this now reads from."""
        return self.cards_put_into_graveyard_this_turn(username, permanent_only=True)

    def _legendary_creature_count_power(
        self: "Game", permanent: CardState, board: ComputedBoard
    ) -> int | None:
        """The count `_LEGENDARY_TYPE_COUNT_POWER_RE`'s own CDA names, or
        `None` when the permanent prints no such line at all.

        Read directly off `self.battlefield`/`computed_board` rather than
        through `machines/layers.py`'s own `Count` machinery (not this task's
        file to add a "legendary" filter to) - a plain sum over the computed
        board (CR 613.5), the identical live recompute every other CDA in
        the pool already gets since `characteristics_of` is asked fresh every
        time a caller wants a permanent's power.

        `computed_board().of(other)`, not `self.characteristics_of(other)`:
        `permanent` itself is a legendary creature under its own count (CR
        608.2h counts "creatures you control", and CR 205.4a's legendary
        supertype does not exclude the CDA's own source), so going back
        through `characteristics_of` - which calls this very method through
        `_supplement_characteristics` - would recurse into itself. Only
        `power` needs the supplement this method exists to fill in;
        `types`/`supertypes` are already right on the board `computed_board`
        hands back on its own.
        """
        normalized = self_normalized_effect_text(permanent.name, permanent.oracle_text or "")
        match = None
        for line in normalized.splitlines():
            match = _LEGENDARY_TYPE_COUNT_POWER_RE.fullmatch(line.strip())
            if match is not None:
                break
        if match is None:
            return None
        try:
            card_type = Type(match.group("type").rstrip("s"))
        except ValueError:
            return None
        controller = board.of(permanent).controller
        return sum(
            1
            for other in self.battlefield
            if board.of(other).controller == controller
            and card_type in board.of(other).types
            and Supertype.LEGENDARY in board.of(other).supertypes
        )

    def _type_mv_threshold_cost_less_self_power(
        self: "Game", text: str, permanent: CardState, spell: CardState, caster: str
    ) -> ManaCost | None:
        """`_TYPE_MV_THRESHOLD_COST_LESS_SELF_POWER_RE`'s reduction for
        `spell`, or `None` when this line is not that shape or does not
        apply.

        Controller-scoped ("spells *you* cast", CR 601.2f), gated on
        `spell`'s own printed mana value (CR 202.3 - unaffected by the
        reduction itself, since it is a characteristic, not the cost being
        paid) meeting the threshold, and on the granting permanent's own
        live power (layer 7c, CR 613.1) being positive - a 0-or-negative
        power discounts nothing rather than raising the cost.
        """
        if permanent.controller != caster:
            return None
        normalized = self_normalized_effect_text(permanent.name, text, legendary=True)
        match = self._TYPE_MV_THRESHOLD_COST_LESS_SELF_POWER_RE.fullmatch(normalized.strip())
        if match is None:
            return None
        wanted_types = {Type(word.lower()) for word in match.group("types").split(" and ")}
        if not wanted_types & set(spell.types_as_a_spell(spell.card.types)):
            return None
        if spell.mana_value < int(match.group("mv")):
            return None
        power = self.power_of(permanent)
        if power is None or power <= 0:
            return None
        return ManaCost.parse(f"{{{power}}}")

    def condition_holds(
        self: "Game",
        controller: str,
        condition: str,
        source: CardState | None = None,
        *,
        ability: Any = None,
        event: Any = None,
        source_stamp: UUID | None = None,
    ) -> bool | None:
        """Whether a printed board condition is true for `controller` right now,
        or None when this does not read it.

        One reader for the conditions a card gates something on without a
        trigger: CR 602.5b's "Activate only if <condition>" and a modal
        instruction's "If <condition>, choose N instead" (CR 700.2, checked as
        the modes are chosen - CR 601.2b for a spell, CR 603.3c for a
        triggered ability). The shapes are the `_CONDITION_*` patterns above;
        every count goes through `magic_cards_model.numbers`.

        CR 613.5: a count of permanents reads the computed board - a card type
        (Liquimetal Coating's "becomes an artifact"), a creature's power, or
        whether it is a creature at all (an earthbent land) can each be true
        only there. `source` is the object the condition is printed on, for
        the shapes that talk about it ("this card is suspended", "this
        artifact has N or more ... counters on it"); without one those are not
        read.

        `ability`/`event`/`source_stamp` are optional, additive context for a
        resolution-time "if <condition>" printed on a *triggered* ability
        whose condition needs to read the trigger's own event - "if five or
        more mana was spent to cast that spell" (Molten-Core Maestro's own
        Opus rider) resolves "that spell" to the cast event's own subject
        (`machines/conditions/cast_record._cast_record_for_clause`), never to
        `source` itself, and can only do that when the ability and its event
        are threaded through the same way `machines/triggers.intervening_if_
        answer` already threads them for a trigger's own intervening *if*.
        Every existing caller passes none of the three and reads exactly as
        before - only a caller that resolves a triggered ability's own rider
        needs to supply them.

        A shape none of those patterns reads is handed to the shared reader,
        `machines/conditions.read_condition` - the registry every other
        condition-asking path falls back to as well - so a template read there
        (whose turn it is, a compound of two read halves) is read here too.
        """
        text = condition.strip().rstrip(".").strip()
        if (alternatives := _condition_alternatives(text)) is not None:
            # The C1 rule every compound keeps (`machines/conditions`): read
            # only when every half is read - a true half does not stand in
            # for one nobody could check.
            answers = [
                self.condition_holds(
                    controller,
                    part,
                    source,
                    ability=ability,
                    event=event,
                    source_stamp=source_stamp,
                )
                for part in alternatives
            ]
            if None in answers:
                return None
            return any(answers)
        held = self.builtin_condition_holds(controller, text, source)
        if held is not None:
            return held
        from ...machines import conditions

        return conditions.read_condition(
            conditions.ConditionContext(
                game=self,
                controller=controller,
                source=source,
                ability=ability,
                event=event,
                source_stamp=source_stamp,
            ),
            text,
        )

    def builtin_condition_holds(
        self: "Game", controller: str, condition: str, source: CardState | None = None
    ) -> bool | None:
        """`condition_holds`' own `_CONDITION_*` chain, without the fallback to
        `machines/conditions.read_condition` - which asks this in turn, so the
        two never recurse into each other."""
        text = condition.strip().rstrip(".").strip()
        board = self.computed_board()
        controlled = self.permanents_controlled_by(controller)
        opponents = [player for player in self.players_in_game if player.username != controller]

        if match := _CONDITION_POWER.fullmatch(text):
            threshold = int(match.group("power"))
            stat_quality = _permanent_quality(match.group("quality"))
            if stat_quality is None:
                return None
            attribute = match.group("stat").lower()
            return any(
                stat_quality(chars)
                and (value := getattr(chars, attribute)) is not None
                and value >= threshold
                for chars in (board.of(state) for state in controlled)
            )

        if match := _CONDITION_CONTROLS_N.fullmatch(text):
            needed = parse_count(match.group("count"))
            quality = _permanent_quality(match.group("quality"))
            if needed is None or quality is None:
                return None
            if match.group("who").lower() == "you control":
                owners = [controller]
            else:
                owners = [player.username for player in opponents]
            return any(
                sum(1 for state in self.permanents_controlled_by(owner) if quality(board.of(state)))
                >= needed
                for owner in owners
            )

        if match := _CONDITION_CONTROLS_A.fullmatch(text):
            qualities: list[Callable[[Characteristics], bool]] = []
            for part in _AND_AN.split(match.group("qualities")):
                named = _A_QUALITY.fullmatch(part.strip())
                quality = _permanent_quality(named.group("quality")) if named else None
                if quality is None:
                    return None
                qualities.append(quality)
            return all(
                any(quality(board.of(state)) for state in controlled) for quality in qualities
            )

        if match := _CONDITION_CONTROLS_ANOTHER.fullmatch(text):
            quality = _permanent_quality(match.group("quality"))
            if quality is None or source is None:
                return None
            return any(state.id != source.id and quality(board.of(state)) for state in controlled)

        if match := _CONDITION_CONTROLS_NAMED_PAIR.fullmatch(text):
            first = match.group("first").strip().lower()
            second = match.group("second").strip().lower()
            kind = _permanent_quality(match.group("kind"))
            if kind is None:
                return None
            names = {
                chars.name.lower()
                for chars in (board.of(state) for state in controlled)
                if kind(chars)
            }
            return first in names and second in names

        if match := _CONDITION_OPPONENT_COMPARISON.fullmatch(text):
            more = (match.group("direction") or match.group("stat_direction")).lower() == "more"
            if match.group("quality") is not None:
                quality = _permanent_quality(match.group("quality"))
                if quality is None:
                    return None

                def measure(username: str) -> int:
                    return sum(
                        1
                        for state in self.permanents_controlled_by(username)
                        if quality(board.of(state))
                    )

            elif match.group("stat").lower() == "life":

                def measure(username: str) -> int:
                    return self.player(username).life

            else:

                def measure(username: str) -> int:
                    return len(self.player(username).hand)

            mine = measure(controller)
            return any(
                (measure(opponent.username) > mine) if more else (measure(opponent.username) < mine)
                for opponent in opponents
            )

        if match := _CONDITION_SELF_IS_A_CREATURE.fullmatch(text):
            if source is None or not _names_the_source(match.group("subject"), source):
                return None
            return source.zone is Zone.BATTLEFIELD and board.of(source).is_creature

        if _CONDITION_SACRIFICED_THIS_TURN.fullmatch(text):
            return self.permanents_sacrificed_this_turn.get(controller, 0) > 0

        if match := _CONDITION_ENTERED_THIS_TURN.fullmatch(text):
            needed = parse_count(match.group("count"))
            turn_number = getattr(self.turn, "turns_taken", None)
            if needed is None:
                return None
            if turn_number is None:
                return False
            entered = sum(
                1
                for state in controlled
                if board.of(state).is_creature and state.turn_entered == turn_number
            )
            return entered >= needed

        if match := _CONDITION_TYPES_AMONG_GRAVEYARD.fullmatch(text):
            needed = parse_count(match.group("count"))
            if needed is None:
                return None
            found = {
                card_type
                for state in self.player(controller).graveyard
                for card_type in state.types
            }
            if match.group("permanents") is not None:
                found.update(
                    card_type for state in controlled for card_type in board.of(state).types
                )
            if match.group("kind").lower() == "permanent":
                found &= _PERMANENT_TYPES
            return len(found) >= needed

        if match := _CONDITION_GRAVEYARD_CARDS.fullmatch(text):
            needed = parse_count(match.group("count"))
            card_quality = _card_quality(match.group("quality"))
            if needed is None or card_quality is None:
                return None
            graveyard = self.player(controller).graveyard
            return sum(1 for state in graveyard if card_quality(state)) >= needed

        if match := _CONDITION_OPPONENT_GRAVEYARD_CARDS.fullmatch(text):
            needed = parse_count(match.group("count"))
            if needed is None:
                return None
            return any(len(player.graveyard) >= needed for player in opponents)

        if match := _CONDITION_HAND_CARDS.fullmatch(text):
            needed = parse_count(match.group("count"))
            if needed is None:
                return None
            return len(self.player(controller).hand) >= needed

        if match := _CONDITION_OPPONENT_POISON.fullmatch(text):
            needed = parse_count(match.group("count"))
            if needed is None:
                return None
            return any(player.poison >= needed for player in opponents)

        if match := _CONDITION_SELF_COUNTERS.fullmatch(text):
            needed = parse_count(match.group("count") or match.group("count2"))
            kind = (match.group("kind") or match.group("kind2")).lower()
            counter = next((each for each in Counter if each.value == kind), None)
            if needed is None or source is None or counter is None:
                return None
            return source.counter_count(counter) >= needed

        if match := _CONDITION_LOYALTY_AMONG_NAMED.fullmatch(text):
            needed = parse_count(match.group("count"))
            name = match.group("name").strip()
            if needed is None or not name:
                return None
            # CR 205.3h / CR 201.5: "Jaces" is every planeswalker with the
            # subtype Jace - the token and a nontoken Jace (Jace, Reality
            # Sculptor, whose name is not "Jace") both count - plus anything
            # whose printed name is exactly the word, as before.
            wanted = name.lower()
            total = sum(
                state.loyalty or 0
                for state in controlled
                if state.name.lower() == wanted
                or any(
                    subtype.lower() == wanted for subtype in self.characteristics_of(state).subtypes
                )
            )
            return total >= needed

        if match := _CONDITION_SPELLS_CAST_THIS_TURN.fullmatch(text):
            needed = parse_count(match.group("count"))
            if needed is None:
                return None
            return len(self.spells_cast_this_turn.get(controller, [])) >= needed

        if _CONDITION_OPPONENT_NONCOMBAT_DAMAGE_THIS_TURN.fullmatch(text):
            return any(
                self.turn_fact_holds("dealt_noncombat_damage", opponent.username)
                for opponent in opponents
            )

        if match := _CONDITION_CAST_A_SPELL_THIS_TURN.fullmatch(text):
            quality = _card_quality(match.group("quality"))
            if quality is None:
                return None
            if match.group("opponent"):
                return any(
                    quality(state)
                    for opponent in opponents
                    for state in self.spells_cast_this_turn.get(opponent.username, [])
                )
            return any(quality(state) for state in self.spells_cast_this_turn.get(controller, []))

        if match := _CONDITION_OPPONENT_CAST_COLOR.fullmatch(text):
            colors: list[Color] = []
            for word in re.split(r",\s*|\s+and/or\s+|\s+or\s+|\s+and\s+", match.group("colors")):
                color = _COLOR_WORDS.get(word.strip().lower())
                if color is None:
                    return None
                if color not in colors:
                    colors.append(color)
            return any(
                any(color in state.colors for color in colors)
                for opponent in opponents
                for state in self.spells_cast_this_turn.get(opponent.username, [])
            )

        if _CONDITION_SUSPENDED.fullmatch(text):
            if source is None:
                return None
            return source.is_suspended

        if _CONDITION_KICKED.fullmatch(text):
            # CR 702.33d: "this spell" is the ability's own source. Reads the
            # finalized `CastRecord`, which only exists once `Casting.cast()`
            # completes - the right answer for anything asking after the
            # fact, but *not* for a modal choice made mid-announcement
            # (CR 601.2b), which is exactly what `Casting._alternative_mode_
            # count` special-cases with its own live `self.kicked` and this
            # method's `condition_override` instead of reaching here at all.
            if source is None:
                return None
            record = self.cast_record_of(source)
            return record is not None and record.kicked > 0

        if _CONDITION_CAST_USING_TEAMWORK.fullmatch(text):
            # Same shape as `_CONDITION_KICKED` just above, off `CastRecord.
            # cast_using_teamwork` instead of `.kicked` - a mid-announcement
            # modal choice reaches `Casting._alternative_mode_count`'s own
            # `self.teamwork_paid` override instead of this branch, the same
            # way kicker's own in-progress read never reaches here either.
            if source is None:
                return None
            record = self.cast_record_of(source)
            return record is not None and record.cast_using_teamwork

        if _CONDITION_GIFT_PROMISED.fullmatch(text):
            if source is None:
                return None
            record = self.cast_record_of(source)
            return record is not None and record.gift_promised

        if _CONDITION_DESCENDED.fullmatch(text):
            # CR 700.11, Molten Collapse's own "If you descended this turn,
            # you may choose both instead." - the same running count
            # `intervening_if_holds`'s "you descended this turn" reads.
            return self.descended(controller)

        if _CONDITION_SCRIED_OR_SURVEILLED_THIS_TURN.fullmatch(text):
            return self.turn_fact_holds("scried_or_surveilled", controller)

        if _CONDITION_LIBRARY_EMPTY_RE.fullmatch(text):
            return len(self.player(controller).library) == 0

        if match := _CONDITION_CREATURES_DIED_THIS_TURN.fullmatch(text):
            needed = parse_count(match.group("count"))
            if needed is None:
                return None
            return self.creatures_died_this_turn >= needed

        if match := _CONDITION_ATTACKED_WITH_N.fullmatch(text):
            needed = parse_count(match.group("count"))
            if needed is None:
                return None
            # Only the active player declares attackers (CR 508.1), so this
            # turn's attackers were all declared by whoever's turn it is.
            if self.active_player.username != controller:
                return False
            return len(self.attacked_this_turn) >= needed

        if match := _CONDITION_SELF_NO_COUNTERS.fullmatch(text):
            if source is None:
                return None
            return source.counter_count(match.group("kind").lower()) == 0

        if _CONDITION_CREATURE_DIED_THIS_TURN.fullmatch(text):
            # Morbid (an ability word, CR 207.2c - "no special rules
            # meaning"): CR 700.4's own "dies" is what `creatures_died_
            # this_turn` counts, reset for the new turn alongside the other
            # per-turn trackers just above.
            return self.creatures_died_this_turn > 0

        if _CONDITION_NOT_CAST_FROM_HAND.fullmatch(text):
            # Twinned Vision's own "this spell wasn't cast from your hand"
            # (CR 601.2a: casting moves the card "from where it is to the
            # stack") - read off `source`, the resolving spell itself; a
            # copy (CR 707.10) "isn't cast" at all, so it counts too. No
            # `source` means this is unread rather than guessed.
            if source is None:
                return None
            record = self.cast_record(source)
            return record.is_copy or record.origin_zone is not Zone.HAND

        if _CONDITION_CAST_FROM_GRAVEYARD.fullmatch(text):
            # CR 601.2a's origin zone of the resolving spell itself; a copy
            # (CR 707.10) was not cast at all, so it answers False.
            if source is None:
                return None
            record = self.cast_record(source)
            return not record.is_copy and record.origin_zone is Zone.GRAVEYARD

        if _CONDITION_ADDITIONAL_COST_PAID.fullmatch(text):
            # Read off `source`, the resolving spell; no spell, no answer.
            if source is None:
                return None
            return self.cast_record(source).optional_additional_cost_paid

        if _CONDITION_SELF_ENTERED_THIS_TURN.fullmatch(text):
            if source is None:
                return None
            return self._entered_this_turn(source)

        if _CONDITION_YOU_ATTACKED_THIS_TURN.fullmatch(text):
            return self.turn_fact_holds("attacked", controller)

        if _CONDITION_LAND_ENTERED_THIS_TURN.fullmatch(text):
            return self.turn_fact_holds("land_entered", controller)

        return None

    def _record_unread_static_line(self: "Game", source: CardState, text: str) -> None:
        """Record a static ability sentence this engine could not read (CR 611.1).

        The static ability generates a continuous effect that affects the rules
        of the game, and nothing here built it - which is exactly what
        `LayerNotice` records for a static ability whose continuous effect went
        unmade. Both directions land here: a prohibition read as permission
        would let an illegal activation through, and a *permission* read as
        silence keeps a legal one out. One entry per source, not one per query:
        `why_cannot_activate` and `can_activate_tap_ability` are both called
        constantly.
        """
        already = {
            notice.source_id
            for notice in self.continuous_effects.layer_notices
            if notice.text == text
        }
        if source.id in already:
            return
        self.continuous_effects.layer_notices.append(
            LayerNotice(source_id=source.id, source_name=source.name, text=text)
        )

    def _permanent_matches_group_quality(
        self: "Game", permanent: CardState, quality: str
    ) -> bool | None:
        """Whether `permanent` fits an "activated abilities of `<quality>` you
        control cost `{N}` less to activate" static's own group phrase
        (`ActivatedAbilityGroupDiscount.quality`), or `None` when `quality`
        names nothing this can read at all - the same "unreadable, not the
        same as no effect" answer `activation_cost_reduction_for`'s own
        quality reader gives, which its caller turns into a `CostModifierNotice`
        rather than a silent no-op (DDR#978).

        `quality` is read word by word, the same generic way `activation_cost_
        reduction_for` already reads a *self* discount's own "for each
        `<quality>` you control": a CR 205.4a supertype ("legendary"), a
        CR 205.2a card type ("creature", "artifact"), or a CR 205.3 subtype
        (`canonical_subtype` - "Food", "Treasure", "Elf"), every word ANDed
        together, plus CR 111.1's own "token"/"tokens" trailing word (Mutagen
        Man's own "artifact tokens") read separately since a token is not a
        card type or subtype at all. A permanent still off the battlefield
        (a granted ability paid for by sacrificing its own source, `activation_
        cost`'s own docstring) is read off its printed characteristics rather
        than the computed board, since `computed_board` only ever covers
        battlefield permanents.
        """
        words = quality.strip().split()
        require_token = bool(words) and words[-1].lower() in ("token", "tokens")
        if require_token:
            words = words[:-1]
        if not words:
            return None
        if require_token and not getattr(permanent, "token", False):
            return False
        on_battlefield = permanent.zone is Zone.BATTLEFIELD
        chars = self.characteristics_of(permanent) if on_battlefield else None
        types_present = set(chars.types) if chars is not None else set(permanent.types)
        supertypes_present = (
            set(chars.supertypes) if chars is not None else set(permanent.supertypes)
        )
        subtypes_present = {
            word.lower() for word in (chars.subtypes if chars is not None else permanent.subtypes)
        }
        for word in words:
            singular = word.removesuffix("s")
            try:
                if Supertype(singular.lower()) in supertypes_present:
                    continue
                return False
            except ValueError:
                pass
            try:
                if Type(singular.lower()) in types_present:
                    continue
                return False
            except ValueError:
                pass
            subtype = canonical_subtype(word)
            if subtype is None:
                return None
            if subtype not in subtypes_present:
                return False
        return True


from ._casting import (  # noqa: E402
    _is_cast_this_turn_quality,
    _is_spell_quality,
    _spell_colour_quality,
)
from ._common import (  # noqa: E402
    _COLOR_COUNT_QUALITIES,
    _COLOR_WORDS,
    _EACH_OPPONENT_PROTECTION_QUALITY,
    _LEGENDARY_TYPE_COUNT_POWER_RE,
)
from ._continuous import (  # noqa: E402
    _card_characteristics,
    _characteristic_quality,
    _characteristic_word,
)
from .records import CombatDamageToPlayer, GraveyardArrival  # noqa: E402
