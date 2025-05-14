# -*- coding: utf-8 -*-

from packaging import version
from PySide6.QtCore import QJsonDocument, QObject, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from qgitc.common import logger
from qgitc.version import __version__


class VersionChecker(QObject):

    newVersionAvailable = Signal(str)
    finished = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

    def startCheck(self):
        request = QNetworkRequest()
        request.setUrl("https://pypi.org/pypi/qgitc/json")

        self._manager = QNetworkAccessManager(self)
        reply = self._manager.get(request)
        if not reply:
            return

        reply.finished.connect(self._onFinished)

    def _onFinished(self):
        reply: QNetworkReply = self.sender()
        reply.deleteLater()

        try:
            if reply.error() != QNetworkReply.NoError:
                return

            data = reply.readAll()
            if not data:
                return

            latestVersion = version.parse(self._getVersion(data))
            curVersion = version.parse(__version__)
            if curVersion < latestVersion:
                self.newVersionAvailable.emit(latestVersion.public)
        except Exception as e:
            logger.exception("Error checking for new version: %s", e)
        finally:
            self.finished.emit()

    def _getVersion(self, data):
        doc = QJsonDocument.fromJson(data)
        if doc.isNull():
            return ""

        root = doc.object()
        if "info" not in root:
            return ""

        infoObj = root["info"]
        if "version" not in infoObj:
            return ""

        version = infoObj["version"]
        if not isinstance(version, str):
            return ""

        return version
