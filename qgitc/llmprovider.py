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
    def createModel(cls, *args):
        name = ApplicationBase.instance().settings().preferLlmModel()
        return AiModelFactory.create(name, *args)
