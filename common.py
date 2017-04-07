# -*- coding: utf-8 -*-

import subprocess
import os
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


def getRepoDirectory(directory):
    """simply check whether directory is git repository,
       if it is, return the top directory path
    """
    oldDir = os.getcwd()
    try:
        os.chdir(directory)
    except FileNotFoundError:
        return None
    except NotADirectoryError:
        return None

    process = subprocess.Popen(["git", "rev-parse", "--show-toplevel"],
                               stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE)

    realDir = process.communicate()[0]

    os.chdir(oldDir)

    if process.returncode is not 0:
        return None

    return realDir.decode("utf-8").replace("\n", "")


def getCommitSummary(sha1):
    fmt = "%h%x01%s%x01%ad%x01%an%x01%ae"
    args = ["git", "show", "-s",
            "--pretty=format:{0}".format(fmt),
            "--date=short",
            sha1]

    process = subprocess.Popen(args,
                               stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE)
    data = process.communicate()[0]

    if process.returncode is not 0:
        return None

    if not data:
        return None

    parts = data.decode("utf-8").split("\x01")

    return {"sha1": parts[0],
            "subject": parts[1],
            "date": parts[2],
            "author": parts[3],
            "email": parts[4]}


def getCommitFiles(sha1):
    args = ["git", "diff-tree", "--no-commit-id",
            "--name-only", "--root", "-r", "-z",
            "--submodule", sha1]
    process = subprocess.Popen(args,
                               stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE)
    data = process.communicate()[0]
    if process.returncode is not 0:
        return None

    return data.decode("utf-8")


def getCommitRawDiff(sha1, filePath=None, gitArgs=None):
    args = ["git", "diff-tree",
            "-r", "-p", "--textconv",
            "--submodule", "-C",
            "--cc", "--no-commit-id",
            "-U3", "--root",
            sha1]
    if gitArgs:
        args.extend(gitArgs)

    if filePath:
        args.append(filePath)

    process = subprocess.Popen(args,
                               stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE)
    data = process.communicate()[0]
    if process.returncode is not 0:
        return None

    return data


def htmlEscape(text):
    return "".join(html_escape_table.get(c, c) for c in text)


def externalDiff(commit, path=None):
    args = ["git", "difftool",
            "{0}^..{0}".format(commit.sha1)]
    if path:
        args.append(path)

    prcoess = subprocess.Popen(args,
                               stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE)


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


def normalizeRegex(string):
    specal_chars = "\\^$.*|?+()[]{}"
    new_string = "".join(
        "\\" + c if c in specal_chars else c for c in string)
    return new_string
