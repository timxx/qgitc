# -*- coding: utf-8 -*-

from PySide6.QtWidgets import QCheckBox, QMessageBox

from qgitc.applicationbase import ApplicationBase


class NewVersionDialog(QMessageBox):

    def __init__(self, version, parent=None):
        super().__init__(parent)

        self._version = version

        self.setIcon(QMessageBox.Information)
        self.setWindowTitle(self.tr("New version available"))
        # TODO: for source version?
        newVersion = self.tr("A new version ({0}) was available.").format(version)
        instruct = self.tr("Run `{0}` for getting the latest version.").format(
            "pip install qgitc --upgrade")
        self.setText(newVersion + "\n" + instruct)

        cb = QCheckBox(self.tr("Ignore this version"), self)
        self.setCheckBox(cb)

        cb.toggled.connect(self._onCbIgnoreToggled)

    def _onCbIgnoreToggled(self, checked):
        ApplicationBase.instance().settings().setIgnoredVersion(self._version)
