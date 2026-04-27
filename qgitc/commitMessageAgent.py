# -*- coding: utf-8 -*-

from typing import Dict, List, Optional

from PySide6.QtCore import QObject, Signal

from qgitc.agent.agent_loop import AgentLoop, QueryParams
from qgitc.agent.aimodel_adapter import AiModelBaseAdapter
from qgitc.agent.permissions import PermissionEngine
from qgitc.agent.skills.discovery import loadSkillRegistry
from qgitc.agent.skills.prompt import renderSkillsReminder
from qgitc.agent.tool_registry import ToolRegistry
from qgitc.agent.tools.git_diff_staged import GitDiffStagedTool
from qgitc.agent.tools.git_log import GitLogTool
from qgitc.agent.tools.git_status import GitStatusTool
from qgitc.agent.tools.skill import SkillTool
from qgitc.applicationbase import ApplicationBase
from qgitc.common import dataDirPath, logger
from qgitc.gitutils import Git
from qgitc.llm import AiChatMode
from qgitc.llmprovider import AiModelProvider


class CommitMessageAgent(QObject):
    messageAvailable = Signal(str)
    errorOccurred = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._agentLoop = None  # type: Optional[AgentLoop]
        self._model = None
        self._textBuffer = []  # type: List[str]

    def generate(self, submoduleFiles, template=None, useTemplateOnly=False):
        # type: (Dict[str, list], Optional[str], bool) -> None
        self.cancel()
        self._textBuffer = []

        skillRegistry = loadSkillRegistry(
            cwd=Git.REPO_DIR or ".",
            additional_directories=[dataDirPath() + "/skills"],
        )

        systemPrompt = "You are a helpful assistant that generates commit messages based on git status and diffs. Try use the skills available to gather necessary information before generating the commit message. Prefer project's commit generation skills if they exist, otherwise use commit-message skill."
        reminder = renderSkillsReminder(skillRegistry.getModelVisibleSkills())
        if reminder:
            systemPrompt += "\n\n" + reminder

        try:
            self._model = AiModelProvider.createModel(self)
        except Exception as e:
            self.errorOccurred.emit(str(e))
            return
        settings = ApplicationBase.instance().settings()
        modelKey = settings.defaultLlmModel()
        modelId = settings.defaultLlmModelId(modelKey)
        caps = self._model.getModelCapabilities(modelId)
        adapter = AiModelBaseAdapter(
            self._model,
            modelId,
            max_tokens=(caps.max_output_tokens if self._model.isLocal() else None),
            temperature=0.1,
            chat_mode=AiChatMode.Agent,
        )
        queryParams = QueryParams(
            provider=adapter,
            context_window=caps.context_window,
            max_output_tokens=caps.max_output_tokens,
            skill_registry=skillRegistry,
        )

        self._agentLoop = AgentLoop(
            tool_registry=self._buildToolRegistry(),
            permission_engine=PermissionEngine(),
            system_prompt=systemPrompt,
            parent=self,
        )
        self._agentLoop.textDelta.connect(self._onTextDelta)
        self._agentLoop.agentFinished.connect(self._onAgentFinished)
        self._agentLoop.errorOccurred.connect(self._onAgentError)

        prompt = self._buildPrompt(submoduleFiles, template, useTemplateOnly)
        logger.debug("CommitMessageAgent: submitting to agent loop")
        self._agentLoop.submit(prompt, queryParams)

    def cancel(self):
        if self._agentLoop is not None:
            if self._agentLoop.isRunning():
                self._agentLoop.abort()
                self._agentLoop.wait(3000)
            self._disconnectAgentLoop()
        self._agentLoop = None
        self._model = None

    def _disconnectAgentLoop(self):
        if self._agentLoop is None:
            return
        self._agentLoop.textDelta.disconnect(self._onTextDelta)
        self._agentLoop.agentFinished.disconnect(self._onAgentFinished)
        self._agentLoop.errorOccurred.disconnect(self._onAgentError)

    def _buildToolRegistry(self):
        # type: () -> ToolRegistry
        registry = ToolRegistry()
        registry.register(GitDiffStagedTool())
        registry.register(GitLogTool())
        registry.register(GitStatusTool())
        registry.register(SkillTool())
        return registry

    def _buildPrompt(self, submoduleFiles, template, useTemplateOnly):
        # type: (Dict[str, list], Optional[str], bool) -> str
        repos = []
        for submodule in submoduleFiles.keys():
            repos.append("." if not submodule or submodule == "." else submodule)
        repoList = " ".join(repos) if repos else "."
        prompt = "Generate a commit message. Repos with staged changes: {}".format(repoList)
        if template and useTemplateOnly:
            prompt += "\n\nCommit message template to follow:\n{}".format(template.rstrip())
        return prompt

    def _onTextDelta(self, text):
        # type: (str) -> None
        self._textBuffer.append(text)

    def _onAgentFinished(self):
        message = "".join(self._textBuffer).strip()
        self._disconnectAgentLoop()
        self._agentLoop = None
        self._model = None
        self.messageAvailable.emit(message)

    def _onAgentError(self, errorMsg):
        # type: (str) -> None
        self._disconnectAgentLoop()
        self._agentLoop = None
        self._model = None
        self.errorOccurred.emit(errorMsg)
