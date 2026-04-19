# -*- coding: utf-8 -*-

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, Iterator, List, Optional, Union

from qgitc.agent.types import Message, Usage


@dataclass
class ContentDelta:
    text: str


@dataclass
class ReasoningDelta:
    text: str
    reasoning_data: Optional[Dict[str, Any]] = None


@dataclass
class ToolCallDelta:
    id: str
    name: str
    arguments_delta: str


@dataclass
class MessageComplete:
    stop_reason: str
    usage: Optional[Usage] = None


StreamEvent = Union[ContentDelta, ReasoningDelta, ToolCallDelta, MessageComplete]


class ModelProvider(ABC):
    @abstractmethod
    def stream(
        self,
        messages,          # type: List[Message]
        tools=None,        # type: Optional[List[Dict[str, Any]]]
        model=None,        # type: Optional[str]
        max_tokens=4096,   # type: int
    ):
        # type: (...) -> Iterator[StreamEvent]
        ...

    @abstractmethod
    def countTokens(
        self,
        messages,          # type: List[Message]
        system_prompt=None,  # type: Optional[str]
        tools=None,        # type: Optional[List[Dict[str, Any]]]
    ):
        # type: (...) -> int
        ...
