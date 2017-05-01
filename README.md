# gitc

A file conflict viewer for git

## Features

* Two branches view for easy comparing a conflict commit base on the file.
* Visualize white spaces and carriage return for easy diff compare.
* Syntax highlight for diff contents.
* Filter logs by file path or commit pattern.
* Copy commit summary as HTML format for pasting.
* Custom pattern for creating links.

## Build & Run

- Using source directly

You should run build for the first time: *python setup.py build*
Now run **gitc** which in the source directory.

- Using binary

Run *python setup.py build_exe*, the binary will be generated in the **build** directory.
NOTE: Run *python setup.py build* before *build_exe*


## TODO

* Auto collect git conflict files for merging.

