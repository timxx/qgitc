# -*- coding: utf-8 -*-

from PySide6.QtCore import QSize
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QVBoxLayout

from qgitc.commitactionwidget import CommitActionWidget


class CommitActionEditDialog(QDialog):

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle(self.tr("Edit Commit Actions"))

        layout = QVBoxLayout(self)

        self.widget = CommitActionWidget(self)
        layout.addWidget(self.widget)

        buttonBox = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        layout.addWidget(buttonBox)

        buttonBox.accepted.connect(self.accept)
        buttonBox.rejected.connect(self.reject)

    def sizeHint(self):
        return QSize(600, 300)
