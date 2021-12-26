"""Contains constant variables."""

from __future__ import annotations

from typing import Dict, Final, Literal


Kind = Literal["add", "chg", "dep", "fix", "misc", "rm", "sec"]

KIND_TO_SECTION_MAP: Final[Dict[Kind, str]] = {
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
`* add(csre-103): Added the cldr.py script.`
"""

_CLDR_URL = "https://bbgithub.dev.bloomberg.com/ComplianceSRE/tools/blob/master/src/bloomberg/compliance/sre/tools/cldr.py"
UNRELEASED_BEGIN = f"""\
The unreleased section is unique in that we do not add content to it directly.
Instead, developers of this project add specially formatted bullets to files of
the form `{{0}}/USER@BRANCH.md`. Refer to the [{{0}}/README.md] file or the
[cldr] script (which consumes these bullets when a new version of this project
is released) for more information.

[{{0}}/README.md]: {{1}}/tree/master/{{0}}
[cldr]: {_CLDR_URL}
""".format

README_CONTENTS = f"""\
# Changelog Bullet Files

This directory should contain markdown files of the form `USER@BRANCH.md`. Each
of these files should contain one or more bullets of the form described in the
following paragraph. These bullets will be consumed by the [cldr] script when a
new version of this project is released.

{BULLET_EXPLANATION}

[cldr]: {_CLDR_URL}
"""

PROJECT_NAME: Final = "cldr"
