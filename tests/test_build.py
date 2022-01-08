"""Tests for the 'build' cldr subcommand."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from pytest import mark, param
from syrupy.assertion import SnapshotAssertion as Snapshot

from cldr.__main__ import main as cldr_main


params = mark.parametrize


CONTENTS1 = """\
# ChangeLog

All notable changes to this project will be documented in this file.


## [Unreleased](https://github.com/bbugyi200/cldr/compare/0.9.9...HEAD)

This section's contents will just be overwritten by cldr anyway.

## [0.9.9](https://github.com/bbugyi200/cldr/compare/0.9.8...0.9.9) - 2021-08-08

### Fixed

* Fixed some bug.
"""

CONTENTS2 = """\
# ChangeLog

All notable changes to this project will be documented in this file.


## Unreleased
"""


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
    config_file: Path,
    contents: str,
    bullet: str,
    ec: int,
) -> None:
    """Test the 'build' cldr subcommand"""
    changelog = changelog_dir.parent / "CHANGELOG.md"
    changelog.write_text(contents)

    bullet_file = changelog_dir / "user@branch.md"
    bullet_file.write_text(bullet + "\n")

    exit_code = cldr_main(
        [
            "",
            "--config",
            str(config_file),
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
