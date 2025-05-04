# -*- coding: utf-8 -*-


class FindFlags:

    Backward = 0x01
    CaseSenitively = 0x02
    WholeWords = 0x04
    UseRegExp = 0x08


class FindPart:

    BeforeCurPage = 0
    CurrentPage = 1
    AfterCurPage = 2
    All = 3
