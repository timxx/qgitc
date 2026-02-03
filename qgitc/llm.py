# -*- coding: utf-8 -*-

import json
from dataclasses import dataclass
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


@dataclass
class AiChatMessage:
    role: AiRole = AiRole.User
    message: str = None
    reasoning: str = None
    description: str = None
    toolCalls: Optional[List[Dict[str, Any]]] = None


@dataclass
class AiResponse:
    role: AiRole = AiRole.Assistant
    message: str = None
    description: str = None
    reasoning: str = None
    total_tokens: int = None
    is_delta: bool = False
    first_delta: bool = False
    # OpenAI-compatible tool calls (Chat Completions).
    # Each item is a dict like: {"id": str, "type": "function", "function": {"name": str, "arguments": str}}
    tool_calls: Optional[List[Dict[str, Any]]] = None


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
        # When True, send the current conversation history as-is (including tool
        # messages) without appending a new user message. This is required for
        # proper OpenAI tool-calling continuation after tool execution.
        self.continue_only: bool = False
        # OpenAI-compatible tool definitions, e.g. [{"type":"function","function":{...}}]
        self.tools: Optional[List[Dict[str, Any]]] = None
        # OpenAI tool choice (e.g. "auto"); leave None to omit.
        self.tool_choice: Optional[str] = None


class AiChatMode(Enum):

    Chat = 0
    CodeReview = 1
    Agent = 2


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

        # True = Responses API; False = Chat Completions API
        self._isResponsesApiEnabled = False

        self._data: bytes = b""
        self._isStreaming = False
        self._firstDelta = True

        # Per-choice accumulators for streaming responses.
        # OpenAI can legally return multiple choices in one response.
        self._choiceRoles = {}
        self._choiceContents = {}
        self._choiceReasonings = {}
        # Nested mapping: choiceIndex -> (toolCallIndex -> toolCall dict accumulator)
        self._choiceToolCallAcc = {}

        # Responses API per-request state.
        self._responsesText: str = ""
        self._responsesReasoning: str = ""
        self._responsesToolCalls = []

    def clear(self):
        self._history.clear()

    def queryAsync(self, params: AiParameters):
        pass

    def addHistory(self, role: AiRole, message: str, description: str = None,
                   toolCalls=None, reasoning: str = None):
        self._history.append(AiChatMessage(
            role, message, description=description,
            toolCalls=toolCalls, reasoning=reasoning))

    def toOpenAiMessages(self):
        """Convert internal chat history to OpenAI Chat Completions messages.

        Notes:
        - OpenAI only allows `tool_calls` on assistant messages.
        - If an assistant message contains `tool_calls`, the conversation must
          include a subsequent `tool` role message for each `tool_call_id`
          before any later assistant message.
        """

        messages: List[Dict[str, Any]] = []

        i = 0
        while i < len(self._history):
            h = self._history[i]

            # Tool results must only appear immediately after a corresponding assistant tool_calls.
            # Ignore any orphan/out-of-order tool results to prevent OpenAI 400s.
            if h.role == AiRole.Tool:
                toolCallId = None
                if isinstance(h.toolCalls, dict):
                    toolCallId = h.toolCalls.get("tool_call_id")
                elif isinstance(h.toolCalls, str):
                    toolCallId = h.toolCalls

                if toolCallId:
                    logger.warning(
                        "Ignoring orphan tool result tool_call_id=%s (no active tool_calls)",
                        toolCallId,
                    )
                i += 1
                continue

            # Assistant tool_calls need their tool results before the next assistant.
            if h.role == AiRole.Assistant and isinstance(h.toolCalls, list) and h.toolCalls:
                tool_calls = h.toolCalls
                ids: List[str] = []
                for tc in tool_calls:
                    if isinstance(tc, dict) and tc.get("id"):
                        ids.append(tc.get("id"))

                if not ids:
                    messages.append({
                        "role": "assistant",
                        "content": h.message or "(tool call pending)",
                    })
                    i += 1
                    continue

                expected = set(ids)
                found: set[str] = set()
                tool_msgs: List[Dict[str, Any]] = []

                j = i + 1
                while j < len(self._history):
                    n = self._history[j]
                    if n.role != AiRole.Tool:
                        break

                    if n.toolCalls:
                        tcid = None
                        if isinstance(n.toolCalls, dict):
                            tcid = n.toolCalls.get("tool_call_id")
                        elif isinstance(n.toolCalls, str):
                            tcid = n.toolCalls

                        if tcid:
                            if tcid in expected:
                                found.add(tcid)
                                tool_msgs.append({
                                    "role": "tool",
                                    "tool_call_id": tcid,
                                    "content": n.message or "",
                                })
                            else:
                                logger.warning(
                                    "Ignoring out-of-order tool result tool_call_id=%s (does not match current tool_calls)",
                                    tcid,
                                )
                    j += 1

                missing = expected - found
                if missing:
                    # Invalid/incomplete: do not emit tool_calls (or partial tool results).
                    if j < len(self._history):
                        logger.warning(
                            "Assistant tool_calls missing results before next assistant; ignoring tool_calls ids=%s",
                            sorted(missing),
                        )
                    messages.append({
                        "role": "assistant",
                        "content": h.message or "(tool call pending)",
                    })
                    i += 1
                    continue

                # Valid: emit assistant tool_calls followed by tool results.
                messages.append({
                    "role": "assistant",
                    "content": h.message or "",
                    "tool_calls": tool_calls,
                })
                messages.extend(tool_msgs)
                i = j
                continue

            # Default: forward as plain message.
            msg: Dict[str, Any] = {
                "role": h.role.name.lower(), "content": h.message or ""}
            messages.append(msg)
            i += 1

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
        self._firstDelta = True

        self._choiceRoles = {}
        self._choiceContents = {}
        self._choiceReasonings = {}
        self._choiceToolCallAcc = {}

        self._responsesText = ""
        self._responsesReasoning = ""
        self._responsesToolCalls = []

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
        if self._isResponsesApiEnabled:
            self._handleFinishedResponses()
        else:
            self._handleFinishedChat()

    def _handleFinishedChat(self):
        # Iterate over a snapshot since we'll pop from the dict.
        for choiceIndex in list(self._choiceRoles.keys()):
            role = self._choiceRoles.pop(choiceIndex, AiRole.Assistant)
            fullContent = self._choiceContents.pop(choiceIndex, None)
            fullReasoning = self._choiceReasonings.pop(choiceIndex, None)
            toolCalls = self._choiceToolCallAcc.pop(choiceIndex, {})
            if fullContent or fullReasoning or toolCalls:
                self.addHistory(role, fullContent,
                                reasoning=fullReasoning, toolCalls=toolCalls)

    def _handleFinishedResponses(self):
        if self._responsesText or self._responsesReasoning or self._responsesToolCalls:
            self.addHistory(AiRole.Assistant, self._responsesText,
                            reasoning=self._responsesReasoning, toolCalls=self._responsesToolCalls)

    def _handleError(self, code: QNetworkReply.NetworkError):
        if code in [QNetworkReply.ConnectionRefusedError, QNetworkReply.HostNotFoundError]:
            self.serviceUnavailable.emit()
        elif isinstance(self.sender(), QNetworkReply):
            reply: QNetworkReply = self.sender()
            errorString = reply.errorString()

            if self._data and self._data.startswith(b"{"):
                try:
                    msg = json.loads(self._data.decode("utf-8"))
                    error = msg.get("error", {})
                    message = error.get("message")
                    if message:
                        errorString += f"\n\n{message}"
                except:
                    pass

            self.networkError.emit(errorString)

    def isRunning(self):
        return self._reply is not None and self._reply.isRunning()

    def requestInterruption(self):
        if not self._reply:
            return

        self._reply.abort()

    def handleStreamResponse(self, line: bytes):
        if self._isResponsesApiEnabled:
            self._handleStreamResponseResponses(line)
        else:
            self._handleStreamResponseChat(line)

    def _handleStreamResponseChat(self, line: bytes):
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

        # OpenAI can stream multiple choices concurrently.
        for choice in choices:
            choiceIndex = choice.get("index", 0)
            delta = choice.get("delta", {})
            finishReason = choice.get("finish_reason")

            if choiceIndex not in self._choiceRoles:
                self._choiceRoles[choiceIndex] = AiRole.Assistant
            if choiceIndex not in self._choiceContents:
                self._choiceContents[choiceIndex] = ""
            if choiceIndex not in self._choiceReasonings:
                self._choiceReasonings[choiceIndex] = ""

            roleStr = delta.get("role")
            if roleStr:
                self._choiceRoles[choiceIndex] = AiRole.fromString(roleStr)

            # Tool calls can stream as incremental chunks of function.arguments.
            tools = delta.get("tool_calls")
            if tools:
                accMap = self._choiceToolCallAcc.get(choiceIndex, {})
                for tc in tools:
                    idx = tc.get("index")
                    if idx is None:
                        continue
                    acc = accMap.get(idx, {"type": "function"})
                    if tc.get("id"):
                        acc["id"] = tc.get("id")
                    if tc.get("type"):
                        acc["type"] = tc.get("type")
                    func = tc.get("function", {})
                    if func.get("name"):
                        acc.setdefault("function", {})[
                            "name"] = func.get("name")
                    if func.get("arguments"):
                        acc.setdefault("function", {})
                        prev = acc["function"].get("arguments", "")
                        acc["function"]["arguments"] = prev + \
                            func.get("arguments")
                    accMap[idx] = acc
                self._choiceToolCallAcc[choiceIndex] = accMap

            content = self._getContent(delta)
            if content:
                self._choiceContents[choiceIndex] = self._choiceContents.get(
                    choiceIndex) + content

            reasoning = self._getReasoning(delta)
            if reasoning:
                # content and reasoning are mutually exclusive in a single delta.
                assert not content
                self._choiceReasonings[choiceIndex] = self._choiceReasonings.get(
                    choiceIndex) + reasoning

            if content or reasoning:
                if not self._firstDelta and content:
                    if self._choiceReasonings.get(choiceIndex) and \
                            self._choiceContents.get(choiceIndex) == content:
                        # To prevent mixing reasoning and content in a single UI message
                        self._firstDelta = True
                role = self._choiceRoles.get(choiceIndex, AiRole.Assistant)
                self._emitResponse(content, reasoning, role=role)

            # If model signaled completion for this choice, commit immediately.
            if finishReason in ("stop", "tool_calls", "content_filter"):
                role = self._choiceRoles.pop(choiceIndex, AiRole.Assistant)
                fullContent = self._choiceContents.pop(choiceIndex, None)
                fullReasoning = self._choiceReasonings.pop(choiceIndex, None)
                toolCalls = None
                if finishReason == "tool_calls":
                    accMap = self._choiceToolCallAcc.pop(choiceIndex, {})
                    toolCalls = [accMap[i]
                                 for i in sorted(accMap.keys())] if accMap else []
                    if toolCalls:
                        self._emitResponse(
                            isDelta=False, role=role, toolCalls=toolCalls)

                if fullContent or fullReasoning or toolCalls:
                    self.addHistory(
                        role, fullContent, reasoning=fullReasoning, toolCalls=toolCalls)

    def _handleStreamResponseResponses(self, line: bytes):
        if not line:
            return

        # Responses streaming can include `event:` lines alongside `data:`.
        for raw in line.splitlines():
            raw = raw.strip()
            if not raw.startswith(b"data:"):
                if not raw.startswith(b"event:"):
                    logger.warning(b"Unexpected chunk: %s" % raw)
                continue
            payload = raw[5:].strip()
            if not payload:
                continue
            if payload == b"[DONE]":
                return

            try:
                evt = json.loads(payload.decode("utf-8"))
            except Exception as e:
                logger.warning(
                    "Failed to decode Responses stream event: %s", e)
                continue
            self._handleResponsesStreamEvent(evt)

    def handleNonStreamResponse(self, response: bytes):
        if self._isResponsesApiEnabled:
            return self._handleNonStreamResponseResponses(response)
        return self._handleNonStreamResponseChat(response)

    def _handleNonStreamResponseChat(self, response: bytes):
        try:
            data: dict = json.loads(response)
        except json.JSONDecodeError as e:
            logger.error("Failed to decode JSON response: %s", e)
            return
        usage: dict = data.get("usage", {})
        totalTokens = usage.get("total_tokens", 0)

        for choice in data.get("choices", []):
            message: dict = choice.get("message", {})
            content = self._getContent(message)
            reasoning = self._getReasoning(message)
            role = AiRole.fromString(message.get("role", "assistant"))
            tool_calls = message.get("tool_calls")
            self._emitResponse(isDelta=False, role=role, text=content,
                               reasoning=reasoning, toolCalls=tool_calls)

            if content or reasoning or tool_calls:
                self.addHistory(
                    role, content, reasoning=reasoning, toolCalls=tool_calls)

    def _handleNonStreamResponseResponses(self, response: bytes):
        self._data += response
        while self._data:
            pos = self._data.find(b"\n")
            if pos == -1:
                break

            line = self._data[:pos].strip()
            self._data = self._data[pos+1:]
            if not line:
                continue
            try:
                data = json.loads(line.decode("utf-8"))
            except Exception as e:
                logger.warning(
                    "Failed to decode Responses non-stream line: %s", e)
                continue
            self._processResponsesResponseObject(data)

    def _emitResponse(self, text: str = None, reasoning: str = None,
                      isDelta=True, role=AiRole.Assistant,
                      toolCalls: Optional[List[Dict[str, Any]]] = None):
        if not text and not reasoning and not toolCalls:
            return

        aiResponse = AiResponse()
        aiResponse.is_delta = isDelta
        aiResponse.role = role
        aiResponse.message = text
        aiResponse.reasoning = reasoning
        aiResponse.tool_calls = toolCalls
        aiResponse.first_delta = self._firstDelta
        self.responseAvailable.emit(aiResponse)
        self._firstDelta = False

    @staticmethod
    def historyToResponsesInput(history: List[AiChatMessage]):
        """Convert internal chat history to Responses API `input` array."""
        if not history:
            return []

        converted: List[Dict[str, Any]] = []
        for h in history:
            # Tool calls
            if h.role == AiRole.Assistant and isinstance(h.toolCalls, list) and h.toolCalls:
                for tc in h.toolCalls:
                    function = tc.get("function", {})
                    item = {
                        "type": "function_call",
                        "name": function.get("name", ""),
                        "arguments": function.get("arguments", "{}"),
                        "call_id": tc.get("id", ""),
                    }
                    converted.append(item)
                continue

            # Tool results
            if h.role == AiRole.Tool and h.toolCalls:
                toolCalls = h.toolCalls
                item = {
                    "type": "function_call_output",
                    "call_id": toolCalls.get("tool_call_id", ""),
                    "output": h.message or "",
                }
                converted.append(item)
                continue

            assert h.role != AiRole.Tool

            # Regular messages
            item = {
                "role": h.role.name.lower(),
                "content": h.message or "",
            }
            converted.append(item)

        return converted

    @staticmethod
    def chatToolsToResponsesTools(tools: List[Dict[str, Any]]):
        """Convert Chat Completions tool definitions to Responses API format.

        Chat Completions uses: {"type":"function","function":{...}}
        Responses API uses:   {"type":"function", ...function_fields_at_root }
        """

        if not tools:
            return []

        converted: List[Dict[str, Any]] = []
        for t in tools:
            if not isinstance(t, dict):
                continue

            # If already in Responses shape (no nested function), keep as-is.
            if isinstance(t.get("name"), str) and "function" not in t:
                converted.append(t)
                continue

            ttype = t.get("type", "function")
            fn = t.get("function")
            if not isinstance(fn, dict):
                # Unknown shape; forward as-is rather than dropping it.
                converted.append(t)
                continue

            out: Dict[str, Any] = {"type": ttype}
            # Keep only fields known to be accepted by Responses tools.
            for k in ("name", "description", "parameters", "strict"):
                v = fn.get(k)
                if v is not None:
                    out[k] = v
            # Keep compatibility with Chat Completions strict mode.
            out["strict"] = False
            converted.append(out)

        return converted

    def toResponsesInput(self):
        return AiModelBase.historyToResponsesInput(self._history)

    def _handleResponsesStreamEvent(self, evt: dict):
        evtType: str = evt.get("type") or evt.get("event")
        if not evtType:
            return

        if evtType == "response.output_text.delta":
            delta = evt.get("delta", "")
            self._firstDelta = not self._responsesText
            self._responsesText += delta
            self._emitResponse(text=delta)
        elif evtType == "response.reasoning_summary_text.delta":
            delta = evt.get("delta", "")
            self._responsesReasoning += delta
            self._emitResponse(reasoning=delta)

        # Parse function call in done event (we don't need deltas for tool calls).
        elif evtType == "response.output_item.done":
            item = evt.get("item", {})
            itemType = item.get("type")
            if itemType == "function_call":
                toolCalls = [self._parseResponsesFunctionCall(item)]
                self._responsesToolCalls.extend(toolCalls)

        # A response is complete
        elif evtType == "response.completed":
            if self._responsesText or self._responsesReasoning or self._responsesToolCalls:
                self.addHistory(AiRole.Assistant, self._responsesText,
                                reasoning=self._responsesReasoning,
                                toolCalls=self._responsesToolCalls)

                if self._responsesToolCalls:
                    self._emitResponse(
                        isDelta=False, toolCalls=self._responsesToolCalls)

                self._responsesText = ""
                self._responsesReasoning = ""
                self._responsesToolCalls = []

    def _processResponsesResponseObject(self, data: dict):
        output: List[Dict[str, Any]] = data.get("output", [])
        message = ""
        reasoning = ""
        toolCalls = []
        role = AiRole.Assistant

        for item in output:
            itemType = item.get("type")
            if not itemType:
                continue
            if itemType == "message":
                message += self._parseResponsesMessage(item)
                role = AiRole.fromString(item.get("role", "assistant"))
            elif itemType == "function_call":
                toolCalls.append(self._parseResponsesFunctionCall(item))
            elif itemType == "reasoning":
                reasoning += self._parseResponsesReasoning(item)

        if message or reasoning or toolCalls:
            self.addHistory(role, message, reasoning=reasoning,
                            toolCalls=toolCalls)

            self._emitResponse(isDelta=False, role=role,
                               text=message, reasoning=reasoning,
                               toolCalls=toolCalls)

    def _parseResponsesMessage(self, item: dict):
        content: List[Dict[str, any]] = item.get("content", [])
        message = ""
        for chunk in content:
            text = chunk.get("text", "")
            chunkType = chunk.get("type")
            if chunkType == "output_text":
                message += text
            else:
                logger.warning(
                    "Unknown Responses message chunk type: %s", chunkType)
        return message

    def _parseResponsesFunctionCall(self, item: dict):
        return {
            "function": {
                "name": item.get("name"),
                "arguments": item.get("arguments"),
            },
            "id": item.get("call_id"),
            "type": "function",
        }

    def _parseResponsesReasoning(self, item: dict):
        summary: List[Dict[str, any]] = item.get("summary", [])
        reasoning = ""
        for chunk in summary:
            chunkType = chunk.get("type")
            if chunkType == "summary_text":
                text = chunk.get("text", "")
                reasoning += text
            else:
                logger.warning(
                    "Unknown Responses reasoning chunk type: %s", chunkType)

        return reasoning

    @staticmethod
    def _getContent(data: dict) -> str:
        return data.get("content", None)

    @staticmethod
    def _getReasoning(data: dict) -> str:
        content = data.get("reasoning", None)
        if content:
            return content

        content = data.get("reasoning_text", None)
        if content:
            return content

        content = data.get("reasoning_content", None)
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
