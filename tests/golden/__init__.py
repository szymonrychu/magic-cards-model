"""Golden per-card behaviour snapshots: what each swept ability did, pinned.

The behavioural sweep (`tests/test_behavioural_sweep.py`) proves a handled
ability *does something*. A golden pins *what* it did. For every trigger and
activation the sweep executes there is one file,
`tests/golden/<card-slug>/<triggered|activated>-<n>.json`, holding:

- `board` - the setup, in the scenario harness's own words: the keyword
  arguments `Scenario().player(...)` was built with for each seat, plus the
  predefined tokens (CR 111.10), tapped material and the step the game was
  started at (`Scenario.build`, `PlayedScenario.start_at`).
- `recipe` - how the sweep raised the event on that board: the variant (the
  quiet / busy / lonely / war board), the attempt (its name, its place in
  the event kind's attempt list and its own parameters), or for an
  activation, whether the source entered this turn.
- `action` - the ability as it stood on the stack before it resolved: its
  source, controller and targets.
- `delta` - what resolving it changed, normalised: every object that moved,
  tapped, took damage or counters, every token created, every life total
  and player counter, every question asked (CR 608.2d), every notice raised,
  the top-level game fields that changed, and the stack left behind.

Objects are named, never by raw id: each object is labelled
`<name>@<owner>#<k>` - the k-th object of that name and owner in a fixed walk
of the game before the resolution (players in turn order, zones in a fixed
order, each zone front to back) - and one that appears only afterwards (a
token) `<name>@<owner>+<k>`. The board itself is built under the engine's
deterministic id allocator (`ids.install_id_allocator`, `Game.game_uid`)
pinned per case, so every shuffle and every minted id is the same on every
run. No timestamps: no clock, epoch, stamp or counter of the engine's own
bookkeeping is recorded.

The sweep compares the live record to the file and fails that case's own
test id with a unified diff. Regenerate with `mise run golden:update`
(`pytest tests/test_behavioural_sweep.py --update-golden`) and review the
diff in the commit; never edit a golden by hand.

A golden is also a scenario: `load(path)` gives a `Golden` whose
`build_board()` builds the recorded board through the harness, and whose
`replay()` plays the recorded recipe through the real engine and returns the
record it produces - equal to the file while the engine behaves the same.
`mise run golden:replay <path>` prints a golden and its replay side by side.
"""

from __future__ import annotations

import difflib
import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

GOLDEN_DIR = Path(__file__).parent

#: Bumped when the record's shape changes, so an old file reads as a diff.
FORMAT = 1


def slug(card: str) -> str:
    """A card's directory name: lowercase words joined by hyphens."""
    return "-".join(re.findall(r"[a-z0-9]+", card.lower().replace("'", "")))


def golden_path(card: str, family: str, number: int) -> Path:
    """Where the golden for the `number`-th handled `family` clause of `card`
    lives - `family` is "triggered" or "activated", as the sweep numbers them."""
    return GOLDEN_DIR / slug(card) / f"{family}-{number}.json"


# ---------------------------------------------------------------------------
# Stable text.
# ---------------------------------------------------------------------------


def _scalar(value: Any) -> bool:
    return value is None or isinstance(value, str | int | float | bool)


def _render(value: Any, indent: int) -> str:
    pad = "  " * indent
    if isinstance(value, dict):
        if not value:
            return "{}"
        items = [
            f"{pad}  {json.dumps(str(key))}: {_render(value[key], indent + 1)}"
            for key in sorted(value, key=str)
        ]
        return "{\n" + ",\n".join(items) + f"\n{pad}}}"
    if isinstance(value, list | tuple):
        if all(_scalar(item) for item in value):
            return json.dumps(list(value), ensure_ascii=False)
        items = [f"{pad}  {_render(item, indent + 1)}" for item in value]
        return "[\n" + ",\n".join(items) + f"\n{pad}]"
    return json.dumps(value, ensure_ascii=False)


def dumps(value: Any) -> str:
    """JSON with sorted keys, two-space indent, and every list of scalars on
    one line - a zone reads as one line, a change as one line of diff."""
    return _render(value, 0) + "\n"


def diff(recorded: Any, live: Any, name: str = "golden") -> str:
    """A unified diff from the golden to what the engine did now."""
    return "".join(
        difflib.unified_diff(
            dumps(recorded).splitlines(keepends=True),
            dumps(live).splitlines(keepends=True),
            fromfile=f"{name} (recorded)",
            tofile=f"{name} (live)",
        )
    )


# ---------------------------------------------------------------------------
# Labels and the state projection.
# ---------------------------------------------------------------------------

#: The per-player zones, in the order the label walk visits them.
_PLAYER_ZONES = ("battlefield", "hand", "graveyard", "library", "exile", "command", "sideboard")


def _objects(game: Any) -> list[Any]:
    """Every card, token and stack object in a fixed order."""
    found: list[Any] = []
    for zone_cards in game.shared_zones.values():
        found += list(zone_cards)
    for player in game.players:
        zones = player.zones
        for name in _PLAYER_ZONES:
            for key, cards in zones.items():
                if getattr(key, "value", key) == name:
                    found += list(cards)
    return found


def _owner(item: Any) -> str:
    return (
        getattr(item, "owner", None)
        or getattr(item, "controller_or_owner", None)
        or getattr(item, "controller", None)
        or "?"
    )


class Labels:
    """Stable names for the objects of one game, fixed on first sight."""

    def __init__(self, game: Any) -> None:
        self._by_id: dict[Any, str] = {}
        self._seen: Counter[tuple[str, str]] = Counter()
        self._late: Counter[tuple[str, str]] = Counter()
        for item in _objects(game):
            self.name(item)

    def name(self, item: Any, *, late: bool = False) -> str:
        key = getattr(item, "id", None)
        if key in self._by_id:
            return self._by_id[key]
        stem = (getattr(item, "name", None) or type(item).__name__, _owner(item))
        if late:
            self._late[stem] += 1
            label = f"{stem[0]}@{stem[1]}+{self._late[stem]}"
        else:
            self._seen[stem] += 1
            label = f"{stem[0]}@{stem[1]}#{self._seen[stem]}"
        self._by_id[key] = label
        return label

    def of_id(self, game: Any, key: Any) -> str | None:
        if key is None:
            return None
        if key in self._by_id:
            return self._by_id[key]
        try:
            found = game.find_by_id(key)
        except (KeyError, ValueError):
            found = None
        if found is None:
            return "?"
        return self.name(found, late=True)

    def target(self, game: Any, ref: Any) -> str:
        if getattr(ref, "username", None) is not None and getattr(ref, "card_id", None) is None:
            return f"player:{ref.username}"
        return self.of_id(game, getattr(ref, "card_id", None)) or "?"


def _counters(counters: Any) -> dict[str, int]:
    raw = getattr(counters, "root", None) or {}
    return {str(kind): count for kind, count in raw.items() if count}


def _card_view(game: Any, labels: Labels, item: Any) -> dict[str, Any]:
    zone = getattr(item, "zone", None)
    view: dict[str, Any] = {"zone": getattr(zone, "value", zone)}
    if zone is not None and getattr(zone, "value", zone) == "battlefield":
        view["controller"] = getattr(item, "controller", None)
        view["tapped"] = getattr(item, "tapped", False)
        for field in ("face_up", "transformed", "monstrous"):
            view[field] = getattr(item, field, None)
        view["damage"] = getattr(item, "damage", 0)
        view["class_level"] = getattr(item, "class_level", 1)
        attachment = getattr(item, "attachment", None)
        view["attached_to"] = labels.target(game, attachment) if attachment is not None else None
        try:
            view["power"], view["toughness"] = item.power, item.toughness
        except Exception:  # an object with no board to read yet
            view["power"] = view["toughness"] = None
        view["granted"] = sorted(getattr(item, "granted_ability_texts", ()) or ())
    view["counters"] = _counters(getattr(item, "counters", None))
    return view


def _decision_view(game: Any, labels: Labels, decision: Any) -> dict[str, Any]:
    return {
        "kind": getattr(decision.kind, "value", str(decision.kind)),
        "player": decision.player,
        "prompt": decision.prompt,
        "source": decision.source,
        "amount": decision.amount,
        "cards": [labels.of_id(game, _as_uuid(card)) for card in decision.cards],
        "players": list(decision.players),
    }


def _as_uuid(value: Any) -> Any:
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except ValueError:
        return value


def stack_view(game: Any, labels: Labels) -> list[str]:
    """The stack bottom first, each object by label (an ability by its source)."""
    views = []
    for item in game.stack:
        if type(item).__name__ == "AbilityOnStack":
            source = labels.of_id(game, item.source_id) or item.source_name
            views.append(f"ability of {source}: {item.ability.text}")
        else:
            views.append(labels.name(item))
    return views


def action_view(game: Any, labels: Labels, item: Any) -> dict[str, Any]:
    """The resolving object as it stands on the stack (CR 113.1c)."""
    if item is None:
        return {"on_stack": False}
    return {
        "on_stack": True,
        "source": labels.of_id(game, getattr(item, "source_id", None)),
        "controller": getattr(item, "controller", None),
        "targets": [labels.target(game, ref) for ref in getattr(item, "targets", [])],
        "modes": list(getattr(item, "modes", []) or []),
        "x": getattr(item, "x_value", 0),
    }


@dataclass
class Snapshot:
    """One moment of a game, projected onto what a golden records."""

    objects: dict[str, dict[str, Any]]
    players: dict[str, dict[str, Any]]
    dump: dict[str, Any]
    asked: int


def snapshot(game: Any, labels: Labels) -> Snapshot:
    objects = {}
    for item in _objects(game):
        if type(item).__name__ == "AbilityOnStack":
            continue
        objects[labels.name(item, late=True)] = _card_view(game, labels, item)
    players = {
        player.username: {
            "life": player.life,
            "counters": _counters(player.counters),
            "mana_pool": _mana(player.mana_pool),
        }
        for player in game.players
    }
    return Snapshot(objects, players, game.model_dump(mode="json"), len(game.decisions.asked))


def _mana(pool: Any) -> Any:
    dumped = pool.model_dump(mode="json")
    return {key: value for key, value in dumped.items() if value}


#: Top-level game fields that are the engine's own bookkeeping, not an
#: effect's result - never recorded (ids, clocks, counters of minted objects).
_BOOKKEEPING = frozenset(
    {
        "stack",
        "priority",
        "decisions",
        "objects_created",
        "ability_resolutions_this_turn",
        "pending_triggers",
        "trigger_targets",
        "resolving",
        "fizzled",
        "players",
        "battlefield",
        "exile",
        "command",
        "shared_zones",
    }
)


def _changes(before: dict[str, Any], after: dict[str, Any]) -> dict[str, list[Any]]:
    changed = {}
    for key in sorted(set(before) | set(after)):
        if before.get(key) != after.get(key):
            changed[key] = [before.get(key), after.get(key)]
    return changed


def delta(game: Any, labels: Labels, before: Snapshot, after: Snapshot) -> dict[str, Any]:
    """What changed between two snapshots, in the golden's normalised form."""
    objects = {}
    created = {}
    for label, view in after.objects.items():
        if label not in before.objects:
            created[label] = view
            continue
        was = before.objects[label]
        # A field only one side has (a permanent's tapped/damage/controller
        # once it has left the battlefield) is not a change - the zone is.
        changes = _changes(
            {key: value for key, value in was.items() if key in view},
            {key: value for key, value in view.items() if key in was},
        )
        if was["zone"] != view["zone"]:
            changes["zone"] = [was["zone"], view["zone"]]
        if changes:
            objects[label] = changes
    for label in before.objects:
        if label not in after.objects:
            objects[label] = {"zone": [before.objects[label]["zone"], None]}
    players = {}
    for username, view in after.players.items():
        changes = _changes(before.players.get(username, {}), view)
        if changes:
            players[username] = changes
    fields = sorted(
        key
        for key in set(before.dump) | set(after.dump)
        if key not in _BOOKKEEPING
        and not key.endswith("_notices")
        and before.dump.get(key) != after.dump.get(key)
    )
    notices = {
        key: len(after.dump.get(key) or []) - len(before.dump.get(key) or [])
        for key in after.dump
        if key.endswith("_notices")
        and len(after.dump.get(key) or []) != len(before.dump.get(key) or [])
    }
    asked = [
        _decision_view(game, labels, decision)
        for decision in game.decisions.asked[before.asked : after.asked]
    ]
    return {
        "objects": objects,
        "created": created,
        "players": players,
        "decisions": asked,
        "notices": notices,
        "fields_changed": fields,
        "stack": stack_view(game, labels),
    }


# ---------------------------------------------------------------------------
# Loading and replaying.
# ---------------------------------------------------------------------------


@dataclass
class Golden:
    """One golden file, read back: a scenario that can be built and replayed."""

    path: Path
    card: str
    family: str
    number: int
    ability: str
    kind: str
    board: dict[str, Any]
    recipe: dict[str, Any]
    recorded: dict[str, Any]

    def build_board(self) -> Any:
        """The recorded board, built through the scenario harness: each seat
        from its `Scenario().player(...)` arguments, the predefined tokens
        created, the game started at the recorded step and the tapped
        material tapped - the state the recipe's event is raised on."""
        from magic_cards_model.machines import Step
        from magic_cards_model.models import Zone
        from magic_cards_model.models.token import create_predefined_tokens
        from tests.scenarios.harness import Scenario

        scenario = Scenario()
        for username in self.board["order"]:
            scenario.player(username, **self.board["players"][username])
        played = scenario.build()
        for name, owner in self.board["tokens"]:
            create_predefined_tokens(played.game, name, owner)
        if self.board["step"] is not None:
            played.start_at(Step(self.board["step"]))
        for name, owner in self.board["tapped"]:
            for state in played.game.battlefield:
                if state.name == name and _owner(state) == owner and not state.tapped:
                    state.tapped = True
                    break
        for name, owner in self.board["entering"]:
            state = next(s for s in played.game.player(owner).cards_in(Zone.HAND) if s.name == name)
            played.game.put_onto_battlefield(state, owner)
        return played

    def replay(self) -> dict[str, Any]:
        """Play the recorded recipe through the real engine and return the
        record it produces now - `recorded` when nothing has changed."""
        from tests import test_behavioural_sweep as sweep

        case = sweep.case_named(self.card, self.family, self.number)
        return sweep.replay(case, self.recipe)


def load(path: Path | str) -> Golden:
    path = Path(path)
    data = json.loads(path.read_text())
    return Golden(
        path=path,
        card=data["card"],
        family=data["family"],
        number=data["number"],
        ability=data["ability"],
        kind=data["kind"],
        board=data["board"],
        recipe=data["recipe"],
        recorded=data,
    )


def main(argv: list[str]) -> int:
    """`mise run golden:replay <golden.json>...`: print each golden's board,
    recipe and recorded delta, replay it, and print any difference."""
    status = 0
    for arg in argv:
        golden = load(arg)
        print(f"# {golden.card} - {golden.family} #{golden.number} [{golden.kind}]")
        print(f"# {golden.ability}")
        print(dumps({"board": golden.board, "recipe": golden.recipe}), end="")
        live = golden.replay()
        text = diff(golden.recorded, live, str(golden.path))
        if text:
            status = 1
            print(text, end="")
        else:
            print(dumps({"action": live["action"], "delta": live["delta"]}), end="")
            print("# replayed: identical to the golden")
    return status
