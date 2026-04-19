# -*- coding: utf-8 -*-

import os
import pathlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from qgitc.agent.tool import Tool, ToolContext, ToolResult
from qgitc.agent.tools.utils import detectBom
from qgitc.common import decodeFileData

# see https://cookbook.openai.com/examples/gpt4-1_prompting_guide#reference-implementation-apply_patchpy

APPLY_PATCH_TOOL_DESC = """Edit text files. `apply_patch` effectively allows you to execute a diff/patch against a file, but the format of the diff specification is unique to this task, so pay careful attention to these instructions. To use the `apply_patch` command, you should pass a message of the following structure as "input":

*** Begin Patch
[YOUR_PATCH]
*** End Patch

Where [YOUR_PATCH] is the actual content of your patch, specified in the following V4A diff format.

*** [ACTION] File: [/absolute/path/to/file] -> ACTION can be one of Add, Update, or Delete.
For each snippet of code that needs to be changed, repeat the following:
[context_before] -> See below for further instructions on context.
-[old_code] -> Precede the old code with a minus sign.
+[new_code] -> Precede the new, replacement code with a plus sign.
[context_after] -> See below for further instructions on context.

For instructions on [context_before] and [context_after]:
- By default, show 3 lines of code immediately above and 3 lines immediately below each change. If a change is within 3 lines of a previous change, do NOT duplicate the first change’s [context_after] lines in the second change’s [context_before] lines.
- If 3 lines of context is insufficient to uniquely identify the snippet of code within the file, use the @@ operator to indicate the class or function to which the snippet belongs. For instance, we might have:
@@class BaseClass
[3 lines of pre-context]
-[old_code]
+[new_code]
[3 lines of post-context]

- If a code block is repeated so many times in a class or function such that even a single @@ statement and 3 lines of context cannot uniquely identify the snippet of code, you can use multiple `@@` statements to jump to the right context. For instance:

@@class BaseClass
@@	def method():
[3 lines of pre-context]
-[old_code]
+[new_code]
[3 lines of post-context]

An example of a message that you might pass as "input" to this function, in order to apply a patch, is shown below.

*** Begin Patch
*** Update File: /Users/someone/pygorithm/searching/binary_search.py
@@class BaseClass
@@    def search():
-        pass
+        raise NotImplementedError()

@@class Subclass
@@    def search():
-        pass
+        raise NotImplementedError()

*** End Patch

Do not use line numbers in this diff format.

You must use the same indentation style as the original code. If the original code uses tabs, you must use tabs. If the original code uses spaces, you must use spaces. Be sure to use a proper UNESCAPED tab character.
"""


# --------------------------------------------------------------------------- #
#  Domain objects
# --------------------------------------------------------------------------- #
class ActionType(str, Enum):
    ADD = "add"
    DELETE = "delete"
    UPDATE = "update"


@dataclass
class FileChange:
    type: ActionType
    old_content: Optional[str] = None
    new_content: Optional[str] = None
    move_path: Optional[str] = None


@dataclass
class Commit:
    changes: Dict[str, FileChange] = field(default_factory=dict)


# --------------------------------------------------------------------------- #
#  Exceptions
# --------------------------------------------------------------------------- #
class DiffError(ValueError):
    """Any problem detected while parsing or applying a patch."""


# --------------------------------------------------------------------------- #
#  Helper dataclasses used while parsing patches
# --------------------------------------------------------------------------- #
@dataclass
class Chunk:
    orig_index: int = -1
    del_lines: List[str] = field(default_factory=list)
    ins_lines: List[str] = field(default_factory=list)


@dataclass
class PatchAction:
    type: ActionType
    new_file: Optional[str] = None
    chunks: List[Chunk] = field(default_factory=list)
    move_path: Optional[str] = None


@dataclass
class Patch:
    actions: Dict[str, PatchAction] = field(default_factory=dict)


# --------------------------------------------------------------------------- #
#  Patch text parser
# --------------------------------------------------------------------------- #
@dataclass
class Parser:
    current_files: Dict[str, str]
    lines: List[str]
    index: int = 0
    patch: Patch = field(default_factory=Patch)
    fuzz: int = 0

    # ------------- low-level helpers -------------------------------------- #
    def _cur_line(self) -> str:
        if self.index >= len(self.lines):
            raise DiffError("Unexpected end of input while parsing patch")
        return self.lines[self.index]

    @staticmethod
    def _norm(line: str) -> str:
        """Strip CR so comparisons work for both LF and CRLF input."""
        return line.rstrip("\r")

    # ------------- scanning convenience ----------------------------------- #
    def isDone(self, prefixes: Optional[Tuple[str, ...]] = None) -> bool:
        if self.index >= len(self.lines):
            return True
        if (
            prefixes
            and len(prefixes) > 0
            and self._norm(self._cur_line()).startswith(prefixes)
        ):
            return True
        return False

    def startswith(self, prefix: Union[str, Tuple[str, ...]]) -> bool:
        return self._norm(self._cur_line()).startswith(prefix)

    def readStr(self, prefix: str) -> str:
        """
        Consume the current line if it starts with *prefix* and return the text
        **after** the prefix.  Raises if prefix is empty.
        """
        if prefix == "":
            raise ValueError("read_str() requires a non-empty prefix")
        if self._norm(self._cur_line()).startswith(prefix):
            text = self._cur_line()[len(prefix):]
            self.index += 1
            return text
        return ""

    def readLine(self) -> str:
        """Return the current raw line and advance."""
        line = self._cur_line()
        self.index += 1
        return line

    # ------------- public entry point -------------------------------------- #
    def parse(self) -> None:
        while not self.isDone(("*** End Patch",)):
            # ---------- UPDATE ---------- #
            path = self.readStr("*** Update File: ")
            if path:
                if path in self.patch.actions:
                    raise DiffError(f"Duplicate update for file: {path}")
                move_to = self.readStr("*** Move to: ")
                if path not in self.current_files:
                    raise DiffError(
                        f"Update File Error - missing file: {path}")
                text = self.current_files[path]
                action = self._parse_update_file(text)
                action.move_path = move_to or None
                self.patch.actions[path] = action
                continue

            # ---------- DELETE ---------- #
            path = self.readStr("*** Delete File: ")
            if path:
                if path in self.patch.actions:
                    raise DiffError(f"Duplicate delete for file: {path}")
                if path not in self.current_files:
                    raise DiffError(
                        f"Delete File Error - missing file: {path}")
                self.patch.actions[path] = PatchAction(type=ActionType.DELETE)
                continue

            # ---------- ADD ---------- #
            path = self.readStr("*** Add File: ")
            if path:
                if path in self.patch.actions:
                    raise DiffError(f"Duplicate add for file: {path}")
                if path in self.current_files:
                    raise DiffError(
                        f"Add File Error - file already exists: {path}")
                self.patch.actions[path] = self._parse_add_file()
                continue

            raise DiffError(f"Unknown line while parsing: {self._cur_line()}")

        if not self.startswith("*** End Patch"):
            raise DiffError("Missing *** End Patch sentinel")
        self.index += 1  # consume sentinel

    # ------------- section parsers ---------------------------------------- #
    def _parse_update_file(self, text: str) -> PatchAction:
        action = PatchAction(type=ActionType.UPDATE)
        lines = text.split("\n")
        index = 0
        while not self.isDone(
            (
                "*** End Patch",
                "*** Update File:",
                "*** Delete File:",
                "*** Add File:",
                "*** End of File",
            )
        ):
            def_str = self.readStr("@@ ")
            if not def_str:
                # Accept anchors without a space after '@@' (e.g. '@@void foo()').
                cur = self._norm(self._cur_line())
                if cur.startswith("@@") and cur != "@@":
                    def_str = self.readStr("@@")
            section_str = ""
            if not def_str and self._norm(self._cur_line()) == "@@":
                section_str = self.readLine()

            if not (def_str or section_str or index == 0):
                raise DiffError(
                    f"Invalid line in update section:\n{self._cur_line()}")

            if def_str.strip():
                found = False
                if def_str not in lines[:index]:
                    for i, s in enumerate(lines[index:], index):
                        if s == def_str:
                            index = i + 1
                            found = True
                            break
                if not found and def_str.strip() not in [
                    s.strip() for s in lines[:index]
                ]:
                    for i, s in enumerate(lines[index:], index):
                        if s.strip() == def_str.strip():
                            index = i + 1
                            self.fuzz += 1
                            found = True
                            break

            next_ctx, chunks, end_idx, eof = peekNextSection(
                self.lines, self.index)
            new_index, fuzz = findContext(lines, next_ctx, index, eof)
            if new_index == -1:
                ctx_txt = "\n".join(next_ctx)
                raise DiffError(
                    f"Invalid {'EOF ' if eof else ''}context at {index}:\n{ctx_txt}"
                )
            self.fuzz += fuzz
            for ch in chunks:
                ch.orig_index += new_index
                action.chunks.append(ch)
            index = new_index + len(next_ctx)
            self.index = end_idx
        return action

    def _parse_add_file(self) -> PatchAction:
        lines: List[str] = []
        while not self.isDone(
            ("*** End Patch", "*** Update File:",
             "*** Delete File:", "*** Add File:")
        ):
            s = self.readLine()
            if not s.startswith("+"):
                raise DiffError(f"Invalid Add File line (missing '+'): {s}")
            lines.append(s[1:])  # strip leading '+'
        return PatchAction(type=ActionType.ADD, new_file="\n".join(lines))


# --------------------------------------------------------------------------- #
#  Helper functions
# --------------------------------------------------------------------------- #
def findContextCore(
    lines: List[str], context: List[str], start: int
) -> Tuple[int, int]:
    if not context:
        return start, 0

    for i in range(start, len(lines)):
        if lines[i: i + len(context)] == context:
            return i, 0
    for i in range(start, len(lines)):
        if [s.rstrip() for s in lines[i: i + len(context)]] == [
            s.rstrip() for s in context
        ]:
            return i, 1
    for i in range(start, len(lines)):
        if [s.strip() for s in lines[i: i + len(context)]] == [
            s.strip() for s in context
        ]:
            return i, 100
    return -1, 0


def findContext(
    lines: List[str], context: List[str], start: int, eof: bool
) -> Tuple[int, int]:
    if eof:
        new_index, fuzz = findContextCore(
            lines, context, len(lines) - len(context))
        if new_index != -1:
            return new_index, fuzz
        new_index, fuzz = findContextCore(lines, context, start)
        return new_index, fuzz + 10_000
    return findContextCore(lines, context, start)


def peekNextSection(
    lines: List[str], index: int
) -> Tuple[List[str], List[Chunk], int, bool]:
    old: List[str] = []
    del_lines: List[str] = []
    ins_lines: List[str] = []
    chunks: List[Chunk] = []
    mode = "keep"
    orig_index = index

    while index < len(lines):
        s = lines[index]
        if s.startswith(
            (
                "@@",
                "*** End Patch",
                "*** Update File:",
                "*** Delete File:",
                "*** Add File:",
                "*** End of File",
            )
        ):
            break
        if s == "***":
            break
        if s.startswith("***"):
            raise DiffError(f"Invalid Line: {s}")
        index += 1

        last_mode = mode
        if s == "":
            s = " "
        if s[0] == "+":
            mode = "add"
        elif s[0] == "-":
            mode = "delete"
        elif s[0] == " ":
            mode = "keep"
        else:
            raise DiffError(f"Invalid Line: {s}")
        s = s[1:]

        if mode == "keep" and last_mode != mode:
            if ins_lines or del_lines:
                chunks.append(
                    Chunk(
                        orig_index=len(old) - len(del_lines),
                        del_lines=del_lines,
                        ins_lines=ins_lines,
                    )
                )
            del_lines, ins_lines = [], []

        if mode == "delete":
            del_lines.append(s)
            old.append(s)
        elif mode == "add":
            ins_lines.append(s)
        elif mode == "keep":
            old.append(s)

    if ins_lines or del_lines:
        chunks.append(
            Chunk(
                orig_index=len(old) - len(del_lines),
                del_lines=del_lines,
                ins_lines=ins_lines,
            )
        )

    if index < len(lines) and lines[index] == "*** End of File":
        index += 1
        return old, chunks, index, True

    if index == orig_index:
        raise DiffError("Nothing in this section")
    return old, chunks, index, False


# --------------------------------------------------------------------------- #
#  Patch → Commit and Commit application
# --------------------------------------------------------------------------- #
def _get_updated_file(text: str, action: PatchAction, path: str) -> str:
    if action.type is not ActionType.UPDATE:
        raise DiffError("_get_updated_file called with non-update action")
    orig_lines = text.split("\n")
    dest_lines: List[str] = []
    orig_index = 0

    def _has_cr(line: str) -> bool:
        # For CRLF files, splitting on '\n' keeps '\r' at the end of each line.
        return line.endswith("\r")

    def _choose_cr(insert_at: int, del_count: int) -> bool:
        # Prefer CRLF for inserted lines when the nearby original lines use CRLF.
        if del_count > 0 and insert_at < len(orig_lines):
            end = min(insert_at + del_count, len(orig_lines))
            window = orig_lines[insert_at:end]
            if window:
                cr_votes = sum(1 for l in window if _has_cr(l))
                return cr_votes * 2 >= len(window)

        if insert_at > 0:
            return _has_cr(orig_lines[insert_at - 1])
        if insert_at < len(orig_lines):
            return _has_cr(orig_lines[insert_at])
        return False

    for chunk in action.chunks:
        if chunk.orig_index > len(orig_lines):
            raise DiffError(
                f"{path}: chunk.orig_index {chunk.orig_index} exceeds file length"
            )
        if orig_index > chunk.orig_index:
            raise DiffError(
                f"{path}: overlapping chunks at {orig_index} > {chunk.orig_index}"
            )

        dest_lines.extend(orig_lines[orig_index: chunk.orig_index])
        orig_index = chunk.orig_index

        want_cr = _choose_cr(chunk.orig_index, len(chunk.del_lines))
        if want_cr:
            dest_lines.extend([
                (s if s.endswith("\r") else (s + "\r")) for s in chunk.ins_lines
            ])
        else:
            dest_lines.extend([
                (s[:-1] if s.endswith("\r") else s) for s in chunk.ins_lines
            ])
        orig_index += len(chunk.del_lines)

    dest_lines.extend(orig_lines[orig_index:])
    return "\n".join(dest_lines)


def patchToCommit(patch: Patch, orig: Dict[str, str]) -> Commit:
    commit = Commit()
    for path, action in patch.actions.items():
        if action.type is ActionType.DELETE:
            commit.changes[path] = FileChange(
                type=ActionType.DELETE, old_content=orig[path]
            )
        elif action.type is ActionType.ADD:
            if action.new_file is None:
                raise DiffError("ADD action without file content")
            commit.changes[path] = FileChange(
                type=ActionType.ADD, new_content=action.new_file
            )
        elif action.type is ActionType.UPDATE:
            new_content = _get_updated_file(orig[path], action, path)
            commit.changes[path] = FileChange(
                type=ActionType.UPDATE,
                old_content=orig[path],
                new_content=new_content,
                move_path=action.move_path,
            )
    return commit


# --------------------------------------------------------------------------- #
#  User-facing helpers
# --------------------------------------------------------------------------- #
def textToPatch(lines: List[str], orig: Dict[str, str]) -> Tuple[Patch, int]:
    if (
        len(lines) < 2
        or not Parser._norm(lines[0]).startswith("*** Begin Patch")
        or Parser._norm(lines[-1]) != "*** End Patch"
    ):
        raise DiffError("Invalid patch text - missing sentinels")

    parser = Parser(current_files=orig, lines=lines, index=1)
    parser.parse()
    return parser.patch, parser.fuzz


def identifyFilesNeeded(lines: List[str]) -> List[str]:
    return [
        line[len("*** Update File: "):]
        for line in lines
        if line.startswith("*** Update File: ")
    ] + [
        line[len("*** Delete File: "):]
        for line in lines
        if line.startswith("*** Delete File: ")
    ]


# --------------------------------------------------------------------------- #
#  File-system helpers
# --------------------------------------------------------------------------- #
def loadFiles(paths: List[str], open_fn: Callable[[str], str]) -> Dict[str, str]:
    return {path: open_fn(path) for path in paths}


def applyCommit(
    commit: Commit,
    write_fn: Callable[[str, str, Optional[str]], None],
    remove_fn: Callable[[str], None],
) -> None:
    for path, change in commit.changes.items():
        if change.type is ActionType.DELETE:
            remove_fn(path)
        elif change.type is ActionType.ADD:
            if change.new_content is None:
                raise DiffError(f"ADD change for {path} has no content")
            write_fn(path, change.new_content, None)
        elif change.type is ActionType.UPDATE:
            if change.new_content is None:
                raise DiffError(f"UPDATE change for {path} has no new content")
            target = change.move_path or path
            write_fn(target, change.new_content, path)
            if change.move_path:
                remove_fn(path)


def processPatch(
    text: str,
    open_fn: Callable[[str], str],
    write_fn: Callable[[str, str, Optional[str]], None],
    remove_fn: Callable[[str], None],
) -> str:
    if not text.startswith("*** Begin Patch"):
        raise DiffError("Patch text must start with *** Begin Patch")
    text_lines = text.splitlines()
    paths = identifyFilesNeeded(text_lines)
    orig = loadFiles(paths, open_fn)
    patch, _fuzz = textToPatch(text_lines, orig)
    commit = patchToCommit(patch, orig)
    applyCommit(commit, write_fn, remove_fn)
    return "Done!"


# --------------------------------------------------------------------------- #
#  Default FS helpers
# --------------------------------------------------------------------------- #
def openFile(path: str) -> str:
    with open(path, "rt", encoding="utf-8") as fh:
        return fh.read()


def writeFile(path: str, content: str, source_path: Optional[str] = None) -> None:
    target = pathlib.Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("wt", encoding="utf-8") as fh:
        fh.write(content)


def removeFile(path: str) -> None:
    pathlib.Path(path).unlink(missing_ok=True)


class ApplyPatchTool(Tool):
    name = "apply_patch"
    description = APPLY_PATCH_TOOL_DESC

    def isReadOnly(self):
        return False

    def execute(self, input_data: Dict[str, Any], context: ToolContext) -> ToolResult:
        patch_input = input_data.get("input")
        if not patch_input:
            return ToolResult(content="input is required.", is_error=True)

        repoDir = context.working_directory
        if not repoDir or not os.path.isdir(repoDir):
            return ToolResult(
                content="No repository is currently opened.", is_error=True
            )

        patch_text = (patch_input or "").strip("\ufeff")
        if not patch_text.strip():
            return ToolResult(content="Patch is empty.", is_error=True)

        # Track per-file encoding/BOM so we can write patched content back
        # without changing encoding. Newlines are preserved by the patch engine.
        # Values are (bom_bytes_or_None, encoding_name).
        file_format = {}  # type: Dict[str, Tuple[Optional[bytes], str]]

        def _normalize_path(path):
            # type: (str) -> str
            """Accept Windows paths from tool output and normalize quotes."""
            p = (path or "").strip().strip('"').strip("'")
            return p

        def _resolve_repo_path(filePath):
            # type: (str) -> Tuple[bool, str]
            """Resolve filePath against repoDir and ensure it stays within the repo."""
            if not repoDir or not os.path.isdir(repoDir):
                return False, "Invalid repo_dir: {}".format(repoDir)

            if os.name == "nt" and filePath.startswith("/") and filePath.find(":") != 1:
                filePath = filePath.lstrip("/")

            if os.path.isabs(filePath):
                absPath = os.path.abspath(filePath)
            else:
                absPath = os.path.abspath(os.path.join(repoDir, filePath))

            try:
                repoRoot = os.path.abspath(repoDir)
                common = os.path.commonpath([repoRoot, absPath])
            except Exception:
                return False, "Invalid file path: {}".format(filePath)

            if common != repoRoot:
                return False, "Refusing to access paths outside the repository: {}".format(filePath)

            return True, absPath

        def _probe_file_format(abs_path):
            # type: (str) -> Tuple[Optional[bytes], str, str]
            """Return (bom, encoding, text) for an existing file."""
            with open(abs_path, "rb") as fb:
                raw = fb.read()

            bom, bom_encoding = detectBom(abs_path)
            if bom:
                # Decode while stripping BOM bytes; we'll re-add BOM on write.
                raw_wo_bom = raw[len(bom):]
                enc_for_decode = bom_encoding
                # utf-8 BOM is typically handled via utf-8-sig; since we
                # stripped the BOM, decode with plain utf-8.
                if enc_for_decode == "utf-8-sig":
                    enc_for_decode = "utf-8"
                try:
                    text = raw_wo_bom.decode(enc_for_decode)
                    encoding = enc_for_decode
                except Exception:
                    # Fall back to our heuristic decoding for robustness.
                    text, encoding = decodeFileData(raw_wo_bom, enc_for_decode)
                    encoding = encoding or enc_for_decode
            else:
                # Heuristic decode for files without BOM.
                text, encoding = decodeFileData(raw, "utf-8")
                encoding = encoding or "utf-8"

            return bom, encoding, text

        def _open_file(path):
            # type: (str) -> str
            filePath = _normalize_path(path)
            ok, absPath = _resolve_repo_path(filePath)
            if not ok:
                raise DiffError(absPath)

            if not os.path.isfile(absPath):
                raise DiffError("File does not exist: {}".format(filePath))

            bom, encoding, text = _probe_file_format(absPath)
            # Cache format by the repo-relative patch path.
            file_format[filePath] = (bom, encoding)
            return text

        def _write_file(path, content, source_path=None):
            # type: (str, str, Optional[str]) -> None
            filePath = _normalize_path(path)
            ok, absPath = _resolve_repo_path(filePath)
            if not ok:
                raise DiffError(absPath)
            parent = os.path.dirname(absPath)
            os.makedirs(parent, exist_ok=True)

            # Determine target format.
            fmt = file_format.get(filePath)
            if fmt is None and source_path:
                src = _normalize_path(source_path)
                fmt = file_format.get(src)

            if fmt is None and os.path.isfile(absPath):
                # Patch may write without ever having opened the file.
                bom, encoding, _ = _probe_file_format(absPath)
                fmt = (bom, encoding)

            if fmt is None:
                # New file: default to UTF-8.
                fmt = (None, "utf-8")

            bom, encoding = fmt

            enc_for_bytes = encoding
            if bom and enc_for_bytes == "utf-8-sig":
                enc_for_bytes = "utf-8"

            try:
                payload = content.encode(enc_for_bytes)
            except UnicodeEncodeError as e:
                raise DiffError(
                    "Failed to encode {} as {}: {}".format(
                        filePath, enc_for_bytes, e)
                )

            with open(absPath, "wb") as f:
                if bom:
                    f.write(bom)
                f.write(payload)

            # Update cache to reflect what we just wrote.
            file_format[filePath] = (bom, encoding)

        def _remove_file(path):
            # type: (str) -> None
            filePath = _normalize_path(path)
            ok, absPath = _resolve_repo_path(filePath)
            if not ok:
                raise DiffError(absPath)
            if os.path.isfile(absPath):
                os.unlink(absPath)

        try:
            message = processPatch(
                patch_text, _open_file, _write_file, _remove_file
            )
            return ToolResult(content=message)
        except DiffError as e:
            return ToolResult(content=str(e), is_error=True)
        except Exception as e:
            return ToolResult(
                content="Failed to apply patch: {}".format(e), is_error=True
            )

    def inputSchema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "input": {
                    "type": "string",
                    "description": "The edit patch to apply (V4A format).",
                },
                "explanation": {
                    "type": "string",
                    "description": (
                        "A short description of what the patch is aiming to achieve."
                    ),
                },
            },
            "required": ["input", "explanation"],
            "additionalProperties": False,
        }
