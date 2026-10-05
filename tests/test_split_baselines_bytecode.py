"""The goldens hash ignores bytecode caches.

tests/golden is a package (`__init__.py`, `__main__.py`), so running the suite writes
`tests/golden/__pycache__/*.pyc`, whose header carries the source file's mtime. A fresh
checkout has fresh mtimes, so the dry run read a different goldens hash on every fresh
worktree with identical goldens (r5 and r6, both on b0da375b: 68b64dde9c24, 425f2f15d461).
"""

from __future__ import annotations

from scripts.split import baselines as B


def test_hash_tree_ignores_bytecode_caches(tmp_path):
    root = tmp_path / "golden"
    (root / "card").mkdir(parents=True)
    (root / "card" / "triggered-1.json").write_text("{}")
    (root / "__init__.py").write_text("")
    clean = B.hash_tree(root)
    (root / "__pycache__").mkdir()
    (root / "__pycache__" / "__init__.cpython-313.pyc").write_bytes(b"\x00mtime-a")
    (root / "card" / "stray.pyc").write_bytes(b"\x00mtime-b")
    assert B.hash_tree(root) == clean
