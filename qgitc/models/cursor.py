# -*- coding: utf-8 -*-

from qgitc.llm import AiModelBase, AiModelFactory


@AiModelFactory.register()
class Cursor(AiModelBase):

    def __init__(self, model: str = None, parent=None):
        super().__init__(None, model, parent)

    @property
    def name(self):
        return "Cursor"

    def queryAsync(self, params):
        self.serviceUnavailable.emit()
