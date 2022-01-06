"""Contains the clack runner functions."""

from __future__ import annotations

import clack
from logrus import Logger

from ._config import clack_parser
from ._constants import PROJECT_NAME
from ._runners import run_build, run_info, run_new


logger = Logger(__name__)


main = clack.main_factory(
    PROJECT_NAME, runners=[run_build, run_info, run_new], parser=clack_parser
)
