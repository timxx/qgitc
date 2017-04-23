# gitc
A file conflict viewer for git

It also can be a commit viewer if pass --log-mode/-l argument

**Features**

* Two branches view for easy comparing a conflict commit base on the file.
* Visualize white spaces and carriage return for easy diff compare.
* Syntax highlight for diff contents.
* Filter logs by file path or commit pattern.
* Copy commit summary as HTML format for pasting.
* Custom pattern for creating links.

**TODO**

1. Improve performance for finding commit, use ==--stdin== to avoid start git process many times e.t.c.
2. Auto collect git conflict files for merging.

