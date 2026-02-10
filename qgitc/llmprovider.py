# -*- coding: utf-8 -*-

import importlib
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from qgitc.applicationbase import ApplicationBase
from qgitc.llm import AiModelBase, AiModelFactory


@dataclass(frozen=True)
class AiModelDescriptor:
    """Lightweight model provider descriptor.

    This avoids importing/initializing provider implementations (which may
    start network fetches in __init__) until the user actually selects a model.
    """

    modelKey: str
    displayName: str
    modulePath: str
    localProvider: bool = False

    # Minimal AiModelBase-like surface for callers/tests that iterate cbBots
    # items and expect `name`/`isLocal()` to exist.
    @property
    def name(self) -> str:
        return ApplicationBase.instance().translate(self.modelKey, self.displayName)

    def isLocal(self) -> bool:
        return bool(self.localProvider)

    def models(self) -> List[Tuple[str, str]]:
        return []


class AiModelProvider():

    # NOTE: Keep this list minimal and explicit to avoid eager imports.
    # modelKey must match the class name registered in AiModelFactory.
    _MODEL_DESCRIPTORS: List[AiModelDescriptor] = [
        AiModelDescriptor(
            modelKey="GithubCopilot",
            displayName="GitHub Copilot",
            modulePath="qgitc.models.githubcopilot",
            localProvider=False,
        ),
        AiModelDescriptor(
            modelKey="LocalLLM",
            displayName="Local LLM",
            modulePath="qgitc.models.localllm",
            localProvider=True,
        ),
    ]

    _moduleByKey: Dict[str, str] = {
        d.modelKey: d.modulePath for d in _MODEL_DESCRIPTORS}

    @staticmethod
    def models():
        return list(AiModelProvider._MODEL_DESCRIPTORS)

    @staticmethod
    def _ensureRegistered(modelKey: str) -> bool:
        """Ensure the model provider class is registered in AiModelFactory."""
        if not modelKey:
            return False

        # Already registered.
        if AiModelFactory.isRegistered(modelKey):
            return True

        modulePath = AiModelProvider._moduleByKey.get(modelKey)
        if not modulePath:
            return False

        # Importing the module should run @AiModelFactory.register decorators.
        importlib.import_module(modulePath)

        return AiModelFactory.isRegistered(modelKey)

    @staticmethod
    def createSpecificModel(modelKey: str, modelId: Optional[str] = None, parent=None) -> AiModelBase:
        if not AiModelProvider._ensureRegistered(modelKey):
            raise ValueError(f"Model {modelKey} is not available.")
        return AiModelFactory.create(modelKey, model=modelId, parent=parent)

    @staticmethod
    def createModel(parent=None):
        settings = ApplicationBase.instance().settings()
        modelKey = settings.defaultLlmModel()
        modelId = settings.defaultLlmModelId(modelKey)
        return AiModelProvider.createSpecificModel(modelKey, modelId=modelId, parent=parent)
