# -*- coding: utf-8 -*-

import json
import os
from datetime import datetime
from typing import Any, Dict, Optional

from PySide6.QtCore import QDir, QStandardPaths


def defaultResolutionReportFile() -> str:
    dirPath = QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation)
    dt = datetime.now()
    fileName = "qgitc-auto-resolve/{}.jsonl".format(
        dt.strftime("%Y%m%d%H%M%S"))
    return os.path.normpath(dirPath + QDir.separator() + fileName)


def appendResolutionReportEntry(reportFile: str, entry: Dict[str, Any]):
    if not reportFile:
        return

    os.makedirs(os.path.dirname(reportFile), exist_ok=True)

    # JSON Lines: one JSON object per line.
    with open(reportFile, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False))
        f.write("\n")


def buildResolutionReportEntry(
    *,
    repoDir: str,
    path: str,
    sha1: str,
    operation: str,
    ok: bool,
    reason: Optional[Any] = None
) -> Dict[str, Any]:
    ts = datetime.now().isoformat()
    return {
        "timestamp": ts,
        "repoDir": repoDir,
        "path": path,
        "sha1": sha1,
        "operation": operation,
        "ok": ok,
        "reason": None if reason is None else str(reason),
    }
