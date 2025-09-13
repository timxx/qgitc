# -*- coding: utf-8 -*-

from typing import List

from PySide6.QtCore import QStringListModel, Qt, QTimer, Signal
from PySide6.QtWidgets import QCompleter, QLineEdit


class FuzzyStringListModel(QStringListModel):
    """A string list model that supports fuzzy matching"""

    def __init__(self, strings: List[str] = None, parent=None):
        super().__init__(parent)
        self._allStrings = strings or []
        self.setStringList(self._allStrings)

    def setAllStrings(self, strings: List[str]):
        """Set the complete list of strings"""
        self._allStrings = strings or []
        self.setStringList(self._allStrings)

    def filterStrings(self, filterText: str) -> List[str]:
        """Filter strings using fuzzy matching"""
        if not filterText:
            return self._allStrings

        filterText = filterText.lower()
        matches = []

        for s in self._allStrings:
            # Check if all characters of filterText appear in order in the string
            if self._fuzzyMatch(s.lower(), filterText):
                matches.append(s)

        # Sort by relevance (exact prefix match first, then fuzzy matches)
        matches.sort(key=lambda x: (
            not x.lower().startswith(filterText),  # Exact prefix first
            not filterText in x.lower(),           # Contains substring second
            len(x),                                # Shorter strings first
            x.lower()                             # Alphabetical order
        ))

        return matches

    def _fuzzyMatch(self, text: str, pattern: str) -> bool:
        """Check if pattern characters appear in order in text"""
        if not pattern:
            return True
        if not text:
            return False

        i = 0  # Index for pattern
        for char in text:
            if i < len(pattern) and char == pattern[i]:
                i += 1

        return i == len(pattern)


class RepoPathInput(QLineEdit):
    """A QLineEdit with fuzzy completion for repository paths"""

    repositorySelected = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)

        self._recentRepos: List[str] = []
        self._completer = None
        self._fuzzyModel = None
        self._filterTimer = QTimer()
        self._filterTimer.setSingleShot(True)
        self._filterTimer.timeout.connect(self._updateCompletion)

        self.textEdited.connect(self._onTextChanged)
        self._setupCompleter()

    def _setupCompleter(self):
        """Setup the completer with fuzzy matching"""
        self._fuzzyModel = FuzzyStringListModel(self._recentRepos)
        self._completer = QCompleter(self._fuzzyModel, self)
        self._completer.setFilterMode(Qt.MatchContains)
        self._completer.setCompletionMode(QCompleter.PopupCompletion)
        self._completer.setCaseSensitivity(Qt.CaseInsensitive)
        self._completer.setModelSorting(QCompleter.UnsortedModel)
        self._completer.activated.connect(self._onCompletionActivated)

        self.setCompleter(self._completer)

    def setRecentRepositories(self, repos: List[str]):
        """Set the list of recent repositories"""
        self._recentRepos = repos
        if self._fuzzyModel:
            self._fuzzyModel.setAllStrings(self._recentRepos)

    def _onTextChanged(self, text: str):
        """Handle text changes to trigger fuzzy filtering"""
        # Delay the filtering to avoid too frequent updates while typing
        self._filterTimer.start(150)

    def _updateCompletion(self):
        """Update the completion popup with fuzzy matches"""
        if not self._fuzzyModel:
            return

        currentText = self.text().strip()
        if not currentText:
            # Show all recent repos when text is empty
            matches = self._recentRepos
        else:
            # Show fuzzy matches
            matches = self._fuzzyModel.filterStrings(currentText)

        # use our filtered list
        self._completer.setCompletionPrefix("")
        # Update the model with filtered results
        self._fuzzyModel.setStringList(matches)

        # Show popup if we have matches and the widget has focus
        if matches and self.hasFocus():
            self._completer.complete()

    def _onCompletionActivated(self, text: str):
        """Handle completion selection"""
        self.setText(text)
        self.repositorySelected.emit(text)

    def showPopup(self):
        """Show the completion popup"""
        if self._completer:
            self._updateCompletion()

    def keyPressEvent(self, event):
        """Handle key press events"""
        if event.key() == Qt.Key_Down and not self._completer.popup().isVisible():
            # Show completion popup when Down arrow is pressed
            self.showPopup()
        else:
            super().keyPressEvent(event)

    def focusInEvent(self, event):
        """Handle focus in event"""
        super().focusInEvent(event)
        # Show all repositories when focused if text is empty
        if event.reason() == Qt.MouseFocusReason and not self.text().strip():
            QTimer.singleShot(100, self._updateCompletion)
