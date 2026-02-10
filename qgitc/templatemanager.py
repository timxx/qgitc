# -*- coding: utf-8 -*-

import os
from typing import List, Tuple

from PySide6.QtCore import QObject, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from qgitc.commitmessageedit import CommitMessageEdit
from qgitc.common import logger
from qgitc.gitutils import Git


def templatesDir():
    """Get the directory for storing qgitc templates"""
    return os.path.expanduser("~/.qgitc/templates")


def loadTemplates(context: QObject) -> List[Tuple[str, str]]:
    # Get git global and local templates
    gitGlobalTemplate = Git.getConfigValue(
        "commit.template", isGlobal=True)
    gitLocalTemplate = Git.getConfigValue(
        "commit.template", isGlobal=False)

    dir = templatesDir()

    # Add template selection items
    templates = []
    gitTemplatePaths = set()

    # Add git global template if it exists
    if gitGlobalTemplate and os.path.exists(gitGlobalTemplate):
        name = context.tr("[Git Global] {}").format(
            os.path.basename(gitGlobalTemplate))
        templates.append((name, gitGlobalTemplate))
        gitTemplatePaths.add(os.path.realpath(gitGlobalTemplate))

    # Add git local template if it exists and differs from global
    if gitLocalTemplate != gitGlobalTemplate and os.path.exists(gitLocalTemplate):
        name = context.tr("[Git Local] {}").format(
            os.path.basename(gitLocalTemplate))
        templates.append((name, gitLocalTemplate))
        gitTemplatePaths.add(os.path.realpath(gitLocalTemplate))

    if os.path.isdir(dir):
        try:
            for item in os.listdir(dir):
                itemPath = os.path.realpath(
                    os.path.join(dir, item))
                if os.path.isfile(itemPath):
                    # Skip if this path is already listed as a git template
                    if itemPath not in gitTemplatePaths:
                        templates.append((item, itemPath))
        except Exception as e:
            logger.warning(f"Failed to list templates: {e}")

    templates.sort(key=lambda x: x[0])

    return templates


class TemplateManageDialog(QDialog):
    """Dialog for managing templates with embedded preview/editor"""

    def __init__(self, currentTemplateFile: str = None, parent=None):
        super().__init__(parent)
        self._curTemplateFile = currentTemplateFile
        self._templatesDir = templatesDir()
        self._editMode = False
        self._curTemplate = None
        self._originalContent = ""
        self._originalName = ""

        self.setWindowTitle(self.tr("Manage Templates"))
        self.resize(900, 600)

        mainLayout = QVBoxLayout(self)

        # Splitter for list and editor
        splitter = QSplitter(Qt.Horizontal, self)

        # Left side: Template list
        leftWidget = QWidget()
        leftLayout = QVBoxLayout(leftWidget)
        leftLayout.setContentsMargins(0, 0, 0, 0)

        leftLayout.addWidget(QLabel(self.tr("Templates:")))

        self._templateList = QListWidget(self)
        self._templateList.itemSelectionChanged.connect(
            self._onSelectionChanged)
        leftLayout.addWidget(self._templateList)

        # List action buttons
        listButtonLayout = QHBoxLayout()
        self._btnNew = QPushButton(self.tr("New"), self)
        self._btnNew.clicked.connect(self._onNewTemplate)
        listButtonLayout.addWidget(self._btnNew)

        self._btnDelete = QPushButton(self.tr("Delete"), self)
        self._btnDelete.clicked.connect(self._onDeleteTemplate)
        self._btnDelete.setEnabled(False)
        listButtonLayout.addWidget(self._btnDelete)

        listButtonLayout.addStretch()
        leftLayout.addLayout(listButtonLayout)

        splitter.addWidget(leftWidget)

        # Right side: Preview/Edit area
        rightWidget = QWidget()
        rightLayout = QVBoxLayout(rightWidget)
        rightLayout.setContentsMargins(0, 0, 0, 0)

        # Template info
        infoLayout = QGridLayout()
        infoLayout.addWidget(QLabel(self.tr("Name:")), 0, 0)
        self._nameEdit = QLineEdit(self)
        self._nameEdit.setReadOnly(True)
        infoLayout.addWidget(self._nameEdit, 0, 1)

        infoLayout.addWidget(QLabel(self.tr("Path:")), 1, 0)
        self._pathLabel = QLabel(self)
        self._pathLabel.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._pathLabel.setWordWrap(True)
        infoLayout.addWidget(self._pathLabel, 1, 1)

        rightLayout.addLayout(infoLayout)

        # Content label
        self._contentLabel = QLabel(self.tr("Content (preview):"))
        rightLayout.addWidget(self._contentLabel)

        # Content editor with syntax highlighting
        self._editor = CommitMessageEdit(self)
        self._editor.setReadOnly(True)
        rightLayout.addWidget(self._editor)

        # Set as default checkbox
        self._chkSetDefault = QCheckBox(
            self.tr("Set as git default template"), self)
        self._chkSetDefault.setEnabled(False)
        rightLayout.addWidget(self._chkSetDefault)

        # Edit/Save/Cancel buttons
        editButtonLayout = QHBoxLayout()

        self._btnEdit = QPushButton(self.tr("Edit"), self)
        self._btnEdit.clicked.connect(self._onEditMode)
        self._btnEdit.setEnabled(False)
        editButtonLayout.addWidget(self._btnEdit)

        self._btnSave = QPushButton(self.tr("Save"), self)
        self._btnSave.clicked.connect(self._onSave)
        self._btnSave.setVisible(False)
        editButtonLayout.addWidget(self._btnSave)

        self._btnCancel = QPushButton(self.tr("Cancel"), self)
        self._btnCancel.clicked.connect(self._onCancelEdit)
        self._btnCancel.setVisible(False)
        editButtonLayout.addWidget(self._btnCancel)

        editButtonLayout.addStretch()
        rightLayout.addLayout(editButtonLayout)

        splitter.addWidget(rightWidget)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)

        mainLayout.addWidget(splitter)

        self._loadTemplates()
        self._previewDefaultTemplate()

    def _loadTemplates(self):
        """Load templates from directory"""
        self._templateList.clear()

        templates = loadTemplates(self)
        for name, path in templates:
            row = self._templateList.count()
            self._templateList.addItem(name)
            self._templateList.item(row).setData(Qt.ToolTipRole, path)

    def _previewDefaultTemplate(self):
        """Auto-preview the default git template or first template in list"""
        if self._templateList.count() == 0:
            return

        if self._curTemplateFile:
            # Try to find and select the current template file
            for i in range(self._templateList.count()):
                item = self._templateList.item(i)
                path = item.data(Qt.ToolTipRole)
                if path == self._curTemplateFile:
                    self._templateList.setCurrentItem(item)
                    return

        # Otherwise select the first template
        self._templateList.setCurrentRow(0)

    def _onSelectionChanged(self):
        """Handle template selection change"""
        if self._editMode:
            # Cannot change selection while editing
            return

        items = self._templateList.selectedItems()
        if not items:
            self._clearPreview()
            return

        item = items[0]
        path = item.data(Qt.ToolTipRole)
        self._loadTemplatePreview(item.text(), path)

    def _loadTemplatePreview(self, displayName: str, path: str):
        """Load and display template in preview mode"""
        # Load content
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            logger.error(f"Error loading template: {e}")
            self._clearPreview()
            return

        # Update UI
        self._nameEdit.setText(displayName)
        self._pathLabel.setText(path)
        self._editor.setPlainText(content)
        self._contentLabel.setText(self.tr("Content (preview):"))

        # Check if this is the current git template (prefer local over global)
        currentGitLocalTemplate = Git.getConfigValue(
            "commit.template", isGlobal=False)
        currentGitGlobalTemplate = Git.getConfigValue(
            "commit.template", isGlobal=True)

        isCurrentTemplate = (
            (currentGitLocalTemplate and currentGitLocalTemplate == path) or
            (not currentGitLocalTemplate and currentGitGlobalTemplate == path)
        )
        self._chkSetDefault.setChecked(isCurrentTemplate)

        isGitTemplate = displayName.startswith(
            self.tr("[Git Global] ")) or displayName.startswith(self.tr("[Git Local] "))

        # Store current state
        self._curTemplate = {
            'name': displayName,
            'path': path,
            'isGit': isGitTemplate
        }

        self._btnEdit.setEnabled(True)
        self._btnDelete.setEnabled(not isGitTemplate)

    def _clearPreview(self):
        """Clear preview area"""
        self._nameEdit.clear()
        self._pathLabel.clear()
        self._editor.clear()
        self._chkSetDefault.setChecked(False)
        self._curTemplate = None
        self._btnEdit.setEnabled(False)
        self._btnDelete.setEnabled(False)

    def _onNewTemplate(self):
        """Create a new template"""
        if self._editMode:
            return

        # Ask for template name
        name, ok = QInputDialog.getText(
            self,
            self.tr("New Template"),
            self.tr("Enter template name:"))

        if not ok or not name.strip():
            return

        name = name.strip()

        # Create templates directory if needed
        os.makedirs(self._templatesDir, exist_ok=True)

        templatePath = os.path.join(self._templatesDir, name)

        # Check if already exists
        if os.path.exists(templatePath):
            QMessageBox.warning(
                self,
                self.tr("Template Exists"),
                self.tr(f"A template named '{name}' already exists."))
            return

        try:
            # Create empty template file
            with open(templatePath, "w", encoding="utf-8") as f:
                f.write("")

            logger.info(f"Created new template: {name}")

            # Reload and select the new template
            self._loadTemplates()
            item = self._findItemByPath(templatePath)
            if item:
                self._templateList.setCurrentItem(item)
                # Automatically enter edit mode
                self._onEditMode()

        except Exception as e:
            logger.error(f"Error creating template: {e}")
            QMessageBox.critical(
                self,
                self.tr("Error"),
                self.tr(f"Error creating template: {str(e)}"))

    def _onEditMode(self):
        """Enter edit mode"""
        if not self._curTemplate or self._editMode:
            return

        self._editMode = True

        # Store original state
        self._originalContent = self._editor.toPlainText()
        self._originalName = self._curTemplate['name']

        # Update UI for edit mode
        self._editor.setReadOnly(False)
        self._contentLabel.setText(self.tr("Content (editing):"))

        # Enable name editing for qgitc templates
        if not self._curTemplate['isGit']:
            self._nameEdit.setReadOnly(False)

        self._chkSetDefault.setEnabled(True)

        # Update buttons
        self._btnEdit.setVisible(False)
        self._btnSave.setVisible(True)
        self._btnCancel.setVisible(True)
        self._btnNew.setEnabled(False)
        self._btnDelete.setEnabled(False)

        # Disable list selection
        self._templateList.setEnabled(False)

        self._editor.setFocus()

    def _onSave(self):
        """Save changes and exit edit mode"""
        if not self._editMode or not self._curTemplate:
            return

        newName = self._nameEdit.text().strip()
        if not newName:
            QMessageBox.warning(
                self,
                self.tr("Invalid Name"),
                self.tr("Template name cannot be empty."))
            return

        newContent = self._editor.toPlainText()
        isGitTemplate = self._curTemplate['isGit']
        oldPath = self._curTemplate['path']

        try:
            if isGitTemplate:
                # Just save content for git template
                newPath = oldPath
                with open(newPath, "w", encoding="utf-8") as f:
                    f.write(newContent)
            else:
                # Handle potential rename
                newPath = os.path.join(self._templatesDir, newName)

                # Check if renaming to existing file
                if oldPath != newPath and os.path.exists(newPath):
                    QMessageBox.warning(
                        self,
                        self.tr("Template Exists"),
                        self.tr(f"A template named '{newName}' already exists."))
                    return

                # Save content
                with open(newPath, "w", encoding="utf-8") as f:
                    f.write(newContent)

                # Remove old file if renamed
                if oldPath != newPath and os.path.exists(oldPath):
                    os.remove(oldPath)
                    logger.info(
                        f"Renamed template from {self._originalName} to {newName}")

            # Set as default if requested
            if self._chkSetDefault.isChecked():
                Git.setConfigValue("commit.template", newPath, isGlobal=False)
                logger.info(f"Set template as git local default: {newName}")
            else:
                # Unset if it was previously set and now unchecked
                currentGitLocal = Git.getConfigValue(
                    "commit.template", isGlobal=False)
                currentGitGlobal = Git.getConfigValue(
                    "commit.template", isGlobal=True)

                # Unset local if it matches
                if currentGitLocal and (currentGitLocal == oldPath or currentGitLocal == newPath):
                    Git.setConfigValue("commit.template", "", isGlobal=False)
                # Also unset global if it matches (for consistency)
                elif currentGitGlobal and (currentGitGlobal == oldPath or currentGitGlobal == newPath):
                    Git.setConfigValue("commit.template", "", isGlobal=True)

            logger.info(f"Saved template: {newName}")

            # Exit edit mode
            self._exitEditMode()

            # Reload templates and reselect
            self._loadTemplates()

            item = self._findItemByPath(newPath)
            if item:
                self._templateList.setCurrentItem(item)

        except Exception as e:
            logger.error(f"Error saving template: {e}")
            QMessageBox.critical(
                self,
                self.tr("Error"),
                self.tr(f"Error saving template: {str(e)}"))

    def _onCancelEdit(self):
        """Cancel editing and restore original state"""
        if not self._editMode:
            return

        # Ask for confirmation if content changed
        if self._editor.toPlainText() != self._originalContent:
            reply = QMessageBox.question(
                self,
                self.tr("Discard Changes"),
                self.tr("Discard changes to this template?"),
                QMessageBox.Yes | QMessageBox.No)

            if reply != QMessageBox.Yes:
                return

        # Restore original content
        self._editor.setPlainText(self._originalContent)
        self._nameEdit.setText(self._originalName)

        # Exit edit mode
        self._exitEditMode()

    def _exitEditMode(self):
        """Exit edit mode and return to preview"""
        self._editMode = False

        # Update UI for preview mode
        self._editor.setReadOnly(True)
        self._nameEdit.setReadOnly(True)
        self._contentLabel.setText(self.tr("Content (preview):"))
        self._chkSetDefault.setEnabled(False)

        # Update buttons
        self._btnEdit.setVisible(True)
        self._btnSave.setVisible(False)
        self._btnCancel.setVisible(False)
        self._btnNew.setEnabled(True)
        self._btnEdit.setEnabled(True)
        if self._curTemplate and not self._curTemplate['isGit']:
            self._btnDelete.setEnabled(True)

        # Enable list selection
        self._templateList.setEnabled(True)

    def _onDeleteTemplate(self):
        """Delete the selected template"""
        if self._editMode:
            return

        items = self._templateList.selectedItems()
        if not items:
            return

        name = items[0].text()
        templatePath = os.path.join(self._templatesDir, name)

        reply = QMessageBox.question(
            self,
            self.tr("Delete Template"),
            self.tr("Delete template '{}'?".format(name)),
            QMessageBox.Yes | QMessageBox.No)

        if reply != QMessageBox.Yes:
            return

        try:
            if os.path.exists(templatePath):
                os.remove(templatePath)

                logger.info(f"Deleted template: {name}")

                # Clear preview and reload
                self._clearPreview()
                self._loadTemplates()

        except Exception as e:
            logger.error(f"Error deleting template: {e}")
            QMessageBox.critical(
                self,
                self.tr("Error"),
                self.tr(f"Error deleting template: {str(e)}"))

    def _findItemByPath(self, path: str):
        """Find list item by template path"""
        for i in range(self._templateList.count()):
            item = self._templateList.item(i)
            itemPath = item.data(Qt.ToolTipRole)
            if itemPath == path:
                return item
        return None
