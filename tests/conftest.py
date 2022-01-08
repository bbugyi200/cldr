"""This file contains shared fixtures and pytest hooks.

https://docs.pytest.org/en/6.2.x/fixture.html#conftest-py-sharing-fixtures-across-multiple-files
"""

from pathlib import Path
from typing import Any, Protocol

from pytest import fixture
import yaml


DEFAULT_CONFIG = {
    "current_version": "1.2.3",
    "github_repo": "https://github.com/bbugyi200/cldr",
    "jira_base_url": "https://jira.prod.company.com",
}


@fixture(name="changelog_dir")
def changelog_dir_fixture(tmp_path: Path) -> Path:
    """TODO"""
    result = tmp_path / "changelog"
    result.mkdir()
    return result


class MakeConfigFile(Protocol):
    """Type of the function returned by `make_config_file()`."""

    def __call__(self, basename: str, **kwargs: Any) -> Path:
        """Captures the `make_config_file()` function's signature."""


@fixture(name="make_config_file")
def make_config_file_fixture(tmp_path: Path) -> MakeConfigFile:
    """Returns a function that can be used to generate YAML config files."""

    def make_config_file(basename: str, **kwargs: Any) -> Path:
        config_dict = dict(**kwargs)

        config_file = tmp_path / basename
        config_file.parent.mkdir(parents=True, exist_ok=True)

        # Initialize config file...
        with config_file.open("w+") as f:
            yaml.dump(config_dict, f, allow_unicode=True)

        return config_file

    return make_config_file


@fixture(name="config_file")
def config_file_fixture(make_config_file: MakeConfigFile) -> Path:
    """Returns the path to a config file with default contents."""
    return make_config_file("cldr_test_config", **DEFAULT_CONFIG)
