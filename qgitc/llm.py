# -*- coding: utf-8 -*-

from enum import Enum
from threading import Lock
from typing import List, Tuple

from PySide6.QtCore import QThread, Signal


class AiRole(Enum):
    User = 0
    Assistant = 1
    System = 2


class AiResponse:

    def __init__(self, role=AiRole.Assistant, message=None):
        self.role = role
        self.message = message
        self.total_tokens = None
        self.is_delta = False
        self.first_delta = False


class AiParameters:

    def __init__(self):
        self.prompt: str = None
        self.sys_prompt: str = None
        self.temperature: float = None
        self.top_p = None
        self.stream = True
        self.max_tokens = None
        self.chat_mode = None
        self.fill_point = None
        self.language = None
        self.model: str = None


class AiChatMode(Enum):

    Chat = 0
    Completion = 1
    Infilling = 2
    CodeReview = 3
    CodeFix = 4
    CodeExplanation = 5


class AiModelBase(QThread):
    responseAvailable = Signal(AiResponse)
    serviceUnavailable = Signal()
    modelsReady = Signal()

    def __init__(self, url, parent=None):
        super().__init__(parent)
        self._history = []
        self.url_base = url
        self._mutex = Lock()
        self._params: AiParameters = None

    def clear(self):
        with self._mutex:
            self._history.clear()

    def queryAsync(self, params: AiParameters):
        self._params = params
        self.start()

    def query(self, params: AiParameters):
        pass

    def add_history(self, message):
        with self._mutex:
            self._history.append(message)

    @property
    def name(self):
        return None

    def run(self):
        self.query(self._params)

    def isLocal(self):
        return False

    def supportedChatModes(self):
        return [AiChatMode.Chat]

    def models(self) -> List[Tuple[str, str]]:
        """Returns a list of model names supported by this AI model.
        Each tuple contains (model_id, model_name).
        """
        return []

    def cleanup(self):
        pass


class AiModelFactory:

    _registry = {}

    @classmethod
    def register(cls, modelName: str):
        def decorator(modelClass):
            cls._registry[modelName] = modelClass
            return modelClass
        return decorator

    @classmethod
    def models(cls):
        return list(cls._registry.values())

    @classmethod
    def modelNames(cls) -> List[str]:
        return list(cls._registry.keys())

    @classmethod
    def create(cls, modelName: str, *args) -> AiModelBase:
        modelClass = cls._registry.get(modelName, None)
        if modelClass:
            return modelClass(*args)
        raise ValueError(f"Model {modelName} is not registered.")
