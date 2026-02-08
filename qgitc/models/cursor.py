# -*- coding: utf-8 -*-

from qgitc.llm import AiModelBase, AiModelFactory
from qgitc.models.cursor_internal.modelsfetcher import ModelsFetcher
from qgitc.models.cursor_internal.utils import CURSOR_API_URL


@AiModelFactory.register()
class Cursor(AiModelBase):

    _models = None

    def __init__(self, model: str = None, parent=None):
        super().__init__(CURSOR_API_URL, model, parent)

        self._modelFetcher: ModelsFetcher = None
        self._updateModels()

    @property
    def name(self):
        return "Cursor"

    def queryAsync(self, params):
        self.serviceUnavailable.emit()

    def _updateModels(self):
        if self._modelFetcher:
            return

        if Cursor._models is not None:
            return

        Cursor._models = []

        # TODO: add to settings
        try:
            from qgitc.cursorenv import CURSOR_BEARER
            self._modelFetcher = ModelsFetcher(CURSOR_BEARER, self)
            self._modelFetcher.finished.connect(self._onModelsAvailable)
            self._modelFetcher.start()
        except ImportError:
            pass

    def _onModelsAvailable(self):
        fetcher: ModelsFetcher = self.sender()
        Cursor._models = fetcher.models

        self._modelFetcher = None
        self.modelsReady.emit()
