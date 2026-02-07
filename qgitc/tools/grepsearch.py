# -*- coding: utf-8 -*-

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import List, Optional, Set, Tuple

from qgitc.common import decodeFileData
from qgitc.tools.utils import detectBom, runGit


def _isGitRepo(repoDir: str) -> bool:
    if not repoDir:
        return False
    gitMarkerPath = os.path.join(repoDir, ".git")
    # In standard repos, .git is a directory; in git worktrees, .git is a file.
    return os.path.isdir(gitMarkerPath) or os.path.isfile(gitMarkerPath)


def _splitZ(data: bytes) -> List[str]:
    if not data:
        return []
    parts = data.split(b"\x00")
    out: List[str] = []
    for p in parts:
        if not p:
            continue
        out.append(p.decode("utf-8", errors="replace"))
    return out


def _gitListNonIgnoredFiles(repoDir: str) -> Tuple[bool, str, List[str]]:
    """List tracked + untracked (not ignored) files. Returns repo-relative paths."""
    ok, outTracked, err = runGit(repoDir, ["ls-files", "-z"], text=False)
    if not ok:
        return False, (err.decode("utf-8", errors="replace") or "git ls-files failed"), []

    ok, outOthers, err = runGit(
        repoDir, ["ls-files", "-z", "--others", "--exclude-standard"], text=False)
    if not ok:
        return False, (err.decode("utf-8", errors="replace") or "git ls-files --others failed"), []

    files = _splitZ(outTracked) + _splitZ(outOthers)
    files = [f for f in files if f and not f.startswith(
        ".git/") and f != ".git"]
    files.sort()
    return True, "", files


def _gitFilterIgnored(repoDir: str, relPaths: List[str]) -> Tuple[bool, str, Set[str]]:
    """Return a set of ignored paths (subset of relPaths)."""
    if not relPaths:
        return True, "", set()

    payload = ("\x00".join(relPaths) +
               "\x00").encode("utf-8", errors="replace")
    ok, out, err = runGit(
        repoDir, ["check-ignore", "-z", "--stdin"], stdin=payload, text=False)
    if not ok:
        # If git can't evaluate ignore rules (e.g. not a repo), treat as no ignored.
        msg = err.decode("utf-8", errors="replace").strip()
        if msg:
            return False, msg, set()
        return True, "", set()

    ignored = set(_splitZ(out))
    return True, "", ignored


def _iterRepoFiles(repoDir: str, includePattern: Optional[str], includeIgnoredFiles: bool) -> Tuple[bool, str, List[str]]:
    """Return (ok, message, files) where files is a list of absolute file paths."""
    if not repoDir:
        return False, "No repository is currently opened.", []
    if not os.path.isdir(repoDir):
        return False, f"Invalid repoDir: {repoDir}", []

    pattern = (includePattern or "").strip() or None
    repoPath = Path(repoDir)

    # Always skip .git. For non-ignored search, also skip common build/cache dirs.
    skip_dirs = {".git"}
    if not includeIgnoredFiles:
        skip_dirs |= {
            "__pycache__",
            ".venv",
            "venv",
            "build",
            "dist",
            ".eggs",
        }

    files: List[str] = []

    if pattern:
        pat = pattern.lstrip("/\\")
        if os.path.isabs(pat):
            try:
                pat = os.path.relpath(pat, repoDir)
            except Exception:
                return False, f"Invalid includePattern: {pattern}", []

        pat = pat.replace("\\", "/")
        try:
            for p in repoPath.glob(pat):
                if p.is_file():
                    try:
                        p.resolve().relative_to(repoPath.resolve())
                    except Exception:
                        continue
                    files.append(str(p))
        except Exception as e:
            return False, f"Invalid includePattern: {pattern} ({e})", []

        files.sort()

        # Respect .gitignore by default when in a git repo.
        if not includeIgnoredFiles and _isGitRepo(repoDir):
            rels: List[str] = []
            for absPath in files:
                try:
                    rels.append(os.path.relpath(
                        absPath, repoDir).replace('\\', '/'))
                except Exception:
                    continue
            okIg, msgIg, ignored = _gitFilterIgnored(repoDir, rels)
            if okIg:
                kept = []
                ignoredSet = set(ignored)
                for absPath in files:
                    rel = os.path.relpath(absPath, repoDir).replace('\\', '/')
                    if rel in ignoredSet:
                        continue
                    kept.append(absPath)
                files = kept
            else:
                # If git check-ignore fails, fall back to returning glob matches.
                pass

        return True, "", files

    # No includePattern.
    if not includeIgnoredFiles and _isGitRepo(repoDir):
        okGit, msgGit, relFiles = _gitListNonIgnoredFiles(repoDir)
        if okGit:
            absFiles = [os.path.join(repoDir, p) for p in relFiles]
            return True, "", absFiles
        # If git listing fails, fall back to walking the filesystem.

    for root, dirs, filenames in os.walk(repoDir):
        dirs[:] = [d for d in dirs if d not in skip_dirs]

        for fn in filenames:
            files.append(os.path.join(root, fn))

    files.sort()
    return True, "", files


def grepSearch(
    *,
    repoDir: str,
    query: str,
    isRegexp: bool,
    includeIgnoredFiles: bool = False,
    includePattern: Optional[str] = None,
    maxResults: int = 30,
) -> str:
    """Search for text across files in a repository.

    Returns a human-readable multi-line string:
    - Each match line: `path/to/file:line: <line text>`
    - Summary footer with counts and truncation flag.

    Notes:
    - Search is case-insensitive for both plain and regexp.
    - Skips obvious binary files and very large files for responsiveness.
    """

    if not query:
        raise ValueError("query must be a non-empty string")

    ok, msg, files = _iterRepoFiles(
        repoDir, includePattern, includeIgnoredFiles)
    if not ok:
        raise ValueError(msg)

    if maxResults < 1:
        maxResults = 1

    regex = None
    needle = None
    if isRegexp:
        try:
            regex = re.compile(query, re.IGNORECASE)
        except re.error as e:
            raise ValueError(f"Invalid regex: {e}")
    else:
        needle = query.casefold()

    results: List[str] = []
    matched_files: Set[str] = set()
    scannedFiles = 0
    skippedFiles = 0

    maxFileBytes = 5 * 1024 * 1024  # 5MB
    repoRoot = os.path.abspath(repoDir)

    for absPath in files:
        if len(results) >= maxResults:
            break

        try:
            absPath2 = os.path.abspath(absPath)
            if os.path.commonpath([repoRoot, absPath2]) != repoRoot:
                skippedFiles += 1
                continue

            if not os.path.isfile(absPath2):
                continue

            try:
                size = os.path.getsize(absPath2)
            except Exception:
                size = 0

            if size and size > maxFileBytes:
                skippedFiles += 1
                continue

            with open(absPath2, 'rb') as f:
                data = f.read()

            if b'\x00' in data[:8192]:
                skippedFiles += 1
                continue

            preferEncoding = detectBom(absPath2)[1]
            text, _ = decodeFileData(data, preferEncoding)
            scannedFiles += 1

            rel = os.path.relpath(absPath2, repoRoot).replace('\\', '/')

            for idx, line in enumerate(text.splitlines(), start=1):
                if len(results) >= maxResults:
                    break

                if regex is not None:
                    found = regex.search(line) is not None
                else:
                    found = needle in line.casefold()

                if not found:
                    continue

                matched_files.add(rel)

                shown = line
                if len(shown) > 400:
                    shown = shown[:400] + "…"

                results.append(f"{rel}:{idx}: {shown}")

        except Exception:
            skippedFiles += 1
            continue

    if not results:
        return "No matches found."

    truncated = len(results) >= maxResults
    summary = (
        f"\n\nMatches: {len(results)}"
        f" | Files: {len(matched_files)}"
        f" | Scanned files: {scannedFiles}"
        f" | Skipped files: {skippedFiles}"
        + (" | Truncated: true" if truncated else "")
    )

    return "\n".join(results) + summary
