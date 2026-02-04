# -*- coding: utf-8 -*-

from __future__ import annotations

import json
import os
from typing import Optional, Tuple

from qgitc.common import decodeFileData
from qgitc.tools.utils import detectBom


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
