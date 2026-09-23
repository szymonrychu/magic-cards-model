"""Suite-wide pytest options."""

from __future__ import annotations

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--update-golden",
        action="store_true",
        default=False,
        help=(
            "Write the behavioural sweep's golden files (tests/golden/) from what the "
            "engine does now instead of comparing against them; `mise run golden:update`."
        ),
    )
