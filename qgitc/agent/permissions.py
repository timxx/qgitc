# -*- coding: utf-8 -*-

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from qgitc.agent.tool import Tool


class PermissionBehavior(Enum):
    ALLOW = "allow"
    ASK = "ask"
    DENY = "deny"


@dataclass
class PermissionRule:
    tool_name: str
    behavior: PermissionBehavior = PermissionBehavior.ASK
    pattern: Optional[str] = None


@dataclass
class PermissionAllow:
    updated_input: Optional[Dict[str, Any]] = None


@dataclass
class PermissionAsk:
    message: str = ""


@dataclass
class PermissionDeny:
    message: str = ""


@dataclass
class PermissionUpdate:
    action: str  # "add" or "remove"
    rule: PermissionRule = None


PermissionResult = Union[PermissionAllow, PermissionAsk, PermissionDeny]


def _rule_matches(rule, tool, input_data):
    # type: (PermissionRule, Tool, Dict[str, Any]) -> bool
    """Check whether a permission rule matches the given tool and input data."""
    if rule.tool_name != "*" and rule.tool_name != tool.name:
        return False
    if rule.pattern is not None:
        joined = " ".join(str(v) for v in input_data.values())
        if rule.pattern not in joined:
            return False
    return True


class PermissionEngine:
    def __init__(self, allow_rules=None, deny_rules=None):
        # type: (Optional[List[PermissionRule]], Optional[List[PermissionRule]]) -> None
        self.allow_rules = list(allow_rules) if allow_rules else []  # type: List[PermissionRule]
        self.deny_rules = list(deny_rules) if deny_rules else []  # type: List[PermissionRule]

    def check(self, tool, input_data):
        # type: (Tool, Dict[str, Any]) -> PermissionResult
        """Evaluate permission rules for a tool invocation.

        Step 1: If any deny rule matches, return PermissionDeny.
        Step 2: If any allow rule matches, return PermissionAllow.
        Step 3: If the tool is read-only, return PermissionAllow.
        Step 4: Otherwise, return PermissionAsk.
        """
        for rule in self.deny_rules:
            if _rule_matches(rule, tool, input_data):
                return PermissionDeny(
                    message="Tool '{}' is denied by permission rule".format(tool.name)
                )

        for rule in self.allow_rules:
            if _rule_matches(rule, tool, input_data):
                return PermissionAllow()

        if tool.isReadOnly():
            return PermissionAllow()

        return PermissionAsk(
            message="Tool '{}' requires permission to proceed".format(tool.name)
        )

    def applyUpdate(self, update):
        # type: (PermissionUpdate) -> None
        """Add or remove a permission rule."""
        if update.rule.behavior == PermissionBehavior.ALLOW:
            target = self.allow_rules
        elif update.rule.behavior == PermissionBehavior.DENY:
            target = self.deny_rules
        else:
            return

        if update.action == "add":
            target.append(update.rule)
        elif update.action == "remove":
            try:
                target.remove(update.rule)
            except ValueError:
                pass
