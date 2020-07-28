# QGitc

[![PyPI version](https://img.shields.io/pypi/v/qgitc.svg)](https://pypi.org/project/qgitc)
[![Python version](https://img.shields.io/pypi/pyversions/qgitc.svg)](https://pypi.org/project/qgitc)
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
- [x] File blame support


## Requirements

- PySide2 >= 5.2.0
- git (command line)


## Build & Run

- Using source directly
  - Run **qgitc.py** under project root directory.
  - NOTE: If you want translation other than English or updated the UI files, run **python setup.py build** for the first time.

- Build from source
  - Run *pip install .* under project root directory to install qgitc, and then run *qgitc* command.

- Install from pypi
  - pip install qgitc


## Shell Integration (Windows only)

``` sh
qgitc shell register
# to unregister, run:
qgitc shell unregister

# to use the source directly:
python qgitc.py shell register
```
