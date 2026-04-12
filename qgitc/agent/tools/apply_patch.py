# -*- coding: utf-8 -*-

import os
from typing import Any, Dict, Optional, Tuple

from qgitc.agent.tool import Tool, ToolContext, ToolResult
from qgitc.common import decodeFileData
from qgitc.tools.applypatch import APPLY_PATCH_TOOL_DESC, DiffError, process_patch
from qgitc.tools.utils import detectBom


class ApplyPatchTool(Tool):
    name = "apply_patch"
    description = APPLY_PATCH_TOOL_DESC

    def is_read_only(self):
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
                    "Failed to encode {} as {}: {}".format(filePath, enc_for_bytes, e)
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
            message = process_patch(
                patch_text, _open_file, _write_file, _remove_file
            )
            return ToolResult(content=message)
        except DiffError as e:
            return ToolResult(content=str(e), is_error=True)
        except Exception as e:
            return ToolResult(
                content="Failed to apply patch: {}".format(e), is_error=True
            )

    def input_schema(self) -> Dict[str, Any]:
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
