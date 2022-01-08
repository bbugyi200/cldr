"""Command-line tool to make managing a changelog file easier.

Examples:
    # Prints new changelog file contents to STDOUT.
    cldr build -V 1.2.3

    # Updates CHANGELOG.md in-place.
    cldr build -V 1.2.3 -i

    # Print internal cldr information to STDOUT as JSON data.
    cldr info

    # Add a new bullet to the 'Added' section of the next release's
    # CHANGELOG.md section.
    cldr new add -b "Added new feature."

    # Add a new bullet to the 'Added' section of the next release's
    # CHANGELOG.md section, which is related to the CSRE-123 jira issue.
    cldr new add -t csre-123 -b "Added new feature."

    # Add a new bullet to the 'Fixed' section...
    cldr new fix -b "Fixed a bug."

    # Add a new bullet to the 'Miscellaneous' section...
    cldr new misc -b "Did something unreleated to any feature."

    # Add a new bullet to the 'Changed' section...
    cldr new chg -b "Changed an existing feature."

    # Add a new bullet to the 'Removed' section...
    cldr new rm -b "Removed an existing feature."
"""

# NOTE: The above docstring is used by clack for the command-line --help
#   message. This module is used to define clack configuration classes and the
#   clack parser function.
from __future__ import annotations

from pathlib import Path
from typing import Any, List, Literal, Optional, Sequence

import clack
from typist import literal_to_list

from ._bump import BumpPart
from ._constants import Kind


BuildCommand = Literal["build"]
BumpCommand = Literal["bump"]
InfoCommand = Literal["info"]
NewCommand = Literal["new"]
Command = Literal[
    BuildCommand, BumpCommand, InfoCommand, NewCommand
]  # available CLI sub-commands


class Config(clack.Config):
    """Base configuration class."""

    command: Command

    # --- OPTIONS
    changelog_dir: Path = Path("changelog")

    # --- CONFIG
    current_version: str
    github_repo: str
    infer_version_part: bool = False
    jira_base_url: Optional[str] = None
    jira_org: Optional[str] = None


class BuildConfig(Config):
    """Config for the 'build' subcommand."""

    command: BuildCommand

    # --- OPTIONS
    changelog: Path = Path("CHANGELOG.md")
    in_place: bool = False
    new_version: str


class BumpConfig(Config):
    """Config for the 'bump' subcommand."""

    command: BumpCommand

    # --- ARGS
    part: BumpPart

    # --- OPTIONS
    commit_changes: bool = True


class InfoConfig(Config):
    """Config for the 'info' subcommand."""

    command: InfoCommand


class NewConfig(Config):
    """Config for the 'new' subcommand."""

    command: NewCommand

    # --- ARGS
    kind: Kind

    # --- OPTIONS
    body: Optional[str] = None
    bullet_file_name: Optional[str] = None
    commit_changes: bool = True
    tags: Optional[List[str]] = None


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

    ### setup the 'build' subcommand...
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

    ### setup the 'bump' subcommand...
    bump_parser = new_command(
        "bump",
        help=(
            "Configure this repository to release a new PART version (i.e."
            " 'major', 'minor', or 'patch') on the next merge into master."
        ),
    )

    choices = literal_to_list(BumpPart)
    bump_parser.add_argument(
        "part",
        metavar="PART",
        choices=choices,
        help=(
            "The part of the semantic version to bump forward. Choose from"
            f" one of {choices}."
        ),
    )

    bump_parser.add_argument(
        "-n",
        "--no-commit",
        dest="commit_changes",
        action="store_false",
        help=(
            "Specify this option if you do NOT want to commit these changes"
            " using git."
        ),
    )

    ### setup the 'info' subcommand...
    new_command(
        "info", help="Print internal state to standard output as JSON."
    )

    ### setup the 'new' subcommand...
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
