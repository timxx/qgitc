# -*- coding: utf-8 -*-

from __future__ import annotations

import os
from typing import Any, Optional, Tuple, Union

from qgitc.gitutils import GitProcess


def detectBom(path: str) -> Tuple[Optional[bytes], str]:
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


def _makeError(msg: str, text: bool) -> Union[bytes, str]:
    if text:
        return msg
    return msg.encode("utf-8")


def runGit(
    repoDir: str,
    args: list[str],
    *,
    stdin: Optional[Union[bytes, str]] = None,
    text: bool = False,
    env: Optional[dict[str, str]] = None,
) -> Tuple[bool, Union[bytes, str], Union[bytes, str]]:
    """Run git in repoDir.

    Returns (ok, stdout, stderr). When text=False, stdout/stderr are bytes.
    When text=True, stdout/stderr are str decoded as UTF-8 with replacement.
    """

    emptyStr = "" if text else b""

    if not repoDir:
        return False, emptyStr, \
            _makeError("No repository is currently opened.", text)

    if not os.path.isdir(repoDir):
        msg = f"Invalid repoDir: {repoDir}"
        return False, emptyStr, _makeError(msg, text)

    env: dict[str, str] = os.environ.copy()
    if "LANGUAGE" not in env:
        env["LANGUAGE"] = "en_US"
    if env:
        env.update({str(k): str(v) for k, v in env.items()})

    try:
        gitArgs = [str(a) for a in args]
        process = GitProcess(repoDir, gitArgs, text=text,
                             env=env, stdinPipe=bool(stdin))
        out, err = process.communicate(input=stdin)
        ok = process.returncode == 0
        return ok, out or emptyStr, err or emptyStr
    except Exception as e:
        return False, emptyStr, _makeError(str(e), text)
