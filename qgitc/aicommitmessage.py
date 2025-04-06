# -*- coding: utf-8 -*-

import os
from typing import List
from PySide6.QtCore import QObject, Signal, QEvent, QThread

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


class GenerateThread(QThread):
    responseAvailable = Signal(AiResponse)

    def __init__(self, model: AiModelBase, parent=None):
        super().__init__(parent)
        self._model = model
        self._params: AiParameters = None

        self._model.responseAvailable.connect(self.responseAvailable)

    def generate(self, params: AiParameters):
        self._params = params
        self.start()

    def run(self):
        self._model.query(self._params)


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

        self._aiThread: GenerateThread = None

    def __del__(self):
        self.cancel()

    def generate(self, submodules: List[str]):
        if len(submodules) <= 1:
            commitCount = 5
        elif len(submodules) < 3:
            commitCount = 3
        else:
            commitCount = 2

        commitCount = 5 if len(submodules) <= 1 else 3
        repoData = {}
        for submodule in submodules:
            repoData[submodule] = commitCount
        if not repoData:
            repoData[None] = commitCount

        self.cancel()

        self._userLogs.clear()
        self._repoLogs.clear()
        self._diffs.clear()
        self._message = ""
        self._executor.submit(repoData, self._fetchCommitInfo)

    def cancel(self):
        if self._aiThread:
            self._aiThread.responseAvailable.disconnect(
                self._onAiResponseAvailable)
            self._aiThread.finished.disconnect(self._onAiResponseFinished)
            self._aiThread.requestInterruption()
            self._aiThread.wait(50)
            self._aiThread = None

        self._executor.cancel()

    def _fetchCommitInfo(self, submodule: str, commitCount: int):
        repoDir = AiCommitMessage._toRepoDir(submodule)
        diff = Git.commitRawDiff(Git.LCC_SHA1, repoDir=repoDir)
        if diff is not None:
            diff = diff.decode("utf-8", errors="replace")
        else:
            diff = ""

        repoLogs = AiCommitMessage._fetchLogs(repoDir, commitCount)

        author = Git.userName()
        if author:
            userLogs = AiCommitMessage._fetchLogs(repoDir, commitCount, author)
        else:
            userLogs = []

        qApp.postEvent(self, CommitInfoEvent(diff, userLogs, repoLogs))

    @staticmethod
    def _fetchLogs(repoDir: str, commitCount: int, author=None):
        args = ["log", "--pretty=format:%B", "-z", "-n", str(commitCount)]
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
        params = AiParameters()
        params.sys_prompt = SYSTEM_PROMPT
        params.temperature = 0.1
        params.max_tokens = 4096

        params.prompt = COMMIT_PROMPT.format(
            user_commits=AiCommitMessage._makeLogs(self._userLogs),
            recent_commits=AiCommitMessage._makeLogs(self._repoLogs),
            code_changes="\n".join(self._diffs)
        )

        if self._aiThread:
            # useless for now
            self._aiThread.requestInterruption()
            self._aiThread.wait(50)

        # TODO: add model provider to provide models
        self._aiThread = GenerateThread(GithubCopilot(self), self)
        self._aiThread.responseAvailable.connect(self._onAiResponseAvailable)
        self._aiThread.finished.connect(self._onAiResponseFinished)
        self._aiThread.generate(params)

    @staticmethod
    def _makeLogs(logs: List[str]):
        message = ""
        for log in logs:
            lines = log.splitlines()
            message += "- " + lines[0]
            for line in lines[1:]:
                message += "  \n" + line
            message += "\n"
        return message

    @staticmethod
    def _toRepoDir(submodule: str):
        if not submodule or submodule == ".":
            return Git.REPO_DIR
        return os.path.join(Git.REPO_DIR, submodule)

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
        self._aiThread = None
