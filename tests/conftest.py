"""This file contains shared fixtures and pytest hooks.

https://docs.pytest.org/en/6.2.x/fixture.html#conftest-py-sharing-fixtures-across-multiple-files
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from clack.types import ClackConfigFile
from pytest import fixture


if TYPE_CHECKING:  # fixes pytest warning
    from clack.pytest_plugin import MakeConfigFile


pytest_plugins = ["clack.pytest_plugin"]

DEFAULT_CONFIG = {
    "current_version": "1.2.3",
    "github_repo": "https://github.com/bbugyi200/cldr",
    "jira_base_url": "https://jira.prod.company.com",
    "version_part_to_bump": "none",
}


@fixture(name="changelog_dir")
def changelog_dir_fixture(tmp_path: Path) -> Path:
    """TODO"""
    result = tmp_path / "changelog"
    result.mkdir()
    return result


@fixture(name="default_config_file")
def default_config_file_fixture(
    make_config_file: MakeConfigFile,
) -> ClackConfigFile:
    """Returns the path to a config file with default contents."""
    return make_config_file("cldr_test_config", **DEFAULT_CONFIG)
