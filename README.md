# gitc

[![PyPI version](https://img.shields.io/pypi/v/gitc2.svg)](https://pypi.org/project/gitc2)
[![Python version](https://img.shields.io/pypi/pyversions/gitc2.svg)](https://pypi.org/project/gitc2)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)

A file conflict viewer for git

## Features

- [x] Two branches view for easy comparing a conflict commit base on the file.
- [x] Visualize white spaces and carriage return for easy diff compare.
- [x] Syntax highlight for diff contents.
- [x] Filter logs by file path or commit pattern.
- [x] Copy commit summary as HTML format for pasting.
- [x] Custom pattern for creating links.
- [x] Collect conflict files for merging.
- [x] Launch specify merge tool for specify file suffix.
- [x] Builtin image diff tool for easy finding the difference.
- [ ] Auto finding which commit cause conflicts.


## Requirements

- PySide2


## Build & Run

- Using source directly
  - Run **gitc.py** under project root directory.
  - NOTE: If you want translation other than English or updated the UI files, run **python setup.py build** for the first time.

- Build from source
  - Run *pip install .* under project root directory to install gitc, and then run *gitc* command.

- Install from pypi
  - pip install gitc2
