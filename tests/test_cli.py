"""Tests the cldr project's CLI."""

from __future__ import annotations

from cldr import main


def test_main() -> None:
    """Tests main() function."""
    assert main([""]) == 0
