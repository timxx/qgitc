# -*- coding: utf-8 -*-

from PySide6.QtCore import QObject, Signal

from qgitc.applicationbase import ApplicationBase
from qgitc.llm import AiParameters, AiResponse
from qgitc.llmprovider import AiModelProvider

GEN_TITLE_PROMPT = "Generate a short, descriptive title (3-6 words max) for this conversation based on the first message. Return only the title, no explanations or quotes.\nResponse in language of mesessage or use {ui_lang} if unable to detect the language:\n\n"


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

        # Create a simple prompt to generate a title
        ui_lang = ApplicationBase.instance().uiLanguage()
        prompt = f"{GEN_TITLE_PROMPT.format(ui_lang=ui_lang)}\n\n{firstMessage[:512]}"

        params = AiParameters()
        params.prompt = prompt
        params.temperature = 0.3
        params.max_tokens = 1024
        params.stream = False

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
