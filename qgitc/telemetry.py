# -*- coding: utf-8 -*-

import abc
from logging import Logger
from typing import Dict


class TraceSpanBase(abc.ABC):
    """Abstract base class for a trace span."""

    @abc.abstractmethod
    def addTag(self, key: str, value: object) -> None:
        """Add a tag to the span."""
        pass

    @abc.abstractmethod
    def addEvent(self, name: str, attributes: Dict[str, object] = None) -> None:
        """Add an event to the span."""
        pass

    @abc.abstractmethod
    def end(self) -> None:
        """End the span."""
        pass

    @abc.abstractmethod
    def setStatus(self, ok: bool, desc: str = None) -> None:
        """Set the status of the span."""
        pass

    @abc.abstractmethod
    def __enter__(self):
        """Start the span."""
        pass

    @abc.abstractmethod
    def __exit__(self, exc_type, exc_value, traceback) -> None:
        """End the span."""
        pass


class TelemetryBase(abc.ABC):

    @abc.abstractmethod
    def startTrace(self, name: str) -> TraceSpanBase:
        """Start a trace with a given name."""
        pass

    @abc.abstractmethod
    def logger(self) -> Logger:
        """The common logger for otel"""
        pass

    @abc.abstractmethod
    def shutdown(self) -> None:
        """Shutdown the telemetry service."""
        pass
