# -*- coding: utf-8 -*-


short_log_fmt = "%H%x01%s%x01%an%x01%ae%x01%ai%x01%P"


class Commit():

    def __init__(self,
                 sha1="",
                 subject="",
                 author="",
                 email="",
                 date="",
                 parents=[]):

        self.sha1 = sha1
        self.subject = subject
        self.author = author
        self.email = email
        self.date = date
        self.parents = parents

    def __str__(self):
        return "{0} [{1}] ({2} <{3}>) - {4}".format(self.sha1,
                                                    self.subject, self.author, self.email,
                                                    self.date)
