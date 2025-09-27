# -*- coding: utf-8 -*-

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox, QMessageBox

from qgitc.applicationbase import ApplicationBase


class NewVersionDialog(QMessageBox):

    def __init__(self, version, parent=None):
        super().__init__(parent)

        self._version = version

        self.setIcon(QMessageBox.Information)
        self.setWindowTitle(self.tr("New Version Available"))

        self.setTextInteractionFlags(
            self.textInteractionFlags() | Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)

        new_version_msg = self.tr(
            "A new version ({0}) of QGitc is available!").format(version)
        update_instruct = self.tr(
            "To update, run: pip install qgitc --upgrade")
        release_notes = self.tr(
            'See <a href="https://github.com/timxx/qgitc/releases/tag/v{0}">release notes</a> for details.').format(version)
        self.setText(f"{new_version_msg}\n\n{update_instruct}")
        self.setInformativeText(release_notes)

        cb = QCheckBox(self.tr("Ignore this version"), self)
        self.setCheckBox(cb)

        cb.toggled.connect(self._onCbIgnoreToggled)

    def _onCbIgnoreToggled(self, checked):
        ApplicationBase.instance().settings().setIgnoredVersion(self._version)
