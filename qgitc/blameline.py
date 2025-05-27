# -*- coding: utf-8 -*-


class BlameLine:

    def __init__(self):
        self.sha1: str = None
        self.oldLineNo = 0
        self.newLineNo = 0
        self.groupLines = 0

        self.author: str = None
        self.authorMail: str = None
        self.authorTime: str = None

        self.committer: str = None
        self.committerMail: str = None
        self.committerTime: str = None

        self.previous: str = None
        self.prevFileName: str = None
        self.filename: str = None
        self.text: str = None
