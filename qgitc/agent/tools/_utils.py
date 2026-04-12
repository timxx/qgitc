# -*- coding: utf-8 -*-

from typing import List, Tuple

from qgitc.tools.utils import runGit


def run_git(working_directory: str, args: List[str]) -> Tuple[bool, str]:
    """Run a git command using the project's GitProcess (which handles CREATE_NO_WINDOW on Windows).

    Uses qgitc.tools.utils.runGit internally.
    Returns (ok: bool, output: str) where output merges stderr into stdout on failure.
    """
    ok, out, err = runGit(working_directory, args, text=True)
    output = out.strip("\n")

    # Only include stderr when the command fails.
    if not ok:
        errText = err.strip("\n")
        if errText:
            if output:
                output += "\n"
            output += errText

    return ok, output
