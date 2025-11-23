# -*- coding: utf-8 -*-

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Tuple

from PySide6.QtCore import QEvent, QObject, Signal

from qgitc.applicationbase import ApplicationBase
from qgitc.cancelevent import CancelEvent
from qgitc.common import fullRepoDir, logger, toSubmodulePath
from qgitc.gitutils import Git
from qgitc.llm import AiModelBase, AiParameters, AiResponse
from qgitc.llmprovider import AiModelProvider
from qgitc.submoduleexecutor import SubmoduleExecutor

SYSTEM_PROMPT = \
    """You are an AI programming assistant, helping a software developer to come with the best git commit message for their code changes.
You excel in interpreting the purpose behind code changes to craft succinct, clear commit messages that adhere to the repository's guidelines.

# First, think step-by-step:
1. Analyze the CODE CHANGES thoroughly to understand what's been modified.
2. Identify the purpose of the changes to answer the *why* for the commit messages, also considering the optionally provided RECENT FILE COMMITS.
3. Review the provided RECENT REPOSITORY COMMITS to identify established commit message conventions. Focus on the format and style, ignoring commit-specific details like refs, tags, and authors.
4. Generate a thoughtful and succinct commit message for the given CODE CHANGES. It MUST follow the the established writing conventions.
5. Remove any meta information like issue references, tags, or author names from the commit message. The developer will add them.
6. Now only show your message, wrapped with a single markdown ```text codeblock! Do not provide any explanations or details.
"""


COMMIT_PROMPT = \
    """<file-commits>
# RECENT FILE COMMITS (For reference only, do not copy!):
{file_commits}
</file-commits>
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
Please follow the style of the RECENT FILE/REPOSITORY COMMITS, and use SAME LANGUAGE.
DO NOT COPY commits from RECENT COMMITS, but it as reference for the commit style.
ONLY return a single markdown code block, NO OTHER PROSE!
```text
commit message goes here
```
</reminder>
<custom-instructions>

</custom-instructions>"""


REFINE_MESSAGE_PROMPT = \
    """Please optimize the provided git commit message by correcting spelling/grammar errors, improving clarity, and refining phrasing without altering its original structure (e.g., preserve line breaks, template sections like "Co-authored-by", "Signed-off-by", or issue references). Retain technical terms, jargon, and specific formatting.

# Instructions:
1. Fix errors: Correct typos, grammar, and punctuation.
2. Improve clarity: Rephrase ambiguous or redundant descriptions concisely while preserving intent.
3. Preserve structure: Do NOT reorder, add, or remove sections (e.g., keep lines like "Fixes #123" unchanged).
4. Output: Return only the optimized commit message in plain text. No explanations, markdown, or extra text.

# Commit Message:
{message}
"""


class CommitInfoEvent(QEvent):
    Type = QEvent.User + 1

    def __init__(self, diff: str, fileCommits: Dict[str, List[str]], repoLogs: List[str]):
        super().__init__(QEvent.Type(CommitInfoEvent.Type))
        self.diff = diff
        # Dict[file_path, List[commit_messages]]
        self.fileCommits = fileCommits
        self.repoLogs = repoLogs


class AiCommitMessage(QObject):
    messageAvailable = Signal(str)
    errorOccurred = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)

        self._executor = SubmoduleExecutor(self)
        self._executor.finished.connect(self._onFetchCommitInfoFinished)

        # Dict[file_path, List[commit_messages]]
        self._fileCommits: Dict[str, List[str]] = {}
        self._repoLogs: List[str] = []
        self._diffs: List[str] = []
        self._message = ""

        self._aiModel: AiModelBase = None
        self._fileStatuses: Dict[str, str] = {}  # Dict[file_path, status_code]

    def generate(self, submoduleFiles: Dict[str, str], fileStatuses: Dict[str, str] = None):
        """
        Generate commit message.
        
        Args:
            submoduleFiles: Dict mapping submodule to list of files
            fileStatuses: Optional dict mapping file paths to their status codes (e.g., 'M', 'A', 'D')
        """
        if fileStatuses:
            self._fileStatuses = fileStatuses
        else:
            self._fileStatuses = {}

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

        self._fileCommits.clear()
        self._repoLogs.clear()
        self._diffs.clear()
        self._message = ""
        self._executor.submit(repoData, self._fetchCommitInfo)

    def refine(self, message: str):
        if not message:
            self.messageAvailable.emit("")
            logger.info("No commit message to refine")
            return

        self.cancel()
        self._message = ""

        params = AiParameters()
        params.temperature = 0.1
        params.max_tokens = 4096
        params.prompt = REFINE_MESSAGE_PROMPT.format(message=message)

        self._aiModel = AiModelProvider.createModel(self)
        self._aiModel.responseAvailable.connect(self._onAiResponseAvailable)
        self._aiModel.serviceUnavailable.connect(self._onAiServiceUnavailable)
        self._aiModel.finished.connect(self._onAiResponseFinished)
        self._aiModel.queryAsync(params)

    def cancel(self, force=False):
        if self._aiModel and self._aiModel.isRunning():
            logger.info("cancelling AI model")
            self._aiModel.responseAvailable.disconnect(
                self._onAiResponseAvailable)
            self._aiModel.finished.disconnect(self._onAiResponseFinished)
            self._aiModel.serviceUnavailable.disconnect(
                self._onAiServiceUnavailable)
            self._aiModel.requestInterruption()
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

        newFiles = set()
        if self._fileStatuses:
            for filePath in repoFiles:
                status = self._fileStatuses.get(filePath, '')
                if status in ('A'):
                    newFiles.add(filePath)

        # Get files that have history to fetch
        filesToFetch = [f for f in repoFiles if f not in newFiles]

        # Determine commits per file based on filtered file count
        totalFiles = len(filesToFetch)
        if totalFiles == 0:
            # No files with history, skip
            commitsPerFile = 0
        elif totalFiles > 20:
            # Too many files, limit to 15 and reduce commits per file
            filesToFetch = filesToFetch[:15]
            commitsPerFile = 2
        elif totalFiles > 10:
            commitsPerFile = 2
        else:
            commitsPerFile = 3

        if cancelEvent.isSet():
            return

        fileCommits = {}
        if filesToFetch:
            with ThreadPoolExecutor(max_workers=min(10, len(filesToFetch))) as executor:
                future_to_file = {
                    executor.submit(AiCommitMessage._fetchFileCommits, repoDir, f, commitsPerFile): f
                    for f in filesToFetch
                }

                for future in as_completed(future_to_file):
                    if cancelEvent.isSet():
                        executor.shutdown(wait=False, cancel_futures=True)
                        return

                    filePath = future_to_file[future]
                    try:
                        commits = future.result()
                        if commits:
                            fileCommits[filePath] = commits
                    except Exception as e:
                        logger.warning(
                            f"Failed to fetch commits for {filePath}: {e}")

        if cancelEvent.isSet():
            return

        ApplicationBase.instance().postEvent(
            self, CommitInfoEvent(diff, fileCommits, repoLogs))

    @staticmethod
    def _fetchFileCommits(repoDir: str, filePath: str, commitCount: int) -> List[str]:
        """Fetch commit messages for a specific file."""
        args = ["log", "--pretty=format:%B",
                "--no-merges", "-z", "-n", str(commitCount),
                "--", filePath]

        logs = Git.checkOutput(args, repoDir=repoDir)
        if logs is not None:
            logs = logs.decode("utf-8", errors="replace").split("\0")
            logs = [log.rstrip() for log in logs if log.rstrip()]
        else:
            logs = []

        return logs

    @staticmethod
    def _fetchLogs(repoDir: str, commitCount: int, author=None):
        args = ["log", "--pretty=format:%B",
                "--no-merges", "-z", "-n", str(commitCount)]
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
            self.errorOccurred.emit(
                self.tr("No changes found, please make sure you have staged your changes."))
            return

        params = AiParameters()
        params.sys_prompt = SYSTEM_PROMPT
        params.temperature = 0.1
        params.max_tokens = 4096

        params.prompt = COMMIT_PROMPT.format(
            file_commits=AiCommitMessage._makeFileCommits(self._fileCommits),
            recent_commits=AiCommitMessage._makeLogs(self._repoLogs),
            code_changes="\n".join(self._diffs)
        )

        logger.debug("AI commit message prompt: %s", params.prompt)

        self._aiModel = AiModelProvider.createModel(self)
        self._aiModel.responseAvailable.connect(self._onAiResponseAvailable)
        self._aiModel.serviceUnavailable.connect(self._onAiServiceUnavailable)
        self._aiModel.finished.connect(self._onAiResponseFinished)
        self._aiModel.queryAsync(params)

    @staticmethod
    def _makeFileCommits(fileCommits: Dict[str, List[str]]) -> str:
        """Format file commits by grouping files with identical commit histories."""
        if not fileCommits:
            return ""

        # Create a signature for each file's commit history (list of commits)
        # Group files that share the exact same commit history together
        # tuple of commits -> list of files
        commitHistory: Dict[tuple, List[str]] = {}

        for filePath, commits in fileCommits.items():
            commitsKey = tuple(commits)
            if commitsKey not in commitHistory:
                commitHistory[commitsKey] = []
            commitHistory[commitsKey].append(filePath)

        # Format output: list files, then their commit messages
        result = ""
        for commits, files in commitHistory.items():
            for file in files:
                result += file + "\n"

            for commit in commits:
                lines = commit.splitlines()
                result += "- " + lines[0] + "\n"
                for line in lines[1:]:
                    result += "  " + line + "\n"

            result += "\n"

        return result

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
            AiCommitMessage._mergeFileCommits(
                self._fileCommits, evt.fileCommits)
            AiCommitMessage._appendLogs(self._repoLogs, evt.repoLogs)
            return True

        return super().event(evt)

    @staticmethod
    def _mergeFileCommits(target: Dict[str, List[str]], source: Dict[str, List[str]]):
        """Merge file commits from source into target."""
        for filePath, commits in source.items():
            if filePath not in target:
                target[filePath] = []
            for commit in commits:
                if commit not in target[filePath]:
                    target[filePath].append(commit)

    @staticmethod
    def _appendLogs(oldLogs: List[str], newLogs: List[str]):
        for log in newLogs:
            if log not in oldLogs:
                oldLogs.append(log)

    def _onAiResponseAvailable(self, response: AiResponse):
        if response.message:
            self._message += response.message

    def _onAiServiceUnavailable(self):
        message = self.tr("AI service unavailable, please try again later.")
        self.errorOccurred.emit(message)

    def _onAiResponseFinished(self):
        stripMessage = ""
        if self._message:
            message = self._message.strip()
            if message.startswith("<think>"):
                pos = message.find("</think>\n")
                if pos >= 0:
                    message = message[pos + 9:].strip()

            if message.startswith("```text"):
                message = message[7:]
            if message.endswith("```"):
                message = message[:-3]
            message = message.strip()
            for line in message.splitlines():
                if stripMessage:
                    stripMessage += "\n"
                stripMessage += line.rstrip()

        self.messageAvailable.emit(stripMessage)
        self._aiModel = None
