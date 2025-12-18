# -*- coding: utf-8 -*-

import json
from enum import Enum
from typing import Dict, List, Tuple

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QNetworkReply, QNetworkRequest

from qgitc.applicationbase import ApplicationBase
from qgitc.common import logger


class AiRole(Enum):
    User = 0
    Assistant = 1
    System = 2

    @staticmethod
    def fromString(role: str) -> 'AiRole':
        role = role.lower()
        if role == "user":
            return AiRole.User
        if role == "assistant":
            return AiRole.Assistant
        if role == "system":
            return AiRole.System
        return AiRole.Assistant


class AiChatMessage:
    def __init__(self, role=AiRole.User, message: str = None):
        self.role = role
        self.message = message


class AiResponse:

    def __init__(self, role=AiRole.Assistant, message: str = None):
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


def _aiRoleFromString(role: str) -> AiRole:
    role = role.lower()
    if role == "user":
        return AiRole.User
    elif role == "assistant":
        return AiRole.Assistant
    elif role == "system":
        return AiRole.System
    else:
        logger.warning("Unknown role: %s", role)
        return AiRole.Assistant


class AiModelBase(QObject):
    responseAvailable = Signal(AiResponse)
    serviceUnavailable = Signal()
    modelsReady = Signal()
    finished = Signal()

    def __init__(self, url, model: str = None, parent=None):
        super().__init__(parent)
        self._history: List[AiChatMessage] = []
        self.url_base = url
        self.modelId: str = model
        self._reply: QNetworkReply = None

        self._data: bytes = b""
        self._isStreaming = False
        self._role = AiRole.Assistant
        self._content = ""
        self._firstDelta = True

    def clear(self):
        self._history.clear()

    def queryAsync(self, params: AiParameters):
        pass

    def addHistory(self, role: AiRole, message: str):
        self._history.append(AiChatMessage(role, message))

    def toOpenAiMessages(self):
        return [{"role": history.role.name.lower(), "content": history.message}
                for history in self._history]

    @property
    def name(self):
        return None

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

    def post(self, url: str, headers: Dict[bytes, bytes] = None, data: Dict[str, any] = None, stream=True):
        self.requestInterruption()
        self._isStreaming = stream
        if stream:
            headers = headers or {}
            headers[b"Accept"] = b"text/event-stream"
            headers[b"Cache-Control"] = b"no-cache"
        reply = AiModelBase.request(url, headers=headers, post=True, data=data)
        self._initReply(reply)

    def get(self, url: str, headers: Dict[bytes, bytes] = None):
        self.requestInterruption()
        _reply = AiModelBase.request(url, headers=headers, post=False)
        self._initReply(_reply)

    def _initReply(self, reply: QNetworkReply):
        self._data = b""
        self._content = ""
        self._role = AiRole.Assistant
        self._firstDelta = True

        if not reply:
            return

        self._reply = reply
        self._reply.readyRead.connect(self._onDataReady)
        self._reply.errorOccurred.connect(self._onError)
        self._reply.finished.connect(self._onFinished)
        self._reply.sslErrors.connect(self._onSslErrors)

    @staticmethod
    def request(url: str, headers: Dict[bytes, bytes] = None, post=True, data: Dict[str, any] = None, timeout=None):
        mgr = ApplicationBase.instance().networkManager
        request = QNetworkRequest()
        request.setUrl(url)
        if timeout:
            request.setTransferTimeout(timeout)

        if headers:
            for key, value in headers.items():
                request.setRawHeader(key, value)

        if post:
            jsonData = json.dumps(data).encode("utf-8") if data else b''
            reply = mgr.post(request, jsonData)
        else:
            reply = mgr.get(request)

        return reply

    def _onDataReady(self):
        data = self._reply.readAll()
        if not data:
            return
        self._handleData(data.data())

    def _onError(self, code: QNetworkReply.NetworkError):
        self._handleError(code)

    def _onSslErrors(self, errors):
        reply: QNetworkReply = self.sender()
        reply.ignoreSslErrors()

    def _onFinished(self):
        self._handleFinished()
        self._reply.deleteLater()
        self._reply = None
        self.finished.emit()
        self._isStreaming = False
        self._content = ""

    def _handleData(self, data: bytes):
        if self._isStreaming:
            self._data += data
            while self._data:
                pos = self._data.find(b"\n\n")
                offset = 2
                if pos == -1:
                    pos = self._data.find(b"\r\n\r\n")
                    offset = 4
                if pos != -1:
                    line = self._data[:pos]
                    self._data = self._data[pos+offset:]
                    self.handleStreamResponse(line)
                else:
                    break
        else:
            self.handleNonStreamResponse(data)

    def _handleFinished(self):
        """Implement this method to handle the finished state of the network reply."""
        pass

    def _handleError(self, code: QNetworkReply.NetworkError):
        if code in [QNetworkReply.ConnectionRefusedError, QNetworkReply.HostNotFoundError]:
            self.serviceUnavailable.emit()

    def isRunning(self):
        return self._reply is not None and self._reply.isRunning()

    def requestInterruption(self):
        if not self._reply:
            return

        self._reply.abort()

    def handleStreamResponse(self, line: bytes):
        if not line:
            return

        if not line.startswith(b"data:"):
            if not line.startswith(b": ping - "):
                logger.warning(b"Corrupted chunk: %s", line)
            return

        if line == b"data: [DONE]":
            return

        data: dict = json.loads(line[5:].decode("utf-8"))
        choices: list = data.get("choices")
        if not choices:
            return

        delta = choices[0]["delta"]
        if not delta:
            return

        if "role" in delta and delta["role"]:
            self._role = _aiRoleFromString(delta["role"])
        if "content" in delta:
            if not delta["content"]:
                return
            aiResponse = AiResponse()
            aiResponse.is_delta = True
            aiResponse.role = AiRole.Assistant
            aiResponse.message = delta["content"]
            aiResponse.first_delta = self._firstDelta
            self.responseAvailable.emit(aiResponse)
            self._content += aiResponse.message
            self._firstDelta = False
        elif "role" not in delta:
            logger.warning(b"Invalid delta: %s", delta)

    def handleNonStreamResponse(self, response: bytes):
        try:
            data: dict = json.loads(response)
        except json.JSONDecodeError as e:
            logger.error("Failed to decode JSON response: %s", e)
            return
        usage: dict = data.get("usage", {})
        aiResponse = AiResponse()
        aiResponse.total_tokens = usage.get("total_tokens", 0)

        for choice in data["choices"]:
            message: dict = choice["message"]
            content = message["content"]
            role = message.get("role", "assistant")
            aiResponse.role = AiRole.Assistant
            aiResponse.message = content
            self.responseAvailable.emit(aiResponse)
            break

        self._role = _aiRoleFromString(role)
        self._content = content

    @property
    def history(self) -> List[AiChatMessage]:
        return self._history


class AiModelFactory:

    _registry = {}

    @classmethod
    def register(cls):
        def decorator(modelClass):
            cls._registry[modelClass.__name__] = modelClass
            return modelClass
        return decorator

    @classmethod
    def models(cls):
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
