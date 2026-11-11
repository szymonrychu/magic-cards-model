"""MCM goldens as scenario specs for ironsmith's data-driven test runner, and the runner's
JUnit output read back as one verdict per golden.

A golden (`tests/golden/<slug>/<family>-<n>.json`) records a board, how the ability was
raised and what resolving it changed. `translate` rebuilds that board with `addCard`
operations, raises the ability the way a player would (cast the source for an enters
trigger, activate it by its cost for an activated ability), lets the game run to the
beginning of combat and asserts what MCM recorded. Only shapes the translator maps are
emitted; everything else is `Untranslated` with the reason, so the report always shows how
much of the corpus was compared.

The specs are our data. The generated `.test.mjs` shim beside each spec file only hands the
spec to the runner the user built locally; it is written into the gitignored out dir at run
time and never committed.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree

#: The `sourcePath` every generated spec file carries; JUnit names are
#: `<SOURCE_PATH> :: <golden id>`.
SOURCE_PATH = "mcm-goldens"

_RUNNER_PLAYERS = ("playerA", "playerB", "playerC", "playerD")
_BASIC_LANDS = frozenset({"Plains", "Island", "Swamp", "Mountain", "Forest", "Wastes"})
_ZONES = ("battlefield", "hand", "graveyard", "library")
_COUNTED = {"hand": "assertHandCount", "graveyard": "assertGraveyardCount"}
_TURN = {"turn": 1, "phase": "PRECOMBAT_MAIN"}
#: The ability-word separator as Scryfall prints it (U+2014), and the ASCII form.
_ABILITY_WORD_DASHES = (chr(0x2014), " - ")
_UNMOVED = ["battlefield", "battlefield"]


@dataclass(frozen=True)
class Untranslated:
    reason: str


def golden_id(path: Path) -> str:
    return f"{path.parent.name}/{path.name.removesuffix('.json')}"


def _front(name: str) -> str:
    return name.split("//")[0].strip()


def _label_name(label: str) -> str:
    return _front(label.split("@", 1)[0])


def _label_owner(label: str) -> str:
    return label.split("@", 1)[1].split("#", 1)[0].split("+", 1)[0]


def _refusal(golden: dict) -> str | None:
    board, action, recipe = golden["board"], golden["action"], golden["recipe"]
    delta = golden["delta"]
    checks = [
        (not action.get("on_stack"), "the ability never on the stack (mana ability)"),
        (board["variant"] != "quiet", f"board variant {board['variant']} not mapped"),
        (board["step"] != "precombat_main", f"board step {board['step']} not mapped"),
        (board["busy_turn"] or board["war_turn"], "busy or war turn not mapped"),
        (bool(board["tapped"]), "tapped material not mapped"),
        (bool(board["tokens"]), "predefined tokens not mapped"),
        (bool(board["entering"]), "entering objects not mapped"),
        (len(board["order"]) > len(_RUNNER_PLAYERS), "more players than the runner seats"),
        (bool(action.get("modes")), "modes not mapped"),
        (bool(action.get("x")), "X value not mapped"),
        (bool(delta.get("stack")), "something left on the stack after resolution"),
        (bool(delta.get("notices")), "notices raised"),
    ]
    for decision in delta.get("decisions") or []:
        checks.append((True, f"decision {decision.get('kind')} (answers are not recorded)"))
    if golden["family"] == "activated":
        checks += [
            (recipe.get("enters", False), "source entered this turn not mapped"),
            (recipe.get("off_zone", False), "ability activated outside the battlefield"),
            (":" not in golden["ability"], "ability has no cost: text to select it by"),
        ]
    else:
        mapped = golden["kind"] == "enters_the_battlefield" and recipe.get("attempt") == "put"
        checks += [
            (not mapped, f"trigger {golden['kind']}/{recipe.get('attempt')} not mapped"),
            ((recipe.get("params") or {}).get("tapped", False), "enters tapped not mapped"),
        ]
    return next((reason for refused, reason in checks if refused), None)


def _cost_label(ability: str) -> str:
    """The activation's cost as the runner selects it: the text before the first colon,
    without an ability-word lead ("Power-up - {5}{U}" -> "{5}{U}:")."""
    cost = ability.split(":", 1)[0]
    for dash in _ABILITY_WORD_DASHES:
        cost = cost.rsplit(dash, 1)[-1]
    return cost.strip() + ":"


def _target(label: str, seats: dict[str, int]) -> str:
    return _RUNNER_PLAYERS[seats[label]] if label in seats else _label_name(label)


def _raise(golden: dict, seats: dict[str, int]) -> dict | Untranslated:
    action = golden["action"]
    controller = seats[action["controller"]]
    source = _label_name(action["source"])
    zones = golden["board"]["players"][action["controller"]]
    if golden["family"] == "activated":
        if source not in {_front(n) for n in zones["battlefield"]}:
            return Untranslated("source not on its controller's battlefield")
        ability = _cost_label(golden["ability"])
        return {"op": "activateAbility", **_TURN, "player": controller, "ability": ability}
    if source not in {_front(n) for n in zones["hand"]}:
        return Untranslated("source not in its controller's hand")
    return {"op": "castSpell", **_TURN, "player": controller, "name": source}


def translate(golden: dict) -> list[dict] | Untranslated:
    """The runner operations replaying `golden`, or why it cannot be replayed yet."""
    reason = _refusal(golden)
    if reason:
        return Untranslated(reason)
    board, action, delta = golden["board"], golden["action"], golden["delta"]
    seats = {name: index for index, name in enumerate(board["order"])}
    raise_op = _raise(golden, seats)
    if isinstance(raise_op, Untranslated):
        return raise_op
    controller = raise_op["player"]

    ops: list[dict] = []
    # The state the delta starts from: the board, with an enters trigger's source
    # already moved from hand to battlefield.
    perms: Counter[tuple[int, str]] = Counter()
    zones: Counter[tuple[int, str]] = Counter()
    for player, seat in seats.items():
        for zone in _ZONES:
            names = board["players"][player].get(zone) or []
            for name, count in Counter(names).items():
                ops.append(
                    {
                        "op": "addCard",
                        "zone": zone.upper(),
                        "player": seat,
                        "name": name,
                        "count": count,
                    }
                )
            zones[seat, zone] = len(names)
            if zone == "battlefield":
                perms.update((seat, _front(name)) for name in names)
    if raise_op["op"] == "castSpell":
        zones[controller, "hand"] -= 1
        zones[controller, "battlefield"] += 1
        perms[controller, raise_op["name"]] += 1
    before_perms, before_zones = Counter(perms), Counter(zones)

    objects = sorted((delta.get("objects") or {}).items())
    exiled = 0
    for label, change in objects:
        name, owner = _label_name(label), seats[_label_owner(label)]
        old_ctl, new_ctl = (seats.get(c, owner) for c in change.get("controller", [None, None]))
        old_zone, new_zone = change.get("zone", _UNMOVED)
        if old_zone == "battlefield":
            perms[old_ctl, name] -= 1
        if new_zone == "battlefield":
            perms[new_ctl, name] += 1
        if old_zone != new_zone:
            zones[owner, old_zone] -= 1
            zones[owner, new_zone] += 1
            exiled += (new_zone == "exile") - (old_zone == "exile")
    for label, token in sorted((delta.get("created") or {}).items()):
        if token.get("zone") == "battlefield":
            seat = seats.get(token.get("controller"), seats[_label_owner(label)])
            perms[seat, _label_name(label)] += 1

    asserts: list[dict] = []
    for player, change in sorted((delta.get("players") or {}).items()):
        if "life" in change:
            asserts.append({"op": "assertLife", "player": seats[player], "life": change["life"][1]})
    for seat, name in sorted(set(perms) | set(before_perms)):
        if perms[seat, name] != before_perms[seat, name]:
            asserts.append(
                {
                    "op": "assertPermanentCount",
                    "player": seat,
                    "name": name,
                    "count": perms[seat, name],
                }
            )
    for seat in sorted(seats.values()):
        for zone, op in _COUNTED.items():
            if zones[seat, zone] != before_zones[seat, zone]:
                asserts.append({"op": op, "player": seat, "count": zones[seat, zone]})
    if exiled:
        asserts.append({"op": "assertExileCount", "count": exiled})
    tapped: Counter[tuple[int, str]] = Counter()
    for label, change in objects:
        name, owner = _label_name(label), seats[_label_owner(label)]
        seat = seats.get(change.get("controller", [None, None])[1], owner)
        # Per-object assertions select by name, so only a name unique on its
        # controller's battlefield is checked.
        if change.get("zone", _UNMOVED)[1] != "battlefield" or perms[seat, name] != 1:
            continue
        before, after = change.get("counters", [{}, {}])
        for kind in sorted(set(before) | set(after)):
            if before.get(kind, 0) != after.get(kind, 0):
                asserts.append(
                    {
                        "op": "assertCounterCount",
                        "player": seat,
                        "name": name,
                        "counter": kind,
                        "count": after.get(kind, 0),
                    }
                )
        power, toughness = change.get("power"), change.get("toughness")
        if power and toughness and power[1] is not None and toughness[1] is not None:
            asserts.append(
                {
                    "op": "assertPowerToughness",
                    "player": seat,
                    "name": name,
                    "power": power[1],
                    "toughness": toughness[1],
                }
            )
        # Basic lands also tap to pay for the raise, which MCM's delta does not see.
        if change.get("tapped", [False, False])[1] and name not in _BASIC_LANDS:
            tapped[seat, name] += 1
    for (seat, name), count in sorted(tapped.items()):
        asserts.append(
            {
                "op": "assertTappedCount",
                "player": seat,
                "name": name,
                "tapped": True,
                "count": count,
            }
        )

    if not asserts:
        return Untranslated("no recorded change the runner can assert")
    ops.append(raise_op)
    ops += [
        {"op": "addTarget", "player": controller, "target": _target(t, seats)}
        for t in action.get("targets") or []
    ]
    ops += [{"op": "setStopAt", "turn": 1, "phase": "BEGIN_COMBAT"}, {"op": "execute"}]
    return ops + asserts


_SHIM = """import {{ readFileSync }} from "node:fs";
import {{ registerPortedMageTests }} from "{runner}";
const spec = new URL("./{spec}", import.meta.url);
registerPortedMageTests(JSON.parse(readFileSync(spec, "utf8")));
"""


def write_specs(
    golden_paths: Iterable[Path], out_dir: Path, runner: Path, *, chunk: int = 200
) -> dict:
    """Translate every golden, write the specs `chunk` tests per file with one shim
    each, and `manifest.json` (translated ids, untranslated ids with reasons)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    tests: list[dict] = []
    untranslated: dict[str, str] = {}
    for path in sorted(golden_paths, key=golden_id):
        result = translate(json.loads(path.read_text()))
        if isinstance(result, Untranslated):
            untranslated[golden_id(path)] = result.reason
        else:
            tests.append({"name": golden_id(path), "operations": result})
    for index in range(0, len(tests), chunk):
        stem = f"{SOURCE_PATH}-{index // chunk:03d}"
        spec = {"sourcePath": SOURCE_PATH, "tests": tests[index : index + chunk]}
        (out_dir / f"{stem}.json").write_text(json.dumps(spec, indent=1, ensure_ascii=False))
        shim = _SHIM.format(runner=runner.resolve().as_uri(), spec=f"{stem}.json")
        (out_dir / f"{stem}.test.mjs").write_text(shim)
    manifest = {"translated": [t["name"] for t in tests], "untranslated": untranslated}
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n")
    return manifest


def _message(element: ElementTree.Element) -> str:
    message = element.get("message") or (element.text or "").strip()
    return message.splitlines()[0].removeprefix("Error: ").strip() if message else ""


def parse_junit(xml_text: str) -> dict[str, dict[str, str]]:
    """`{golden id: {verdict, message}}` for every generated test in a Node `junit`
    report. A failure whose message is one of the runner's assertion messages
    ("expected ..., got ...") is a disagreement; any other failure, an error or a skip
    means the scenario could not be judged (`ironsmith-error`)."""
    verdicts: dict[str, dict[str, str]] = {}
    prefix = f"{SOURCE_PATH} :: "
    for case in ElementTree.fromstring(xml_text).iter("testcase"):
        name = case.get("name", "")
        if not name.startswith(prefix):
            continue
        failure = case.find("failure")
        if failure is None:
            failure = case.find("error")
        if case.find("skipped") is not None:
            verdict = {"verdict": "ironsmith-error", "message": "skipped"}
        elif failure is None:
            verdict = {"verdict": "agree", "message": ""}
        else:
            message = _message(failure)
            kind = "disagree" if message.startswith("expected ") else "ironsmith-error"
            verdict = {"verdict": kind, "message": message}
        verdicts[name.removeprefix(prefix)] = verdict
    return verdicts


def behaviour_rows(
    manifest: dict, verdicts: dict[str, dict[str, str]], cards: dict[str, str]
) -> list[dict]:
    """One normalised row per golden (`id`, `card`, `verdict`, `message`): the
    runner's verdict for a translated golden (`ironsmith-error` when the report has no
    result for it), `untranslated` with the reason otherwise."""
    rows = []
    for gid in manifest["translated"]:
        verdict = verdicts.get(gid, {"verdict": "ironsmith-error", "message": "no JUnit result"})
        rows.append({"id": gid, "card": cards.get(gid, ""), **verdict})
    for gid, reason in manifest["untranslated"].items():
        rows.append(
            {"id": gid, "card": cards.get(gid, ""), "verdict": "untranslated", "message": reason}
        )
    return sorted(rows, key=lambda row: row["id"])
