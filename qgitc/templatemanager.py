# -*- coding: utf-8 -*-

import os
from dataclasses import dataclass
from enum import IntEnum
from typing import List

from PySide6.QtCore import Qt
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
from qgitc.common import logger, pathsEqual
from qgitc.gitutils import Git


class TemplateScope(IntEnum):
    User = 0
    Local = 1
    Global = 2


@dataclass
class TemplateInfo:

    name: str
    path: str
    scope: TemplateScope


def templatesDir():
    """Get the directory for storing qgitc templates"""
    return os.path.expanduser("~/.qgitc/templates")


def gitTemplateFile(isGlobal: bool) -> str:
    """Get the git template file path from config"""
    file = Git.getConfigValue("commit.template", isGlobal=isGlobal)
    if file and os.path.exists(file):
        return os.path.realpath(file)
    return None


def loadTemplates() -> List[TemplateInfo]:
    # Get git global and local templates
    gitGlobalTemplate = gitTemplateFile(isGlobal=True)
    gitLocalTemplate = gitTemplateFile(isGlobal=False)

    dir = templatesDir()

    # Add template selection items
    templates = []
    gitTemplatePaths = set()

    # Add git global template if it exists
    if gitGlobalTemplate:
        name = os.path.basename(gitGlobalTemplate)
        templates.append(TemplateInfo(
            name, gitGlobalTemplate, TemplateScope.Global))
        gitTemplatePaths.add(gitGlobalTemplate)

    # Add git local template if it exists and differs from global
    if gitLocalTemplate and not pathsEqual(gitLocalTemplate, gitGlobalTemplate):
        name = os.path.basename(gitLocalTemplate)
        templates.append(TemplateInfo(
            name, gitLocalTemplate, TemplateScope.Local))
        gitTemplatePaths.add(gitLocalTemplate)

    if os.path.isdir(dir):
        try:
            for item in os.listdir(dir):
                itemPath = os.path.realpath(
                    os.path.join(dir, item))
                if os.path.isfile(itemPath):
                    # Skip if this path is already listed as a git template
                    # Use pathsEqual for case-insensitive comparison
                    if not any(pathsEqual(itemPath, gitPath) for gitPath in gitTemplatePaths):
                        templates.append(TemplateInfo(
                            item, itemPath, TemplateScope.User))
        except Exception as e:
            logger.warning(f"Failed to list templates: {e}")

    templates.sort(key=lambda x: x.name)

    return templates


class TemplateManageDialog(QDialog):
    """Dialog for managing templates with embedded preview/editor"""

    def __init__(self, currentTemplateFile: str = None, parent=None):
        super().__init__(parent)
        self._curTemplateFile = currentTemplateFile
        self._templatesDir = templatesDir()
        self._editMode = False
        self._curTemplate: TemplateInfo = None
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

        templates = loadTemplates()
        for template in templates:
            row = self._templateList.count()
            if template.scope == TemplateScope.Global:
                displayName = self.tr("{} (Global)").format(template.name)
            elif template.scope == TemplateScope.Local:
                displayName = self.tr("{} (Local)").format(template.name)
            else:
                displayName = template.name
            self._templateList.addItem(displayName)
            item = self._templateList.item(row)
            item.setData(Qt.ToolTipRole, template.path)
            item.setData(Qt.UserRole, template)

    def _previewDefaultTemplate(self):
        """Auto-preview the default git template or first template in list"""
        if self._templateList.count() == 0:
            return

        if self._curTemplateFile:
            # Try to find and select the current template file
            for i in range(self._templateList.count()):
                item = self._templateList.item(i)
                path = item.data(Qt.UserRole).path
                if pathsEqual(path, self._curTemplateFile):
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
        self._loadTemplatePreview(item)

    def _loadTemplatePreview(self, item):
        """Load and display template in preview mode"""
        # Get data from item
        template: TemplateInfo = item.data(Qt.UserRole)

        # Load content
        try:
            with open(template.path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            logger.error(f"Error loading template: {e}")
            self._clearPreview()
            return

        # Update UI
        self._nameEdit.setText(template.name)
        self._pathLabel.setText(template.path)
        self._editor.setPlainText(content)
        self._contentLabel.setText(self.tr("Content (preview):"))

        # Check if this is the current git template by scope
        isGitDefault = template.scope in (
            TemplateScope.Local, TemplateScope.Global)
        self._chkSetDefault.setChecked(isGitDefault)

        # Store current state
        self._curTemplate = TemplateInfo(
            template.name, template.path, template.scope)

        self._btnEdit.setEnabled(True)
        self._btnDelete.setEnabled(template.scope == TemplateScope.User)

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
        self._originalName = self._curTemplate.name

        # Update UI for edit mode
        self._editor.setReadOnly(False)
        self._contentLabel.setText(self.tr("Content (editing):"))

        # Enable name editing for qgitc templates
        if self._curTemplate.scope == TemplateScope.User:
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
        scope = self._curTemplate.scope
        oldPath = self._curTemplate.path

        try:
            if scope != TemplateScope.User:
                # Just save content for git template
                newPath = oldPath
                with open(newPath, "w", encoding="utf-8") as f:
                    f.write(newContent)
            else:
                # Handle potential rename
                newPath = os.path.join(self._templatesDir, newName)

                # Check if renaming to existing file
                if not pathsEqual(oldPath, newPath) and os.path.exists(newPath):
                    QMessageBox.warning(
                        self,
                        self.tr("Template Exists"),
                        self.tr(f"A template named '{newName}' already exists."))
                    return

                # Save content
                with open(newPath, "w", encoding="utf-8") as f:
                    f.write(newContent)

                # Remove old file if renamed
                if not pathsEqual(oldPath, newPath) and os.path.exists(oldPath):
                    os.remove(oldPath)
                    logger.info(
                        f"Renamed template from {self._originalName} to {newName}")

            # Set as default if requested
            if self._chkSetDefault.isChecked():
                # Preserve the original scope if it was a git template, otherwise default to local
                if scope == TemplateScope.Global:
                    isGlobal = True
                    scopeLabel = "global"
                else:
                    isGlobal = False
                    scopeLabel = "local"
                Git.setConfigValue("commit.template",
                                   newPath, isGlobal=isGlobal)
                logger.info(
                    f"Set template as git {scopeLabel} default: {newName}")
            else:
                # Unset only in the scope where it was previously configured
                if scope == TemplateScope.Local:
                    Git.setConfigValue("commit.template", "", isGlobal=False)
                elif scope == TemplateScope.Global:
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
        if self._curTemplate and self._curTemplate.scope == TemplateScope.User:
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
            itemPath = item.data(Qt.UserRole).path
            if pathsEqual(itemPath, path):
                return item
        return None
