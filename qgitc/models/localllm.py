# -*- coding: utf-8 -*-

import json

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QNetworkReply, QNetworkRequest

from qgitc.applicationbase import ApplicationBase
from qgitc.llm import AiChatMode, AiModelFactory
from qgitc.models.chatgpt import ChatGPTModel


class LocalLLMNameFetcher(QObject):

    finished = Signal()

    def __init__(self, url):
        super().__init__()
        self.models = []
        self.url_base = url
        self._reply: QNetworkReply = None

    def start(self):
        url = f"{self.url_base}/models"

        mgr = ApplicationBase.instance().networkManager
        request = QNetworkRequest()
        request.setUrl(url)

        self._reply = mgr.get(request)
        self._reply.finished.connect(self._onFinished)
        self._reply.sslErrors.connect(self._onSslErrors)

    def _onFinished(self):
        reply = self._reply
        reply.deleteLater()
        self._reply = None
        if reply.error() != QNetworkReply.NoError:
            return

        model_list = json.loads(reply.readAll().data())
        if not model_list:
            return

        models = model_list.get("data", [])
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
class LocalLLM(ChatGPTModel):

    _models = {}

    def __init__(self, model: str = None, parent=None):
        url = ApplicationBase.instance().settings().localLlmServer()
        super().__init__(url, model, parent)
        self.url = f"{self.url_base}/chat/completions"

        if url not in LocalLLM._models:
            LocalLLM._models[url] = []
            self.nameFetcher = LocalLLMNameFetcher(self.url_base)
            self.nameFetcher.finished.connect(self._onFetchFinished)
            self.nameFetcher.start()
        else:
            self.nameFetcher = None

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
                AiChatMode.CodeReview]

    def models(self):
        return LocalLLM._models.get(self.url_base, [])

    def cleanup(self):
        if self.nameFetcher and self.nameFetcher.isRunning():
            self.nameFetcher.disconnect(self)
            self.nameFetcher.requestInterruption()
            self.nameFetcher = None
