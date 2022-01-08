"""Miscellaneous tests for cldr."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Sequence

from _pytest.capture import CaptureFixture
from pytest import mark
from syrupy.assertion import SnapshotAssertion as Snapshot

from cldr.__main__ import main as cldr_main


params = mark.parametrize


@params(
    "bullets,args",
    [
        ([], ["add", "-t", "123,!5", "--body", "Added some feature."]),
        (
            ["* add(123,!5): Added some feature."],
            ["fix", "--body", "Fixed some bug."],
        ),
        (
            ["* add(123,!5): Added some feature.", "* fix: Fixed some bug."],
            ["rm", "-t", "bc", "--body", "Removed some important feature."],
        ),
    ],
)
def test_new(
    snapshot: Snapshot,
    changelog_dir: Path,
    bullets: Iterable[str],
    args: Sequence[str],
) -> None:
    """Test the 'new' cldr subcommand"""
    bullet_fname = "temp_bullet_file"
    bullet_file_path = changelog_dir / f"{bullet_fname}.md"
    if bullets:
        bullet_file_path.write_text(
            "\n".join(bullet for bullet in bullets) + "\n"
        )

    cmd_list = ["", "--changelog-dir", str(changelog_dir)]
    cmd_list.append("new")
    cmd_list.extend(["--no-commit", "--bullet-file-name", bullet_fname])
    cmd_list.extend(args)
    cldr_main(cmd_list)

    assert bullet_file_path.read_text() == snapshot


def test_info(
    snapshot: Snapshot, capsys: CaptureFixture, changelog_dir: Path
) -> None:
    """Test the 'info' cldr subcommand"""
    bullet_fname = "temp_bullet_file"
    bullet_file_path = changelog_dir / f"{bullet_fname}.md"
    bullet_file_path.write_text(
        "* add(123,!5): Add some new feature.\n"
        "* rm(!6,bc): Remove some old feature.\n"
    )

    cldr_main(["", "--changelog-dir", str(changelog_dir), "info"])
    captured = capsys.readouterr()
    assert captured.out == snapshot
