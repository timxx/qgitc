# -*- coding: utf-8 -*-

from qgitc.agent.permissions import (
    PermissionAllow,
    PermissionAsk,
    PermissionEngine,
)


def createPermissionEngine(strategy_value):
    # type: (int) -> PermissionEngine
    """Create a PermissionEngine from a strategy setting value.

    Strategy values:
        0 (Default)    - Allow read-only tools automatically, ask for rest
        1 (Aggressive) - Allow read-only + non-destructive, ask for destructive
        2 (Safe)       - Ask for all tools
        3 (AllAuto)    - Allow all tools automatically
    """
    if strategy_value == 1:
        return _AggressivePermissionEngine()
    if strategy_value == 2:
        return _SafePermissionEngine()
    if strategy_value == 3:
        return _AllAutoPermissionEngine()
    return PermissionEngine()


class _AggressivePermissionEngine(PermissionEngine):
    """Allow read-only and non-destructive tools; ask for destructive."""

    def __init__(self):
        super().__init__()

    def check(self, tool, input_data):
        if tool.isReadOnly():
            return PermissionAllow()
        if not tool.isDestructive():
            return PermissionAllow()
        return PermissionAsk()


class _SafePermissionEngine(PermissionEngine):
    """Ask for all tools regardless of type."""

    def __init__(self):
        super().__init__()

    def check(self, tool, input_data):
        return PermissionAsk()


class _AllAutoPermissionEngine(PermissionEngine):
    """Allow all tools automatically."""

    def __init__(self):
        super().__init__()

    def check(self, tool, input_data):
        return PermissionAllow()
