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
    providerId: Optional[str] = None
    providerConfig: Optional[dict] = None

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

    LOCAL_MODEL_KEY = "LocalLLM"
    LOCAL_MODEL_PREFIX = "LocalLLM:"

    # NOTE: Keep this list minimal and explicit to avoid eager imports.
    # modelKey must match the class name registered in AiModelFactory.
    _MODEL_DESCRIPTORS: List[AiModelDescriptor] = [
        AiModelDescriptor(
            modelKey="GithubCopilot",
            displayName="GitHub Copilot",
            modulePath="qgitc.models.githubcopilot",
            localProvider=False,
        ),
    ]

    _moduleByKey: Dict[str, str] = {
        d.modelKey: d.modulePath for d in _MODEL_DESCRIPTORS}
    _moduleByKey[LOCAL_MODEL_KEY] = "qgitc.models.openaicompat"

    @staticmethod
    def models():
        models = list(AiModelProvider._MODEL_DESCRIPTORS)

        settings = ApplicationBase.instance().settings()
        providers = settings.localLlmProviders()
        for provider in providers:
            providerId = provider.get("id")
            if not providerId:
                continue
            providerName = provider.get("name")
            if not providerName:
                providerName = "OpenAI Compatible"

            models.append(AiModelDescriptor(
                modelKey=f"{AiModelProvider.LOCAL_MODEL_PREFIX}{providerId}",
                displayName=providerName,
                modulePath="qgitc.models.openaicompat",
                localProvider=True,
                providerId=providerId,
                providerConfig=provider,
            ))

        return models

    @staticmethod
    def _resolveCreateArgs(modelKey: str):
        if modelKey.startswith(AiModelProvider.LOCAL_MODEL_PREFIX):
            providerId = modelKey[len(AiModelProvider.LOCAL_MODEL_PREFIX):]
            settings = ApplicationBase.instance().settings()
            providers = settings.localLlmProviders()
            provider = next(
                (item for item in providers if item.get("id") == providerId), None)
            return AiModelProvider.LOCAL_MODEL_KEY, provider
        return modelKey, None

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
        actualModelKey, providerConfig = AiModelProvider._resolveCreateArgs(
            modelKey)

        if not AiModelProvider._ensureRegistered(actualModelKey):
            raise ValueError(f"Model {modelKey} is not available.")

        kwargs = {
            "model": modelId,
            "parent": parent,
        }
        if providerConfig is not None:
            kwargs["providerConfig"] = providerConfig

        model = AiModelFactory.create(actualModelKey, **kwargs)
        if providerConfig is not None:
            model.modelKey = modelKey
        return model

    @staticmethod
    def createModel(parent=None):
        settings = ApplicationBase.instance().settings()
        modelKey = settings.defaultLlmModel()
        modelId = settings.defaultLlmModelId(modelKey)
        return AiModelProvider.createSpecificModel(modelKey, modelId=modelId, parent=parent)
