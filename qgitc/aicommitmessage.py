# -*- coding: utf-8 -*-

from typing import Dict, List, Tuple
from PySide6.QtCore import QObject, Signal, QEvent

from .cancelevent import CancelEvent
from .common import fullRepoDir, logger, toSubmodulePath
from .githubcopilot import GithubCopilot
from .gitutils import Git
from .llm import AiModelBase, AiParameters, AiResponse
from .submoduleexecutor import SubmoduleExecutor


SYSTEM_PROMPT = \
    """You are an AI programming assistant, helping a software developer to come with the best git commit message for their code changes.
You excel in interpreting the purpose behind code changes to craft succinct, clear commit messages that adhere to the repository's guidelines.

# First, think step-by-step:
1. Analyze the CODE CHANGES thoroughly to understand what's been modified.
2. Identify the purpose of the changes to answer the *why* for the commit messages, also considering the optionally provided RECENT USER COMMITS.
3. Review the provided RECENT REPOSITORY COMMITS to identify established commit message conventions. Focus on the format and style, ignoring commit-specific details like refs, tags, and authors.
4. Generate a thoughtful and succinct commit message for the given CODE CHANGES. It MUST follow the the established writing conventions. 5. Remove any meta information like issue references, tags, or author names from the commit message. The developer will add them.
6. Now only show your message, wrapped with a single markdown ```text codeblock! Do not provide any explanations or details
Follow Microsoft content policies.
Avoid content that violates copyrights.
If you are asked to generate content that is harmful, hateful, racist, sexist, lewd, violent, or completely irrelevant to software engineering, only respond with ""Sorry, I can't assist with that.""
Keep your answers short and impersonal."""


COMMIT_PROMPT = \
    """<user-commits>
# RECENT USER COMMITS (For reference only, do not copy!):
{user_commits}

</user-commits>
<recent-commits>
# RECENT REPOSITORY COMMITS (For reference only, do not copy!):
{recent_commits}

</recent-commits>
<changes>
# CODE CHANGES:
```
{code_changes}
```

</changes>
<reminder>
Now generate a commit messages that describe the CODE CHANGES.
Please follow the style of the RECENT USER/REPOSITORY COMMITS, and use SAME LANGUAGE.
DO NOT COPY commits from RECENT COMMITS, but it as reference for the commit style.
ONLY return a single markdown code block, NO OTHER PROSE!
```text
commit message goes here
```
</reminder>
<custom-instructions>

</custom-instructions>"""


class CommitInfoEvent(QEvent):
    Type = QEvent.User + 1

    def __init__(self, diff: str, userLogs: List[str], repoLogs: List[str]):
        super().__init__(QEvent.Type(CommitInfoEvent.Type))
        self.diff = diff
        self.userLogs = userLogs
        self.repoLogs = repoLogs


class AiCommitMessage(QObject):
    messageAvailable = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)

        self._executor = SubmoduleExecutor(self)
        self._executor.finished.connect(self._onFetchCommitInfoFinished)

        self._userLogs: List[str] = []
        self._repoLogs: List[str] = []
        self._diffs: List[str] = []
        self._message = ""

        self._aiModel: AiModelBase = None

    def generate(self, submoduleFiles: Dict[str, str]):
        if len(submoduleFiles) <= 1:
            commitCount = 5
        elif len(submoduleFiles) < 3:
            commitCount = 3
        else:
            commitCount = 2

        commitCount = 5 if len(submoduleFiles) <= 1 else 3
        repoData = {}
        for submodule, files in submoduleFiles.items():
            repoData[submodule] = (files, commitCount)
        if not repoData:
            repoData[None] = (files, commitCount)

        self.cancel()

        self._userLogs.clear()
        self._repoLogs.clear()
        self._diffs.clear()
        self._message = ""
        self._executor.submit(repoData, self._fetchCommitInfo)

    def cancel(self):
        if self._aiModel and self._aiModel.isRunning():
            logger.warning("cancelling AI model")
            self._aiModel.responseAvailable.disconnect(
                self._onAiResponseAvailable)
            self._aiModel.finished.disconnect(self._onAiResponseFinished)
            self._aiModel.requestInterruption()
            self._aiModel.wait(50)
            if self._aiModel.isRunning():
                logger.error("AI model still running")
            self._aiModel = None

        self._executor.cancel()

    def _fetchCommitInfo(self, submodule: str, userData: Tuple[list, int], cancelEvent: CancelEvent):
        repoDir = fullRepoDir(submodule)
        files, commitCount = userData
        repoFiles = [toSubmodulePath(submodule, file) for file in files]

        diff = Git.commitRawDiff(Git.LCC_SHA1, repoFiles, repoDir=repoDir)
        if cancelEvent.isSet():
            return

        if diff is not None:
            diff = diff.decode("utf-8", errors="replace")
        else:
            diff = ""

        repoLogs = AiCommitMessage._fetchLogs(repoDir, commitCount)
        if cancelEvent.isSet():
            return

        author = Git.userName()
        if author:
            userLogs = AiCommitMessage._fetchLogs(repoDir, commitCount, author)
        else:
            userLogs = []

        if cancelEvent.isSet():
            return

        qApp.postEvent(self, CommitInfoEvent(diff, userLogs, repoLogs))

    @staticmethod
    def _fetchLogs(repoDir: str, commitCount: int, author=None):
        args = ["log", "--pretty=format:%B", "--no-merges", "-z", "-n", str(commitCount)]
        if author:
            args.append("--author={}".format(author))

        logs = Git.checkOutput(args, repoDir=repoDir)
        if logs is not None:
            logs = logs.decode("utf-8", errors="replace").split("\0")
            logs = [log.rstrip() for log in logs if log.rstrip()]
        else:
            logs = []

        return logs

    def _onFetchCommitInfoFinished(self):
        if not self._diffs:
            logger.warning(
                "No code changes found, skipping AI commit message generation")
            return

        params = AiParameters()
        params.sys_prompt = SYSTEM_PROMPT
        params.temperature = 0.1
        params.max_tokens = 4096

        params.prompt = COMMIT_PROMPT.format(
            user_commits=AiCommitMessage._makeLogs(self._userLogs),
            recent_commits=AiCommitMessage._makeLogs(self._repoLogs),
            code_changes="\n".join(self._diffs)
        )

        # TODO: add model provider to provide models
        self._aiModel = GithubCopilot(self)
        self._aiModel.responseAvailable.connect(self._onAiResponseAvailable)
        self._aiModel.finished.connect(self._onAiResponseFinished)
        self._aiModel.queryAsync(params)

    @staticmethod
    def _makeLogs(logs: List[str]):
        message = ""
        for log in logs:
            lines = log.splitlines()
            message += "- " + lines[0]
            for line in lines[1:]:
                message += "  \n  " + line
            message += "\n"
        return message

    def event(self, evt):
        if evt.type() == CommitInfoEvent.Type:
            if evt.diff:
                self._diffs.append(evt.diff)
            AiCommitMessage._appendLogs(self._userLogs, evt.userLogs)
            AiCommitMessage._appendLogs(self._repoLogs, evt.repoLogs)
            return True

        return super().event(evt)

    @staticmethod
    def _appendLogs(oldLogs: List[str], newLogs: List[str]):
        for log in newLogs:
            if log not in oldLogs:
                oldLogs.append(log)

    def _onAiResponseAvailable(self, response: AiResponse):
        if response.message:
            self._message += response.message

    def _onAiResponseFinished(self):
        if self._message:
            message = self._message.strip()
            if message.startswith("```text"):
                message = message[7:]
            if message.endswith("```"):
                message = message[:-3]
            message = message.strip()
            self.messageAvailable.emit(message)
        self._aiModel = None
