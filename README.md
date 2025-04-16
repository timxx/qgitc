# QGitc

[![Build Status](https://github.com/timxx/qgitc/actions/workflows/main.yml/badge.svg)](https://github.com/timxx/qgitc/actions)
[![PyPI version](https://img.shields.io/pypi/v/qgitc.svg)](https://pypi.org/project/qgitc)
[![Python version](https://img.shields.io/pypi/pyversions/qgitc.svg)](https://pypi.org/project/qgitc)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)

A file conflict viewer for git

## Screenshots

### Main Window
![Main Window](./screenshots/main.png)

### Blame Window
![Blame](./screenshots/blame.png)

### Commit Window
![Commit](./screenshots/commit.png)

### AI Assistant
![AI Assistant](./screenshots/assistant.png)

### Merge Tool
![Merge Tool](./screenshots/resolve.png)

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
- [x] AI intergrated
- [x] Composite mode
- [x] AI-based commits


## Requirements

- PySide6
- git (command line)
- chardet
- pywin32
  - Optional for Windows if you want record the conflict log easily
- pywpsrpc
  - Optional for Linux if you want record the conflict log easily
- openpyxl
  - Optional if no pywin32/ pywpsrpc is available


## Build & Run

- Using source directly
  - Run **python setup.py build** to build the project
  - Run **qgitc.py** under project root directory.

- Build from source
  - Run *pip install .* under project root directory to install qgitc, and then run *qgitc* command.

- Install from pypi
  - pip install qgitc


## Shell Integration

``` sh
qgitc shell register
# to unregister, run:
qgitc shell unregister

# to use the source directly:
python qgitc.py shell register

# for Linux user
# if your file manager isn't the default one comes with desktop
# say your desktop is Ubuntu, but use thunar as default one
# use --file-manager to specify reigster for
qgitch shell register --file-manager=thunar
```
