# gitc

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

## Build & Run

- Using source directly
  - Run **gitc** which in the source directory directly.
  - NOTE: If you want translation other than English or updated the UI files, run *python setup.py build* for the first time.

- Using binary
  - Run *python setup.py build_exe*, the binary will be generated in the **build** directory.
  - NOTE: Run *python setup.py build* before *build_exe*


