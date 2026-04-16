# -*- coding: utf-8 -*-

from typing import Dict, List, Optional, Protocol


class SlashCommand(Protocol):
    name: str
    description: str
    aliases: List[str]
    argument_hint: Optional[str]


class CommandRegistry:
    """Registry for slash commands with name/alias lookup."""

    def __init__(self) -> None:
        self._commands = {}  # type: Dict[str, SlashCommand]
        self._aliases = {}  # type: Dict[str, str]

    def register(self, command: SlashCommand) -> None:
        self._commands[command.name] = command
        for alias in command.aliases:
            self._aliases[alias] = command.name

    def find(self, name: str) -> Optional[SlashCommand]:
        cmd = self._commands.get(name)
        if cmd is not None:
            return cmd

        canonical = self._aliases.get(name)
        if canonical is not None:
            return self._commands.get(canonical)

        return None

    def has(self, name: str) -> bool:
        return self.find(name) is not None

    def list_commands(self) -> List[SlashCommand]:
        return list(self._commands.values())
