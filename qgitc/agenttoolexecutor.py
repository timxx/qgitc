# -*- coding: utf-8 -*-

from __future__ import annotations

import os
import subprocess
import sys
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Callable, Dict, List, Optional, Tuple

from PySide6.QtCore import QObject, Signal

from qgitc.agenttools import (
    AgentToolRegistry,
    ApplyPatchParams,
    CreateFileParams,
    GitAddParams,
    GitBlameParams,
    GitBranchParams,
    GitCheckoutParams,
    GitCherryPickParams,
    GitCommitParams,
    GitCurrentBranchParams,
    GitDiffParams,
    GitDiffRangeParams,
    GitDiffStagedParams,
    GitDiffUnstagedParams,
    GitLogParams,
    GitShowFileParams,
    GitShowIndexFileParams,
    GitShowParams,
    GitStatusParams,
    GrepSearchParams,
    ReadExternalFileParams,
    ReadFileParams,
    RunCommandParams,
)
from qgitc.basemodel import ValidationError
from qgitc.common import decodeFileData
from qgitc.gitutils import Git
from qgitc.tools.applypatch import DiffError, process_patch
from qgitc.tools.grepsearch import grepSearch
from qgitc.tools.readfile import (
    buildReadFileOutput,
    normalizeToolFilePath,
    resolveRepoPath,
)
from qgitc.tools.utils import detectBom, runGit


def _resolveToolRepoDir(repoDir: Optional[str]) -> Tuple[bool, str]:
    """Resolve an optional repoDir coming from a tool call.

    - If repoDir is empty/None: uses Git.REPO_DIR
    - If repoDir is relative: resolves it against Git.REPO_DIR
    - If repoDir is absolute: must stay within Git.REPO_DIR

    Returns (ok, abs_repo_dir_or_error).
    """

    baseRepoDir = Git.REPO_DIR
    if not baseRepoDir:
        return False, "No repository is currently opened."

    baseRepoDir = os.path.abspath(baseRepoDir)
    if not os.path.isdir(baseRepoDir):
        return False, f"Invalid repoDir: {baseRepoDir}"

    p = (repoDir or "").strip().strip('"').strip("'")
    p = normalizeToolFilePath(p) if p else ""

    candidate = baseRepoDir if not p else (
        p if os.path.isabs(p) else os.path.join(baseRepoDir, p))
    absRepoDir = os.path.abspath(candidate)

    try:
        baseReal = os.path.realpath(baseRepoDir)
        absReal = os.path.realpath(absRepoDir)
        common = os.path.commonpath([baseReal, absReal])
    except Exception:
        return False, f"Invalid repoDir: {repoDir}"

    if common != baseReal:
        return False, f"Refusing to access paths outside the repository: {repoDir}"

    if not os.path.isdir(absRepoDir):
        return False, f"Invalid repoDir: {absRepoDir}"

    return True, absRepoDir


def _runGit(repoDir: Optional[str], args: List[str]) -> Tuple[bool, str]:
    okRepo, absRepoDirOrErr = _resolveToolRepoDir(repoDir)
    if not okRepo:
        return False, absRepoDirOrErr

    ok, out, err = runGit(absRepoDirOrErr, [str(a) for a in args], text=True)
    output = out.strip("\n")

    # Only include stderr when the command fails.
    if not ok:
        errText = err.strip("\n")
        if errText:
            if output:
                output += "\n"
            output += errText

    return ok, output


class AgentToolResult:
    def __init__(self, toolName: str, ok: bool, output: str):
        self.toolName = toolName
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
            "git_diff_range": self._handle_git_diff_range,
            "git_diff_unstaged": self._handle_git_diff_unstaged,
            "git_diff_staged": self._handle_git_diff_staged,
            "git_show": self._handle_git_show,
            "git_show_file": self._handle_git_show_file,
            "git_show_index_file": self._handle_git_show_index_file,
            "git_blame": self._handle_git_blame,
            "git_current_branch": self._handle_git_current_branch,
            "git_branch": self._handle_git_branch,
            "git_checkout": self._handle_git_checkout,
            "git_cherry_pick": self._handle_git_cherry_pick,
            "git_commit": self._handle_git_commit,
            "git_add": self._handle_git_add,
            "run_command": self._handle_run_command,
            "read_file": self._handle_read_file,
            "read_external_file": self._handle_read_external_file,
            "grep_search": self._handle_grep_search,
            "create_file": self._handle_create_file,
            "apply_patch": self._handle_apply_patch,
        }

    @staticmethod
    def _normalizePatchPath(path: str) -> str:
        # Accept Windows paths from tool output and normalize quotes.
        p = (path or "").strip().strip('"').strip("'")
        return p

    @staticmethod
    def _resolveRepoPath(repoDir: str, filePath: str) -> Tuple[bool, str]:
        """Resolve filePath against repoDir and ensure it stays within the repo."""
        if not repoDir or not os.path.isdir(repoDir):
            return False, f"Invalid repo_dir: {repoDir}"

        if os.name == 'nt' and filePath.startswith('/') and filePath.find(':') != 1:
            # Handle Unix-style absolute paths on Windows (e.g. /C:/path/to/file).
            filePath = filePath.lstrip('/')

        if os.path.isabs(filePath):
            absPath = os.path.abspath(filePath)
        else:
            absPath = os.path.abspath(os.path.join(repoDir, filePath))

        try:
            repoRoot = os.path.abspath(repoDir)
            common = os.path.commonpath([repoRoot, absPath])
        except Exception:
            return False, f"Invalid file path: {filePath}"

        if common != repoRoot:
            return False, f"Refusing to access paths outside the repository: {filePath}"

        return True, absPath

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

        args = ["status", "--porcelain=v1", "-b"]
        if not validated.untracked:
            args.append("--untracked-files=no")
        ok, output = _runGit(validated.repoDir, args)
        if ok:
            # Porcelain v1 with -b typically includes a branch line like:
            #   ## main...origin/main [ahead 1]
            # If that's the only line, the working tree is clean.
            lines = output.splitlines()
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

        args = ["log", "--oneline"]
        if validated.nth:
            args += ["-n", "1", "--skip", str(validated.nth - 1)]
        else:
            args += ["-n", str(validated.maxCount)]

        if validated.since:
            args += ["--since", validated.since]
        if validated.until:
            args += ["--until", validated.until]
        if validated.nameStatus:
            args.append("--name-status")
        if validated.rev:
            args.append(validated.rev)

        if validated.path:
            if validated.follow:
                args.append("--follow")
            args += ["--", validated.path]

        ok, output = _runGit(validated.repoDir, args)
        if ok:
            if validated.nth:
                line = output.splitlines()[0].strip() if output.strip() else ""
                if line:
                    # Include explicit metadata so the LLM can trust this is the requested position.
                    label = f"nth={validated.nth} (1-based from HEAD)"
                    if validated.path:
                        label += f" (filtered by path={validated.path})"
                    return AgentToolResult(tool_name, True, f"{label}: {line}")
                return AgentToolResult(tool_name, False, f"No commit found at nth={validated.nth} (1-based from HEAD).")

        if ok and not output.strip():
            output = "No commits found."

        return AgentToolResult(tool_name, ok, output)

    def _handle_git_diff(self, tool_name: str, params: Dict) -> AgentToolResult:
        try:
            validated = GitDiffParams(**params)
        except ValidationError as e:
            return AgentToolResult(tool_name, False, f"Invalid parameters: {e}")

        args = ["diff-tree", "-r", "--root", validated.rev,
                "-p", "--textconv", "--submodule",
                "-C", "--no-commit-id", "-U3"]
        if validated.files:
            args += ["--"] + [str(f) for f in validated.files]
        ok, output = _runGit(validated.repoDir, args)
        if ok and not output.strip():
            output = "No differences found"
        return AgentToolResult(tool_name, ok, output)

    def _handle_git_diff_range(self, tool_name: str, params: Dict) -> AgentToolResult:
        try:
            validated = GitDiffRangeParams(**params)
        except ValidationError as e:
            return AgentToolResult(tool_name, False, f"Invalid parameters: {e}")

        args = ["diff"]
        if validated.nameStatus:
            args += ["--name-status"]
        else:
            args += [f"-U{validated.contextLines}"]

        if validated.findRenames:
            args += ["-M", "-C"]

        args.append(validated.rev)

        if validated.files:
            args += ["--"] + [f for f in validated.files]

        ok, output = _runGit(validated.repoDir, args)
        if ok and not output.strip():
            output = "No differences found"
        return AgentToolResult(tool_name, ok, output)

    def _handle_git_diff_unstaged(self, tool_name: str, params: Dict) -> AgentToolResult:
        try:
            validated = GitDiffUnstagedParams(**params)
        except ValidationError as e:
            return AgentToolResult(tool_name, False, f"Invalid parameters: {e}")

        if validated.nameOnly:
            args = ["diff", "--name-only"]
        else:
            args = ["diff-files", "-p", "--textconv",
                    "--submodule", "-C", "-U3"]
        if validated.files:
            args += ["--"] + [str(f) for f in validated.files]
        ok, output = _runGit(validated.repoDir, args)
        if not output:
            output = "No changed files found"
        return AgentToolResult(tool_name, ok, output)

    def _handle_git_diff_staged(self, tool_name: str, params: Dict) -> AgentToolResult:
        try:
            validated = GitDiffStagedParams(**params)
        except ValidationError as e:
            return AgentToolResult(tool_name, False, f"Invalid parameters: {e}")

        if validated.nameOnly:
            args = ["diff", "--name-only", "--cached"]
        else:
            args = ["diff-index", "--cached",
                    "HEAD", "-p", "--textconv",
                    "--submodule", "-C", "-U3"]
        if validated.files:
            args += ["--"] + [str(f) for f in validated.files]
        ok, output = _runGit(validated.repoDir, args)
        if not output:
            output = "No changed files found"
        return AgentToolResult(tool_name, ok, output)

    def _handle_git_show(self, tool_name: str, params: Dict) -> AgentToolResult:
        try:
            validated = GitShowParams(**params)
        except ValidationError as e:
            return AgentToolResult(tool_name, False, f"Invalid parameters: {e}")

        args = ["show", str(validated.rev)]
        ok, output = _runGit(validated.repoDir, args)
        return AgentToolResult(tool_name, ok, output)

    def _handle_git_show_file(self, tool_name: str, params: Dict) -> AgentToolResult:
        try:
            validated = GitShowFileParams(**params)
        except ValidationError as e:
            return AgentToolResult(tool_name, False, f"Invalid parameters: {e}")

        spec = f"{validated.rev}:{validated.path}"
        ok, output = _runGit(validated.repoDir, ["show", spec])
        if not ok:
            return AgentToolResult(tool_name, ok, output)

        lines = output.splitlines()
        start_line = validated.startLine - 1 if validated.startLine else 0
        end_line = validated.endLine if validated.endLine else len(lines)
        output = "\n".join(lines[start_line:end_line])

        return AgentToolResult(tool_name, ok, output)

    def _handle_git_show_index_file(self, tool_name: str, params: Dict) -> AgentToolResult:
        try:
            validated = GitShowIndexFileParams(**params)
        except ValidationError as e:
            return AgentToolResult(tool_name, False, f"Invalid parameters: {e}")

        spec = f":{validated.path}"
        ok, output = _runGit(validated.repoDir, ["show", spec])
        if not ok:
            return AgentToolResult(tool_name, ok, output)

        lines = output.splitlines()
        start_line = validated.startLine - 1 if validated.startLine else 0
        end_line = validated.endLine if validated.endLine else len(lines)
        output = "\n".join(lines[start_line:end_line])

        return AgentToolResult(tool_name, ok, output)

    def _handle_git_blame(self, tool_name: str, params: Dict) -> AgentToolResult:
        try:
            validated = GitBlameParams(**params)
        except ValidationError as e:
            return AgentToolResult(tool_name, False, f"Invalid parameters: {e}")

        args = ["blame"]
        if validated.ignoreWhitespace:
            args.append("-w")

        if validated.startLine and validated.endLine:
            args += ["-L",
                     f"{validated.startLine},{validated.endLine}"]
        elif validated.startLine and not validated.endLine:
            args += ["-L", f"{validated.startLine},"]
        elif validated.endLine:
            args += ["-L", f"1,{validated.endLine}"]

        if validated.rev:
            args.append(validated.rev)

        args += ["--", validated.path]

        ok, output = _runGit(validated.repoDir, args)
        if ok and not output.strip():
            output = "No blame output"
        return AgentToolResult(tool_name, ok, output)

    def _handle_git_current_branch(self, tool_name: str, params: Dict) -> AgentToolResult:
        try:
            validated = GitCurrentBranchParams(**params)
        except ValidationError as e:
            return AgentToolResult(tool_name, False, f"Invalid parameters: {e}")

        # Prefer a cheap command that returns only the current branch name.
        ok, output = _runGit(
            validated.repoDir, ["rev-parse", "--abbrev-ref", "HEAD"])
        if not ok:
            return AgentToolResult(tool_name, False, output)
        branch = output.strip()
        if not branch:
            return AgentToolResult(tool_name, False, "Failed to determine current branch.")
        if branch == "HEAD":
            ok2, sha = _runGit(validated.repoDir, ["rev-parse", "--short", "HEAD"])
            sha = (sha or "").strip() if ok2 else ""
            msg = f"detached HEAD" + (f" at {sha}" if sha else "")
            return AgentToolResult(tool_name, True, msg)
        return AgentToolResult(tool_name, True, branch)

    def _handle_git_branch(self, tool_name: str, params: Dict) -> AgentToolResult:
        try:
            validated = GitBranchParams(**params)
        except ValidationError as e:
            return AgentToolResult(tool_name, False, f"Invalid parameters: {e}")

        args = ["branch"] + (["-a"] if validated.all else [])
        ok, output = _runGit(validated.repoDir, args)
        return AgentToolResult(tool_name, ok, output)

    def _handle_git_checkout(self, tool_name: str, params: Dict) -> AgentToolResult:
        try:
            validated = GitCheckoutParams(**params)
        except ValidationError as e:
            return AgentToolResult(tool_name, False, f"Invalid parameters: {e}")

        args = ["checkout", str(validated.branch)]
        ok, output = _runGit(validated.repoDir, args)
        return AgentToolResult(tool_name, ok, output)

    def _handle_git_cherry_pick(self, tool_name: str, params: Dict) -> AgentToolResult:
        try:
            validated = GitCherryPickParams(**params)
        except ValidationError as e:
            return AgentToolResult(tool_name, False, f"Invalid parameters: {e}")

        args = ["cherry-pick"] + [str(c) for c in validated.commits]
        ok, output = _runGit(validated.repoDir, args)
        return AgentToolResult(tool_name, ok, output)

    def _handle_git_commit(self, tool_name: str, params: Dict) -> AgentToolResult:
        try:
            validated = GitCommitParams(**params)
        except ValidationError as e:
            return AgentToolResult(tool_name, False, f"Invalid parameters: {e}")

        args = ["commit", "-m", str(validated.message), "--no-edit"]
        ok, output = _runGit(validated.repoDir, args)
        return AgentToolResult(tool_name, ok, output)

    def _handle_git_add(self, tool_name: str, params: Dict) -> AgentToolResult:
        try:
            validated = GitAddParams(**params)
        except ValidationError as e:
            return AgentToolResult(tool_name, False, f"Invalid parameters: {e}")

        args = ["add"] + [str(f) for f in validated.files]
        ok, output = _runGit(validated.repoDir, args)
        return AgentToolResult(tool_name, ok, output)

    def _handle_run_command(self, tool_name: str, params: Dict) -> AgentToolResult:
        try:
            validated = RunCommandParams(**params)
        except ValidationError as e:
            return AgentToolResult(tool_name, False, f"Invalid parameters: {e}")

        working_dir = validated.workingDir or Git.REPO_DIR

        if not working_dir or not os.path.isdir(working_dir):
            return AgentToolResult(tool_name, False, f"Invalid working directory: {working_dir}")

        try:
            # Run the command using subprocess. On Windows, hide the console window.
            creationflags = 0
            if os.name == "nt":
                creationflags = subprocess.CREATE_NO_WINDOW

            process = subprocess.Popen(
                validated.command,
                shell=True,
                cwd=working_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                creationflags=creationflags
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
            output = (stdout or "").strip("\n")

            # Only include stderr when the command fails.
            if not ok:
                err_text = (stderr or "").strip("\n")
                if err_text:
                    if output:
                        output += "\n"
                    output += err_text

            if not output:
                output = f"Command executed {'successfully' if ok else 'with errors'} (no output)."

            return AgentToolResult(tool_name, ok, output)

        except Exception as e:
            return AgentToolResult(tool_name, False, f"Failed to execute command: {e}")

    def _handle_read_file(self, tool_name: str, params: Dict) -> AgentToolResult:
        try:
            validated = ReadFileParams(**params)
        except ValidationError as e:
            return AgentToolResult(tool_name, False, f"Invalid parameters: {e}")

        filePath = normalizeToolFilePath(validated.filePath)
        if not filePath:
            return AgentToolResult(tool_name, False, "filePath is required.")
        if not Git.REPO_DIR:
            return AgentToolResult(tool_name, False, "No repository is currently opened.")

        ok, absPathOrErr = resolveRepoPath(Git.REPO_DIR, filePath)
        if not ok:
            return AgentToolResult(tool_name, False, absPathOrErr)
        if not os.path.isfile(absPathOrErr):
            return AgentToolResult(tool_name, False, f"File does not exist: {absPathOrErr}")

        ok, outputOrErr = buildReadFileOutput(
            absPathOrErr, validated.startLine, validated.endLine)
        return AgentToolResult(tool_name, ok, outputOrErr)

    def _handle_read_external_file(self, tool_name: str, params: Dict) -> AgentToolResult:
        try:
            validated = ReadExternalFileParams(**params)
        except ValidationError as e:
            return AgentToolResult(tool_name, False, f"Invalid parameters: {e}")

        filePath = normalizeToolFilePath(validated.filePath)
        if not filePath:
            return AgentToolResult(tool_name, False, "filePath is required.")
        if not os.path.isabs(filePath):
            return AgentToolResult(tool_name, False, "read_external_file requires an absolute filePath.")

        absPath = os.path.abspath(filePath)
        if not os.path.isfile(absPath):
            return AgentToolResult(tool_name, False, f"File does not exist: {absPath}")

        ok, outputOrErr = buildReadFileOutput(
            absPath, validated.startLine, validated.endLine)
        return AgentToolResult(tool_name, ok, outputOrErr)

    def _handle_grep_search(self, tool_name: str, params: Dict) -> AgentToolResult:
        try:
            validated = GrepSearchParams(**params)
        except ValidationError as e:
            return AgentToolResult(tool_name, False, f"Invalid parameters: {e}")

        okRepo, repoDirOrErr = _resolveToolRepoDir(validated.repoDir)
        if not okRepo:
            return AgentToolResult(tool_name, False, repoDirOrErr)
        try:
            output = grepSearch(
                repoDir=repoDirOrErr,
                query=validated.query,
                isRegexp=validated.isRegexp,
                includeIgnoredFiles=validated.includeIgnoredFiles,
                includePattern=validated.includePattern,
                maxResults=(validated.maxResults or 10),
            )
        except Exception as e:
            return AgentToolResult(tool_name, False, str(e))

        return AgentToolResult(tool_name, True, output)

    def _handle_create_file(self, tool_name: str, params: Dict) -> AgentToolResult:
        try:
            validated = CreateFileParams(**params)
        except ValidationError as e:
            return AgentToolResult(tool_name, False, f"Invalid parameters: {e}")

        repoDir = Git.REPO_DIR
        filePath = self._normalizePatchPath(validated.filePath)
        ok, absPath = self._resolveRepoPath(repoDir, filePath)
        if not ok:
            return AgentToolResult(tool_name, False, absPath)

        if os.path.exists(absPath):
            return AgentToolResult(tool_name, False, f"File already exists: {absPath}")

        parent = os.path.dirname(absPath)
        try:
            os.makedirs(parent, exist_ok=True)
        except Exception as e:
            return AgentToolResult(tool_name, False, f"Failed to create directories: {e}")

        try:
            with open(absPath, 'w', encoding='utf-8', newline='\n') as f:
                f.write(validated.content)
            rel = os.path.relpath(absPath, repoDir)
            size = os.path.getsize(absPath)
            return AgentToolResult(tool_name, True, f"Created {rel} ({size} bytes).")
        except Exception as e:
            return AgentToolResult(tool_name, False, f"Failed to create file: {e}")

    def _handle_apply_patch(self, tool_name: str, params: Dict) -> AgentToolResult:
        try:
            validated = ApplyPatchParams(**params)
        except ValidationError as e:
            return AgentToolResult(tool_name, False, f"Invalid parameters: {e}")

        repoDir = Git.REPO_DIR
        if not repoDir or not os.path.isdir(repoDir):
            return AgentToolResult(tool_name, False, "No repository is currently opened.")

        patch_text = (validated.input or "").strip("\ufeff")
        if not patch_text.strip():
            return AgentToolResult(tool_name, False, "Patch is empty.")

        # Track per-file encoding/BOM so we can write patched content back without
        # changing encoding. Newlines are preserved by the patch engine.
        # Values are (bom_bytes_or_None, encoding_name).
        file_format: Dict[str, Tuple[Optional[bytes], str]] = {}

        def _probe_file_format(abs_path: str) -> Tuple[Optional[bytes], str, str]:
            """Return (bom, encoding, text) for an existing file."""
            with open(abs_path, 'rb') as fb:
                raw = fb.read()

            bom, bom_encoding = detectBom(abs_path)
            if bom:
                # Decode while stripping BOM bytes; we'll re-add BOM on write.
                raw_wo_bom = raw[len(bom):]
                enc_for_decode = bom_encoding
                # utf-8 BOM is typically handled via utf-8-sig; since we stripped the BOM,
                # decode with plain utf-8.
                if enc_for_decode == 'utf-8-sig':
                    enc_for_decode = 'utf-8'
                try:
                    text = raw_wo_bom.decode(enc_for_decode)
                    encoding = enc_for_decode
                except Exception:
                    # Fall back to our heuristic decoding for robustness.
                    text, encoding = decodeFileData(raw_wo_bom, enc_for_decode)
                    encoding = encoding or enc_for_decode
            else:
                # Heuristic decode for files without BOM.
                text, encoding = decodeFileData(raw, 'utf-8')
                encoding = encoding or 'utf-8'

            return bom, encoding, text

        def _open_file(path: str) -> str:
            filePath = self._normalizePatchPath(path)
            ok, absPath = self._resolveRepoPath(repoDir, filePath)
            if not ok:
                raise DiffError(absPath)

            if not os.path.isfile(absPath):
                raise DiffError(f"File does not exist: {filePath}")

            bom, encoding, text = _probe_file_format(absPath)
            # Cache format by the repo-relative patch path.
            file_format[filePath] = (bom, encoding)
            return text

        def _write_file(path: str, content: str, source_path: Optional[str] = None):
            filePath = self._normalizePatchPath(path)
            ok, absPath = self._resolveRepoPath(repoDir, filePath)
            if not ok:
                raise DiffError(absPath)
            parent = os.path.dirname(absPath)
            os.makedirs(parent, exist_ok=True)

            # Determine target format.
            fmt = file_format.get(filePath)
            if fmt is None and source_path:
                src = self._normalizePatchPath(source_path)
                fmt = file_format.get(src)

            if fmt is None and os.path.isfile(absPath):
                # Patch may write without ever having opened the file.
                bom, encoding, _ = _probe_file_format(absPath)
                fmt = (bom, encoding)

            if fmt is None:
                # New file: default to UTF-8.
                fmt = (None, 'utf-8')

            bom, encoding = fmt

            enc_for_bytes = encoding
            if bom and enc_for_bytes == 'utf-8-sig':
                enc_for_bytes = 'utf-8'

            try:
                payload = content.encode(enc_for_bytes)
            except UnicodeEncodeError as e:
                raise DiffError(
                    f"Failed to encode {filePath} as {enc_for_bytes}: {e}")

            with open(absPath, 'wb') as f:
                if bom:
                    f.write(bom)
                f.write(payload)

            # Update cache to reflect what we just wrote.
            file_format[filePath] = (bom, encoding)

        def _remove_file(path: str):
            filePath = self._normalizePatchPath(path)
            ok, absPath = self._resolveRepoPath(repoDir, filePath)
            if not ok:
                raise DiffError(absPath)
            if os.path.isfile(absPath):
                os.unlink(absPath)

        try:
            message = process_patch(
                patch_text, _open_file, _write_file, _remove_file)
            return AgentToolResult(tool_name, True, message)
        except DiffError as e:
            return AgentToolResult(tool_name, False, str(e))
        except Exception as e:
            return AgentToolResult(tool_name, False, f"Failed to apply patch: {e}")
