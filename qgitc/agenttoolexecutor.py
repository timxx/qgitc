# -*- coding: utf-8 -*-

from __future__ import annotations

import os
import subprocess
import sys
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Callable, Dict, Optional, Tuple

from PySide6.QtCore import QObject, Signal

from qgitc.agenttools import (
    AgentToolRegistry,
    GitAddParams,
    GitBranchParams,
    GitCheckoutParams,
    GitCherryPickParams,
    GitCommitParams,
    GitCurrentBranchParams,
    GitDiffParams,
    GitDiffStagedParams,
    GitDiffUnstagedParams,
    GitLogParams,
    GitShowParams,
    GitStatusParams,
    RunCommandParams,
)
from qgitc.basemodel import ValidationError
from qgitc.gitutils import Git


class AgentToolResult:
    def __init__(self, tool_name: str, ok: bool, output: str):
        self.tool_name = tool_name
        self.ok = ok
        self.output = output


class AgentToolExecutor(QObject):
    """Executes agent tools in a background thread (non-blocking UI)."""

    toolFinished = Signal(object)  # AgentToolResult

    def __init__(self, parent=None):
        super().__init__(parent)
        self._executor = ThreadPoolExecutor(max_workers=1)
        self._inflight: Optional[Future] = None
        self._tool_handlers: Dict[str, Callable[[str, Dict], AgentToolResult]] = {
            "git_status": self._handle_git_status,
            "git_log": self._handle_git_log,
            "git_diff": self._handle_git_diff,
            "git_diff_unstaged": self._handle_git_diff_unstaged,
            "git_diff_staged": self._handle_git_diff_staged,
            "git_show": self._handle_git_show,
            "git_current_branch": self._handle_git_current_branch,
            "git_branch": self._handle_git_branch,
            "git_checkout": self._handle_git_checkout,
            "git_cherry_pick": self._handle_git_cherry_pick,
            "git_commit": self._handle_git_commit,
            "git_add": self._handle_git_add,
            "run_command": self._handle_run_command,
        }

    def executeAsync(self, tool_name: str, params: Dict) -> bool:
        if self._inflight and not self._inflight.done():
            return False

        self._inflight = self._executor.submit(
            self._execute, tool_name, params)
        self._inflight.add_done_callback(self._onDone)
        return True

    def shutdown(self):
        if sys.version_info >= (3, 9):
            self._executor.shutdown(wait=False, cancel_futures=True)
        else:
            self._executor.shutdown(wait=False)

    def _onDone(self, fut: Future):
        try:
            result: AgentToolResult = fut.result()
        except Exception as e:
            result = AgentToolResult(
                "unknown", False, f"Tool execution failed: {e}")
        self.toolFinished.emit(result)

    @staticmethod
    def _run_git(repo_dir: str, args: list) -> Tuple[bool, str]:
        if not repo_dir:
            return False, "No repository is currently opened."
        if not os.path.isdir(repo_dir):
            return False, f"Invalid repo_dir: {repo_dir}"

        process = Git.run(args, repoDir=repo_dir, text=True)
        out, err = process.communicate()
        ok = process.returncode == 0
        output = (out or "")
        if err:
            if output:
                output += "\n"
            output += err
        output = output.strip("\n")
        return ok, output

    def _execute(self, tool_name: str, params: Dict) -> AgentToolResult:
        tool = AgentToolRegistry.tool_by_name(tool_name)
        if not tool:
            return AgentToolResult(tool_name, False, f"Unknown tool: {tool_name}")

        handler = self._tool_handlers.get(tool_name)
        if handler:
            return handler(tool_name, params)

        return AgentToolResult(tool_name, False, f"Tool not implemented: {tool_name}")

    def _handle_git_status(self, tool_name: str, params: Dict) -> AgentToolResult:
        try:
            validated = GitStatusParams(**params)
        except ValidationError as e:
            return AgentToolResult(tool_name, False, f"Invalid parameters: {e}")

        repo_dir = validated.repo_dir or Git.REPO_DIR
        args = ["status", "--porcelain=v1", "-b"]
        if not validated.untracked:
            args.append("--untracked-files=no")
        ok, output = self._run_git(repo_dir, args)
        if ok:
            # Porcelain v1 with -b typically includes a branch line like:
            #   ## main...origin/main [ahead 1]
            # If that's the only line, the working tree is clean.
            lines = (output or "").splitlines()
            if not lines:
                output = "working tree clean (no changes)."
            elif len(lines) == 1 and lines[0].startswith("##"):
                output = f"{lines[0]}\nworking tree clean (no changes)."
        return AgentToolResult(tool_name, ok, output)

    def _handle_git_log(self, tool_name: str, params: Dict) -> AgentToolResult:
        try:
            validated = GitLogParams(**params)
        except ValidationError as e:
            return AgentToolResult(tool_name, False, f"Invalid parameters: {e}")

        repo_dir = validated.repo_dir or Git.REPO_DIR

        if validated.nth is not None:
            # Fetch exactly one commit, skipping the first (nth-1) commits.
            # This avoids returning commits 1..(nth-1) to the UI.
            args = ["log", "--oneline", "-n", "1",
                    "--skip", str(validated.nth - 1)]
            ok, output = self._run_git(repo_dir, args)
            if ok:
                line = (output or "").splitlines()[
                    0].strip() if (output or "").strip() else ""
                if line:
                    # Include explicit metadata so the LLM can trust this is the requested position.
                    return AgentToolResult(
                        tool_name,
                        True,
                        f"nth={validated.nth} (1-based from HEAD): {line}",
                    )
                return AgentToolResult(tool_name, False, f"No commit found at nth={validated.nth} (1-based from HEAD).")
            return AgentToolResult(tool_name, False, output)

        args = ["log", "--oneline", "-n", str(validated.max_count)]
        if validated.since:
            args += ["--since", str(validated.since)]
        if validated.until:
            args += ["--until", str(validated.until)]
        ok, output = self._run_git(repo_dir, args)
        return AgentToolResult(tool_name, ok, output)

    def _handle_git_diff(self, tool_name: str, params: Dict) -> AgentToolResult:
        try:
            validated = GitDiffParams(**params)
        except ValidationError as e:
            return AgentToolResult(tool_name, False, f"Invalid parameters: {e}")

        repo_dir = validated.repo_dir or Git.REPO_DIR
        args = ["diff-tree", "-r", "--root", validated.rev,
                "-p", "--textconv", "--submodule",
                "-C", "--no-commit-id", "-U3"]
        if validated.files:
            args += ["--"] + [str(f) for f in validated.files]
        ok, output = self._run_git(repo_dir, args)
        return AgentToolResult(tool_name, ok, output)

    def _handle_git_diff_unstaged(self, tool_name: str, params: Dict) -> AgentToolResult:
        try:
            validated = GitDiffUnstagedParams(**params)
        except ValidationError as e:
            return AgentToolResult(tool_name, False, f"Invalid parameters: {e}")

        repo_dir = validated.repo_dir or Git.REPO_DIR
        if validated.name_only:
            args = ["diff", "--name-only"]
        else:
            args = ["diff-files", "-p", "--textconv",
                    "--submodule", "-C", "-U3"]
        if validated.files:
            args += ["--"] + [str(f) for f in validated.files]
        ok, output = self._run_git(repo_dir, args)
        return AgentToolResult(tool_name, ok, output)

    def _handle_git_diff_staged(self, tool_name: str, params: Dict) -> AgentToolResult:
        try:
            validated = GitDiffStagedParams(**params)
        except ValidationError as e:
            return AgentToolResult(tool_name, False, f"Invalid parameters: {e}")

        repo_dir = validated.repo_dir or Git.REPO_DIR
        if validated.name_only:
            args = ["diff", "--name-only", "--cached"]
        else:
            args = ["diff-index", "--cached",
                    "HEAD", "-p", "--textconv",
                    "--submodule", "-C", "-U3"]
        if validated.files:
            args += ["--"] + [str(f) for f in validated.files]
        ok, output = self._run_git(repo_dir, args)
        return AgentToolResult(tool_name, ok, output)

    def _handle_git_show(self, tool_name: str, params: Dict) -> AgentToolResult:
        try:
            validated = GitShowParams(**params)
        except ValidationError as e:
            return AgentToolResult(tool_name, False, f"Invalid parameters: {e}")

        repo_dir = validated.repo_dir or Git.REPO_DIR
        args = ["show", str(validated.rev)]
        ok, output = self._run_git(repo_dir, args)
        return AgentToolResult(tool_name, ok, output)

    def _handle_git_current_branch(self, tool_name: str, params: Dict) -> AgentToolResult:
        try:
            validated = GitCurrentBranchParams(**params)
        except ValidationError as e:
            return AgentToolResult(tool_name, False, f"Invalid parameters: {e}")

        repo_dir = validated.repo_dir or Git.REPO_DIR
        # Prefer a cheap command that returns only the current branch name.
        ok, output = self._run_git(
            repo_dir, ["rev-parse", "--abbrev-ref", "HEAD"])
        if not ok:
            return AgentToolResult(tool_name, False, output)
        branch = (output or "").strip()
        if not branch:
            return AgentToolResult(tool_name, False, "Failed to determine current branch.")
        if branch == "HEAD":
            ok2, sha = self._run_git(
                repo_dir, ["rev-parse", "--short", "HEAD"])
            sha = (sha or "").strip() if ok2 else ""
            msg = f"detached HEAD" + (f" at {sha}" if sha else "")
            return AgentToolResult(tool_name, True, msg)
        return AgentToolResult(tool_name, True, branch)

    def _handle_git_branch(self, tool_name: str, params: Dict) -> AgentToolResult:
        try:
            validated = GitBranchParams(**params)
        except ValidationError as e:
            return AgentToolResult(tool_name, False, f"Invalid parameters: {e}")

        repo_dir = validated.repo_dir or Git.REPO_DIR
        args = ["branch"] + (["-a"] if validated.all else [])
        ok, output = self._run_git(repo_dir, args)
        return AgentToolResult(tool_name, ok, output)

    def _handle_git_checkout(self, tool_name: str, params: Dict) -> AgentToolResult:
        try:
            validated = GitCheckoutParams(**params)
        except ValidationError as e:
            return AgentToolResult(tool_name, False, f"Invalid parameters: {e}")

        repo_dir = validated.repo_dir or Git.REPO_DIR
        args = ["checkout", str(validated.branch)]
        ok, output = self._run_git(repo_dir, args)
        return AgentToolResult(tool_name, ok, output)

    def _handle_git_cherry_pick(self, tool_name: str, params: Dict) -> AgentToolResult:
        try:
            validated = GitCherryPickParams(**params)
        except ValidationError as e:
            return AgentToolResult(tool_name, False, f"Invalid parameters: {e}")

        repo_dir = validated.repo_dir or Git.REPO_DIR
        args = ["cherry-pick"] + [str(c) for c in validated.commits]
        ok, output = self._run_git(repo_dir, args)
        return AgentToolResult(tool_name, ok, output)

    def _handle_git_commit(self, tool_name: str, params: Dict) -> AgentToolResult:
        try:
            validated = GitCommitParams(**params)
        except ValidationError as e:
            return AgentToolResult(tool_name, False, f"Invalid parameters: {e}")

        repo_dir = validated.repo_dir or Git.REPO_DIR
        args = ["commit", "-m", str(validated.message), "--no-edit"]
        ok, output = self._run_git(repo_dir, args)
        return AgentToolResult(tool_name, ok, output)

    def _handle_git_add(self, tool_name: str, params: Dict) -> AgentToolResult:
        try:
            validated = GitAddParams(**params)
        except ValidationError as e:
            return AgentToolResult(tool_name, False, f"Invalid parameters: {e}")

        repo_dir = validated.repo_dir or Git.REPO_DIR
        args = ["add"] + [str(f) for f in validated.files]
        ok, output = self._run_git(repo_dir, args)
        return AgentToolResult(tool_name, ok, output)

    def _handle_run_command(self, tool_name: str, params: Dict) -> AgentToolResult:
        try:
            validated = RunCommandParams(**params)
        except ValidationError as e:
            return AgentToolResult(tool_name, False, f"Invalid parameters: {e}")

        working_dir = validated.working_dir or Git.REPO_DIR

        if not working_dir or not os.path.isdir(working_dir):
            return AgentToolResult(tool_name, False, f"Invalid working directory: {working_dir}")

        try:
            # Run the command using subprocess
            process = subprocess.Popen(
                validated.command,
                shell=True,
                cwd=working_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            try:
                stdout, stderr = process.communicate(timeout=validated.timeout)
            except subprocess.TimeoutExpired:
                process.kill()
                stdout, stderr = process.communicate()
                return AgentToolResult(
                    tool_name,
                    False,
                    f"Command timed out after {validated.timeout} seconds.\nPartial output:\n{stdout}\n{stderr}"
                )

            ok = process.returncode == 0
            output = (stdout or "")
            if stderr:
                if output:
                    output += "\n"
                output += stderr
            output = output.strip("\n")

            if not output:
                output = f"Command executed {'successfully' if ok else 'with errors'} (no output)."

            return AgentToolResult(tool_name, ok, output)

        except Exception as e:
            return AgentToolResult(tool_name, False, f"Failed to execute command: {e}")
