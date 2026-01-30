# -*- coding: utf-8 -*-

from enum import IntEnum


class ResolveEventKind(IntEnum):
    STARTED = 1
    STEP = 2
    PROGRESS = 3
    PROMPT = 4
    FILE_RESOLVED = 5
    COMPLETED = 6


class ResolvePromptKind(IntEnum):
    RUN_MERGETOOL_CONFIRM = 1
    DELETED_CONFLICT_CHOICE = 2
    SYMLINK_CONFLICT_CHOICE = 3
    EMPTY_COMMIT_CHOICE = 4


class ResolveOutcomeStatus(IntEnum):
    RESOLVED = 1
    NEEDS_USER = 2
    ABORTED = 3
    FAILED = 4


class ResolveMethod(IntEnum):
    AI = 1
    MERGETOOL = 2
    OURS = 3
    THEIRS = 4
    TRIVIAL = 5
