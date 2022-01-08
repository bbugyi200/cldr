"""Contains the main() function constructed by clack.

This function is used by setuptools as the main entry point for this program.
"""

from __future__ import annotations

import clack

from ._config import clack_parser
from ._constants import PROJECT_NAME
from ._runners import ALL_RUNNERS


main = clack.main_factory(
    PROJECT_NAME, runners=ALL_RUNNERS, parser=clack_parser
)
if __name__ == "__main__":
    main()
