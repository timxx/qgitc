# -*- coding: utf-8 -*-

import json

import requests
from PySide6.QtCore import QThread

from qgitc.applicationbase import ApplicationBase
from qgitc.common import logger
from qgitc.llm import AiChatMode, AiParameters
from qgitc.models.chatgpt import ChatGPTModel


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
            if ApplicationBase.instance().terminateThread(self.nameFetcher):
                logger.warning(
                    "Name fetcher thread is still running, terminating it.")
            self.nameFetcher = None
