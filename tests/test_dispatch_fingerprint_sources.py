"""The dispatch fingerprint must not depend on the ladders living in one file.

Fixture monolith (`tests/fixtures/split/fingerprint/mono.py`) and an equivalent
package (ladders in `dispatch.py`, parsers in two family modules, a facade
re-exporting everything) must fingerprint identically, and a name only the
facade binds must not be picked up.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
from scripts.dispatch_fingerprint import compute_fingerprint

FIXTURES = Path(__file__).parent / "fixtures" / "split" / "fingerprint"

CHAINS = (
    ("ladder_plain", "texts", (None, False, True)),
    ("ladder_chain", "texts", (None,)),
)
CORPUS = {"texts": ["abc", "bxc", "sxx", "t", "zzc", "q", "a", "tb"]}


def _load(name: str, path: Path, package: bool = False):
    kwargs = {"submodule_search_locations": [str(path.parent)]} if package else {}
    spec = importlib.util.spec_from_file_location(name, path, **kwargs)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def mono():
    module = _load("_fp_fixture_mono", FIXTURES / "mono.py")
    yield module
    sys.modules.pop("_fp_fixture_mono", None)


@pytest.fixture
def pkg():
    module = _load("_fp_fixture_pkg", FIXTURES / "pkg" / "__init__.py", package=True)
    yield module
    for key in [k for k in sys.modules if k.startswith("_fp_fixture_pkg")]:
        sys.modules.pop(key)


def test_monolith_and_package_fingerprint_identically(mono, pkg):
    a = compute_fingerprint(module=mono, chains=CHAINS, corpus=CORPUS)
    b = compute_fingerprint(module=pkg, chains=CHAINS, corpus=CORPUS)
    assert a == b


def test_expected_chains(pkg):
    fp = compute_fingerprint(module=pkg, chains=CHAINS, corpus=CORPUS)
    assert fp["ladder_plain"]["chain"] == [
        "parse_alpha",
        "parse_beta",
        "parse_boom",
        "_resolve_gamma",
    ]
    # Chain.run expands in place into the segment's rungs; the later plain
    # parse_seg_two call is deduped against the expanded rung.
    assert fp["ladder_chain"]["chain"] == [
        "parse_alpha",
        "parse_seg_one",
        "parse_seg_two",
        "parse_beta",
        "_resolve_gamma",
    ]


def test_expected_winners(pkg):
    fp = compute_fingerprint(module=pkg, chains=CHAINS, corpus=CORPUS)
    plain = fp["ladder_plain"]["results"]["plain"]
    assert plain["abc"] == "parse_alpha"
    assert plain["bxc"] == "parse_beta"
    assert plain["zzc"] == "_resolve_gamma"  # parse_boom raises -> counts as None
    assert plain["q"] == "<none>"
    chained = fp["ladder_chain"]["results"]["plain"]
    assert chained["sxx"] == "parse_seg_one"
    assert chained["t"] == "parse_seg_two"
    assert chained["tb"] == "parse_seg_two"
    assert chained["bxc"] == "parse_beta"


def test_name_bound_only_by_facade_is_not_picked_up(pkg):
    assert hasattr(pkg, "parse_facade_only")
    fp = compute_fingerprint(
        module=pkg, chains=(("ladder_ghost", "texts", (None,)),), corpus=CORPUS
    )
    assert fp["ladder_ghost"]["chain"] == ["parse_alpha"]
    assert set(fp["ladder_ghost"]["results"]["plain"].values()) <= {"parse_alpha", "<none>"}


_HIDDEN_RUNGS = (
    "def parse_a(text):\n"
    "    return 'a' if text == 'a' else None\n\n"
    "def grab_x(text):\n"
    "    return 'x' if text == 'x' else None\n\n"
)

_HIDDEN_MONO = _HIDDEN_RUNGS + (
    "def ladder_hidden(text):\n"
    "    v1 = parse_a(text)\n"
    "    if v1 is not None:\n"
    "        return v1\n"
    "    v2 = grab_x(text)\n"
    "    if v2 is not None:\n"
    "        return v2\n"
    "    return None\n"
)

_HIDDEN_REGISTERED = _HIDDEN_RUNGS + (
    "class Chain:\n"
    "    def __init__(self, segments):\n"
    "        self._segments = segments\n\n"
    "    def segment_rungs(self, segment):\n"
    "        return tuple(self._segments[segment])\n\n"
    "    def run(self, segment, value):\n"
    "        for rung in self._segments[segment]:\n"
    "            r = rung(value)\n"
    "            if r is not None:\n"
    "                return r\n"
    "        return None\n\n"
    "SEGS = Chain({'s0': (parse_a, grab_x)})\n\n"
    "def ladder_hidden(text):\n"
    "    if (r := SEGS.run('s0', text)) is not None:\n"
    "        return r\n"
    "    return None\n"
)


def _hidden_fingerprint(tmp_path, name: str, source: str) -> dict:
    path = tmp_path / f"{name}.py"
    path.write_text(source)
    module = _load(name, path)
    try:
        return compute_fingerprint(
            module=module,
            chains=(("ladder_hidden", "texts", (None,)),),
            corpus={"texts": ["a", "x", "q"]},
        )
    finally:
        sys.modules.pop(name, None)


def test_rung_without_parse_in_its_name_stays_outside_the_chain(tmp_path):
    """The chain is the ladder's calls through the name filter ('parse' or
    '_resolve'); a pure rung named otherwise is not a chain member, exactly as
    the committed baseline was recorded (P0 keeps it byte-identical)."""
    fp = _hidden_fingerprint(tmp_path, "_fp_hidden_mono", _HIDDEN_MONO)
    assert fp["ladder_hidden"]["chain"] == ["parse_a"]
    assert fp["ladder_hidden"]["results"]["plain"] == {"a": "parse_a", "x": "<none>", "q": "<none>"}


def test_registered_segment_fingerprints_like_the_hand_written_ladder(tmp_path):
    """`X.run(seg, ...)` expands through the same name filter as hand-written
    calls, so registering a ladder's pure rungs (F2) changes neither its chain
    nor its results, whatever the rungs are called."""
    mono = _hidden_fingerprint(tmp_path, "_fp_hidden_mono2", _HIDDEN_MONO)
    registered = _hidden_fingerprint(tmp_path, "_fp_hidden_reg", _HIDDEN_REGISTERED)
    assert registered == mono
