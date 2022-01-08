"""Contains the clack.MainType function."""

from __future__ import annotations

import clack

from ._config import clack_parser
from ._constants import PROJECT_NAME
from ._runners import run_build, run_info, run_new


main = clack.main_factory(
    PROJECT_NAME, runners=[run_build, run_info, run_new], parser=clack_parser
)
if __name__ == "__main__":
    main()
