# -*- coding: utf-8 -*-

import json
import os
from typing import Any, Dict, Optional, Tuple

from qgitc.agent.tool import Tool, ToolContext, ToolResult
from qgitc.agent.tools.utils import detectBom
from qgitc.common import decodeFileData


def normalizeToolFilePath(filePath: str) -> str:
    """Normalize a file path coming from a tool call.

    - Strips whitespace
    - On Windows, converts Unix-style absolute paths like '/C:/path' to 'C:/path'

    Returns the normalized (not necessarily absolute) path.
    """
    p = (filePath or "").strip()
    # Only normalize the specific Windows pattern "/C:/path" -> "C:/path".
    # Do NOT strip leading slashes for other absolute paths like "/etc/hosts"
    # (MSYS/Cygwin style) or UNC-like paths "//server/share".
    if (
        os.name == 'nt'
        and len(p) >= 3
        and p[0] == '/'
        and p[1].isalpha()
        and p[2] == ':'
    ):
        p = p[1:]
    return p


def resolveRepoPath(repoDir: str, filePath: str) -> Tuple[bool, str]:
    """Resolve filePath against repoDir and ensure it stays within repoDir.

    Returns (ok, absPathOrError).
    """
    if not repoDir or not os.path.isdir(repoDir):
        return False, f"Invalid repoDir: {repoDir}"

    p = normalizeToolFilePath(filePath)
    candidate = p if os.path.isabs(p) else os.path.join(repoDir, p)
    absPath = os.path.abspath(candidate)

    try:
        # Use realpath() to avoid symlink escape: a path inside the repo could
        # still point to a target outside the repo via symlinks.
        repoRoot = os.path.realpath(os.path.abspath(repoDir))
        realAbsPath = os.path.realpath(absPath)
        common = os.path.commonpath([repoRoot, realAbsPath])
    except Exception:
        return False, f"Invalid file path: {filePath}"

    if common != repoRoot:
        return False, f"Refusing to access paths outside the repository: {filePath}"

    return True, absPath


def buildReadFileOutput(absPath: str, startLine: Optional[int], endLine: Optional[int]) -> Tuple[bool, str]:
    """Read a file and return tool output with metadata delimiters.

    startLine/endLine are 1-based; endLine is inclusive.
    """
    try:
        with open(absPath, 'rb') as f:
            data = f.read()

        preferEncoding = detectBom(absPath)[1]
        text, _ = decodeFileData(data, preferEncoding)
        lines = text.splitlines(keepends=True)

        totalLines = len(lines)
        requestedStartLine = startLine
        requestedEndLine = endLine

        if requestedStartLine is not None and requestedEndLine is not None and requestedEndLine < requestedStartLine:
            return False, (
                f"Invalid line range: endLine ({requestedEndLine}) is less than startLine ({requestedStartLine})."
            )

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

        output = "<<<METADATA>>>\n" + \
            json.dumps(meta, ensure_ascii=False) + \
            "\n<<<CONTENT>>>\n" + content
        return True, output
    except Exception as e:
        return False, f"Failed to read file: {e}"


class ReadFileTool(Tool):
    name = "read_file"
    description = (
        "Read the contents of a file, optionally specifying line ranges.\n"
        "If it is a relative path, treat it as relative to the repository root."
    )

    def is_read_only(self):
        return True

    def execute(self, input_data: Dict[str, Any], context: ToolContext) -> ToolResult:
        filePath = normalizeToolFilePath(input_data.get("filePath", ""))
        if not filePath:
            return ToolResult(content="filePath is required.", is_error=True)

        repoDir = context.working_directory
        if not repoDir:
            return ToolResult(
                content="No repository is currently opened.", is_error=True
            )

        ok, absPathOrErr = resolveRepoPath(repoDir, filePath)
        if not ok:
            return ToolResult(content=absPathOrErr, is_error=True)
        if not os.path.isfile(absPathOrErr):
            return ToolResult(
                content="File does not exist: {}".format(absPathOrErr),
                is_error=True,
            )

        startLine = input_data.get("startLine")
        endLine = input_data.get("endLine")

        ok, outputOrErr = buildReadFileOutput(absPathOrErr, startLine, endLine)
        return ToolResult(content=outputOrErr, is_error=not ok)

    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "filePath": {
                    "type": "string",
                    "description": "Path to the file to read.",
                },
                "startLine": {
                    "type": "integer",
                    "description": (
                        "Starting line number (1-based). "
                        "If not provided, starts from the beginning."
                    ),
                    "minimum": 1,
                },
                "endLine": {
                    "type": "integer",
                    "description": (
                        "Ending line number (1-based). "
                        "If not provided, reads until the end."
                    ),
                    "minimum": 1,
                },
            },
            "required": ["filePath"],
            "additionalProperties": False,
        }
