# -*- coding: utf-8 -*-

from qgitc.applicationbase import ApplicationBase
from qgitc.llm import AiModelFactory

# To register models with the factory
from qgitc.models.githubcopilot import GithubCopilot
from qgitc.models.localllm import LocalLLM


class AiModelProvider():

    @staticmethod
    def models():
        return AiModelFactory.models()

    @staticmethod
    def createModel(parent=None):
        settings = ApplicationBase.instance().settings()
        modelKey = settings.defaultLlmModel()
        id = settings.defaultLlmModelId(modelKey)
        return AiModelFactory.create(modelKey, model=id, parent=parent)
