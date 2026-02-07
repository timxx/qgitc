# -*- coding: utf-8 -*-

from PySide6.QtCore import QObject, Signal

from qgitc.llm import AiParameters, AiResponse
from qgitc.llmprovider import AiModelProvider
from qgitc.models.prompts import GEN_TITLE_PROMPT, GEN_TITLE_SYS_PROMPT


class AiChatTitleGenerator(QObject):
    titleReady = Signal(str, str)  # historyId, title

    def __init__(self, parent=None):
        super().__init__(parent)
        self._model = None
        self._historyId = ""

    def startGenerate(self, historyId: str, firstMessage: str):
        self.cancel()

        self._historyId = historyId
        self._model = AiModelProvider.createModel(self)

        prompt = f"{GEN_TITLE_PROMPT}{firstMessage[:512]}"

        params = AiParameters()
        params.prompt = prompt
        params.temperature = 0.3
        params.max_tokens = 1024
        params.sys_prompt = GEN_TITLE_SYS_PROMPT
        params.stream = False
        params.reasoning = False

        self._model.responseAvailable.connect(self._onResponse)
        self._model.finished.connect(self._onFinished)
        self._model.queryAsync(params)

    def _onResponse(self, response: AiResponse):
        if response.message:
            title = response.message.strip().strip('"\'').strip()
            if title and len(title) > 3:
                self.titleReady.emit(self._historyId, title)

    def _onFinished(self):
        self._model = None

    def cancel(self):
        if self._model:
            self._model.requestInterruption()
            self._model = None
