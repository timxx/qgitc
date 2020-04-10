# -*- coding: utf-8 -*-

import cProfile
import pstats
import io
import os
import sys


log_fmt = "%H%x01%B%x01%an <%ae>%x01%ai%x01%cn <%ce>%x01%ci%x01%P"
html_escape_table = {
    "&": "&amp;",
    '"': "&quot;",
    "'": "&apos;",
    ">": "&gt;",
    "<": "&lt;",
}


class Commit():

    def __init__(self):

        self.sha1 = ""
        self.comments = ""
        self.author = ""
        self.authorDate = ""
        self.committer = ""
        self.committerDate = ""
        self.parents = []
        self.children = None

    def __str__(self):
        return "Commit: {0}\n"  \
               "Author: {1} {2}\n"  \
               "Committer: {3} {4}\n\n"    \
               "{5}".format(self.sha1,
                            self.author, self.authorDate,
                            self.committer, self.committerDate,
                            self.comments)

    @classmethod
    def fromRawString(cls, string):
        commit = cls()

        parts = string.split("\x01")
        if len(parts) != 7:
            return commit

        commit.sha1 = parts[0]
        commit.comments = parts[1].strip("\n")
        commit.author = parts[2]
        commit.authorDate = parts[3]
        commit.committer = parts[4]
        commit.committerDate = parts[5]
        commit.parents = [x for x in parts[6].split(" ") if x]

        return commit


class MyProfile():

    def __init__(self):
        self.pr = cProfile.Profile()
        self.pr.enable()

    def __del__(self):
        self.pr.disable()
        s = io.StringIO()
        ps = pstats.Stats(self.pr, stream=s).sort_stats("cumulative")
        ps.print_stats()
        print(s.getvalue())


class FindField():

    AddOrDel = 0
    Changes = 1
    Comments = 2
    # for highlight only
    All = 0xff

    @staticmethod
    def isDiff(field):
        return field == FindField.AddOrDel or \
            field == FindField.Changes


class FindParameter():

    def __init__(self, range, pattern, field, flag):
        self.range = range
        self.pattern = pattern
        self.field = field
        self.flag = flag

    def __eq__(self, other):
        if not other:
            return False

        if self.field != other.field:
            return False
        if self.flag != other.flag:
            return False
        if self.pattern != other.pattern:
            return False
        # ignore range compare
        return True


# refer to find type combobox
FIND_EXTACT = 0
FIND_IGNORECASE = 1
FIND_REGEXP = 2

FIND_NOTFOUND = -1
FIND_CANCELED = -2


def htmlEscape(text):
    return "".join(html_escape_table.get(c, c) for c in text)


def decodeDiffData(data, preferEncoding="utf-8"):
    encodings = ["utf-8", "gb18030", "utf16"]
    if preferEncoding:
        encodings.remove(preferEncoding)
        encodings.insert(0, preferEncoding)
    line = None
    ok = False
    for e in encodings:
        try:
            line = data.decode(e)
            ok = True
            break
        except UnicodeDecodeError:
            pass

    if not ok:
        line = data.decode(preferEncoding, "replace")
        e = preferEncoding

    return line, e


def appDirPath():
    # qApp.applicationDirPath not works as expected
    path = os.path.realpath(__file__)
    return os.path.dirname(path)


def dataDirPath():
    return appDirPath() + "/data"