# -*- coding: utf-8 -*-

import json
from types import MappingProxyType

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

_knownContextWindows = {
    "llama3": 8192,
    "llama3.1": 131072,
    "mistral": 32768,
    "qwen2.5": 131072,
    "gpt-4": 128000,
    "gpt-5": 200000,
    "claude-3": 200000,
}

KNOWN_CONTEXT_WINDOWS = MappingProxyType(_knownContextWindows)

DEFAULT_CONTEXT_WINDOW = 8192
DEFAULT_MAX_OUTPUT_TOKENS = 4096


def _matches_model_prefix(modelId: str, prefix: str) -> bool:
    if not modelId.startswith(prefix):
        return False
    if len(modelId) == len(prefix):
        return True
    return modelId[len(prefix)] in ":-/_"


def lookup_context_window(model_id: str) -> int:
    modelId = (model_id or "").lower()
    for prefix, window in sorted(
            _knownContextWindows.items(),
            key=lambda item: len(item[0]),
            reverse=True):
        if _matches_model_prefix(modelId, prefix):
            return window
    return DEFAULT_CONTEXT_WINDOW


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
        return AiModelCapabilities(
            context_window=lookup_context_window(targetModelId),
            max_output_tokens=DEFAULT_MAX_OUTPUT_TOKENS,
        )

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

        self.post(self.url, headers=requestHeaders, data=payload, stream=stream)
