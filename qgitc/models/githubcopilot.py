# -*- coding: utf-8 -*-

import json
import time

import requests
from PySide6.QtCore import QEventLoop, QThread

from qgitc.applicationbase import ApplicationBase
from qgitc.common import logger
from qgitc.events import LoginFinished, RequestLoginGithubCopilot
from qgitc.llm import AiChatMode, AiModelBase, AiModelFactory, AiParameters, AiResponse
from qgitc.settings import Settings

CODE_REVIEW_PROMPT = """Please review the following code patch. Focus on potential bugs, risks, and improvement suggestions. Please focus only on the modified sections of the code. If you notice any serious issues in the old code that could impact functionality or performance, feel free to mention them. Otherwise, concentrate on providing feedback and suggestions for the changes made.

```diff
{diff}
```

Please respond in {language}:
"""


def _makeHeaders(token: str, intent: str = "conversation-other"):
    return {
        "authorization": f"Bearer {token}",
        "copilot-integration-id": "vscode-chat",
        "editor-plugin-version": "copilot-chat/0.27.2",
        "editor-version": "vscode/1.97.2",
        "openai-intent": intent,
        "user-agent": "GithubCopilotChat/0.27.2",
        "x-github-api-version": "2025-05-01",
    }


# TODO: upgrade to Python 3.7 to support @dataclass
class AiModelCapabilities:

    def __init__(self, streaming: bool = True, tool_calls: bool = False):
        self.streaming = streaming
        self.tool_calls = tool_calls
        self.max_output_tokens = 4096


class ModelsFetcher(QThread):

    def __init__(self, token: str, parent=None):
        super().__init__(parent)
        self.models = []
        self.capabilities = {}
        self.defaultModel = None
        self._token = token

    def run(self):
        try:
            url = "https://api.business.githubcopilot.com/models"
            headers = _makeHeaders(self._token, "model-access")
            response = requests.get(url, headers=headers)
            if not response.ok:
                return
            if self.isInterruptionRequested():
                return

            model_list = json.loads(response.text)
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
        except:
            pass


@AiModelFactory.register()
class GithubCopilot(AiModelBase):

    _models = None
    _capabilities = {}

    def __init__(self, model: str = None, parent=None):
        super().__init__(None, model, parent)
        self._token = ApplicationBase.instance().settings().githubCopilotToken()

        self._eventLoop = None
        self._modelFetcher: ModelsFetcher = None
        self._updateModels()

    def query(self, params: AiParameters):
        if not self._token or not GithubCopilot.isTokenValid(self._token):
            if not self.updateToken():
                self.serviceUnavailable.emit()
                return
            if self.isInterruptionRequested():
                return

        id = params.model or self.modelId or "gpt-4.1"
        caps: AiModelCapabilities = GithubCopilot._capabilities.get(
            id, AiModelCapabilities())
        stream = caps.streaming

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
            self.add_history(self._makeMessage(
                "system", params.sys_prompt))
        elif params.chat_mode == AiChatMode.CodeReview:
            prompt = CODE_REVIEW_PROMPT.format(
                diff=params.prompt,
                language=ApplicationBase.instance().uiLanguage())
        self.add_history(self._makeMessage("user", prompt))
        payload["messages"] = self._history

        try:
            self._doQuery(payload, stream)
        except requests.exceptions.ConnectionError as e:
            self.serviceUnavailable.emit()
        except Exception as e:
            logger.exception("Error in Github Copilot query")

    @property
    def name(self):
        return "GitHub Copilot"

    def _doQuery(self, payload, stream=True):
        response = requests.post(
            "https://api.business.githubcopilot.com/chat/completions",
            headers=_makeHeaders(self._token),
            json=payload,
            stream=stream, verify=True)

        if not response.ok:
            aiResponse = AiResponse()
            aiResponse.message = response.text
            self.responseAvailable.emit(aiResponse)
            return

        if self.isInterruptionRequested():
            return

        if stream:
            role, content = self.handleStreamResponse(response)
        else:
            role, content = self.handleNonStreamResponse(response)

        self.add_history(self._makeMessage(role, content))

    def _makeMessage(self, role, prompt):
        return {"role": role, "content": prompt}

    def updateToken(self):
        settings = Settings(testing=ApplicationBase.instance().testing)
        accessToken = settings.githubCopilotAccessToken()
        if not accessToken:
            accessToken = self._requestAccessToken()
            if not accessToken:
                return False

        response = requests.get(
            "https://api.github.com/copilot_internal/v2/token",
            headers={
                "authorization": f"token {accessToken}",
                "editor-plugin-version": "copilot-chat/0.24.1",
                "editor-version": "vscode/1.97.2",
                "user-agent": "GithubCopilotChat/0.24.1",
            }, verify=True)

        if not response.ok:
            return False

        data: dict = response.json()
        self._token = data.get("token")
        if not self._token:
            return False
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

        self._modelFetcher = ModelsFetcher(self._token, self)
        self._modelFetcher.finished.connect(self._onModelsAvailable)
        self._modelFetcher.start()

    def _onModelsAvailable(self):
        fetcher: ModelsFetcher = self.sender()
        GithubCopilot._models = fetcher.models
        GithubCopilot._capabilities = fetcher.capabilities

        if not self.modelId:
            self.modelId = fetcher.defaultModel or "gpt-4.1"

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
            if ApplicationBase.instance().terminateThread(self._modelFetcher):
                logger.warning(
                    "Model fetcher thread is still running, terminating it.")
            self._modelFetcher = None
