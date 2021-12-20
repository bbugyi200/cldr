# cldr

**ChangeLog Driven Releases (CLDR)...**

project status badges:

[![CI Workflow](https://github.com/bbugyi200/cldr/actions/workflows/ci.yml/badge.svg)](https://github.com/bbugyi200/cldr/actions/workflows/ci.yml)
[![Coverage](https://codecov.io/gh/bbugyi200/cldr/branch/master/graph/badge.svg)](https://codecov.io/gh/bbugyi200/cldr)
[![Documentation Status](https://readthedocs.org/projects/cldr/badge/?version=latest)](https://cldr.readthedocs.io/en/latest/?badge=latest)
[![Package Health](https://snyk.io/advisor/python/cldr/badge.svg)](https://snyk.io/advisor/python/cldr)

version badges:

[![Project Version](https://img.shields.io/pypi/v/cldr)](https://pypi.org/project/cldr/)
[![Python Versions](https://img.shields.io/pypi/pyversions/cldr)](https://pypi.org/project/cldr/)
[![Cookiecutter: cc-python](https://img.shields.io/static/v1?label=cc-python&message=2021.12.20&color=d4aa00&logo=cookiecutter&logoColor=d4aa00)](https://github.com/bbugyi200/cc-python)
[![Docker: bbugyi/python](https://img.shields.io/static/v1?label=bbugyi%20%2F%20python&message=2021.12.20&color=8ec4ad&logo=docker&logoColor=8ec4ad)](https://github.com/bbugyi200/docker-python)


## Installation 🗹

### Using `pipx` to Install (preferred)

This package _could_ be installed using pip like any other Python package (in
fact, see the section below this one for instructions on how to do just that).
Given that we only need this package's entry points, however, we recommend that
[pipx][11] be used instead:

```shell
# install and setup pipx
python3 -m pip install --user pipx
python3 -m pipx ensurepath

# install cldr
pipx install cldr
```

### Using `pip` to Install

To install `cldr` using [pip][9], run the following
commands in your terminal:

``` shell
python3 -m pip install --user cldr  # install cldr
```

If you don't have pip installed, this [Python installation guide][10] can guide
you through the process.


## Useful Links 🔗

* [API Reference][3]: A developer's reference of the API exposed by this
  project.
* [cc-python][4]: The [cookiecutter][5] that was used to generate this project.
  Changes made to this cookiecutter are periodically synced with this project
  using [cruft][12].
* [CHANGELOG.md][2]: We use this file to document all notable changes made to
  this project.
* [CONTRIBUTING.md][7]: This document contains guidelines for developers
  interested in contributing to this project.
* [Create a New Issue][13]: Create a new GitHub issue for this project.
* [Documentation][1]: This project's full documentation.


[1]: https://cldr.readthedocs.io/en/latest
[2]: https://github.com/bbugyi200/cldr/blob/master/CHANGELOG.md
[3]: https://cldr.readthedocs.io/en/latest/modules.html
[4]: https://github.com/bbugyi200/cc-python
[5]: https://github.com/cookiecutter/cookiecutter
[6]: https://docs.readthedocs.io/en/stable/
[7]: https://github.com/bbugyi200/cldr/blob/master/CONTRIBUTING.md
[8]: https://github.com/bbugyi200/cldr
[9]: https://pip.pypa.io
[10]: http://docs.python-guide.org/en/latest/starting/installation/
[11]: https://github.com/pypa/pipx
[12]: https://github.com/cruft/cruft
[13]: https://github.com/bbugyi200/cldr/issues/new/choose
