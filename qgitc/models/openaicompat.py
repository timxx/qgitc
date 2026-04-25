# -*- coding: utf-8 -*-

import json

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QNetworkReply, QNetworkRequest

from qgitc.applicationbase import ApplicationBase
from qgitc.llm import (
    AiModelBase,
    AiModelCapabilities,
    AiModelFactory,
    AiParameters,
    AiRole,
)

_knownModelCapabilities = {
    "glm-4.5": AiModelCapabilities(
        context_window=131072, max_output_tokens=98304, tool_calls=True
    ),
    "glm-4.6": AiModelCapabilities(
        context_window=204800, max_output_tokens=131072, tool_calls=True
    ),
    "glm-4.7": AiModelCapabilities(
        context_window=204800, max_output_tokens=131072, tool_calls=True
    ),
    "glm-4.7-flash": AiModelCapabilities(
        context_window=202752, max_output_tokens=131072, tool_calls=True
    ),
    "glm-5": AiModelCapabilities(
        context_window=202752, max_output_tokens=202752, tool_calls=True
    ),
    "glm-5.1": AiModelCapabilities(
        context_window=204800, max_output_tokens=131072, tool_calls=True
    ),
    "glm-5v-turbo": AiModelCapabilities(
        context_window=200000, max_output_tokens=131072, tool_calls=True
    ),
    "gemma4:31b": AiModelCapabilities(
        context_window=262144, max_output_tokens=8192, tool_calls=True
    ),
    "gemma4:26b": AiModelCapabilities(
        context_window=262144, max_output_tokens=262144, tool_calls=True
    ),
    "qwen3.5:27b": AiModelCapabilities(
        context_window=262144, max_output_tokens=65536, tool_calls=True
    ),
    "qwen3.5:9b": AiModelCapabilities(
        context_window=262144, max_output_tokens=65536, tool_calls=True
    ),
    "qwen3.5-flash": AiModelCapabilities(
        context_window=1000000, max_output_tokens=64000, tool_calls=True
    ),
    "qwen3.5-plus": AiModelCapabilities(
        context_window=1000000, max_output_tokens=64000, tool_calls=True
    ),
    "qwen3.6-plus": AiModelCapabilities(
        context_window=1000000, max_output_tokens=65536, tool_calls=True
    ),
    "deepseek-chat": AiModelCapabilities(
        context_window=163840, max_output_tokens=163840, tool_calls=True
    ),
    "deepseek-reasoner": AiModelCapabilities(
        context_window=128000, max_output_tokens=64000, tool_calls=True
    ),
    "deepseek-v4-flash": AiModelCapabilities(
        context_window=1000000, max_output_tokens=384000, tool_calls=True
    ),
    "deepseek-v4-pro": AiModelCapabilities(
        context_window=1000000, max_output_tokens=384000, tool_calls=True
    ),
    "kimi-k2-0905": AiModelCapabilities(
        context_window=262144, max_output_tokens=16384, tool_calls=True
    ),
    "kimi-k2.5": AiModelCapabilities(
        context_window=262144, max_output_tokens=262144, tool_calls=True
    ),
    "kimi-k2-thinking": AiModelCapabilities(
        context_window=262144, max_output_tokens=262144, tool_calls=True
    ),
    "kimi-k2-thinking-turbo": AiModelCapabilities(
        context_window=262144, max_output_tokens=262144, tool_calls=True
    ),
    "llama3.1": AiModelCapabilities(
        context_window=131072, max_output_tokens=131072, tool_calls=True
    ),
    "claude-opus-4.6": AiModelCapabilities(
        context_window=1000000, max_output_tokens=128000, tool_calls=True
    ),
    "claude-sonnet-4.6": AiModelCapabilities(
        context_window=1000000, max_output_tokens=128000, tool_calls=True
    ),
    "claude-opus-4-7": AiModelCapabilities(
        context_window=1000000, max_output_tokens=128000, tool_calls=True
    ),
    "gemini-2.5-flash-lite": AiModelCapabilities(
        context_window=1048576, max_output_tokens=65536, tool_calls=True
    ),
    "gemini-3.1-flash-image-preview": AiModelCapabilities(
        context_window=131072, max_output_tokens=32768, tool_calls=True
    ),
    "gemini-2.5-flash-lite": AiModelCapabilities(
        context_window=1048576, max_output_tokens=65536, tool_calls=True
    ),
    "gemini-3-flash-preview": AiModelCapabilities(
        context_window=1048576, max_output_tokens=65536, tool_calls=True
    ),
    "gemini-3-pro-image-preview": AiModelCapabilities(
        context_window=1048756, max_output_tokens=65536, tool_calls=True
    ),
    "gemini-3-pro-preview": AiModelCapabilities(
        context_window=1000000, max_output_tokens=64000, tool_calls=True
    ),
    "gpt-4o": AiModelCapabilities(
        context_window=128000, max_output_tokens=16384, tool_calls=True
    ),
    "gpt-4o-mini": AiModelCapabilities(
        context_window=128000, max_output_tokens=16384, tool_calls=True
    ),
    "gpt-5.2": AiModelCapabilities(
        context_window=400000, max_output_tokens=128000, tool_calls=True
    ),
    "gpt-5.4": AiModelCapabilities(
        context_window=400000, max_output_tokens=128000, tool_calls=True
    ),
    "gpt-5.4-mini": AiModelCapabilities(
        context_window=400000, max_output_tokens=128000, tool_calls=True
    ),
    "gpt-5-mini": AiModelCapabilities(
        context_window=400000, max_output_tokens=128000, tool_calls=True
    ),
    "gpt-5.5": AiModelCapabilities(
        context_window=1050000, max_output_tokens=130000, tool_calls=True
    ),
    "doubao-seed-1-6": AiModelCapabilities(
        context_window=256000, max_output_tokens=16384, tool_calls=True
    ),
    "doubao-seed-1-8": AiModelCapabilities(
        context_window=128000, max_output_tokens=8192, tool_calls=True
    ),
    "doubao-seed-2-0": AiModelCapabilities(
        context_window=256000, max_output_tokens=128000, tool_calls=True
    ),
    "mimo-v2-omni": AiModelCapabilities(
        context_window=262144, max_output_tokens=65536, tool_calls=True
    ),
    "mimo-v2-pro": AiModelCapabilities(
        context_window=1048576, max_output_tokens=65536, tool_calls=True
    )
}


def _matchesModelPrefix(modelId: str, prefix: str) -> bool:
    if not modelId.startswith(prefix):
        return False
    if len(modelId) == len(prefix):
        return True
    return modelId[len(prefix)] in ":-/_"


def lookupModelCapabilities(modelId: str) -> AiModelCapabilities:
    modelId = (modelId or "").lower()
    cap = _knownModelCapabilities.get(modelId)
    if cap:
        return cap

    bestPrefix = None
    bestCap = None
    for prefix, cap in _knownModelCapabilities.items():
        if _matchesModelPrefix(modelId, prefix):
            if bestPrefix is None or len(prefix) > len(bestPrefix):
                bestPrefix = prefix
                bestCap = cap

    return bestCap


class OpenAICompatModelsFetcher(QObject):

    finished = Signal()

    def __init__(self, url: str, authToken: str):
        super().__init__()
        self.models = []
        self.url_base = url
        self._reply: QNetworkReply = None
        self._auth = authToken

    def start(self):
        url = f"{self.url_base}/models"

        mgr = ApplicationBase.instance().networkManager
        request = QNetworkRequest()
        request.setUrl(url)

        if self._auth:
            request.setRawHeader(b"Authorization", self._auth.encode())

        self._reply = mgr.get(request)
        self._reply.finished.connect(self._onFinished)
        self._reply.sslErrors.connect(self._onSslErrors)

    def _onFinished(self):
        reply = self._reply
        reply.deleteLater()
        self._reply = None
        if reply.error() != QNetworkReply.NoError:
            return

        modelList = json.loads(reply.readAll().data())
        if not modelList:
            return

        models = modelList.get("data", [])
        if not models:
            return
        for model in models:
            id = model.get("id")
            if not id:
                continue
            self.models.append((id, id))

        self.finished.emit()

    def _onSslErrors(self, errors):
        reply: QNetworkReply = self.sender()
        reply.ignoreSslErrors()

    def isRunning(self):
        return self._reply is not None and self._reply.isRunning()

    def requestInterruption(self):
        if self._reply and self._reply.isRunning():
            self._reply.abort()


@AiModelFactory.register()
class LocalLLM(AiModelBase):

    _models = {}

    def __init__(self, model: str = None, providerConfig: dict = None, parent=None):
        settings = ApplicationBase.instance().settings()
        if providerConfig is None:
            providers = settings.localLlmProviders()
            providerConfig = providers[0] if providers else None

        providerConfig = providerConfig or {}
        self.providerConfig = providerConfig
        self.providerId = providerConfig.get("id", "")

        url = providerConfig.get("url", "")
        model = model or settings.defaultLlmModelId(self.__class__.__name__)
        super().__init__(url, model, parent)
        self.url = f"{self.url_base}/chat/completions"

        cacheKey = self.providerId or self.url_base
        self._cacheKey = cacheKey
        if cacheKey not in LocalLLM._models:
            LocalLLM._models[cacheKey] = []
            headers = providerConfig.get("headers", {})
            authToken = ""
            if isinstance(headers, dict):
                authToken = headers.get("Authorization", "")
            self.nameFetcher = OpenAICompatModelsFetcher(
                self.url_base, authToken)
            self.nameFetcher.finished.connect(self._onFetchFinished)
            self.nameFetcher.start()
        else:
            self.nameFetcher = None

    @property
    def name(self):
        return self.tr("OpenAI Compatible")

    def isLocal(self):
        return True

    def getModelCapabilities(self, modelId: str = None) -> AiModelCapabilities:
        targetModelId = modelId or self.modelId or ""
        caps = lookupModelCapabilities(targetModelId)
        if caps is None:
            settings = ApplicationBase.instance().settings()
            maxTokens = settings.llmMaxTokens()
            caps = AiModelCapabilities(
                context_window=maxTokens, max_output_tokens=maxTokens,
                tool_calls=True)
        return caps

    def _onFetchFinished(self):
        LocalLLM._models[self._cacheKey] = self.nameFetcher.models
        self.nameFetcher.deleteLater()
        self.nameFetcher = None
        self.modelsReady.emit()

    def models(self):
        return LocalLLM._models.get(self._cacheKey, [])

    def cleanup(self):
        if self.nameFetcher and self.nameFetcher.isRunning():
            self.nameFetcher.disconnect(self)
            self.nameFetcher.requestInterruption()
            self.nameFetcher = None

    @property
    def authorization(self):
        headers = self.providerConfig.get("headers", {})
        if not isinstance(headers, dict):
            return ""
        if "Authorization" in headers:
            return headers["Authorization"]
        return ""

    def queryAsync(self, params: AiParameters):
        payload = {
            "frequency_penalty": 0,
            "max_tokens": params.max_tokens or 4096,
            "model": params.model or self.modelId or "gpt-4.1",
            "presence_penalty": 0,
            "temperature": params.temperature,
            "stream": params.stream
        }

        if params.tools:
            payload["tools"] = params.tools
            payload["tool_choice"] = params.tool_choice or "auto"

        if params.continue_only:
            payload["messages"] = self.toOpenAiMessages()
        elif params.fill_point is not None:
            payload["prefix"] = params.prompt[:params.fill_point]
            payload["suffix"] = params.prompt[params.fill_point:]
            if params.language is not None and params.language != "None":
                payload["language"] = params.language
            self.addHistory(AiRole.User, params.prompt)
        else:
            if params.sys_prompt:
                self.addHistory(AiRole.System, params.sys_prompt)
            self.addHistory(AiRole.User, params.prompt)

            payload["messages"] = self.toOpenAiMessages()

        if params.top_p is not None:
            payload["top_p"] = params.top_p

        if params.stream:
            payload["stream_options"] = {
                "include_usage": True
            }

        self._doQuery(payload, params.stream)

    def _doQuery(self, payload, stream=True):
        requestHeaders = {
            b"Content-Type": b"application/json; charset=utf-8"
        }

        if self.authorization:
            requestHeaders[b"Authorization"] = self.authorization.encode()

        rawHeaders = self.providerConfig.get("headers", {})
        if not isinstance(rawHeaders, dict):
            rawHeaders = {}
        for key, value in rawHeaders.items():
            requestHeaders[key.encode()] = value.encode()

        self.post(self.url, headers=requestHeaders,
                  data=payload, stream=stream)
