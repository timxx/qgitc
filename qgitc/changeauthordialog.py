# -*- coding: utf-8 -*-

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
)

from qgitc.gitutils import Git

__all__ = ["ChangeAuthorDialog"]


class ChangeAuthorDialog(QDialog):

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle(self.tr("Change Commit Author"))

        layout = QVBoxLayout(self)

        formLayout = QFormLayout()

        self._leName = QLineEdit(self)
        formLayout.addRow(self.tr("&Name:"), self._leName)

        self._leEmail = QLineEdit(self)
        formLayout.addRow(self.tr("&Email:"), self._leEmail)

        layout.addLayout(formLayout)

        # Add info label
        infoLabel = QLabel(self.tr(
            "Note: This will create a new commit with the updated author information.\n"
            "If this is not the most recent commit, history will be rewritten."), self)
        infoLabel.setWordWrap(True)
        infoLabel.setStyleSheet("QLabel { color: #666; font-size: 9pt; }")
        layout.addWidget(infoLabel)

        buttonBox = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        layout.addWidget(buttonBox)

        buttonBox.accepted.connect(self.accept)
        buttonBox.rejected.connect(self.reject)

        # Pre-fill with current user info
        self._leName.setText(Git.userName())
        self._leEmail.setText(Git.userEmail())
        self._leName.selectAll()
        self._leName.setFocus()

    @property
    def authorName(self):
        return self._leName.text().strip()

    @property
    def authorEmail(self):
        return self._leEmail.text().strip()
