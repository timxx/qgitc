import json
from PySide6.QtCore import (
    QObject,
    Signal,
    QThread)
import requests


class AiResponse:

    def __init__(self, role="assistant", message=None):
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


class AiChatMode:

    Chat = 0
    Completion = 1
    Infilling = 2
    CodeReview = 3
    CodeFix = 4
    CodeExplanation = 5


class AiModelBase(QObject):
    responseAvailable = Signal(AiResponse)
    nameChanged = Signal()
    serviceUnavailable = Signal()

    def __init__(self, url, parent=None):
        super().__init__(parent)
        self._history = []
        self.url_base = url

    def clear(self):
        self._history.clear()

    def query(self, params: AiParameters):
        pass

    def add_history(self, message):
        self._history.append(message)

    @property
    def name(self):
        return None


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
            print(e)

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

        if stream:
            role = "assistant"
            content = ""
            first_delta = True
            for chunk in response.iter_lines():
                if not chunk:
                    continue
                if not chunk.startswith(b"data:"):
                    if not chunk.startswith(b": ping - "):
                        print(f"Corrupted chunk: '{chunk}'")
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
                    aiResponse.role = role
                    aiResponse.message = delta["content"]
                    aiResponse.first_delta = first_delta
                    self.responseAvailable.emit(aiResponse)
                    content += aiResponse.message
                    first_delta = False
                else:
                    print(f"Invalid delta: '{delta}'")
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
                aiResponse.role = role
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
            response = requests.get(url)
            if not response.ok:
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
