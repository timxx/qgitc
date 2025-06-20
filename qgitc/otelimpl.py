# -*- coding: utf-8 -*-

import platform
import sys
from typing import Dict

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from qgitc.applicationbase import ApplicationBase
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
        self._isEnabled = ApplicationBase.instance().settings().isTelemetryEnabled()
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
            headers=self._headers())

        processor = BatchSpanProcessor(
            exporter,
            export_timeout_millis=3000)
        traceProvder.add_span_processor(processor)

        self._tracker = traceProvder.get_tracer(serviceName)

    def _setupMeter(self, resource: Resource, servieName: str, otelEndpoint: str):
        exporter = OTLPMetricExporter(
            endpoint=otelEndpoint,
            timeout=1,
            headers=self._headers())
        reader = PeriodicExportingMetricReader(exporter, 5000, 3000)

        meterProvider = MeterProvider([reader], resource=resource)
        metrics.set_meter_provider(meterProvider)

        self._meter = meterProvider.get_meter(servieName)

    def trackMetric(self, name: str, properties: Dict[str, object] = None, value: float = 1.0) -> None:
        if not self._isEnabled:
            return

        counter = self._meter.create_counter(name, unit="event")
        counter.add(value, properties or {})

    def startTrace(self, name: str):
        if not self._isEnabled:
            return OTelTraceSpan(None)

        span = self._tracker.start_as_current_span(name)
        return OTelTraceSpan(span)

    def shutdown(self):
        if not self._isEnabled:
            return

        trace.get_tracer_provider().shutdown()
        metrics.get_meter_provider().shutdown()
