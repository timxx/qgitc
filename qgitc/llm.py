# -*- coding: utf-8 -*-

import json
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QNetworkReply, QNetworkRequest

from qgitc.applicationbase import ApplicationBase
from qgitc.common import logger


class AiRole(Enum):
    User = 0
    Assistant = 1
    System = 2
    Tool = 3

    @staticmethod
    def fromString(role: str) -> 'AiRole':
        role = role.lower()
        if role == "user":
            return AiRole.User
        if role == "assistant":
            return AiRole.Assistant
        if role == "system":
            return AiRole.System
        if role == "tool":
            return AiRole.Tool
        return AiRole.Assistant


class AiChatMessage:
    def __init__(self, role=AiRole.User, message: str = None, description: str = None, toolCalls=None):
        self.role = role
        self.message = message
        self.description = description
        self.toolCalls = toolCalls


class AiResponse:

    def __init__(self, role=AiRole.Assistant, message: str = None, description: str = None):
        self.role = role
        self.message = message
        # Optional description displayed after the role header (UI-only).
        self.description = description
        self.total_tokens = None
        self.is_delta = False
        self.first_delta = False
        # OpenAI-compatible tool calls (Chat Completions).
        # Each item is a dict like: {"id": str, "type": "function", "function": {"name": str, "arguments": str}}
        self.tool_calls: Optional[List[Dict[str, Any]]] = None


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
        # OpenAI-compatible tool definitions, e.g. [{"type":"function","function":{...}}]
        self.tools: Optional[List[Dict[str, Any]]] = None
        # OpenAI tool choice (e.g. "auto"); leave None to omit.
        self.tool_choice: Optional[str] = None


class AiChatMode(Enum):

    Chat = 0
    CodeReview = 1
    Agent = 2


def _aiRoleFromString(role: str) -> AiRole:
    role = role.lower()
    if role == "user":
        return AiRole.User
    elif role == "assistant":
        return AiRole.Assistant
    elif role == "system":
        return AiRole.System
    elif role == "tool":
        return AiRole.Tool
    else:
        logger.warning("Unknown role: %s", role)
        return AiRole.Assistant


class AiModelBase(QObject):
    responseAvailable = Signal(AiResponse)
    serviceUnavailable = Signal()
    networkError = Signal(str)
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
        self._toolCallAcc: Dict[int, Dict[str, Any]] = {}
        self._toolCalls = []

    def clear(self):
        self._history.clear()

    def queryAsync(self, params: AiParameters):
        pass

    def addHistory(self, role: AiRole, message: str, description: str = None, toolCalls=None):
        self._history.append(AiChatMessage(
            role, message, description=description,
            toolCalls=toolCalls))

    def toOpenAiMessages(self):
        # Tool role is UI-only in QGitc and should not be sent to the LLM.
        messages = []
        for history in self._history:
            if history.role == AiRole.Tool:
                continue

            msg = {"role": history.role.name.lower(),
                   "content": history.message}
            if history.toolCalls:
                msg["tool_calls"] = history.toolCalls
            messages.append(msg)

        return messages

    @property
    def name(self):
        return None

    def isLocal(self):
        return False

    def models(self) -> List[Tuple[str, str]]:
        """Returns a list of model names supported by this AI model.
        Each tuple contains (model_id, model_name).
        """
        return []

    def supportsToolCalls(self, modelId: str) -> bool:
        """Whether the given model id supports OpenAI-style tool calls.

        Providers that expose per-model capability metadata should override this.
        For providers without capability metadata, we assume tool calls are supported.
        """
        return True

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
        self._toolCallAcc = {}
        self._toolCalls = []

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
        self._toolCalls = []

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
        if self._content or self._toolCalls:
            self.addHistory(self._role, self._content,
                            toolCalls=self._toolCalls)

    def _handleError(self, code: QNetworkReply.NetworkError):
        if code in [QNetworkReply.ConnectionRefusedError, QNetworkReply.HostNotFoundError]:
            self.serviceUnavailable.emit()
        elif isinstance(self.sender(), QNetworkReply):
            reply: QNetworkReply = self.sender()
            self.networkError.emit(reply.errorString())

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

        choice0 = choices[0]
        delta = choice0.get("delta")
        if not delta:
            return

        if "role" in delta and delta["role"]:
            self._role = _aiRoleFromString(delta["role"])
        # Tool calls can stream as incremental chunks of function.arguments.
        if "tool_calls" in delta and delta["tool_calls"]:
            for tc in delta["tool_calls"]:
                idx = tc.get("index")
                if idx is None:
                    continue
                acc = self._toolCallAcc.get(idx) or {"type": "function"}
                if tc.get("id"):
                    acc["id"] = tc.get("id")
                if tc.get("type"):
                    acc["type"] = tc.get("type")
                func = tc.get("function") or {}
                if func.get("name"):
                    acc.setdefault("function", {})["name"] = func.get("name")
                if func.get("arguments"):
                    acc.setdefault("function", {})
                    prev = acc["function"].get("arguments", "")
                    acc["function"]["arguments"] = prev + func.get("arguments")
                self._toolCallAcc[idx] = acc

        # If model signaled tool_calls completion in finish_reason, emit a tool-only response.
        if choice0.get("finish_reason") == "tool_calls" and self._toolCallAcc:
            aiResponse = AiResponse()
            aiResponse.is_delta = False
            aiResponse.role = AiRole.Assistant
            aiResponse.message = ""
            aiResponse.tool_calls = [self._toolCallAcc[i]
                                     for i in sorted(self._toolCallAcc.keys())]
            self._toolCalls = aiResponse.tool_calls
            self.responseAvailable.emit(aiResponse)
            return

        content = self._getContent(delta)
        if content:
            aiResponse = AiResponse()
            aiResponse.is_delta = True
            aiResponse.role = AiRole.Assistant
            aiResponse.message = content
            aiResponse.first_delta = self._firstDelta
            self.responseAvailable.emit(aiResponse)
            self._content += aiResponse.message
            self._firstDelta = False

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
            message: dict = choice.get("message") or {}
            content = self._getContent(message)
            role = message.get("role", "assistant")
            aiResponse.role = AiRole.Assistant
            aiResponse.message = content or ""
            if message.get("tool_calls"):
                aiResponse.tool_calls = message.get("tool_calls")
                self._toolCalls = aiResponse.tool_calls
            self.responseAvailable.emit(aiResponse)
            break

        self._role = _aiRoleFromString(role)
        self._content = content

    @staticmethod
    def _getContent(data: dict) -> str:
        content = data.get("content", None)
        if content:
            return content

        content = data.get("reasoning", None)
        if content:
            return content

        content = data.get("reasoning_text", None)
        return content

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
