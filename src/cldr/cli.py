"""Command-line tool to make managing a changelog file easier.

Examples:
    # Prints new changelog file contents to STDOUT.
    clog build -V 1.2.3

    # Updates CHANGELOG.md in-place.
    clog build -V 1.2.3 -i

    # Add a new bullet to the 'Added' section of the next release's
    # CHANGELOG.md section.
    clog add "Added new feature."

    # Add a new bullet to the 'Added' section of the next release's
    # CHANGELOG.md section, which is related to the CSRE-123 jira issue.
    clog add -t csre-123 "Added new feature."

    # Add a new bullet to the 'Fixed' section...
    clog fix "Fixed a bug."

    # Add a new bullet to the 'Miscellaneous' section...
    clog misc "Did something unreleated to any feature."

    # Add a new bullet to the 'Changed' section...
    clog mod "Changed an existing feature."

    # Add a new bullet to the 'Removed' section...
    clog rm "Removed an existing feature."

    # Print internal clog information to STDOUT as JSON data.
    clog info
"""

from abc import ABC
from collections import OrderedDict, defaultdict
import datetime as dt
from functools import lru_cache
import itertools as it
import json
import logging
from operator import attrgetter
import os
from pathlib import Path
import re
import subprocess as sp
import sys
from typing import (
    Any,
    Dict,
    Iterable,
    Iterator,
    List,
    Literal,
    Optional,
    Protocol,
    Sequence,
    Type,
    Union,
    cast,
)

import clack
from eris import ErisError, Err, Ok, Result
from metaman import scriptname
import proctor
from pydantic.dataclasses import dataclass
import toml
from typist import PathLike, assert_never, literal_to_list


# TODO(bugyi): Fix Jenkins docker so clog and bumper can both commit instead of making Jenkins do it.
# TODO(bugyi): Add 'edit' sub-command that opens this branches' bullet file in editor.
# TODO(bugyi): Define markdown links at the bottom of section instead of inline.
# TODO(bugyi): The changelog/README.md file should be updated on `clog build -i`, not after `clog <KIND>`.
# TODO(bugyi): Support setup.cfg and .clogrc (will later be .cldrrc) config files in addition to pyproject.toml.
# TODO(bugyi): Relative commit tag (e.g. `c1`) should use first commit (instead of last commit) that added that bullet.
logging.root.handlers.clear()  # HACK: Remove after https://bbgithub.dev.bloomberg.com/ComplianceSRE/python-libs/pull/15 is merged in.
logger = logging.getLogger(__name__)

# The TAG_TYPES list is populated later by the `register_tag` decorator.
TAG_TYPES: List[Type["Tag"]] = []

Kind = Literal["add", "chg", "dep", "fix", "misc", "rm", "sec"]
Command = Literal["build", "info", Kind]  # available CLI sub-commands

KIND_TO_SECTION_MAP: Dict[Kind, str] = {
    "add": "Added",
    "chg": "Changed",
    "dep": "Deprecated",
    "fix": "Fixed",
    "misc": "Miscellaneous",
    "rm": "Removed",
    "sec": "Security",
}
BULLET_EXPLANATION = f"""\
All bullet lines must be of the form `* KIND(TAG_LIST): BODY` or `* KIND:
BODY`, where `KIND` is one of `{sorted(set(KIND_TO_SECTION_MAP))}`, `BODY` is a
sentence or two about the changes you made, `TAG_LIST` is one or more `TAG`s
separated by commas, and `TAG` is one of `'bc'` (to indicate a breaking
change), `GITHUB_ISSUE`, `GITHUB_PR`, `JIRA_ISSUE`, or `RELATIVE_COMMIT`.
These latter tag types are described below:

* `GITHUB_ISSUE`: is either of the form `#N`, `REPO#N`, or `ORG/REPO#N`.
* `GITHUB_PR`: is either of the form `!N`, `REPO!N`, or `ORG/REPO!N`.
* `JIRA_ISSUE`: is either of the form `ORG-N` or `N` (this latter form can only
be used if the 'jira_org' option is set in your project's pyproject.toml).
* `RELATIVE_COMMIT`: is used to reference a commit hash relative to the commit
that added the current changelog bullet. This tag is of the form `cN` where `N`
is an integer offset (e.g. the `c1` tag will reference the commit made directly
before the commit that added the changelog bullet). NOTE: If the current
changelog bullet's `BODY` is `'...'` and the bullet references a commit,
`BODY` will be taken to be the subject of the referenced commit's message.

Here is an example of a valid bullet which references the CSRE-103 Jira issue:
`* add(csre-103): Added the clog.py script.`
"""
CLOG_URL = "https://bbgithub.dev.bloomberg.com/ComplianceSRE/tools/blob/master/src/bloomberg/compliance/sre/tools/clog.py"
UNRELEASED_BEGIN = f"""\
The unreleased section is unique in that we do not add content to it directly.
Instead, developers of this project add specially formatted bullets to files of
the form `{{0}}/USER@BRANCH.md`. Refer to the [{{0}}/README.md] file or the
[clog] script (which consumes these bullets when a new version of this project
is released) for more information.

[{{0}}/README.md]: {{1}}/tree/master/{{0}}
[clog]: {CLOG_URL}
""".format
README_CONTENTS = f"""\
# Changelog Bullet Files

This directory should contain markdown files of the form `USER@BRANCH.md`. Each
of these files should contain one or more bullets of the form described in the
following paragraph. These bullets will be consumed by the [clog] script when a
new version of this project is released.

{BULLET_EXPLANATION}

[clog]: {CLOG_URL}
"""


@dataclass(frozen=True)
class SharedConfig(clack.Config):
    command: Command
    changelog_dir: Path


@dataclass(frozen=True)
class BuildConfig(SharedConfig):
    changelog: Path
    in_place: bool
    new_version: str


@dataclass(frozen=True)
class KindConfig(SharedConfig):
    body: Optional[str]
    commit_changes: bool
    tags: Optional[List[str]]
    bullet_file_name: Optional[str]


@dataclass(frozen=True)
class InfoConfig(SharedConfig):
    pass


Config = Union[BuildConfig, KindConfig, InfoConfig]


def parse_cli_args(argv: Sequence[str]) -> Config:
    parser = clack.Parser()
    parser.add_argument(
        "--changelog-dir",
        type=Path,
        default=Path("changelog"),
        help=(
            "Can be used to explicitly specify the path of the changelog"
            " directory where unreleased change bullets are stored. Defaults"
            " to '%(default)s'."
        ),
    )

    new_command = clack.new_command_factory(parser)

    build_parser = new_command(
        "build",
        help=(
            "Use the bullets found in the changelog directory to generate a"
            " new release section."
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
            "Change the changelog file in-place instead of outputing the new"
            " changelog contents to STDOUT."
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
                "The contents of the new bullet. If no body is provided, the"
                " bullet file will be opened using your system's default"
                " editor so you can provide one."
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
                "Tags (e.g. a Jira issue number) to apply to the new bullet."
            ),
        )
        kind_parser.add_argument(
            "-b",
            "--bullet-file-name",
            default=None,
            help=(
                "The basename of the bullet file which we will add this"
                " changelog bullet to. Defaults to a bullet filename of the"
                " form USER@BRANCH."
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


def run(args: Config) -> int:
    if isinstance(args, BuildConfig):
        return run_build(args)
    elif isinstance(args, KindConfig):
        return run_kind(args)
    elif isinstance(args, InfoConfig):
        return run_info(args)
    else:
        assert_never(args)


def run_build(args: BuildConfig) -> int:
    UNRELEASED_TITLE = "## [Unreleased]"

    unreleased_section_start: Optional[int] = None
    unreleased_section_end: Optional[int] = None
    kind_to_bullets_map_r = read_bullets_from_changelog_dir(args.changelog_dir)
    if isinstance(kind_to_bullets_map_r, Err):
        e = kind_to_bullets_map_r.err()
        logger.error(
            "An error occurred while attempting to load bullets from the"
            " changelog directory (%s).\n%s",
            args.changelog_dir,
            e.report(),
        )
        return 1

    kind_to_bullets_map = kind_to_bullets_map_r.ok()

    for i, line in enumerate(args.changelog.open()):
        line = line.strip()
        if line.startswith(
            (
                UNRELEASED_TITLE,
                "".join(c for c in UNRELEASED_TITLE if c not in ["[", "]"]),
            )
        ):
            unreleased_section_start = i
            continue

        if unreleased_section_start is None:
            continue

        if line.startswith("#"):
            unreleased_section_end = i
            break

    if unreleased_section_start is None:
        logger.error(
            "No unreleased section found in %s. The unreleased section should"
            " have the following form: '%s(%s/compare/X.Y.Z...HEAD)'",
            args.changelog,
            UNRELEASED_TITLE,
            github_repo(),
        )
        return 1

    old_lines = args.changelog.read_text().split("\n")

    new_contents = "\n".join(old_lines[:unreleased_section_start]) + "\n"
    new_contents += "{}({}/compare/{}...HEAD)\n".format(
        UNRELEASED_TITLE, github_repo(), args.new_version
    )
    new_contents += (
        f"\n{UNRELEASED_BEGIN(args.changelog_dir.name, github_repo())}\n\n"
    )

    if unreleased_section_end is None:
        new_version_url = f"{github_repo()}/releases/tag/{args.new_version}"
    else:
        old_version_r = get_version(old_lines[unreleased_section_end])
        if isinstance(old_version_r, Err):
            e = old_version_r.err()
            logger.error(
                "An error occurred while attempting to parse the project"
                " version from a changelog markdown header:\n%s",
                e.report(),
            )
            return 1

        old_version = old_version_r.ok()
        new_version_url = (
            f"{github_repo()}/compare/{old_version}...{args.new_version}"
        )

    version_part = f"[{args.new_version}]({new_version_url})"
    date_part = dt.datetime.today().strftime("%Y-%m-%d")
    new_contents += f"## {version_part} - {date_part}\n\n"

    first_subsection = True
    for kind in sorted(
        KIND_TO_SECTION_MAP, key=lambda x: KIND_TO_SECTION_MAP[x]
    ):
        if kind in kind_to_bullets_map:
            if first_subsection:
                first_subsection = False
            else:
                new_contents += "\n"

            new_contents += f"### {KIND_TO_SECTION_MAP[kind]}\n\n"

            for bullet in kind_to_bullets_map[kind]:
                new_contents += bullet.to_string()

    if unreleased_section_end is not None:
        new_contents += "\n\n"
        new_contents += "\n".join(old_lines[unreleased_section_end:])

    out_file = args.changelog.open("w") if args.in_place else sys.stdout
    out_file.write(new_contents)
    out_file.close()

    # Delete the bullet files if the --in-place option was given...
    if args.in_place:
        for path in iter_bullet_files(args.changelog_dir):
            path.unlink()

    return 0


def run_kind(args: KindConfig) -> int:
    if not args.changelog_dir.exists():
        logger.info("Creating %s directory...", args.changelog_dir)
        args.changelog_dir.mkdir(parents=True)

    git_add_paths = []

    readme_file = args.changelog_dir / "README.md"
    update_readme = False
    if not readme_file.exists():
        logger.info("Initializing %s contents...", readme_file)
        update_readme = True
    elif not readme_file.read_text() == README_CONTENTS:
        logger.info("Updating the %s file's contents...", readme_file)
        update_readme = True

    if update_readme:
        readme_file.write_text(README_CONTENTS)
        git_add_paths.append(readme_file)

    if args.bullet_file_name is None:
        bullet_file = args.changelog_dir / f"{get_user()}@{get_branch()}.md"
    else:
        bullet_file = args.changelog_dir / f"{args.bullet_file_name}.md"

    git_add_paths.append(bullet_file)
    logger.info(
        "Adding new '%s' bullet to the %s file.", args.command, bullet_file
    )

    old_lines = (
        bullet_file.read_text().split("\n") if bullet_file.exists() else []
    )
    bullet_line = "* {}{}: {}".format(
        args.command,
        f'({",".join(args.tags)})' if args.tags else "",
        "" if args.body is None else f"{args.body}\n",
    )
    with bullet_file.open("a") as f:
        f.write(bullet_line)

    if args.body is None:
        editor_cmd_list = get_editor_cmd_list(
            line=len(old_lines) + 1, column=len(bullet_line) + 1
        )
        editor_cmd_list.append(str(bullet_file))
        logger.info(
            "Opening editor so user can manually enter bullet(s): %r",
            editor_cmd_list,
        )
        ps = sp.Popen(editor_cmd_list)
        ps.communicate()

    new_lines = (
        bullet_file.read_text().split("\n") if bullet_file.exists() else []
    )
    if args.commit_changes and old_lines != new_lines:
        git_add_files = [str(f) for f in git_add_paths]
        logger.info(
            "Commiting the following files to version-control using git: %s",
            git_add_files,
        )

        git_add_cmd_list = ["git", "add"]
        git_add_cmd_list.extend(git_add_files)
        proctor.safe_popen(git_add_cmd_list).unwrap()

        proctor.safe_popen(
            [
                "git",
                "commit",
                "-m",
                f"clog: Add new changelog bullet(s) to the {bullet_file.name}"
                " bullet file.",
            ],
            stdout=sys.stdout,
            stderr=sys.stderr,
        ).unwrap()
    elif args.commit_changes:
        assert (
            old_lines == new_lines
        ), f"Logic Error ({old_lines!r} != {new_lines!r})!"
        logger.info("Not running `git commit` since no changes were made.")

    return 0


def run_info(args: InfoConfig) -> int:
    data: Dict[str, Any] = {}

    data["bullets"] = []
    if list(iter_bullet_files(args.changelog_dir)):
        kind_to_bullets_map = read_bullets_from_changelog_dir(
            args.changelog_dir
        ).unwrap()
        bullets = it.chain.from_iterable(kind_to_bullets_map.values())

        for bullet in sorted(bullets, key=attrgetter("kind")):
            data["bullets"].append(
                OrderedDict(
                    kind=bullet.kind,
                    body=bullet.body,
                    tags=[tag.tag for tag in bullet.tags],
                )
            )
    else:
        logger.warning("No bullet files found.")

    print(json.dumps(OrderedDict(sorted(data.items()))))
    return 0


def get_editor_cmd_list(*, line: int, column: int) -> List[str]:
    editor = os.environ.get("EDITOR", "vim")
    cmd_list = [editor]
    if "vim" in editor:
        cmd_list.append("+startinsert")
        cmd_list.extend(["-c", f"call cursor({line}, {column})"])
    return cmd_list


@lru_cache
def get_user() -> str:
    git_cmd_list = ["git", "config", "--get", "user.email"]
    out_err_r = proctor.safe_popen(git_cmd_list)
    if isinstance(out_err_r, Err):
        logger.warning(
            "Unable to get user's email via the '%s' command.",
            " ".join(git_cmd_list),
        )
        user = os.environ["USER"]
    else:
        out, _err = out_err_r.ok()
        user = out.split("@")[0]

    return user


@lru_cache
def get_branch() -> str:
    branch, _err = proctor.safe_popen(
        ["git", "branch", "--show-current"]
    ).unwrap()
    return branch


def get_version(line: str) -> Result[str, ErisError]:
    pttrn = r"^##[ ]*\[(?P<version>.*)\]"
    if m := re.search(pttrn, line):
        return Ok(m.group("version"))
    else:
        return Err(
            "This regular expression does not match this line.\n\nPATTERN:"
            f" {pttrn!r}\nLINE: {line!r}"
        )


class Tag(Protocol):
    regexp: str
    tag: str

    def __init__(self, tag: str) -> None:
        pass

    def transform_bullet(self, bullet: "Bullet", bullet_line: str) -> str:
        pass


class BulletConfig:
    arbitrary_types_allowed = True


@dataclass(frozen=True, config=BulletConfig)
class Bullet:
    line: str
    changelog_dir: Path
    kind: Kind
    tags: List[Tag]
    body: str

    @classmethod
    def from_string(
        cls, line: str, changelog_dir: PathLike = "changelog"
    ) -> Result["Bullet"]:
        changelog_dir = Path(changelog_dir)

        _TAG_PATTERN = "(?:{})".format(
            "|".join(
                "(?:{})".format(tag_type.regexp) for tag_type in TAG_TYPES
            )
        )
        BULLET_PATTERN = (
            r"^[*-][ ]*(?P<kind>[a-z]+)"
            r"[ ]*(?:\((?P<tags>{0}(?:,{0})*)\))?[ ]*:"
            r"[ ]*(?P<body>.*)$"
        ).format(_TAG_PATTERN)

        if m := re.match(BULLET_PATTERN, line):
            kind = cast(Kind, m.group("kind").lower())
            if kind not in KIND_TO_SECTION_MAP:
                return Err(
                    f"An invalid bullet kind ({kind!r}) was detected in the"
                    f" following line:\n\n{line!r}\n\nUse one of the following"
                    " supported bullet types instead:"
                    f" {sorted(cast(List[Kind], literal_to_list(Kind)))}"
                )

            tags_group = m.group("tags")
            raw_tag_list = tags_group.split(",") if tags_group else []
            tags: List[Tag] = []
            for raw_tag in raw_tag_list:
                for tag_type in TAG_TYPES:
                    if re.match(tag_type.regexp, raw_tag):
                        tags.append(tag_type(raw_tag))
                        break
                else:
                    return Err(
                        "The following tag does not match any known tag"
                        f" types: {raw_tag!r}"
                    )

            return Ok(
                cls(
                    line,
                    changelog_dir,
                    kind,
                    tags,
                    m.group("body"),
                )
            )
        else:
            return Err(
                f"{BULLET_EXPLANATION}\n\nThe following line does not match"
                f" the required form: {line!r}"
            )

    def to_string(self) -> str:
        result = f"* {self.body}"

        for tag in self.tags:
            result = tag.transform_bullet(self, result)

        result += "\n"
        return result


class TagMixin(ABC):
    def __init__(self, tag: str) -> None:
        self.tag = tag


def register_tag(tag_type: Type[Tag]) -> Type[Tag]:
    TAG_TYPES.append(tag_type)
    return tag_type


@register_tag
class BreakingChangeTag(TagMixin):
    regexp = r"bc"

    @staticmethod
    def transform_bullet(bullet: Bullet, bullet_line: str) -> str:
        allowed_kinds: List[Kind] = ["chg", "rm"]
        if bullet.kind not in allowed_kinds:
            raise RuntimeError(
                'Bullets of this kind cannot be marked as a "breaking change"'
                f" (i.e. {bullet.kind!r} not in {allowed_kinds!r}):"
                f" {bullet.line!r}"
            )

        return "* *BREAKING CHANGE*: " + bullet_line[2:]


def _github_tag_regexp(char: str) -> str:
    return r"{0}{1}|{2}{0}{1}|{2}/{2}{0}{1}".format(
        char, "[1-9][0-9]*", f"[^/{char}]+"
    )


def _github_tag_transform_bullet(
    char: str, url_node: str, tag: str, bullet_line: str, *, prefix: str = ""
) -> str:
    if tag.startswith(char):
        url = f"{github_repo()}/{url_node}/{tag.replace(char, '')}"
    elif "/" in tag:
        github_url = "/".join(github_repo().split("/")[:-2])
        org_and_repo, N = tag.split(char)
        url = f"{github_url}/{org_and_repo}/{url_node}/{N}"
    else:
        github_org_url = "/".join(github_repo().split("/")[:-1])
        repo_name, N = tag.split(char)
        url = f"{github_org_url}/{repo_name}/{url_node}/{N}"

    issue_link = f"[{prefix}{tag.replace(char, '#')}]({url})"
    return _add_tag_to_paren_group(bullet_line, issue_link)


@register_tag
class GithubIssue(TagMixin):
    regexp = _github_tag_regexp("#")

    def transform_bullet(self, _bullet: Bullet, bullet_line: str) -> str:
        return _github_tag_transform_bullet(
            "#", "issues", self.tag, bullet_line
        )


@register_tag
class GithubPullRequest(TagMixin):
    regexp = _github_tag_regexp("!")

    def transform_bullet(self, _bullet: Bullet, bullet_line: str) -> str:
        return _github_tag_transform_bullet(
            "!", "pull", self.tag, bullet_line, prefix="PR:"
        )


@register_tag
class JiraIssue(TagMixin):
    regexp = r"(?:[A-Za-z]+-)?[1-9][0-9]*"

    def transform_bullet(self, _bullet: Bullet, bullet_line: str) -> str:
        tag = self.tag
        if tag[0].isdigit():
            if jira_org() is None:
                raise ValueError(
                    "The following line appears to reference a jira issue"
                    f" ({tag}) but the 'jira_org' option is not set in"
                    f" this project's pyproject.toml file: {tag!r}"
                )

            tag = f"{jira_org()}-{tag}"

        tag = tag.upper()
        jira_link = f"[{tag}](https://jira.prod.bloomberg.com/browse/{tag})"
        return _add_tag_to_paren_group(bullet_line, jira_link)


@register_tag
class RelativeCommitTag(TagMixin):
    regexp = r"c(?:0|[1-9][0-9]*)"

    def transform_bullet(self, bullet: Bullet, bullet_line: str) -> str:
        bullet_file: Optional[Path] = None
        bullet_line_number: Optional[int] = None

        for path in iter_bullet_files(bullet.changelog_dir):
            for i, line in enumerate(path.read_text().split("\n")):
                if line == bullet.line:
                    bullet_file = path
                    bullet_line_number = i
                    break

        assert bullet_file is not None and bullet_line_number is not None, (
            "Logic Error! How are we unable to find the bullet line in any"
            f" file?\n\n    bullet={bullet}"
        )

        out, _err = proctor.safe_popen(
            ["git", "blame", str(bullet_file)]
        ).unwrap()
        blame_line = out.split("\n")[bullet_line_number]
        blame_commit_hash = blame_line.split()[0]

        git_log_offset = int(self.tag[1:])
        out, _err = proctor.safe_popen(
            [
                "git",
                "log",
                f"-{git_log_offset + 1}",
                "--format=%h %H %s",
                blame_commit_hash,
            ]
        ).unwrap()
        log_line = out.split("\n")[-1]
        short_hash, long_hash, *subject_list = log_line.split()

        if bullet.body == "...":
            subject = " ".join(subject_list).rstrip()
            if subject[-1] not in ".!?":
                subject += "."

            bullet_line = bullet_line.replace("...", subject)

        commit_link = f"[{short_hash}]({github_repo()}/commit/{long_hash})"
        return _add_tag_to_paren_group(bullet_line, commit_link)


def _add_tag_to_paren_group(bullet_line: str, tag: str) -> str:
    if m := re.match(r"^.*\((?P<tags>.*)\)$", bullet_line):
        tags = m.group("tags")
        return bullet_line.replace(f"({tags})", f"({tags + ', ' + tag})")
    else:
        result = bullet_line + f" ({tag})"
        return result


def read_bullets_from_changelog_dir(
    changelog_dir: PathLike,
) -> Result[Dict[Kind, List[Bullet]]]:
    """
    Arguments:
        @changelog_dir: Path to the directory which contains the bullet files
            we will consume.

    Returns:
        Ok(kind_to_bullets_map) if one or more bullets were consumed
        successfully by this function.
            OR
        Err(ErisError), otherwise.
    """
    changelog_dir = Path(changelog_dir)

    if not changelog_dir.exists():
        return Err("The changelog directory does not exist.")

    bullet_lines: Iterable[str] = []
    for path in iter_bullet_files(changelog_dir):
        logger.info("Consuming bullets from the %s file...", path)
        bullet_lines = it.chain(bullet_lines, path.read_text().split("\n"))

    if not bullet_lines:
        return Err(
            "No markdown files were found in the 'changelog' directory (not"
            " including the README.md file)."
        )

    kind_to_bullets_map = defaultdict(list)
    for line in bullet_lines:
        line = line.strip()
        if not line:
            continue

        bullet_r = Bullet.from_string(line, changelog_dir)
        if isinstance(bullet_r, Err):
            e = bullet_r.err()
            return Err(
                "There was a problem parsing one of the changelog"
                f" bullets:\n\n{line!r}",
                cause=e,
            )

        bullet = bullet_r.ok()
        kind_to_bullets_map[bullet.kind].append(bullet)

    return Ok(kind_to_bullets_map)


def iter_bullet_files(changelog_dir: PathLike) -> Iterator[Path]:
    changelog_dir = Path(changelog_dir)

    for path in changelog_dir.glob("*.md"):
        if path.stem != "README":
            yield path


@lru_cache
def github_repo() -> str:
    conf = _get_conf().unwrap()
    result: Optional[str] = conf.get("github_repo")
    assert result is not None
    return result


@lru_cache
def jira_org() -> Optional[str]:
    conf = _get_conf().unwrap()

    result: Optional[str] = conf.get("jira_org")
    if result is None:
        return None
    else:
        return result.upper()


@lru_cache
def _get_conf(name: str = None) -> Result[Dict[str, Any]]:
    if name is None:
        name = scriptname().replace(".py", "")

    def error(emsg: str) -> Err[ErisError]:
        return Err(
            "{}\n\nIn order to use the 'clog' script, this project's"
            " pyproject.toml file must have a [tool.clog] section that defines"
            " a 'github_repo' option and (optionally) a 'jira_org' option."
            .format(emsg)
        )

    pyproject_toml = Path("pyproject.toml")
    if pyproject_toml.exists():
        conf = toml.loads(pyproject_toml.read_text())
    else:
        return error("The pyproject.toml file does not exist.")

    result = conf.get("tool", {}).get(name)
    if result is None:
        return error(
            f"The pyproject.toml file does not contain a [tool.{name}]"
            " section."
        )

    if result.get("github_repo") is None:
        return error(
            "The [tool.clog] section in the pyproject.toml file does not set"
            " the 'github_repo' option."
        )

    return Ok(result)


main = clack.main_factory(parse_cli_args, run)
if __name__ == "__main__":
    sys.exit(main())
