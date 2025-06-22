# -*- coding: utf-8 -*-

import logging
import platform
import sys
from typing import Dict

from opentelemetry import _logs, metrics, trace
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from qgitc.applicationbase import ApplicationBase
from qgitc.common import logger
from qgitc.telemetry import TelemetryBase, TraceSpanBase

try:
    from qgitc.otelenv import OTEL_AUTH, OTEL_ENDPOINT
except ImportError:
    OTEL_ENDPOINT = "http://localhost:4318"
    OTEL_AUTH = ""


class OTelTraceSpan(TraceSpanBase):

    def __init__(self, ctx):
        self._impl = ctx
        self._span: trace.Span = None

    def addTag(self, key: str, value: object) -> None:
        if self._span is None:
            return
        self._span.set_attribute(key, value)

    def addEvent(self, name: str, attributes: Dict[str, object] = None) -> None:
        if self._span is None:
            return
        self._span.add_event(name, attributes)

    def __enter__(self):
        if self._impl is not None:
            self._span = self._impl.__enter__()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        if self._span is None:
            return
        self._impl.__exit__(exc_type, exc_value, traceback)
        self._span = None


class OTelService(TelemetryBase):

    def __init__(self, serviceName: str, serviceVersion: str):
        app = ApplicationBase.instance()
        self._isEnabled = app.settings().isTelemetryEnabled() and not app.testing
        if not self._isEnabled:
            return

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
        })

        self._setupTracer(resource, serviceName, f"{OTEL_ENDPOINT}/v1/traces")
        self._setupMeter(resource, serviceName, f"{OTEL_ENDPOINT}/v1/metrics")
        self._setupLogger(resource, serviceName, f"{OTEL_ENDPOINT}/v1/logs")

        self._counters: Dict[str, metrics.Counter] = {}

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if OTEL_AUTH:
            headers["Authorization"] = OTEL_AUTH
        return headers

    def _setupTracer(self, resource: Resource, serviceName: str, otelEndpoint: str):
        traceProvder = TracerProvider(resource=resource)
        trace.set_tracer_provider(traceProvder)

        exporter = OTLPSpanExporter(
            endpoint=otelEndpoint,
            timeout=1,
            headers=self._headers())

        processor = BatchSpanProcessor(
            exporter,
            export_timeout_millis=500)
        traceProvder.add_span_processor(processor)

        self._tracker = traceProvder.get_tracer(serviceName)

    def _setupMeter(self, resource: Resource, servieName: str, otelEndpoint: str):
        exporter = OTLPMetricExporter(
            endpoint=otelEndpoint,
            timeout=1,
            headers=self._headers())
        reader = PeriodicExportingMetricReader(exporter, 5000, 500)

        meterProvider = MeterProvider([reader], resource=resource)
        metrics.set_meter_provider(meterProvider)

        self._meter = meterProvider.get_meter(servieName)

    def _setupLogger(self, resource: Resource, serviceName: str, otelEndpoint: str):
        provider = LoggerProvider(resource=resource)
        _logs.set_logger_provider(provider)

        exporter = OTLPLogExporter(
            endpoint=otelEndpoint,
            timeout=1,
            headers=self._headers())
        processor = BatchLogRecordProcessor(
            exporter, 3000, export_timeout_millis=500)
        provider.add_log_record_processor(processor)

        logger = logging.getLogger()
        logger.addHandler(LoggingHandler(logging.WARNING, provider))

        self._logger = logging.getLogger("_otel_")
        self._logger.addHandler(LoggingHandler(logging.INFO, provider))
        self._logger.setLevel(logging.INFO)

    def trackMetric(self, name: str, properties: Dict[str, object] = None, value=1.0, unit="1") -> None:
        if not self._isEnabled:
            return

        key = f"{name}:{unit}"
        if key in self._counters:
            counter = self._counters[key]
        else:
            counter = self._meter.create_counter(name, unit=unit)
            self._counters[key] = counter

        counter.add(value, properties)

    def startTrace(self, name: str):
        if not self._isEnabled:
            return OTelTraceSpan(None)

        span = self._tracker.start_as_current_span(name)
        return OTelTraceSpan(span)

    def logger(self):
        if not self._isEnabled:
            return logger
        return self._logger

    def shutdown(self):
        if not self._isEnabled:
            return

        trace.get_tracer_provider().shutdown()
        metrics.get_meter_provider().shutdown()
