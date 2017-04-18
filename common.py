# -*- coding: utf-8 -*-

import cProfile
import pstats
import io


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
        self.commiterDate = ""
        self.parents = []

    def __str__(self):
        return "Commit: {0}\n"  \
               "Author: {1} {2}\n"  \
               "Commiter: {3} {4}\n\n"    \
               "{5}".format(self.sha1,
                            self.author, self.authorDate,
                            self.commiter, self.commiterDate,
                            self.comments)

    def parseRawString(self, string):
        parts = string.split("\x01")
        # assume everything's fine
        self.sha1 = parts[0]
        self.comments = parts[1].strip("\n")
        self.author = parts[2]
        self.authorDate = parts[3]
        self.commiter = parts[4]
        self.commiterDate = parts[5]
        self.parents = [x for x in parts[6].split(" ") if x]


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

    Comments = 0
    Paths = 1
    Diffs = 2
    # for highlight only
    All = 0xff


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
