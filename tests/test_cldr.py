"""Tests the cldr project's CLI."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Iterable, Sequence

from _pytest.capture import CaptureFixture
from pytest import fixture, mark, param
from syrupy.assertion import SnapshotAssertion as Snapshot

from cldr import cli


params = mark.parametrize

CONTENTS1 = """\
# ChangeLog

All notable changes to this project will be documented in this file.


## [Unreleased](https://bbgithub.dev.bloomberg.com/ComplianceSRE/tools/compare/0.9.9...HEAD)

This section's contents will just be overwritten by cldr anyway.

## [0.9.9](https://bbgithub.dev.bloomberg.com/ComplianceSRE/tools/compare/0.9.8...0.9.9) - 2021-08-08

### Fixed

* Fixed some bug.
"""

CONTENTS2 = """\
# ChangeLog

All notable changes to this project will be documented in this file.


## Unreleased
"""


@fixture(name="changelog_dir")
def changelog_dir_fixture(tmp_path: Path) -> Path:
    """TODO"""
    result = tmp_path / "changelog"
    result.mkdir()
    return result


@params(
    "contents",
    [param(CONTENTS1, id="contents1"), param(CONTENTS2, id="contents2")],
)
@params(
    "bullet,ec",
    [
        param("* add: Adding some feature.", 0, id="add-some-feature"),
        param(
            "- rm(foo-103): Removing some feature.",
            0,
            id="remove-some-feature",
        ),
        param(
            "* chg (foo-103,!123,python-libs#456): Changing some feature.",
            0,
            id="change-some-feature",
        ),
        param("* addd: Added typo...", 1, id="add-typo"),
        param("* add(ak7k2): Bad jira issue...", 1, id="bad-jira-issue"),
        param("* No bullet kind...", 1, id="no-bullet-kind"),
        param("No bullet...", 1, id="no-bullet"),
    ],
)
def test_build(
    snapshot: Snapshot,
    changelog_dir: Path,
    contents: str,
    bullet: str,
    ec: int,
) -> None:
    """TODO"""
    changelog = changelog_dir.parent / "CHANGELOG.md"
    changelog.write_text(contents)

    bullet_file = changelog_dir / "user@branch.md"
    bullet_file.write_text(bullet + "\n")

    exit_code = cli.main(
        [
            "",
            "--changelog-dir",
            str(changelog_dir),
            "build",
            "-V",
            "1.0.0",
            "--changelog",
            str(changelog),
            "-i",
        ]
    )

    # Verify that the exit code is as expected.
    assert exit_code == ec

    # Verify that the CHANGELOG.md file's contents match our expectations.
    today = dt.date.today()
    changelog_contents = changelog.read_text().replace(
        today.strftime("%Y-%m-%d"), "YYYY-MM-DD"
    )
    assert ec != 0 or changelog_contents == snapshot


@params(
    "bullets,args",
    [
        ([], ["add", "-t", "123,!5", "Added some feature."]),
        (["* add(123,!5): Added some feature."], ["fix", "Fixed some bug."]),
        (
            ["* add(123,!5): Added some feature.", "* fix: Fixed some bug."],
            ["rm", "-t", "bc", "Removed some important feature."],
        ),
    ],
)
def test_kind(
    snapshot: Snapshot,
    changelog_dir: Path,
    bullets: Iterable[str],
    args: Sequence[str],
) -> None:
    """TODO"""
    bullet_fname = "temp_bullet_file"
    bullet_file_path = changelog_dir / f"{bullet_fname}.md"
    if bullets:
        bullet_file_path.write_text(
            "\n".join(bullet for bullet in bullets) + "\n"
        )

    cmd_list = ["", "--changelog-dir", str(changelog_dir)]
    cmd_list.extend(args)
    cmd_list.extend(["--no-commit", "--bullet-file-name", bullet_fname])
    cli.main(cmd_list)

    assert bullet_file_path.read_text() == snapshot


def test_info(
    snapshot: Snapshot, capsys: CaptureFixture, changelog_dir: Path
) -> None:
    """TODO"""
    bullet_fname = "temp_bullet_file"
    bullet_file_path = changelog_dir / f"{bullet_fname}.md"
    bullet_file_path.write_text(
        "* add(123,!5): Add some new feature.\n"
        "* rm(!6,bc): Remove some old feature.\n"
    )

    cli.main(["", "--changelog-dir", str(changelog_dir), "info"])
    captured = capsys.readouterr()
    assert captured.out == snapshot
