"""Command-line tool to make managing a changelog file easier.

Examples:
    # Prints new changelog file contents to STDOUT.
    cldr build -V 1.2.3

    # Updates CHANGELOG.md in-place.
    cldr build -V 1.2.3 -i

    # Add a new bullet to the 'Added' section of the next release's
    # CHANGELOG.md section.
    cldr add "Added new feature."

    # Add a new bullet to the 'Added' section of the next release's
    # CHANGELOG.md section, which is related to the CSRE-123 jira issue.
    cldr add -t csre-123 "Added new feature."

    # Add a new bullet to the 'Fixed' section...
    cldr fix "Fixed a bug."

    # Add a new bullet to the 'Miscellaneous' section...
    cldr misc "Did something unreleated to any feature."

    # Add a new bullet to the 'Changed' section...
    cldr mod "Changed an existing feature."

    # Add a new bullet to the 'Removed' section...
    cldr rm "Removed an existing feature."

    # Print internal cldr information to STDOUT as JSON data.
    cldr info
"""

# NOTE: The above docstring is used by clack for the command-line --help
#   message. This module is used to define clack configuration classes and the
#   clack parser function.
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Sequence

import clack
from eris import ErisError, Err, Ok, Result
import toml
from typist import literal_to_list

from ._constants import PROJECT_NAME, Kind


BUildCommand = Literal["build"]
InfoCommand = Literal["info"]
NewCommand = Literal["new"]
Command = Literal[
    BUildCommand, InfoCommand, NewCommand
]  # available CLI sub-commands


class Config(clack.Config):
    """TODO"""

    command: Command

    # --- Options
    changelog_dir: Path = Path("changelog")


class BuildConfig(Config):
    """TODO"""

    command: BUildCommand

    # --- OPTIONS
    changelog: Path = Path("CHANGELOG.md")
    in_place: bool = False
    new_version: str


class NewConfig(Config):
    """TODO"""

    command: NewCommand

    # --- ARGS
    kind: Kind

    # --- OPTIONS
    body: Optional[str] = None
    bullet_file_name: Optional[str] = None
    commit_changes: bool = True
    tags: Optional[List[str]] = None


class InfoConfig(Config):
    """TODO"""

    command: InfoCommand


@lru_cache
def github_repo() -> str:
    """TODO"""
    conf = _get_conf().unwrap()
    result: Optional[str] = conf.get("github_repo")
    assert result is not None
    return result


@lru_cache
def jira_org() -> Optional[str]:
    """TODO"""
    conf = _get_conf().unwrap()

    result: Optional[str] = conf.get("jira_org")
    if result is None:
        return None
    else:
        return result.upper()


@lru_cache
def _get_conf() -> Result[Dict[str, Any], ErisError]:
    def error(emsg: str) -> Err[Any, ErisError]:
        return Err(
            "{}\n\nIn order to use the 'cldr' script, this project's"
            " pyproject.toml file must have a [tool.cldr] section that defines"
            " a 'github_repo' option and (optionally) a 'jira_org' option."
            .format(emsg)
        )

    pyproject_toml = Path("pyproject.toml")
    if pyproject_toml.exists():
        conf = toml.loads(pyproject_toml.read_text())
    else:
        return error("The pyproject.toml file does not exist.")

    result = conf.get("tool", {}).get(PROJECT_NAME)
    if result is None:
        return error(
            f"The pyproject.toml file does not contain a [tool.{PROJECT_NAME}]"
            " section."
        )

    if result.get("github_repo") is None:
        return error(
            "The [tool.cldr] section in the pyproject.toml file does not set"
            " the 'github_repo' option."
        )

    return Ok(result)


def clack_parser(argv: Sequence[str]) -> dict[str, Any]:
    """TODO"""
    parser = clack.Parser()
    parser.add_argument(
        "--changelog-dir",
        type=Path,
        help=(
            "Can be used to explicitly specify the path of the changelog"
            " directory where unreleased change bullets are stored."
            " Defaults to '%(default)s'."
        ),
    )

    new_command = clack.new_command_factory(parser)

    build_parser = new_command(
        "build",
        help=(
            "Use the bullets found in the changelog directory to generate"
            " a new release section."
        ),
    )
    build_parser.add_argument(
        "--changelog",
        type=Path,
        help="Path to the changelog file. Defaults to '%(default)s'.",
    )
    build_parser.add_argument(
        "-V",
        "--new-version",
        required=True,
        help="The newest project version.",
    )
    build_parser.add_argument(
        "-i",
        "--in-place",
        action="store_true",
        help=(
            "Change the changelog file in-place instead of outputing the"
            " new changelog contents to STDOUT."
        ),
    )

    new_command(
        "info", help="Print internal state to standard output as JSON."
    )

    new_parser = new_command(
        "new",
        help="Add a new bullet to the KIND section of the next release.",
    )

    choices = literal_to_list(Kind)
    new_parser.add_argument(
        "kind",
        metavar="KIND",
        choices=choices,
        help=(
            "This is the type (aka KIND) of the changelog bullet that will be"
            f" added. Choose from one of {choices}."
        ),
    )
    new_parser.add_argument(
        "-b",
        "--body",
        help=(
            "The contents of the new bullet. If no body is provided,"
            " the bullet file will be opened using your system's"
            " default editor so you can provide one."
        ),
    )
    new_parser.add_argument(
        "-n",
        "--no-commit",
        dest="commit_changes",
        action="store_false",
        help=(
            "Specify this option if you do NOT want to commit this new"
            " bullet using git."
        ),
    )
    new_parser.add_argument(
        "-t",
        "--tags",
        type=clack.comma_list_or_file.parse,
        help=clack.comma_list_or_file.help(
            "Tags (e.g. a Jira issue number) to apply to the new bullet."
        ),
    )
    new_parser.add_argument(
        "-B",
        "--bullet-file-name",
        help=(
            "The basename of the bullet file which we will add this"
            " changelog bullet to. Defaults to a bullet filename of"
            " the form USER@BRANCH."
        ),
    )

    args = parser.parse_args(argv[1:])
    kwargs = clack.filter_cli_args(args)

    return kwargs
