"""Contains the clack runner functions."""

from __future__ import annotations

from abc import ABC
from collections import OrderedDict, defaultdict
import datetime as dt
from functools import lru_cache
import itertools as it
import json
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
    Optional,
    Protocol,
    Type,
    cast,
    runtime_checkable,
)

import clack
from eris import ErisError, Err, Ok, Result
from logrus import Logger
import proctor
from pydantic.dataclasses import dataclass
from typist import PathLike, literal_to_list

from ._config import BuildConfig, Config, InfoConfig, NewConfig, clack_parser
from ._constants import (
    BULLET_EXPLANATION,
    KIND_TO_SECTION_MAP,
    PROJECT_NAME,
    README_CONTENTS,
    UNRELEASED_BEGIN,
    Kind,
)


logger = Logger(__name__)

# The TAG_TYPES list is populated later by the `register_tag` decorator.
TAG_TYPES: List[Type["Tag"]] = []


def run_build(cfg: BuildConfig) -> int:
    """TODO"""
    UNRELEASED_TITLE = "## [Unreleased]"

    unreleased_section_start: Optional[int] = None
    unreleased_section_end: Optional[int] = None
    kind_to_bullets_map_r = read_bullets_from_changelog_dir(cfg)
    if isinstance(kind_to_bullets_map_r, Err):
        e = kind_to_bullets_map_r.err()
        logger.error(
            "An error occurred while attempting to load bullets from the"
            " changelog directory.",
            changelog_dir=cfg.changelog_dir,
            error=e.to_json(),
        )
        return 1

    kind_to_bullets_map = kind_to_bullets_map_r.ok()

    for i, line in enumerate(cfg.changelog.open()):
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
            cfg.changelog,
            UNRELEASED_TITLE,
            cfg.github_repo,
        )
        return 1

    old_lines = cfg.changelog.read_text().split("\n")

    new_contents = "\n".join(old_lines[:unreleased_section_start]) + "\n"
    new_contents += "{}({}/compare/{}...HEAD)\n".format(
        UNRELEASED_TITLE, cfg.github_repo, cfg.new_version
    )
    new_contents += (
        f"\n{UNRELEASED_BEGIN(cfg.changelog_dir.name, cfg.github_repo)}\n\n"
    )

    if unreleased_section_end is None:
        new_version_url = f"{cfg.github_repo}/releases/tag/{cfg.new_version}"
    else:
        old_version_r = get_version(old_lines[unreleased_section_end])
        if isinstance(old_version_r, Err):
            e = old_version_r.err()
            logger.error(
                "An error occurred while attempting to parse the project"
                " version from a changelog markdown header:\n%r",
                e.to_json(),
            )
            return 1

        old_version = old_version_r.ok()
        new_version_url = (
            f"{cfg.github_repo}/compare/{old_version}...{cfg.new_version}"
        )

    version_part = f"[{cfg.new_version}]({new_version_url})"
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

    out_file = cfg.changelog.open("w") if cfg.in_place else sys.stdout
    out_file.write(new_contents)
    out_file.close()

    # Delete the bullet files if the --in-place option was given...
    if cfg.in_place:
        for path in iter_bullet_files(cfg.changelog_dir):
            path.unlink()

    return 0


def run_new(cfg: NewConfig) -> int:
    """TODO"""
    if not cfg.changelog_dir.exists():
        logger.info("Creating %s directory...", cfg.changelog_dir)
        cfg.changelog_dir.mkdir(parents=True)

    git_add_paths = []

    readme_file = cfg.changelog_dir / "README.md"
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

    if cfg.bullet_file_name is None:
        bullet_file = cfg.changelog_dir / f"{get_user()}@{get_branch()}.md"
    else:
        bullet_file = cfg.changelog_dir / f"{cfg.bullet_file_name}.md"

    git_add_paths.append(bullet_file)
    logger.info(
        "Adding new '%s' bullet to the %s file.", cfg.kind, bullet_file
    )

    old_lines = (
        bullet_file.read_text().split("\n") if bullet_file.exists() else []
    )
    bullet_line = "* {}{}: {}".format(
        cfg.kind,
        f'({",".join(cfg.tags)})' if cfg.tags else "",
        "" if cfg.body is None else f"{cfg.body}\n",
    )
    with bullet_file.open("a") as f:
        f.write(bullet_line)

    if cfg.body is None:
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
    if cfg.commit_changes and old_lines != new_lines:
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
                f"cldr: Add new changelog bullet(s) to the {bullet_file.name}"
                " bullet file.",
            ],
            stdout=sys.stdout,
            stderr=sys.stderr,
        ).unwrap()
    elif cfg.commit_changes:
        assert (
            old_lines == new_lines
        ), f"Logic Error ({old_lines!r} != {new_lines!r})!"
        logger.info("Not running `git commit` since no changes were made.")

    return 0


def run_info(cfg: InfoConfig) -> int:
    """TODO"""
    data: Dict[str, Any] = {}

    data["bullets"] = []
    if list(iter_bullet_files(cfg.changelog_dir)):
        kind_to_bullets_map = read_bullets_from_changelog_dir(cfg).unwrap()
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
    """TODO"""
    editor = os.environ.get("EDITOR", "vim")
    cmd_list = [editor]
    if "vim" in editor:
        cmd_list.append("+startinsert")
        cmd_list.extend(["-c", f"call cursor({line}, {column})"])
    return cmd_list


@lru_cache
def get_user() -> str:
    """TODO"""
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
    """TODO"""
    branch, _err = proctor.safe_popen(
        ["git", "branch", "--show-current"]
    ).unwrap()
    return branch


def get_version(line: str) -> Result[str, ErisError]:
    """TODO"""
    pttrn = r"^##[ ]*\[(?P<version>.*)\]"
    if m := re.search(pttrn, line):
        return Ok(m.group("version"))
    else:
        return Err(
            "This regular expression does not match this line.\n\nPATTERN:"
            f" {pttrn!r}\nLINE: {line!r}"
        )


@runtime_checkable
class Tag(Protocol):
    """TODO"""

    regexp: str
    tag: str

    def __init__(self, tag: str) -> None:
        pass

    def transform_bullet(self, bullet: "Bullet", bullet_line: str) -> str:
        """TODO"""


class BulletConfig:
    """TODO"""

    arbitrary_types_allowed = True


@dataclass(frozen=True, config=BulletConfig)
class Bullet:
    """TODO"""

    cfg: Config
    line: str
    changelog_dir: Path
    kind: Kind
    tags: List[Tag]
    body: str

    @classmethod
    def from_string(
        cls, cfg: Config, line: str, changelog_dir: PathLike = "changelog"
    ) -> Result["Bullet", ErisError]:
        """TODO"""
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
                    cfg,
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
        """TODO"""
        result = f"* {self.body}"

        for tag in self.tags:
            result = tag.transform_bullet(self, result)

        result += "\n"
        return result


class TagMixin(ABC):
    """TODO"""

    def __init__(self, tag: str) -> None:
        self.tag = tag


def register_tag(tag_type: Type[Tag]) -> Type[Tag]:
    """TODO"""
    TAG_TYPES.append(tag_type)
    return tag_type


@register_tag
class BreakingChangeTag(TagMixin):
    """TODO"""

    regexp = r"bc"

    @staticmethod
    def transform_bullet(bullet: Bullet, bullet_line: str) -> str:
        """TODO"""
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
    github_repo: str,
    char: str,
    url_node: str,
    tag: str,
    bullet_line: str,
    *,
    prefix: str = "",
) -> str:
    if tag.startswith(char):
        url = f"{github_repo}/{url_node}/{tag.replace(char, '')}"
    elif "/" in tag:
        github_url = "/".join(github_repo.split("/")[:-2])
        org_and_repo, N = tag.split(char)
        url = f"{github_url}/{org_and_repo}/{url_node}/{N}"
    else:
        github_org_url = "/".join(github_repo.split("/")[:-1])
        repo_name, N = tag.split(char)
        url = f"{github_org_url}/{repo_name}/{url_node}/{N}"

    issue_link = f"[{prefix}{tag.replace(char, '#')}]({url})"
    return _add_tag_to_paren_group(bullet_line, issue_link)


@register_tag
class GithubIssue(TagMixin):
    """TODO"""

    regexp = _github_tag_regexp("#")

    def transform_bullet(self, bullet: Bullet, bullet_line: str) -> str:
        """TODO"""
        return _github_tag_transform_bullet(
            bullet.cfg.github_repo, "#", "issues", self.tag, bullet_line
        )


@register_tag
class GithubPullRequest(TagMixin):
    """TODO"""

    regexp = _github_tag_regexp("!")

    def transform_bullet(self, bullet: Bullet, bullet_line: str) -> str:
        """TODO"""
        return _github_tag_transform_bullet(
            bullet.cfg.github_repo,
            "!",
            "pull",
            self.tag,
            bullet_line,
            prefix="PR:",
        )


@register_tag
class JiraIssue(TagMixin):
    """TODO"""

    regexp = r"(?:[A-Za-z]+-)?[1-9][0-9]*"

    def transform_bullet(self, bullet: Bullet, bullet_line: str) -> str:
        """TODO"""
        tag = self.tag
        if tag[0].isdigit():
            if bullet.cfg.jira_org is None:
                raise ValueError(
                    "The following line appears to reference a jira issue"
                    f" ({tag}) but the 'jira_org' option is not set in"
                    f" this project's pyproject.toml file: {tag!r}"
                )

            tag = f"{bullet.cfg.jira_org}-{tag}"

        tag = tag.upper()
        jira_link = f"[{tag}](https://jira.prod.bloomberg.com/browse/{tag})"
        return _add_tag_to_paren_group(bullet_line, jira_link)


@register_tag
class RelativeCommitTag(TagMixin):
    """TODO"""

    regexp = r"c(?:0|[1-9][0-9]*)"

    def transform_bullet(self, bullet: Bullet, bullet_line: str) -> str:
        """TODO"""
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

        commit_link = (
            f"[{short_hash}]({bullet.cfg.github_repo}/commit/{long_hash})"
        )
        return _add_tag_to_paren_group(bullet_line, commit_link)


def _add_tag_to_paren_group(bullet_line: str, tag: str) -> str:
    if m := re.match(r"^.*\((?P<tags>.*)\)$", bullet_line):
        tags = m.group("tags")
        return bullet_line.replace(f"({tags})", f"({tags + ', ' + tag})")
    else:
        result = bullet_line + f" ({tag})"
        return result


def read_bullets_from_changelog_dir(
    cfg: Config,
) -> Result[Dict[Kind, List[Bullet]], ErisError]:
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
    if not cfg.changelog_dir.exists():
        return Err("The changelog directory does not exist.")

    bullet_lines: Iterable[str] = []
    for path in iter_bullet_files(cfg.changelog_dir):
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

        bullet_r = Bullet.from_string(cfg, line, cfg.changelog_dir)
        if isinstance(bullet_r, Err):
            err: Err[Any, ErisError] = Err(
                "There was a problem parsing one of the changelog"
                f" bullets:\n\n{line!r}"
            )
            return err.chain(bullet_r)

        bullet = bullet_r.ok()
        kind_to_bullets_map[bullet.kind].append(bullet)

    return Ok(kind_to_bullets_map)


def iter_bullet_files(changelog_dir: PathLike) -> Iterator[Path]:
    """TODO"""
    changelog_dir = Path(changelog_dir)

    for path in changelog_dir.glob("*.md"):
        if path.stem != "README":
            yield path


main = clack.main_factory(
    PROJECT_NAME, runners=[run_build, run_info, run_new], parser=clack_parser
)
