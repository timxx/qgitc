# -*- coding: utf-8 -*-

import re


diff_re = re.compile(b"^diff --(git a/(.*) b/(.*)|cc (.*))")
diff_begin_re = re.compile(r"^@{2,}( (\+|\-)[0-9]+(,[0-9]+)?)+ @{2,}")
diff_begin_bre = re.compile(rb"^@{2,}( (\+|\-)[0-9]+(,[0-9]+)?)+ @{2,}")

submodule_re = re.compile(
    rb"^Submodule (.*) [a-z0-9]{7,}\.{2,3}[a-z0-9]{7,}.*$")

diff_encoding = "utf-8"


class DiffType:
    File = 0
    FileInfo = 1
    Diff = 2
