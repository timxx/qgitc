# -*- coding: utf-8 -*-

from __future__ import annotations

import os
import subprocess
import sys
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any, Callable, Dict, List, Optional, Tuple

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
    ReadFileParams,
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
            "create_file": self._handle_create_file,
            "apply_patch": self._handle_apply_patch,
        }

    @staticmethod
    def _normalize_patch_path(path: str) -> str:
        # Accept Windows paths from tool output and normalize quotes.
        p = (path or "").strip().strip('"').strip("'")
        return p

    @staticmethod
    def _read_text_file_lines(path: str) -> Tuple[List[str], bool, Optional[bytes], str]:
        """Return (lines_without_newlines, endswith_newline, bom_bytes, encoding)."""
        bom, encoding = AgentToolExecutor._detect_bom(path)
        with open(path, 'r', encoding=encoding) as f:
            text = f.read()
        endswith_newline = text.endswith('\n')
        lines = text.splitlines()
        return lines, endswith_newline, bom, encoding

    @staticmethod
    def _write_text_file_lines(path: str, lines: List[str], endswith_newline: bool, bom: Optional[bytes], encoding: str):
        text = "\n".join(lines)
        if endswith_newline:
            text += "\n"
        if bom is not None:
            encoded = text.encode(encoding.replace('-sig', ''))
            with open(path, 'wb') as f:
                f.write(bom)
                f.write(encoded)
        else:
            with open(path, 'w', encoding='utf-8', newline='\n') as f:
                f.write(text)

    @staticmethod
    def _find_subsequence(haystack: List[str], needle: List[str]) -> List[int]:
        if not needle:
            return []
        hits: List[int] = []
        n = len(needle)
        for i in range(0, len(haystack) - n + 1):
            if haystack[i:i + n] == needle:
                hits.append(i)
        return hits

    @staticmethod
    def _parse_v4a_patch(patch_text: str) -> Tuple[bool, str, List[Tuple[str, str, List[str]]]]:
        """Parse V4A patch and return list of (action, file_path, block_lines)."""
        text = (patch_text or "").lstrip("\ufeff")
        if "*** Begin Patch" not in text or "*** End Patch" not in text:
            return False, "Patch must include '*** Begin Patch' and '*** End Patch'.", []

        lines = text.splitlines()
        try:
            start = lines.index("*** Begin Patch") + 1
            end = lines.index("*** End Patch")
        except ValueError:
            return False, "Patch markers not found or malformed.", []

        content = lines[start:end]
        ops: List[Tuple[str, str, List[str]]] = []
        current: Optional[Dict[str, Any]] = None

        def flush():
            nonlocal current
            if current is not None:
                ops.append((
                    str(current.get("action") or ""),
                    str(current.get("file_path") or ""),
                    list(current.get("lines") or []),
                ))
                current = None

        for line in content:
            if line.startswith("*** ") and " File:" in line:
                flush()
                # Format: *** Update File: /path/to/file
                parts = line.split(" File:", 1)
                action_part = parts[0].replace("***", "").strip()
                action = action_part.split()[0]
                file_path = AgentToolExecutor._normalize_patch_path(
                    parts[1].lstrip(":").strip())
                current = {"action": action,
                           "file_path": file_path, "lines": []}
                continue

            if current is None:
                # Ignore stray lines between headers.
                continue

            current["lines"].append(line)

        flush()

        # Basic validation
        for action, file_path, _ in ops:
            if action not in ("Add", "Update", "Delete"):
                return False, f"Unsupported patch action: {action}", []
            if not file_path:
                return False, "Patch contains an empty file path.", []

        if not ops:
            return False, "Patch contains no file operations.", []

        return True, "ok", ops

    @staticmethod
    def _apply_v4a_update(abs_path: str, block_lines: List[str]) -> Tuple[bool, str]:
        if not os.path.isfile(abs_path):
            return False, f"File does not exist for update: {abs_path}"

        file_lines, endswith_newline, bom, encoding = AgentToolExecutor._read_text_file_lines(
            abs_path)

        # Build edit blocks.
        context: List[str] = []
        edits = []  # list of (pre, old, new, post)
        in_change = False
        pre: List[str] = []
        old: List[str] = []
        new: List[str] = []
        post: List[str] = []

        def finalize():
            nonlocal in_change, pre, old, new, post
            if in_change and (old or new):
                edits.append((pre[-3:], old, new, post[:3]))
            in_change = False
            pre = []
            old = []
            new = []
            post = []

        for line in block_lines:
            if line.startswith("@@"):
                continue
            if line.startswith("-") or line.startswith("+"):
                if not in_change:
                    pre = context[:]  # snapshot
                    in_change = True
                if post:
                    # A new change block starts after post-context.
                    finalize()
                    pre = context[:]
                    in_change = True
                if line.startswith("-"):
                    old.append(line[1:])
                else:
                    new.append(line[1:])
                continue

            # Plain context line
            if in_change and (old or new):
                post.append(line)
            context.append(line)

        finalize()

        if not edits:
            return False, "No edits found in Update block (need '-'/'+' lines)."

        # Apply edits sequentially.
        for pre3, old_lines, new_lines, post3 in edits:
            target = pre3 + old_lines + post3
            hits = AgentToolExecutor._find_subsequence(
                file_lines, target) if target else []
            if len(hits) == 1:
                i = hits[0] + len(pre3)
                file_lines[i:i + len(old_lines)] = new_lines
                continue

            # Fallback: match old_lines only.
            hits_old = AgentToolExecutor._find_subsequence(
                file_lines, old_lines)
            if len(hits_old) == 1:
                i = hits_old[0]
                file_lines[i:i + len(old_lines)] = new_lines
                continue

            if not hits and not hits_old:
                snippet = "\\n".join(old_lines[:10])
                return False, f"Failed to apply edit: old content not found. Snippet:\n{snippet}"
            return False, "Failed to apply edit: patch context is ambiguous (multiple matches)."

        AgentToolExecutor._write_text_file_lines(
            abs_path, file_lines, endswith_newline, bom, encoding)
        return True, "Patch applied."

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

    @staticmethod
    def _detect_bom(path: str) -> Tuple[Optional[bytes], str]:
        """Return (bom_bytes, encoding_name_for_text) for common Unicode BOMs."""
        try:
            with open(path, 'rb') as fb:
                head = fb.read(4)
        except Exception:
            return None, 'utf-8'

        if head.startswith(b'\xff\xfe\x00\x00'):
            return b'\xff\xfe\x00\x00', 'utf-32-le'
        if head.startswith(b'\x00\x00\xfe\xff'):
            return b'\x00\x00\xfe\xff', 'utf-32-be'
        if head.startswith(b'\xff\xfe'):
            return b'\xff\xfe', 'utf-16-le'
        if head.startswith(b'\xfe\xff'):
            return b'\xfe\xff', 'utf-16-be'
        if head.startswith(b'\xef\xbb\xbf'):
            return b'\xef\xbb\xbf', 'utf-8-sig'

        return None, 'utf-8'

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

    def _handle_git_show_file(self, tool_name: str, params: Dict) -> AgentToolResult:
        try:
            validated = GitShowFileParams(**params)
        except ValidationError as e:
            return AgentToolResult(tool_name, False, f"Invalid parameters: {e}")

        repo_dir = validated.repo_dir or Git.REPO_DIR
        spec = f"{validated.rev}:{validated.path}"
        ok, output = self._run_git(repo_dir, ["show", spec])
        if not ok:
            return AgentToolResult(tool_name, ok, output)

        lines = output.splitlines()
        start_line = validated.start_line - 1 if validated.start_line else 0
        end_line = validated.end_line if validated.end_line else len(lines)
        output = "\n".join(lines[start_line:end_line])

        return AgentToolResult(tool_name, ok, output)

    def _handle_git_show_index_file(self, tool_name: str, params: Dict) -> AgentToolResult:
        try:
            validated = GitShowIndexFileParams(**params)
        except ValidationError as e:
            return AgentToolResult(tool_name, False, f"Invalid parameters: {e}")

        repo_dir = validated.repo_dir or Git.REPO_DIR
        spec = f":{validated.path}"
        ok, output = self._run_git(repo_dir, ["show", spec])
        if not ok:
            return AgentToolResult(tool_name, ok, output)

        lines = output.splitlines()
        start_line = validated.start_line - 1 if validated.start_line else 0
        end_line = validated.end_line if validated.end_line else len(lines)
        output = "\n".join(lines[start_line:end_line])

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

    def _handle_read_file(self, tool_name: str, params: Dict) -> AgentToolResult:
        try:
            validated = ReadFileParams(**params)
        except ValidationError as e:
            return AgentToolResult(tool_name, False, f"Invalid parameters: {e}")

        file_path = validated.file_path
        if not os.path.isabs(file_path):
            file_path = os.path.join(Git.REPO_DIR, file_path)

        ok, abs_path = self._resolve_repo_path(Git.REPO_DIR, file_path)
        if not ok:
            return AgentToolResult(tool_name, False, abs_path)

        if not os.path.isfile(abs_path):
            return AgentToolResult(tool_name, False, f"File does not exist: {abs_path}")

        try:
            encoding = AgentToolExecutor._detect_bom(abs_path)[1]
            with open(abs_path, 'r', encoding=encoding) as f:
                lines = f.readlines()

            start_line = validated.start_line - 1 if validated.start_line else 0
            end_line = validated.end_line if validated.end_line else len(lines)

            selected_lines = lines[start_line:end_line]
            output = ''.join(selected_lines).strip('\n')

            return AgentToolResult(tool_name, True, output)

        except Exception as e:
            return AgentToolResult(tool_name, False, f"Failed to read file: {e}")

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

        ok, msg, ops = self._parse_v4a_patch(patch_text)
        if not ok:
            return AgentToolResult(tool_name, False, msg)

        applied = 0
        for action, path, block in ops:
            file_path = self._normalize_patch_path(path)
            ok2, abs_path = self._resolve_repo_path(repo_dir, file_path)
            if not ok2:
                return AgentToolResult(tool_name, False, abs_path)

            if action == "Add":
                if os.path.exists(abs_path):
                    return AgentToolResult(tool_name, False, f"File already exists: {abs_path}")
                parent = os.path.dirname(abs_path)
                os.makedirs(parent, exist_ok=True)
                # For Add, treat '+' lines as file content.
                content_lines = [ln[1:] for ln in block if ln.startswith("+")]
                with open(abs_path, 'w', encoding='utf-8', newline='\n') as f:
                    f.write("\n".join(content_lines) +
                            ("\n" if content_lines else ""))
                applied += 1
                continue

            if action == "Delete":
                if not os.path.exists(abs_path):
                    return AgentToolResult(tool_name, False, f"File does not exist for delete: {abs_path}")
                if os.path.isdir(abs_path):
                    return AgentToolResult(tool_name, False, f"Refusing to delete a directory: {abs_path}")
                os.remove(abs_path)
                applied += 1
                continue

            # Update
            ok3, msg3 = self._apply_v4a_update(abs_path, block)
            if not ok3:
                return AgentToolResult(tool_name, False, msg3)
            applied += 1

        return AgentToolResult(tool_name, True, f"Applied {applied} patch operation(s).")
