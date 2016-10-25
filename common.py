# -*- coding: utf-8 -*-


short_log_fmt = "%H%x01%B%x01%an <%ae>%x01%ad%x01%cn <%ce>%x01%cd%x01%P"


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
