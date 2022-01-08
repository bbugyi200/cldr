"""Contains the clack runner functions."""

from __future__ import annotations

import datetime as dt
import itertools as it
import json
from operator import attrgetter
from pathlib import Path
import subprocess as sp
import sys
from typing import Any, Dict, Optional

from eris import Err
from logrus import Logger
import proctor

from ._config import BuildConfig, BumpConfig, InfoConfig, NewConfig
from ._constants import KIND_TO_SECTION_MAP, README_CONTENTS, UNRELEASED_BEGIN
from ._helpers import (
    get_branch,
    get_editor_cmd_list,
    get_user,
    get_version,
    iter_bullet_files,
    read_bullets_from_changelog_dir,
)


logger = Logger(__name__)


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


def run_bump(cfg: BumpConfig) -> int:
    """Clack runner for the 'bump' subcommand."""
    print(
        json.dumps(
            {
                k: str(v) if isinstance(v, Path) else v
                for (k, v) in cfg.dict().items()
            },
            sort_keys=True,
        )
    )
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
                dict(
                    kind=bullet.kind,
                    body=bullet.body,
                    tags=[tag.tag for tag in bullet.tags],
                )
            )
    else:
        logger.warning("No bullet files found.")

    data["config"] = {
        k: str(v) if isinstance(v, Path) else v
        for (k, v) in cfg.dict().items()
    }

    print(json.dumps(data, sort_keys=True))
    return 0
