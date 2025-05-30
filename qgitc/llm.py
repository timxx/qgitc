# -*- coding: utf-8 -*-

import json
from enum import Enum
from threading import Lock
from typing import List, Tuple

from PySide6.QtCore import QThread, Signal
from requests import Response

from qgitc.common import logger


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

    def __init__(self, url, model: str = None, parent=None):
        super().__init__(parent)
        self._history = []
        self.url_base = url
        self._mutex = Lock()
        self._params: AiParameters = None
        self.modelId: str = model

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

    def handleStreamResponse(self, response: Response):
        role = "assistant"
        content = ""
        first_delta = True
        for chunk in response.iter_lines():
            if self.isInterruptionRequested():
                return
            if not chunk:
                continue
            if not chunk.startswith(b"data:"):
                if not chunk.startswith(b": ping - "):
                    logger.warning(b"Corrupted chunk: %s", chunk)
                continue

            if chunk == b"data: [DONE]":
                # we should break here, but in case there is still more data
                # to process, we will just continue
                continue

            data: dict = json.loads(chunk[5:].decode("utf-8"))
            choices: list = data.get("choices")
            if not choices:
                continue

            delta = choices[0]["delta"]
            if not delta:
                break
            if "role" in delta:
                role = delta["role"]
            if "content" in delta:
                if not delta["content"]:
                    continue
                aiResponse = AiResponse()
                aiResponse.is_delta = True
                aiResponse.role = AiRole.Assistant
                aiResponse.message = delta["content"]
                aiResponse.first_delta = first_delta
                self.responseAvailable.emit(aiResponse)
                content += aiResponse.message
                first_delta = False
            else:
                logger.warning(b"Invalid delta: %s", delta)

        return role, content

    def handleNonStreamResponse(self, response: Response):
        data = json.loads(response.text)
        usage = data["usage"]
        aiResponse = AiResponse()
        aiResponse.total_tokens = usage["total_tokens"]

        for choice in data["choices"]:
            message = choice["message"]
            content = message["content"]
            role = message["role"]
            aiResponse.role = AiRole.Assistant
            aiResponse.message = content
            self.responseAvailable.emit(aiResponse)
            break

        return role, content


class AiModelFactory:

    _registry = {}

    @classmethod
    def register(cls):
        def decorator(modelClass):
            cls._registry[modelClass.__name__] = modelClass
            return modelClass
        return decorator

    @classmethod
    def models(cls) -> List[type[AiModelBase]]:
        return list(cls._registry.values())

    @classmethod
    def create(cls, modelClassName: str, **kwargs) -> AiModelBase:
        modelClass = cls._registry.get(modelClassName, None)
        if modelClass:
            return modelClass(**kwargs)
        raise ValueError(f"Model {modelClassName} is not registered.")

    @classmethod
    def modelKey(cls, model: AiModelBase) -> str:
        return model.__class__.__name__
