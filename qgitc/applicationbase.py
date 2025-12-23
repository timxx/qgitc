# -*- coding: utf-8 -*-

import abc
from typing import Dict, List, cast

from PySide6.QtCore import QThread, Signal, qVersion
from PySide6.QtNetwork import QNetworkAccessManager
from PySide6.QtWidgets import QApplication

from qgitc.colorschema import ColorSchema
from qgitc.settings import Settings
from qgitc.telemetry import TelemetryBase
from qgitc.windowtype import WindowType


def qtVersion():
    return tuple(map(int, qVersion().split('.')))


# no inherit from abc.ABC here, avoid performance and `metaclass conflict`
class ApplicationBase(QApplication):

    repoDirChanged = Signal()
    # list of submodule paths
    # True if is loaded from cache
    # only newly loaded submodules are emitted if False
    submoduleAvailable = Signal(list, bool)
    submoduleSearchCompleted = Signal()

    def __init__(self, argv: List[str]):
        super().__init__(argv)

    @abc.abstractmethod
    def colorSchema(self) -> ColorSchema: ...

    @abc.abstractmethod
    def settings(self) -> Settings: ...

    @abc.abstractmethod
    def terminateThread(self, thread: QThread, waitTime=3000): ...

    @abc.abstractmethod
    def repoName(self) -> str: ...

    @abc.abstractmethod
    def updateRepoDir(self, repoDir: str, reloadSubmodules=True): ...

    @abc.abstractmethod
    def getWindow(self, type: WindowType, ensureCreated=True): ...

    @staticmethod
    def instance():
        return cast(ApplicationBase, QApplication.instance())

    @abc.abstractmethod
    def telemetry(self) -> TelemetryBase: ...

    @abc.abstractmethod
    def trackFeatureUsage(self, feature: str,
                          properties: Dict[str, object] = None): ...

    @property
    @abc.abstractmethod
    def networkManager(self) -> QNetworkAccessManager: ...

    @property
    @abc.abstractmethod
    def submodules(self) -> List[str]: ...
