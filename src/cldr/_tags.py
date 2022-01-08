"""Contains the Tag Protocol and Tag Implementations."""

from __future__ import annotations

from abc import ABC
from pathlib import Path
import re
from typing import (
    TYPE_CHECKING,
    List,
    Optional,
    Protocol,
    Type,
    runtime_checkable,
)

from eris import ErisError, Err, Ok, Result
import proctor

from ._helpers import iter_bullet_files


if TYPE_CHECKING:
    from ._bullet import Bullet


# The TAG_TYPES list is populated later by the `register_tag` decorator.
TAG_TYPES: List[Type["Tag"]] = []


@runtime_checkable
class Tag(Protocol):
    """TODO"""

    regexp: str
    tag: str

    def __init__(self, tag: str) -> None:
        pass

    def transform_bullet(
        self, bullet: "Bullet", bullet_line: str
    ) -> Result[str, ErisError]:
        """TODO"""


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
    def transform_bullet(
        bullet: Bullet, bullet_line: str
    ) -> Result[str, ErisError]:
        """TODO"""
        from ._constants import Kind

        allowed_kinds: List[Kind] = ["chg", "rm"]
        if bullet.kind not in allowed_kinds:
            raise RuntimeError(
                'Bullets of this kind cannot be marked as a "breaking change"'
                f" (i.e. {bullet.kind!r} not in {allowed_kinds!r}):"
                f" {bullet.line!r}"
            )

        return Ok("* *BREAKING CHANGE*: " + bullet_line[2:])


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

    def transform_bullet(
        self, bullet: Bullet, bullet_line: str
    ) -> Result[str, ErisError]:
        """TODO"""
        result = _github_tag_transform_bullet(
            bullet.cfg.github_repo, "#", "issues", self.tag, bullet_line
        )
        return Ok(result)


@register_tag
class GithubPullRequest(TagMixin):
    """TODO"""

    regexp = _github_tag_regexp("!")

    def transform_bullet(
        self, bullet: Bullet, bullet_line: str
    ) -> Result[str, ErisError]:
        """TODO"""
        result = _github_tag_transform_bullet(
            bullet.cfg.github_repo,
            "!",
            "pull",
            self.tag,
            bullet_line,
            prefix="PR:",
        )
        return Ok(result)


@register_tag
class JiraIssue(TagMixin):
    """TODO"""

    regexp = r"(?:[A-Za-z]+-)?[1-9][0-9]*"

    def transform_bullet(
        self, bullet: Bullet, bullet_line: str
    ) -> Result[str, ErisError]:
        """TODO"""
        cfg = bullet.cfg
        tag = self.tag

        if cfg.jira_base_url is None:
            return Err(
                "The 'jira_base_url' configuration option MUST be set in order"
                f" to use the {self.__class__.__name__} changelog bullet tag."
            )

        if tag[0].isdigit():
            if cfg.jira_org is None:
                return Err(
                    "The following line appears to reference a jira issue"
                    f" ({tag}) but the 'jira_org' option is not set in"
                    f" this project's pyproject.toml file: {tag!r}"
                )

            tag = f"{cfg.jira_org}-{tag}"

        tag = tag.upper()
        jira_link = f"[{tag}]({cfg.jira_base_url}/browse/{tag})"

        result = _add_tag_to_paren_group(bullet_line, jira_link)
        return Ok(result)


@register_tag
class RelativeCommitTag(TagMixin):
    """TODO"""

    regexp = r"c(?:0|[1-9][0-9]*)"

    def transform_bullet(
        self, bullet: Bullet, bullet_line: str
    ) -> Result[str, ErisError]:
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

        result = _add_tag_to_paren_group(bullet_line, commit_link)
        return Ok(result)


def _add_tag_to_paren_group(bullet_line: str, tag: str) -> str:
    if m := re.match(r"^.*\((?P<tags>.*)\)$", bullet_line):
        tags = m.group("tags")
        return bullet_line.replace(f"({tags})", f"({tags + ', ' + tag})")
    else:
        result = bullet_line + f" ({tag})"
        return result
