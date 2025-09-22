# -*- coding: utf-8 -*-

from qgitc.applicationbase import ApplicationBase
from qgitc.common import Commit
from qgitc.patchviewer import SummaryTextLine
from qgitc.textline import Link, LinkTextLine, TextLine
from qgitc.textviewer import TextViewer


class CommitDetailPanel(TextViewer):

    def __init__(self, parent=None):
        super().__init__(parent)

        settings = ApplicationBase.instance().settings()
        settings.diffViewFontChanged.connect(self.delayUpdateSettings)

    def showCommit(self, commit: Commit, previous: str = None):
        super().clear()

        text = self.tr("Commit: ") + commit.sha1
        textLine = LinkTextLine(text, self._font, Link.Sha1)
        self.appendTextLine(textLine)

        text = self.tr("Author: ") + commit.author + " " + commit.authorDate
        textLine = LinkTextLine(text, self._font, Link.Email)
        self.appendTextLine(textLine)

        text = self.tr("Committer: ") + commit.committer + \
            " " + commit.committerDate
        textLine = LinkTextLine(text, self._font, Link.Email)
        self.appendTextLine(textLine)

        if previous:
            text = self.tr("Previous: ") + previous
            textLine = LinkTextLine(text, self._font, Link.Sha1)
            self.appendTextLine(textLine)

        if commit.comments:
            self.appendLine("")
            for line in commit.comments.splitlines():
                textLine = SummaryTextLine(line, self._font, self._option, 0)
                self.appendTextLine(textLine)

    def clear(self):
        super().clear()

    def reloadSettings(self):
        super().reloadSettings()
        self.updateFont(ApplicationBase.instance().settings().diffViewFont())

    def _reloadTextLine(self, textLine: TextLine):
        super()._reloadTextLine(textLine)
        textLine.setFont(self._font)
