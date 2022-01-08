"""Contains the Bullet class definition."""

from __future__ import annotations

from pathlib import Path
import re
from typing import List, Type, TypeVar, cast

from eris import ErisError, Err, Ok, Result
from pydantic.dataclasses import dataclass
from typist import PathLike, literal_to_list

from ._config import Config
from ._constants import BULLET_EXPLANATION, KIND_TO_SECTION_MAP, Kind
from ._tags import TAG_TYPES, Tag


Bullet_T = TypeVar("Bullet_T", bound="Bullet")


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
        cls: Type["Bullet_T"],
        cfg: Config,
        line: str,
        changelog_dir: PathLike = "changelog",
    ) -> Result["Bullet_T", ErisError]:
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
            result = tag.transform_bullet(self, result).unwrap()

        result += "\n"
        return result
