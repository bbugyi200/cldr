"""Utility functions."""

from __future__ import annotations

from collections import defaultdict
from functools import lru_cache
import itertools as it
from operator import attrgetter
import os
from pathlib import Path
import re
from typing import TYPE_CHECKING, Any, Dict, Iterable, Iterator

from clack import ConfigFile
from eris import ErisError, Err, Ok, Result
from logrus import Logger
import proctor
from typist import PathLike


if TYPE_CHECKING:
    from ._bullet import Bullet
    from ._config import Config
    from ._constants import Kind


logger = Logger(__name__)


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


def read_bullets_from_changelog_dir(
    cfg: Config,
) -> Result[dict[Kind, list[Bullet]], ErisError]:
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
    from ._bullet import Bullet

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


def get_editor_cmd_list(*, line: int, column: int) -> list[str]:
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


def get_info(cfg: Config) -> dict[str, Any]:
    """Returns a dict containing information on cldr's current state."""
    result: Dict[str, Any] = {}

    result["bullets"] = []
    if list(iter_bullet_files(cfg.changelog_dir)):
        kind_to_bullets_map = read_bullets_from_changelog_dir(cfg).unwrap()
        bullets = it.chain.from_iterable(kind_to_bullets_map.values())

        for bullet in sorted(bullets, key=attrgetter("kind")):
            result["bullets"].append(
                dict(
                    kind=bullet.kind,
                    body=bullet.body,
                    tags=[tag.tag for tag in bullet.tags],
                )
            )
    else:
        logger.warning("No bullet files found.")

    result["config"] = {
        k: str(v) if isinstance(v, (ConfigFile, Path)) else v
        for (k, v) in cfg.dict().items()
    }

    return result
