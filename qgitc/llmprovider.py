# -*- coding: utf-8 -*-

from qgitc.applicationbase import ApplicationBase
from qgitc.llm import AiModelFactory

# To register models with the factory
from qgitc.models.githubcopilot import GithubCopilot
from qgitc.models.localllm import LocalLLM


class AiModelProvider():

    @classmethod
    def models(cls):
        return AiModelFactory.models()

    @classmethod
    def createModel(cls, parent=None):
        settings = ApplicationBase.instance().settings()
        modelKey = settings.defaultLlmModel()
        id = settings.defaultLlmModelId(modelKey)
        return AiModelFactory.create(modelKey, model=id, parent=parent)
