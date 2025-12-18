# -*- coding: utf-8 -*-

import logging
import os
import platform
import sys
from typing import Dict

from opentelemetry import _logs, trace
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler, LogRecordProcessor
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from qgitc.common import logger
from qgitc.telemetry import TelemetryBase, TraceSpanBase


class LogFilterProcessor(LogRecordProcessor):
    """Processor that removes sensitive information from log records."""

    def emit(self, log_data):
        if log_data.log_record.attributes and "code.file.path" in log_data.log_record.attributes:
            try:
                file_path = log_data.log_record.attributes["code.file.path"]
                log_data.log_record.attributes["code.file.path"] = os.path.basename(
                    file_path)
            except:
                pass

    def on_emit(self, log_data):
        return self.emit(log_data)

    def shutdown(self):
        """No-op shutdown."""
        pass

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return True


class OTelTraceSpan(TraceSpanBase):

    def __init__(self, span: trace.Span):
        self._impl = span

    def addTag(self, key: str, value: object):
        if self._impl is None:
            return
        self._impl.set_attribute(key, value)

    def addEvent(self, name: str, attributes: Dict[str, object] = None):
        if self._impl is None:
            return
        self._impl.add_event(name, attributes)

    def end(self) -> None:
        if self._impl is None:
            return
        self._impl.end()

    def setStatus(self, ok: bool, desc: str = None) -> None:
        if self._impl is None:
            return

        if ok:
            self._impl.set_status(trace.StatusCode.OK)
        else:
            self._impl.set_status(trace.StatusCode.ERROR, desc)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.end()


class OTelService(TelemetryBase):

    def __init__(self):
        self._isEnabled = False
        self.inited = False

    def setupService(self, serviceName: str, serviceVersion: str, qtVersion: str, endPoint: str, auth: str = None):
        self._isEnabled = True
        self.inited = True

        arch = platform.machine().lower()
        if arch in ("amd64", "x86_64"):
            arch = "x86_64"
        elif arch in ("arm64", "aarch64"):
            arch = "arm64"
        resource = Resource.create(attributes={
            "service.name": serviceName,
            "service.version": serviceVersion,
            "py.version": sys.version.split()[0],
            "os.platform": sys.platform,
            "os.arch": arch,
            "qt.version": qtVersion
        })

        headers = None
        if auth:
            headers = {"Authorization": auth}

        self._setupTracer(resource, serviceName,
                          f"{endPoint}/v1/traces", headers)
        self._setupLogger(resource, serviceName,
                          f"{endPoint}/v1/logs", headers)

    def _setupTracer(self, resource: Resource, serviceName: str, otelEndpoint: str, headers: Dict[str, str]):
        traceProvder = TracerProvider(resource=resource)
        trace.set_tracer_provider(traceProvder)

        exporter = OTLPSpanExporter(
            endpoint=otelEndpoint,
            timeout=1,
            headers=headers)

        processor = BatchSpanProcessor(
            exporter,
            export_timeout_millis=500)
        traceProvder.add_span_processor(processor)

        self._tracker = traceProvder.get_tracer(serviceName)

    def _setupLogger(self, resource: Resource, serviceName: str, otelEndpoint: str, headers: Dict[str, str]):
        provider = LoggerProvider(resource=resource)
        _logs.set_logger_provider(provider)

        exporter = OTLPLogExporter(
            endpoint=otelEndpoint,
            timeout=1,
            headers=headers)

        provider.add_log_record_processor(LogFilterProcessor())

        processor = BatchLogRecordProcessor(
            exporter, 3000, export_timeout_millis=500)
        provider.add_log_record_processor(processor)

        logger = logging.getLogger()
        logger.addHandler(LoggingHandler(logging.WARNING, provider))

        self._logger = logging.getLogger("_otel_")
        self._logger.propagate = False
        self._logger.addHandler(LoggingHandler(logging.INFO, provider))
        self._logger.setLevel(logging.INFO)

    def startTrace(self, name: str):
        if not self._isEnabled:
            return OTelTraceSpan(None)

        span = self._tracker.start_span(name)
        return OTelTraceSpan(span)

    def logger(self):
        if not self._isEnabled:
            return logger
        return self._logger

    def shutdown(self):
        if not self._isEnabled:
            return

        trace.get_tracer_provider().shutdown()
        _logs.get_logger_provider().shutdown()
