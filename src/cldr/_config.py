"""Defines the CLDR application's configuration."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Sequence, cast

import clack
from eris import ErisError, Err, Ok, Result
import toml
from typist import assert_never, literal_to_list

from ._constants import KIND_TO_SECTION_MAP, PROJECT_NAME, Kind


Command = Literal["build", "info", Kind]  # available CLI sub-commands


class Config(clack.Config):
    """TODO"""

    command: Command
    changelog_dir: Path

    @classmethod
    def from_cli_args(cls, argv: Sequence[str]) -> Config:
        """TODO"""
        parser = clack.Parser()
        parser.add_argument(
            "--changelog-dir",
            type=Path,
            default=Path("changelog"),
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
            default=Path("CHANGELOG.md"),
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

        for kind in cast(List[Kind], literal_to_list(Kind)):
            kind_parser = new_command(
                kind,
                help=(
                    f"Add a new bullet to the '{KIND_TO_SECTION_MAP[kind]}'"
                    " section of the next release."
                ),
            )
            kind_parser.add_argument(
                "body",
                default=None,
                nargs="?",
                help=(
                    "The contents of the new bullet. If no body is provided,"
                    " the bullet file will be opened using your system's"
                    " default editor so you can provide one."
                ),
            )
            kind_parser.add_argument(
                "-n",
                "--no-commit",
                dest="commit_changes",
                action="store_false",
                help=(
                    "Specify this option if you do NOT want to commit this new"
                    " bullet using git."
                ),
            )
            kind_parser.add_argument(
                "-t",
                "--tags",
                type=clack.comma_list_or_file.parse,
                help=clack.comma_list_or_file.help(
                    "Tags (e.g. a Jira issue number) to apply to the new"
                    " bullet."
                ),
            )
            kind_parser.add_argument(
                "-b",
                "--bullet-file-name",
                default=None,
                help=(
                    "The basename of the bullet file which we will add this"
                    " changelog bullet to. Defaults to a bullet filename of"
                    " the form USER@BRANCH."
                ),
            )

        args = parser.parse_args(argv[1:])
        kwargs = vars(args)

        cmd: Command = args.command
        if cmd == "build":
            return BuildConfig(**kwargs)
        elif (
            cmd == "add"
            or cmd == "chg"
            or cmd == "dep"
            or cmd == "fix"
            or cmd == "misc"
            or cmd == "rm"
            or cmd == "sec"
        ):
            return KindConfig(**kwargs)
        elif cmd == "info":
            return InfoConfig(**kwargs)
        else:
            assert_never(cmd)


class BuildConfig(Config):
    """TODO"""

    changelog: Path
    in_place: bool
    new_version: str


class KindConfig(Config):
    """TODO"""

    body: Optional[str]
    commit_changes: bool
    tags: Optional[List[str]]
    bullet_file_name: Optional[str]


class InfoConfig(Config):
    """TODO"""


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
