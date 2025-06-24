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

from qgitc.common import logger
from qgitc.telemetry import TelemetryBase, TraceSpanBase


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

    def setupService(self, serviceName: str, serviceVersion: str, endPoint: str, auth: str = None):
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
        })

        headers = {"Content-Type": "application/json"}
        if auth:
            headers["Authorization"] = auth

        self._setupTracer(resource, serviceName, f"{endPoint}/v1/traces", headers)
        self._setupMeter(resource, serviceName, f"{endPoint}/v1/metrics", headers)
        self._setupLogger(resource, serviceName, f"{endPoint}/v1/logs", headers)

        self._counters: Dict[str, metrics.Counter] = {}

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

    def _setupMeter(self, resource: Resource, servieName: str, otelEndpoint: str, headers: Dict[str, str]):
        exporter = OTLPMetricExporter(
            endpoint=otelEndpoint,
            timeout=1,
            headers=headers)
        reader = PeriodicExportingMetricReader(exporter, 5000, 500)

        meterProvider = MeterProvider([reader], resource=resource)
        metrics.set_meter_provider(meterProvider)

        self._meter = meterProvider.get_meter(servieName)

    def _setupLogger(self, resource: Resource, serviceName: str, otelEndpoint: str, headers: Dict[str, str]):
        provider = LoggerProvider(resource=resource)
        _logs.set_logger_provider(provider)

        exporter = OTLPLogExporter(
            endpoint=otelEndpoint,
            timeout=1,
            headers=headers)
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
        metrics.get_meter_provider().shutdown()
        _logs.get_logger_provider().shutdown()
