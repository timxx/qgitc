# -*- coding: utf-8 -*-

import json

import requests
from PySide6.QtCore import QThread

from qgitc.applicationbase import ApplicationBase
from qgitc.common import logger
from qgitc.llm import AiChatMode, AiModelFactory, AiParameters
from qgitc.models.chatgpt import ChatGPTModel


class LocalLLMNameFetcher(QThread):

    def __init__(self, url):
        super().__init__()
        self.models = []
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
            for model in model_list["data"]:
                id = model.get("id")
                if not id:
                    continue
                self.models.append((id, id))
        except:
            pass


@AiModelFactory.register()
class LocalLLM(ChatGPTModel):

    _models = {}

    def __init__(self, model: str = None, parent=None):
        url = ApplicationBase.instance().settings().localLlmServer()
        super().__init__(url, model, parent)

        if url not in LocalLLM._models:
            LocalLLM._models[url] = []
            self.nameFetcher = LocalLLMNameFetcher(self.url_base)
            self.nameFetcher.finished.connect(self._onFetchFinished)
            self.nameFetcher.start()
        else:
            self.nameFetcher = None

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
        else:
            self.url = f"{self.url_base}/chat/completions"
        super().query(params)

    @property
    def name(self):
        return self.tr("Local LLM")

    def isLocal(self):
        return True

    def _onFetchFinished(self):
        LocalLLM._models[self.url_base] = self.nameFetcher.models
        self.nameFetcher.deleteLater()
        self.nameFetcher = None
        self.modelsReady.emit()

    def supportedChatModes(self):
        return [AiChatMode.Chat,
                AiChatMode.Completion,
                AiChatMode.Infilling,
                AiChatMode.CodeReview,
                AiChatMode.CodeFix,
                AiChatMode.CodeExplanation
                ]

    def models(self):
        return LocalLLM._models.get(self.url_base, [])

    def cleanup(self):
        if self.nameFetcher and self.nameFetcher.isRunning():
            self.nameFetcher.disconnect(self)
            self.nameFetcher.requestInterruption()
            if ApplicationBase.instance().terminateThread(self.nameFetcher):
                logger.warning(
                    "Name fetcher thread is still running, terminating it.")
            self.nameFetcher = None
