# -*- coding: utf-8 -*-

from __future__ import annotations

import json
import os
import subprocess
import sys
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Callable, Dict, Optional, Tuple

from PySide6.QtCore import QObject, Signal

from qgitc.agenttools import (
    AgentToolRegistry,
    ApplyPatchParams,
    CreateFileParams,
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
    GitShowFileParams,
    GitShowIndexFileParams,
    GitShowParams,
    GitStatusParams,
    GrepSearchParams,
    ReadFileParams,
    RunCommandParams,
)
from qgitc.basemodel import ValidationError
from qgitc.common import decodeFileData
from qgitc.gitutils import Git
from qgitc.tools.applypatch import DiffError, process_patch
from qgitc.tools.grepsearch import grepSearch
from qgitc.tools.utils import detectBom


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
            "git_diff_unstaged": self._handle_git_diff_unstaged,
            "git_diff_staged": self._handle_git_diff_staged,
            "git_show": self._handle_git_show,
            "git_show_file": self._handle_git_show_file,
            "git_show_index_file": self._handle_git_show_index_file,
            "git_current_branch": self._handle_git_current_branch,
            "git_branch": self._handle_git_branch,
            "git_checkout": self._handle_git_checkout,
            "git_cherry_pick": self._handle_git_cherry_pick,
            "git_commit": self._handle_git_commit,
            "git_add": self._handle_git_add,
            "run_command": self._handle_run_command,
            "read_file": self._handle_read_file,
            "grep_search": self._handle_grep_search,
            "create_file": self._handle_create_file,
            "apply_patch": self._handle_apply_patch,
        }

    @staticmethod
    def _normalize_patch_path(path: str) -> str:
        # Accept Windows paths from tool output and normalize quotes.
        p = (path or "").strip().strip('"').strip("'")
        return p

    @staticmethod
    def _resolve_repo_path(repo_dir: str, file_path: str) -> Tuple[bool, str]:
        """Resolve file_path against repo_dir and ensure it stays within the repo."""
        if not repo_dir or not os.path.isdir(repo_dir):
            return False, f"Invalid repo_dir: {repo_dir}"

        if os.name == 'nt' and file_path.startswith('/') and file_path.find(':') != 1:
            # Handle Unix-style absolute paths on Windows (e.g. /C:/path/to/file).
            file_path = file_path.lstrip('/')

        if os.path.isabs(file_path):
            abs_path = os.path.abspath(file_path)
        else:
            abs_path = os.path.abspath(os.path.join(repo_dir, file_path))

        try:
            repo_root = os.path.abspath(repo_dir)
            common = os.path.commonpath([repo_root, abs_path])
        except Exception:
            return False, f"Invalid file path: {file_path}"

        if common != repo_root:
            return False, f"Refusing to access paths outside the repository: {file_path}"

        return True, abs_path

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

        repo_dir = validated.repoDir or Git.REPO_DIR
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

        repo_dir = validated.repoDir or Git.REPO_DIR

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

        args = ["log", "--oneline", "-n", str(validated.maxCount)]
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

        repo_dir = validated.repoDir or Git.REPO_DIR
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

        repo_dir = validated.repoDir or Git.REPO_DIR
        if validated.nameOnly:
            args = ["diff", "--name-only"]
        else:
            args = ["diff-files", "-p", "--textconv",
                    "--submodule", "-C", "-U3"]
        if validated.files:
            args += ["--"] + [str(f) for f in validated.files]
        ok, output = self._run_git(repo_dir, args)
        if not output:
            output = "No changed files found"
        return AgentToolResult(tool_name, ok, output)

    def _handle_git_diff_staged(self, tool_name: str, params: Dict) -> AgentToolResult:
        try:
            validated = GitDiffStagedParams(**params)
        except ValidationError as e:
            return AgentToolResult(tool_name, False, f"Invalid parameters: {e}")

        repo_dir = validated.repoDir or Git.REPO_DIR
        if validated.nameOnly:
            args = ["diff", "--name-only", "--cached"]
        else:
            args = ["diff-index", "--cached",
                    "HEAD", "-p", "--textconv",
                    "--submodule", "-C", "-U3"]
        if validated.files:
            args += ["--"] + [str(f) for f in validated.files]
        ok, output = self._run_git(repo_dir, args)
        if not output:
            output = "No changed files found"
        return AgentToolResult(tool_name, ok, output)

    def _handle_git_show(self, tool_name: str, params: Dict) -> AgentToolResult:
        try:
            validated = GitShowParams(**params)
        except ValidationError as e:
            return AgentToolResult(tool_name, False, f"Invalid parameters: {e}")

        repo_dir = validated.repoDir or Git.REPO_DIR
        args = ["show", str(validated.rev)]
        ok, output = self._run_git(repo_dir, args)
        return AgentToolResult(tool_name, ok, output)

    def _handle_git_show_file(self, tool_name: str, params: Dict) -> AgentToolResult:
        try:
            validated = GitShowFileParams(**params)
        except ValidationError as e:
            return AgentToolResult(tool_name, False, f"Invalid parameters: {e}")

        repo_dir = validated.repoDir or Git.REPO_DIR
        spec = f"{validated.rev}:{validated.path}"
        ok, output = self._run_git(repo_dir, ["show", spec])
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

        repo_dir = validated.repoDir or Git.REPO_DIR
        spec = f":{validated.path}"
        ok, output = self._run_git(repo_dir, ["show", spec])
        if not ok:
            return AgentToolResult(tool_name, ok, output)

        lines = output.splitlines()
        start_line = validated.startLine - 1 if validated.startLine else 0
        end_line = validated.endLine if validated.endLine else len(lines)
        output = "\n".join(lines[start_line:end_line])

        return AgentToolResult(tool_name, ok, output)

    def _handle_git_current_branch(self, tool_name: str, params: Dict) -> AgentToolResult:
        try:
            validated = GitCurrentBranchParams(**params)
        except ValidationError as e:
            return AgentToolResult(tool_name, False, f"Invalid parameters: {e}")

        repo_dir = validated.repoDir or Git.REPO_DIR
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

        repo_dir = validated.repoDir or Git.REPO_DIR
        args = ["branch"] + (["-a"] if validated.all else [])
        ok, output = self._run_git(repo_dir, args)
        return AgentToolResult(tool_name, ok, output)

    def _handle_git_checkout(self, tool_name: str, params: Dict) -> AgentToolResult:
        try:
            validated = GitCheckoutParams(**params)
        except ValidationError as e:
            return AgentToolResult(tool_name, False, f"Invalid parameters: {e}")

        repo_dir = validated.repoDir or Git.REPO_DIR
        args = ["checkout", str(validated.branch)]
        ok, output = self._run_git(repo_dir, args)
        return AgentToolResult(tool_name, ok, output)

    def _handle_git_cherry_pick(self, tool_name: str, params: Dict) -> AgentToolResult:
        try:
            validated = GitCherryPickParams(**params)
        except ValidationError as e:
            return AgentToolResult(tool_name, False, f"Invalid parameters: {e}")

        repo_dir = validated.repoDir or Git.REPO_DIR
        args = ["cherry-pick"] + [str(c) for c in validated.commits]
        ok, output = self._run_git(repo_dir, args)
        return AgentToolResult(tool_name, ok, output)

    def _handle_git_commit(self, tool_name: str, params: Dict) -> AgentToolResult:
        try:
            validated = GitCommitParams(**params)
        except ValidationError as e:
            return AgentToolResult(tool_name, False, f"Invalid parameters: {e}")

        repo_dir = validated.repoDir or Git.REPO_DIR
        args = ["commit", "-m", str(validated.message), "--no-edit"]
        ok, output = self._run_git(repo_dir, args)
        return AgentToolResult(tool_name, ok, output)

    def _handle_git_add(self, tool_name: str, params: Dict) -> AgentToolResult:
        try:
            validated = GitAddParams(**params)
        except ValidationError as e:
            return AgentToolResult(tool_name, False, f"Invalid parameters: {e}")

        repo_dir = validated.repoDir or Git.REPO_DIR
        args = ["add"] + [str(f) for f in validated.files]
        ok, output = self._run_git(repo_dir, args)
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

    def _handle_read_file(self, tool_name: str, params: Dict) -> AgentToolResult:
        try:
            validated = ReadFileParams(**params)
        except ValidationError as e:
            return AgentToolResult(tool_name, False, f"Invalid parameters: {e}")

        # Allow absolute file paths outside the repository if the file exists.
        # Relative paths are still resolved relative to the opened repository.
        filePath = (validated.filePath or "").strip()
        if not filePath:
            return AgentToolResult(tool_name, False, "filePath is required.")

        # Normalize Unix-style absolute paths on Windows (e.g. /C:/path/to/file).
        if os.name == 'nt' and filePath.startswith('/') and filePath.find(':') != 1:
            filePath = filePath.lstrip('/')

        absPath: Optional[str] = None
        if os.path.isabs(filePath):
            candidateAbsPath = os.path.abspath(filePath)
            if os.path.isfile(candidateAbsPath):
                absPath = candidateAbsPath
            else:
                return AgentToolResult(tool_name, False, f"File does not exist: {candidateAbsPath}")
        else:
            if not Git.REPO_DIR:
                return AgentToolResult(tool_name, False, "No repository is currently opened.")
            candidatePath = os.path.join(Git.REPO_DIR, filePath)
            ok, resolved = self._resolve_repo_path(Git.REPO_DIR, candidatePath)
            if not ok:
                return AgentToolResult(tool_name, False, resolved)
            if not os.path.isfile(resolved):
                return AgentToolResult(tool_name, False, f"File does not exist: {resolved}")
            absPath = resolved

        try:
            with open(absPath, 'rb') as f:
                data = f.read()

            preferEncoding = detectBom(absPath)[1]
            text, _ = decodeFileData(data, preferEncoding)
            lines = text.splitlines(keepends=True)

            totalLines = len(lines)
            requestedStartLine = validated.startLine
            requestedEndLine = validated.endLine

            if requestedStartLine is not None and requestedEndLine is not None and \
                    requestedEndLine < requestedStartLine:
                return AgentToolResult(
                    tool_name,
                    False,
                    f"Invalid line range: endLine ({requestedEndLine}) is less than startLine ({requestedStartLine})."
                )

            # Tool convention: startLine/endLine are 1-based and endLine is inclusive.
            effectiveStartLine = requestedStartLine if requestedStartLine is not None else 1
            if effectiveStartLine < 1:
                effectiveStartLine = 1

            effectiveEndLine = requestedEndLine if requestedEndLine is not None else totalLines
            if effectiveEndLine < 0:
                effectiveEndLine = 0
            if effectiveEndLine > totalLines:
                effectiveEndLine = totalLines

            startIndex = max(effectiveStartLine - 1, 0)
            endIndex = max(effectiveEndLine, 0)
            selectedLines = lines[startIndex:endIndex]
            content = ''.join(selectedLines)

            meta = {
                "path": absPath,
                "totalLines": totalLines,
                "startLine": effectiveStartLine if totalLines > 0 and effectiveEndLine > 0 else 0,
                "endLine": effectiveEndLine if totalLines > 0 else 0,
            }

            # Keep metadata clearly separated from content to avoid confusing the LLM.
            output = "<<<METADATA>>>\n" + \
                json.dumps(meta, ensure_ascii=False) + \
                "\n<<<CONTENT>>>\n" + content
            return AgentToolResult(tool_name, True, output)

        except Exception as e:
            return AgentToolResult(tool_name, False, f"Failed to read file: {e}")

    def _handle_grep_search(self, tool_name: str, params: Dict) -> AgentToolResult:
        try:
            validated = GrepSearchParams(**params)
        except ValidationError as e:
            return AgentToolResult(tool_name, False, f"Invalid parameters: {e}")

        repoDir = validated.repoDir or Git.REPO_DIR
        try:
            output = grepSearch(
                repoDir=repoDir,
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

        repo_dir = Git.REPO_DIR
        file_path = self._normalize_patch_path(validated.filePath)
        ok, abs_path = self._resolve_repo_path(repo_dir, file_path)
        if not ok:
            return AgentToolResult(tool_name, False, abs_path)

        if os.path.exists(abs_path):
            return AgentToolResult(tool_name, False, f"File already exists: {abs_path}")

        parent = os.path.dirname(abs_path)
        try:
            os.makedirs(parent, exist_ok=True)
        except Exception as e:
            return AgentToolResult(tool_name, False, f"Failed to create directories: {e}")

        try:
            with open(abs_path, 'w', encoding='utf-8', newline='\n') as f:
                f.write(validated.content)
            rel = os.path.relpath(abs_path, repo_dir)
            size = os.path.getsize(abs_path)
            return AgentToolResult(tool_name, True, f"Created {rel} ({size} bytes).")
        except Exception as e:
            return AgentToolResult(tool_name, False, f"Failed to create file: {e}")

    def _handle_apply_patch(self, tool_name: str, params: Dict) -> AgentToolResult:
        try:
            validated = ApplyPatchParams(**params)
        except ValidationError as e:
            return AgentToolResult(tool_name, False, f"Invalid parameters: {e}")

        repo_dir = Git.REPO_DIR
        if not repo_dir or not os.path.isdir(repo_dir):
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
            file_path = self._normalize_patch_path(path)
            ok, abs_path = self._resolve_repo_path(repo_dir, file_path)
            if not ok:
                raise DiffError(abs_path)

            if not os.path.isfile(abs_path):
                raise DiffError(f"File does not exist: {file_path}")

            bom, encoding, text = _probe_file_format(abs_path)
            # Cache format by the repo-relative patch path.
            file_format[file_path] = (bom, encoding)
            return text

        def _write_file(path: str, content: str, source_path: Optional[str] = None):
            file_path = self._normalize_patch_path(path)
            ok, abs_path = self._resolve_repo_path(repo_dir, file_path)
            if not ok:
                raise DiffError(abs_path)
            parent = os.path.dirname(abs_path)
            os.makedirs(parent, exist_ok=True)

            # Determine target format.
            fmt = file_format.get(file_path)
            if fmt is None and source_path:
                src = self._normalize_patch_path(source_path)
                fmt = file_format.get(src)

            if fmt is None and os.path.isfile(abs_path):
                # Patch may write without ever having opened the file.
                bom, encoding, _ = _probe_file_format(abs_path)
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
                    f"Failed to encode {file_path} as {enc_for_bytes}: {e}")

            with open(abs_path, 'wb') as f:
                if bom:
                    f.write(bom)
                f.write(payload)

            # Update cache to reflect what we just wrote.
            file_format[file_path] = (bom, encoding)

        def _remove_file(path: str):
            file_path = self._normalize_patch_path(path)
            ok, abs_path = self._resolve_repo_path(repo_dir, file_path)
            if not ok:
                raise DiffError(abs_path)
            if os.path.isfile(abs_path):
                os.unlink(abs_path)

        try:
            message = process_patch(
                patch_text, _open_file, _write_file, _remove_file)
            return AgentToolResult(tool_name, True, message)
        except DiffError as e:
            return AgentToolResult(tool_name, False, str(e))
        except Exception as e:
            return AgentToolResult(tool_name, False, f"Failed to apply patch: {e}")
