import json
from enum import Enum
from threading import Lock

import requests
from PySide6.QtCore import QThread, Signal

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
        self.prompt = None
        self.sys_prompt = None
        self.temperature = None
        self.top_p = None
        self.stream = True
        self.max_tokens = None
        self.chat_mode = None
        self.fill_point = None
        self.language = None


class AiChatMode(Enum):

    Chat = 0
    Completion = 1
    Infilling = 2
    CodeReview = 3
    CodeFix = 4
    CodeExplanation = 5


class AiModelBase(QThread):
    responseAvailable = Signal(AiResponse)
    nameChanged = Signal()
    serviceUnavailable = Signal()

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

    def cleanup(self):
        pass


class ChatGPTModel(AiModelBase):

    def __init__(self, url, parent=None):
        super().__init__(url, parent)
        self.api_token = None

    def query(self, params: AiParameters):
        payload = {
            "frequency_penalty": 0,
            "max_tokens": params.max_tokens,
            "model": self.model,
            "presence_penalty": 0,
            "temperature": params.temperature,
            "stream": params.stream
        }

        if params.fill_point is not None:
            payload["prefix"] = params.prompt[:params.fill_point]
            payload["suffix"] = params.prompt[params.fill_point:]
            if params.language is not None and params.language != "None":
                payload["language"] = params.language
        else:
            if params.sys_prompt:
                self.add_history(self._makeMessage(
                    "system", params.sys_prompt))
            self.add_history(self._makeMessage("user", params.prompt))

            payload["messages"] = self._history

        if params.top_p is not None:
            payload["top_p"] = params.top_p

        try:
            self._doQuery(payload, params.stream)
        except requests.exceptions.ConnectionError as e:
            self.serviceUnavailable.emit()
        except Exception as e:
            logger.exception("Error in query")

    def _makeMessage(self, role, prompt):
        return {"role": role, "content": prompt}

    def _doQuery(self, payload, stream=True):
        headers = {
            "Content-Type": "application/json; charset=utf-8"
        }

        if self.api_token:
            headers["api_key"] = self.api_token,

        response = requests.post(
            self.url, headers=headers, json=payload, stream=stream)
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
                data = json.loads(chunk[5:].decode("utf-8"))
                delta = data["choices"][0]["delta"]
                if not delta:
                    break
                if "role" in delta:
                    role = delta["role"]
                    if "model" in data:
                        self.update_name(data["model"])
                elif "content" in delta:
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
            data = json.loads(response.text)
            usage = data["usage"]
            aiResponse = AiResponse()
            aiResponse.total_tokens = usage["total_tokens"]

            if "model" in data:
                self.update_name(data["model"])

            for choice in data["choices"]:
                message = choice["message"]
                content = message["content"]
                role = message["role"]
                aiResponse.role = AiRole.Assistant
                aiResponse.message = content
                self.responseAvailable.emit(aiResponse)
                break

        self.add_history(self._makeMessage(role, content))

    def update_name(self, name):
        pass


class LocalLLMNameFetcher(QThread):

    def __init__(self, url):
        super().__init__()
        self.name = None
        self.url_base = url

    def run(self):
        try:
            url = f"{self.url_base}/models"
            response = requests.get(url, timeout=0.3)
            if not response.ok:
                return
            if self.isInterruptionRequested():
                return

            model_list = json.loads(response.text)
            if not model_list or "data" not in model_list:
                return
            data = model_list["data"]
            if not data or "id" not in data[0]:
                return

            self.name = data[0]["id"]
        except:
            pass


class LocalLLM(ChatGPTModel):

    def __init__(self, url, parent=None):
        super().__init__(url, parent)
        self.model = "local-llm"
        self._name = "Local LLM"

        self.nameFetcher = LocalLLMNameFetcher(self.url_base)
        self.nameFetcher.finished.connect(self._onFetchFinished)
        self.nameFetcher.start()

    def query(self, params: AiParameters):
        if params.chat_mode == AiChatMode.Chat:
            self.url = f"{self.url_base}/chat/completions"
        elif params.chat_mode == AiChatMode.Completion:
            self.url = f"{self.url_base}/code/completion"
        elif params.chat_mode == AiChatMode.Infilling:
            self.url = f"{self.url_base}/code/infilling"
        elif params.chat_mode == AiChatMode.CodeReview:
            self.url = f"{self.url_base}/code/review"
        elif params.chat_mode == AiChatMode.CodeFix:
            self.url = f"{self.url_base}/code/fix"
        elif params.chat_mode == AiChatMode.CodeExplanation:
            self.url = f"{self.url_base}/code/explanation"
        super().query(params)

    @property
    def name(self):
        return self._name

    def isLocal(self):
        return True

    def update_name(self, name):
        if self.model != name:
            self.model = name
            self._name = self.model
            self.nameChanged.emit()

    def _onFetchFinished(self):
        if self.nameFetcher.name:
            self.update_name(self.nameFetcher.name)
        self.nameFetcher.deleteLater()
        self.nameFetcher = None

    def supportedChatModes(self):
        return [AiChatMode.Chat,
                AiChatMode.Completion,
                AiChatMode.Infilling,
                AiChatMode.CodeReview,
                AiChatMode.CodeFix,
                AiChatMode.CodeExplanation
                ]

    def cleanup(self):
        if self.nameFetcher and self.nameFetcher.isRunning():
            self.nameFetcher.disconnect(self)
            self.nameFetcher.requestInterruption()
            if qApp.terminateThread(self.nameFetcher):
                logger.warning(
                    "Name fetcher thread is still running, terminating it.")
            self.nameFetcher = None
