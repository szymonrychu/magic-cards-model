"""Class mode keeps the split class's runtime MRO one class deeper than the old one.

The P0 dry run measured eleven mixin bases on `Game` at +5.6% suite CPU (52.3 s ->
55.2 s single-process on a fixed scenario sample, three rounds each, F2 vs F3): every
attribute lookup that misses the type cache probes one more dict per extra base.
Folding the mixins into one generated base at class creation recovered all of it, so
the codemod emits a metaclass that does that while the source still lists the mixins.
"""

from __future__ import annotations

import shutil

import pytest
from scripts.split import codemod

from tests.test_split_codemod import FIX, run_py

PROBE_MRO = """
import fxtop.game as gm
mro = gm.Game.__mro__
print(len(mro))
print(sorted(c.__name__ for c in mro if c.__name__.endswith("Mixin")))
g = gm.Game()
print(g.combat_a(), g.draw_one(), g.static_one(), g.cls_one(), g.combat_c(), g.settle_pregame())
print(gm.Game.model_validate({"life": 3}).life, sorted(dir(gm.Game)) == sorted(set(dir(gm.Game))))
"""


def test_class_mode_folds_the_mixins_into_one_base(tmp_path):
    result = codemod.build(FIX / "game.toml")
    shadow = codemod.shadow_tree(result, tmp_path / "shadow")
    old = run_py(FIX / "root", PROBE_MRO).splitlines()
    new = run_py(shadow, PROBE_MRO).splitlines()
    assert int(new[0]) == int(old[0]) + 1  # one generated base, not one per mixin
    assert new[1] == "[]"
    assert new[2:] == old[2:]


def test_class_mode_source_still_lists_the_mixins():
    init = codemod.build(FIX / "game.toml").files["__init__.py"]
    assert "class Game(CombatMixin, LibraryMixin, BaseModel, metaclass=_FlatMixins):" in init


def test_class_mode_refuses_a_class_that_already_has_a_metaclass(tmp_path):
    work = tmp_path / "w"
    shutil.copytree(FIX, work, ignore=shutil.ignore_patterns("__pycache__"))
    game = work / "root" / "fxtop" / "game.py"
    game.write_text(
        game.read_text().replace("class Game(BaseModel):", "class Game(BaseModel, metaclass=M):")
    )
    with pytest.raises(codemod.CodemodError, match="already has a metaclass"):
        codemod.build(work / "game.toml")
