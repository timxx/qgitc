# -*- coding: utf-8 -*-

import json
import time

from PySide6.QtCore import QEventLoop, QObject, Signal
from PySide6.QtNetwork import QNetworkReply, QNetworkRequest

from qgitc.applicationbase import ApplicationBase
from qgitc.common import logger
from qgitc.events import LoginFinished, RequestLoginGithubCopilot
from qgitc.llm import AiChatMode, AiModelBase, AiModelFactory, AiParameters, AiRole
from qgitc.settings import Settings


def _makeHeaders(token: str, intent: bytes = b"conversation-other"):
    return {
        b"authorization": f"Bearer {token}".encode("utf-8"),
        b"copilot-integration-id": b"vscode-chat",
        b"editor-plugin-version": b"copilot-chat/0.27.2",
        b"editor-version": b"vscode/1.97.2",
        b"openai-intent": intent,
        b"user-agent": b"GithubCopilotChat/0.27.2",
        b"x-github-api-version": b"2025-05-01",
    }


# TODO: upgrade to Python 3.7 to support @dataclass
class AiModelCapabilities:

    def __init__(self, streaming: bool = True, tool_calls: bool = False):
        self.streaming = streaming
        self.tool_calls = tool_calls
        self.max_output_tokens = 4096


class ModelsFetcher(QObject):

    finished = Signal()

    def __init__(self, token: str, url_prefix: str, parent=None):
        super().__init__(parent)
        self.models = []
        self.capabilities = {}
        self.defaultModel = None
        self._token = token
        self._reply: QNetworkReply = None
        self._url_prefix = url_prefix

    def start(self):
        url = f"{self._url_prefix}/models"
        headers = _makeHeaders(self._token, b"model-access")

        mgr = ApplicationBase.instance().networkManager
        request = QNetworkRequest()
        request.setUrl(url)

        for key, value in headers.items():
            request.setRawHeader(key, value)

        self._reply = mgr.get(request)
        self._reply.finished.connect(self._onFinished)

    def _onFinished(self):
        reply = self._reply
        reply.deleteLater()
        self._reply = None
        if reply.error() != QNetworkReply.NoError:
            return

        model_list = json.loads(reply.readAll().data())
        if not model_list or "data" not in model_list:
            return
        for model in model_list["data"]:
            id = model.get("id")
            if not id:
                continue
            if not model.get("model_picker_enabled", True):
                continue

            caps: dict = model.get("capabilities", {})
            type = caps.get("type", "chat")
            if type != "chat":
                continue

            supports: dict = caps.get("supports", {})
            limits: dict = caps.get("limits", {})

            modelCaps = AiModelCapabilities(
                supports.get("streaming", False),
                supports.get("tool_calls", False)
            )
            modelCaps.max_output_tokens = limits.get(
                "max_output_tokens", 4096)
            self.capabilities[id] = modelCaps

            name = model.get("name")
            self.models.append((id, name or id))

            if model.get("is_chat_default", False):
                self.defaultModel = id

        self.finished.emit()

    def requestInterruption(self):
        if self._reply and self._reply.isRunning():
            self._reply.abort()

    def isRunning(self):
        return self._reply is not None and self._reply.isRunning()


@AiModelFactory.register()
class GithubCopilot(AiModelBase):

    _models = None
    _capabilities = {}

    def __init__(self, model: str = None, parent=None):
        super().__init__(None, model, parent)
        self._token = ApplicationBase.instance().settings().githubCopilotToken()
        self._updateUrlPrefix()

        self._eventLoop = None
        self._modelFetcher: ModelsFetcher = None
        self._updateModels()

    def _updateUrlPrefix(self):
        isIndividual = GithubCopilot.isIndividualToken(self._token)
        self._url_prefix = "https://api.{}.githubcopilot.com".format(
            "individual" if isIndividual else "business"
        )
        if self._token and isIndividual and "individual.githubcopilot" not in self._token:
            logger.warning("GitHub individual url may changed, please check!")

    def queryAsync(self, params: AiParameters):
        if not self._token or not GithubCopilot.isTokenValid(self._token):
            if not self.updateToken():
                self.serviceUnavailable.emit()
                self.finished.emit()
                return

        id = params.model or self.modelId or "gpt-4.1"
        self.modelId = id
        caps: AiModelCapabilities = GithubCopilot._capabilities.get(
            id, AiModelCapabilities())

        stream = params.stream
        if stream and not caps.streaming:
            stream = False

        if params.max_tokens > caps.max_output_tokens:
            params.max_tokens = caps.max_output_tokens
        elif id.startswith("claude-") and "thought" in id:
            # claude-3.7-sonnet-thought seems cannot be 4096
            params.max_tokens = caps.max_output_tokens

        payload = {
            "model": id,
            "temperature": params.temperature,
            "top_p": 1,
            "max_tokens": params.max_tokens,
            "n": 1,
            "stream": stream
        }

        if params.top_p is not None:
            payload["top_p"] = params.top_p

        prompt = params.prompt
        if params.sys_prompt:
            self.addHistory(AiRole.System, params.sys_prompt)
        self.addHistory(AiRole.User, prompt)
        payload["messages"] = self.toOpenAiMessages()

        self._doQuery(payload, stream)

    @property
    def name(self):
        return "GitHub Copilot"

    def _doQuery(self, payload, stream=True):
        headers = _makeHeaders(self._token)
        self.post(
            f"{self._url_prefix}/chat/completions",
            headers=headers,
            data=payload,
            stream=stream)

    def updateToken(self, retry=False):
        settings = Settings(testing=ApplicationBase.instance().testing)
        accessToken = settings.githubCopilotAccessToken()
        if not accessToken:
            accessToken = self._requestAccessToken()
            if not accessToken:
                return False

        reply = AiModelBase.request(
            "https://api.github.com/copilot_internal/v2/token",
            headers={
                b"authorization": f"token {accessToken}".encode("utf-8"),
                b"editor-plugin-version": b"copilot-chat/0.24.1",
                b"editor-version": b"vscode/1.97.2",
                b"user-agent": b"GithubCopilotChat/0.24.1",
            }, post=False, timeout=1500)

        self._eventLoop = QEventLoop()
        reply.finished.connect(self._eventLoop.quit)
        self._eventLoop.exec()

        # If the event loop is interrupted, we should not process the reply
        if self._eventLoop is None:
            return False
        self._eventLoop = None

        if reply.error() == QNetworkReply.AuthenticationRequiredError and not retry:
            # clear the token and retry
            settings.setGithubCopilotAccessToken("")
            return self.updateToken(retry=True)

        if reply.error() != QNetworkReply.NoError:
            return False

        data: dict = json.loads(reply.readAll().data())
        self._token = data.get("token")
        if not self._token:
            return False
        self._updateUrlPrefix()
        settings.setGithubCopilotToken(self._token)
        self._updateModels()
        return True

    @staticmethod
    def isTokenValid(token: str):
        if token is None or 'exp' not in token:
            return False
        expTime = GithubCopilot.getTokenExpTime(token)
        return expTime > time.time()

    @staticmethod
    def getTokenExpTime(token: str):
        pairs = token.split(';')
        for pair in pairs:
            key, value = pair.split('=')
            if key.strip() == "exp":
                return int(value.strip())
        return None

    @staticmethod
    def isIndividualToken(token: str):
        if not token:
            return False

        pairs = token.split(';')
        individual = False
        for pair in pairs:
            key, value = pair.split('=')
            key = key.strip()
            if key == "sku":
                return value.strip() == "free_limited_copilot"
            if key == "proxy-ep":
                individual = "individual" in value

        return individual

    def _requestAccessToken(self):
        if self._eventLoop:
            return None

        ApplicationBase.instance().postEvent(
            ApplicationBase.instance(), RequestLoginGithubCopilot(self))

        self._eventLoop = QEventLoop()
        self._eventLoop.exec()
        self._eventLoop = None

        settings = Settings(testing=ApplicationBase.instance().testing)
        return settings.githubCopilotAccessToken()

    def event(self, evt):
        if evt.type() == LoginFinished.Type:
            if self._eventLoop:
                self._eventLoop.quit()
            return True

        return super().event(evt)

    def supportedChatModes(self):
        return [AiChatMode.Chat, AiChatMode.CodeReview]

    def _updateModels(self):
        if self._modelFetcher:
            return

        if GithubCopilot._models is not None:
            return

        if not self._token:
            return

        if not GithubCopilot.isTokenValid(self._token):
            self.updateToken()
            return

        GithubCopilot._models = []

        self._modelFetcher = ModelsFetcher(self._token, self._url_prefix, self)
        self._modelFetcher.finished.connect(self._onModelsAvailable)
        self._modelFetcher.start()

    def _onModelsAvailable(self):
        fetcher: ModelsFetcher = self.sender()
        GithubCopilot._models = fetcher.models
        GithubCopilot._capabilities = fetcher.capabilities

        if not self.modelId:
            modelKey = AiModelFactory.modelKey(self)
            settings = ApplicationBase.instance().settings()
            self.modelId = settings.defaultLlmModelId(modelKey) or fetcher.defaultModel or "gpt-4.1"

        self._modelFetcher = None
        self.modelsReady.emit()

    def models(self):
        if GithubCopilot._models is None:
            return []

        return GithubCopilot._models

    def cleanup(self):
        if self._modelFetcher and self._modelFetcher.isRunning():
            self._modelFetcher.disconnect(self)
            self._modelFetcher.requestInterruption()
            self._modelFetcher = None

    def _handleFinished(self):
        if self._content:
            self.addHistory(self._role, self._content)

    def requestInterruption(self):
        if self._eventLoop:
            self._eventLoop.quit()
            self._eventLoop = None
        return super().requestInterruption()
