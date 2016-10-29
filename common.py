# -*- coding: utf-8 -*-

import subprocess
import os


log_fmt = "%H%x01%B%x01%an <%ae>%x01%ai%x01%cn <%ce>%x01%ci%x01%P"


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
        self.parents = parts[6].split(" ")


def getRepoDirectory(directory):
    """simply check whether directory is git repository,
       if it is, return the top directory path
    """
    oldDir = os.getcwd()
    try:
        os.chdir(directory)
    except FileNotFoundError:
        return None

    process = subprocess.Popen(["git", "rev-parse", "--show-toplevel"],
                               stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE)

    realDir = process.communicate()[0]

    os.chdir(oldDir)

    if process.returncode is not 0:
        return None

    return realDir.decode("utf-8").replace("\n", "")
