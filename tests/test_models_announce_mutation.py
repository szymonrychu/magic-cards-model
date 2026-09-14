"""Every engine model announces its own field assignments.

A board snapshot (`snapshot.py`) is invalidated by any field assignment on any
engine model, which is only true if every pydantic model in the package is
built on the announcing base. A new model written straight on `BaseModel`
would silently opt out, so this walks every module and checks.
"""

from __future__ import annotations

import importlib
import pkgutil

from pydantic import BaseModel

import magic_cards_model
from magic_cards_model.snapshot import AnnouncesMutation


def _every_subclass(cls: type) -> set[type]:
    found: set[type] = set()
    for sub in cls.__subclasses__():
        found.add(sub)
        found |= _every_subclass(sub)
    return found


def test_every_engine_model_announces_mutation():
    for module in pkgutil.walk_packages(magic_cards_model.__path__, "magic_cards_model."):
        importlib.import_module(module.name)

    engine_models = [
        cls
        for cls in _every_subclass(BaseModel)
        if cls.__module__.startswith("magic_cards_model.")
        and "[" not in cls.__name__  # a parametrised generic alias of a real model
    ]
    assert engine_models, "the walk found no models at all"
    silent = sorted(
        f"{cls.__module__}.{cls.__qualname__}"
        for cls in engine_models
        if not issubclass(cls, AnnouncesMutation)
    )
    assert silent == []
