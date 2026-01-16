# -*- coding: utf-8 -*-

from __future__ import annotations

import os
import sys
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Dict, Optional, Tuple

from PySide6.QtCore import QObject, Signal

from qgitc.agenttools import AgentToolRegistry
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
    def _repo_dir(params: Dict) -> Optional[str]:
        repo_dir = params.get("repo_dir") if isinstance(params, dict) else None
        if repo_dir:
            return repo_dir
        return Git.REPO_DIR

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

        repo_dir = self._repo_dir(params)

        if tool_name == "git_status":
            untracked = True
            if isinstance(params, dict) and "untracked" in params:
                untracked = bool(params.get("untracked"))
            args = ["status", "--porcelain=v1", "-b"]
            if not untracked:
                args.append("--untracked-files=no")
            ok, output = self._run_git(repo_dir, args)
            return AgentToolResult(tool_name, ok, output)

        if tool_name == "git_log":
            nth = None
            if isinstance(params, dict) and params.get("nth") is not None:
                try:
                    nth = int(params.get("nth"))
                except Exception:
                    nth = None

            if nth is not None:
                if nth < 1:
                    return AgentToolResult(tool_name, False, "Parameter nth must be >= 1")
                # Fetch exactly one commit, skipping the first (nth-1) commits.
                # This avoids returning commits 1..(nth-1) to the UI.
                args = ["log", "--oneline", "-n", "1", "--skip", str(nth - 1)]
                ok, output = self._run_git(repo_dir, args)
                if ok:
                    line = (output or "").splitlines()[
                        0].strip() if (output or "").strip() else ""
                    if line:
                        # Include explicit metadata so the LLM can trust this is the requested position.
                        return AgentToolResult(
                            tool_name,
                            True,
                            f"nth={nth} (1-based from HEAD): {line}",
                        )
                    return AgentToolResult(tool_name, False, f"No commit found at nth={nth} (1-based from HEAD).")
                return AgentToolResult(tool_name, False, output)

            max_count = 20
            if isinstance(params, dict) and params.get("max_count") is not None:
                try:
                    max_count = int(params.get("max_count"))
                except Exception:
                    max_count = 20
            max_count = max(1, min(200, max_count))
            args = ["log", "--oneline", "-n", str(max_count)]
            ok, output = self._run_git(repo_dir, args)
            return AgentToolResult(tool_name, ok, output)

        if tool_name == "git_diff":
            staged = bool(params.get("staged")) if isinstance(
                params, dict) else False
            args = ["diff"] + (["--staged"] if staged else [])
            ok, output = self._run_git(repo_dir, args)
            return AgentToolResult(tool_name, ok, output)

        if tool_name == "git_show":
            rev = params.get("rev") if isinstance(params, dict) else None
            if not rev:
                return AgentToolResult(tool_name, False, "Missing required parameter: rev")
            args = ["show", str(rev)]
            ok, output = self._run_git(repo_dir, args)
            return AgentToolResult(tool_name, ok, output)

        if tool_name == "git_branch":
            all_branches = bool(params.get("all")) if isinstance(
                params, dict) else False
            args = ["branch"] + (["-a"] if all_branches else [])
            ok, output = self._run_git(repo_dir, args)
            return AgentToolResult(tool_name, ok, output)

        if tool_name == "git_checkout":
            branch = params.get("branch") if isinstance(params, dict) else None
            if not branch:
                return AgentToolResult(tool_name, False, "Missing required parameter: branch")
            args = ["checkout", str(branch)]
            ok, output = self._run_git(repo_dir, args)
            return AgentToolResult(tool_name, ok, output)

        if tool_name == "git_cherry_pick":
            commits = params.get("commits") if isinstance(
                params, dict) else None
            if not commits or not isinstance(commits, list):
                return AgentToolResult(tool_name, False, "Missing required parameter: commits")
            args = ["cherry-pick"] + [str(c) for c in commits]
            ok, output = self._run_git(repo_dir, args)
            return AgentToolResult(tool_name, ok, output)

        return AgentToolResult(tool_name, False, f"Tool not implemented: {tool_name}")
