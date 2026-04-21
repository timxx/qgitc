# -*- coding: utf-8 -*-

import copy
import uuid
from typing import List

from PySide6.QtWidgets import QDialog, QMenu, QMessageBox, QTableWidgetItem

from qgitc.ui_llmproviderdialog import Ui_LlmProviderDialog


class LlmProviderDialog(QDialog):

    def __init__(self, providers: List[dict], parent=None):
        super().__init__(parent)

        self.ui = Ui_LlmProviderDialog()
        self.ui.setupUi(self)

        self._providers = copy.deepcopy(providers or [])
        self._selectedIndex = -1

        # Match Add button height to Delete button
        self.ui.btnAddProvider.setMinimumHeight(
            self.ui.btnDeleteProvider.sizeHint().height())

        # Template menu on the Add button arrow
        addMenu = QMenu(self)
        self._actionAddOllama = addMenu.addAction(self.tr("Ollama"))
        self._actionAddLmStudio = addMenu.addAction(self.tr("LM Studio"))
        self.ui.btnAddProvider.setMenu(addMenu)

        self.ui.twProviders.itemSelectionChanged.connect(
            self._onProviderSelectionChanged)
        self.ui.btnAddProvider.clicked.connect(self._onAddProviderClicked)
        self._actionAddOllama.triggered.connect(
            lambda: self._onAddFromTemplate(self.tr("Ollama"),
                                            "http://127.0.0.1:11434/v1"))
        self._actionAddLmStudio.triggered.connect(
            lambda: self._onAddFromTemplate(self.tr("LM Studio"),
                                            "http://127.0.0.1:1234/v1"))
        self.ui.btnDeleteProvider.clicked.connect(
            self._onDeleteProviderClicked)
        self.ui.btnAddHeader.clicked.connect(self._onAddHeaderClicked)
        self.ui.btnRemoveHeader.clicked.connect(self._onRemoveHeaderClicked)
        self.ui.buttonBox.accepted.connect(self._onAccepted)
        self.ui.buttonBox.rejected.connect(self.reject)

        self._reloadProvidersTable(selectRow=0)

    def providers(self) -> List[dict]:
        self._saveCurrentHeaders()
        result = []
        for provider in self._providers:
            item = {
                "id": provider.get("id", str(uuid.uuid4())),
                "name": provider.get("name", "").strip(),
                "url": provider.get("url", "").strip(),
                "headers": copy.deepcopy(provider.get("headers", {})),
            }
            result.append(item)
        return result

    def _reloadProvidersTable(self, selectRow: int = -1):
        self.ui.twProviders.blockSignals(True)
        self.ui.twProviders.setRowCount(0)

        for provider in self._providers:
            row = self.ui.twProviders.rowCount()
            self.ui.twProviders.insertRow(row)
            self.ui.twProviders.setItem(
                row, 0, QTableWidgetItem(provider.get("name", "")))
            self.ui.twProviders.setItem(
                row, 1, QTableWidgetItem(provider.get("url", "")))

        self.ui.twProviders.blockSignals(False)

        if self._providers:
            row = selectRow if 0 <= selectRow < len(self._providers) else 0
            self.ui.twProviders.selectRow(row)
            self._selectedIndex = row
            self._loadHeaders(row)
        else:
            self._selectedIndex = -1
            self.ui.twHeaders.setRowCount(0)

    def _readProvidersFromTable(self):
        for row in range(self.ui.twProviders.rowCount()):
            provider = self._providers[row]
            nameItem = self.ui.twProviders.item(row, 0)
            urlItem = self.ui.twProviders.item(row, 1)
            provider["name"] = nameItem.text().strip() if nameItem else ""
            provider["url"] = urlItem.text().strip() if urlItem else ""

    def _saveCurrentHeaders(self):
        self._readProvidersFromTable()

        if self._selectedIndex < 0 or self._selectedIndex >= len(self._providers):
            return

        headers = {}
        for row in range(self.ui.twHeaders.rowCount()):
            keyItem = self.ui.twHeaders.item(row, 0)
            valueItem = self.ui.twHeaders.item(row, 1)
            key = keyItem.text().strip() if keyItem else ""
            value = valueItem.text().strip() if valueItem else ""
            if not key and not value:
                continue
            if key:
                headers[key] = value
        self._providers[self._selectedIndex]["headers"] = headers

    def _loadHeaders(self, providerRow: int):
        self.ui.twHeaders.setRowCount(0)
        if providerRow < 0 or providerRow >= len(self._providers):
            return

        headers = self._providers[providerRow].get("headers", {})
        if not isinstance(headers, dict):
            headers = {}

        for key, value in headers.items():
            row = self.ui.twHeaders.rowCount()
            self.ui.twHeaders.insertRow(row)
            self.ui.twHeaders.setItem(row, 0, QTableWidgetItem(str(key)))
            self.ui.twHeaders.setItem(row, 1, QTableWidgetItem(str(value)))

    def _onProviderSelectionChanged(self):
        selectedRows = self.ui.twProviders.selectionModel().selectedRows()
        if not selectedRows:
            return

        newIndex = selectedRows[0].row()
        if newIndex == self._selectedIndex:
            return

        self._saveCurrentHeaders()
        self._selectedIndex = newIndex
        self._loadHeaders(newIndex)

    def _onAddProviderClicked(self):
        self._saveCurrentHeaders()
        self._providers.append({
            "id": str(uuid.uuid4()),
            "name": self.tr("OpenAI Compatible"),
            "url": "",
            "headers": {},
        })
        self._reloadProvidersTable(selectRow=len(self._providers) - 1)

    def _onDeleteProviderClicked(self):
        selectedRows = self.ui.twProviders.selectionModel().selectedRows()
        if not selectedRows:
            return

        row = selectedRows[0].row()
        self._saveCurrentHeaders()
        self._providers.pop(row)
        self._reloadProvidersTable(
            selectRow=min(row, len(self._providers) - 1))

    def _onAddFromTemplate(self, name: str, url: str):
        self._saveCurrentHeaders()
        template = {
            "id": str(uuid.uuid4()),
            "name": name,
            "url": url,
            "headers": {},
        }
        self._providers.append(template)
        self._reloadProvidersTable(selectRow=len(self._providers) - 1)

    def _onAddHeaderClicked(self):
        row = self.ui.twHeaders.rowCount()
        self.ui.twHeaders.insertRow(row)
        self.ui.twHeaders.setItem(row, 0, QTableWidgetItem(""))
        self.ui.twHeaders.setItem(row, 1, QTableWidgetItem(""))
        self.ui.twHeaders.editItem(self.ui.twHeaders.item(row, 0))

    def _onRemoveHeaderClicked(self):
        selectedRows = self.ui.twHeaders.selectionModel().selectedRows()
        if not selectedRows:
            return
        self.ui.twHeaders.removeRow(selectedRows[0].row())

    def _validate(self) -> bool:
        self._saveCurrentHeaders()

        for i, provider in enumerate(self._providers):
            name = provider.get("name", "").strip()
            url = provider.get("url", "").strip()

            if not name:
                QMessageBox.warning(
                    self,
                    self.windowTitle(),
                    self.tr("Provider row %d has an empty name.") % (i + 1),
                )
                return False

            if not url:
                QMessageBox.warning(
                    self,
                    self.windowTitle(),
                    self.tr("Provider row %d has an empty URL.") % (i + 1),
                )
                return False

        return True

    def _onAccepted(self):
        if not self._validate():
            return
        self.accept()
