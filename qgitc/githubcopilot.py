# -*- coding: utf-8 -*-

import json
import time

import requests
from PySide6.QtCore import QEventLoop, QLocale

from qgitc.common import logger
from qgitc.events import LoginFinished, RequestLoginGithubCopilot
from qgitc.llm import AiChatMode, AiModelBase, AiParameters, AiResponse, AiRole
from qgitc.settings import Settings

CODE_REVIEW_PROMPT = """Please review the following code patch. Focus on potential bugs, risks, and improvement suggestions. Please focus only on the modified sections of the code. If you notice any serious issues in the old code that could impact functionality or performance, feel free to mention them. Otherwise, concentrate on providing feedback and suggestions for the changes made.

```diff
{diff}
```

Please respond in {language}:
"""


class GithubCopilot(AiModelBase):

    def __init__(self, parent=None):
        super().__init__(None, parent)
        self._token = qApp.settings().githubCopilotToken()

        self._eventLoop = None

    def query(self, params: AiParameters):
        if not self._token or not GithubCopilot.isTokenValid(self._token):
            if not self.updateToken():
                self.serviceUnavailable.emit()
                return
            if self.isInterruptionRequested():
                return

        payload = {
            "model": "gpt-4o-mini",  # TODO: allow user to select model
            "temperature": params.temperature,
            "top_p": 1,
            "max_tokens": params.max_tokens,
            "n": 1,
            "stream": params.stream
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
                language=qApp.uiLanguage())
        self.add_history(self._makeMessage("user", prompt))
        payload["messages"] = self._history

        try:
            self._doQuery(payload, params.stream)
        except requests.exceptions.ConnectionError as e:
            self.serviceUnavailable.emit()
        except Exception as e:
            logger.exception("Error in Github Copilot query")

    @property
    def name(self):
        return "Github Copilot"

    def _doQuery(self, payload, stream=True):
        response = requests.post(
            "https://api.business.githubcopilot.com/chat/completions",
            headers={
                "authorization": f"Bearer {self._token}",
                "copilot-integration-id": "vscode-chat",
                "editor-plugin-version": "copilot-chat/0.24.1",
                "editor-version": "vscode/1.97.2",
                "openai-intent": "conversation-other",
                "user-agent": "GithubCopilotChat/0.24.1",
            },
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
                elif "content" in delta:
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
        else:
            # TODO: handle non-streaming response
            pass

        self.add_history(self._makeMessage(role, content))

    def _makeMessage(self, role, prompt):
        return {"role": role, "content": prompt}

    def updateToken(self):
        settings = Settings(testing=qApp.testing)
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

        qApp.postEvent(qApp, RequestLoginGithubCopilot(self))

        self._eventLoop = QEventLoop()
        self._eventLoop.exec()
        self._eventLoop = None

        settings = Settings(testing=qApp.testing)
        return settings.githubCopilotAccessToken()

    def event(self, evt):
        if evt.type() == LoginFinished.Type:
            if self._eventLoop:
                self._eventLoop.quit()
            return True

        return super().event(evt)

    def supportedChatModes(self):
        return [AiChatMode.Chat, AiChatMode.CodeReview]
