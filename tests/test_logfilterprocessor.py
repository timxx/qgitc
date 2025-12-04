import unittest

try:
    from opentelemetry.sdk._logs import LogData, LogRecord
    use_log_data = True
except ImportError:
    from opentelemetry.sdk._logs import ReadWriteLogRecord
    from opentelemetry.sdk._logs._internal import LogRecord
    use_log_data = False

from qgitc.otelimpl import LogFilterProcessor


class TestLogFilterProcessor(unittest.TestCase):

    def test_emit_removes_file_path(self):
        log_record = LogRecord(
            attributes={"code.file.path": "/path/to/sensitive/file.txt"}
        )
        if use_log_data:
            log_data = LogData(log_record, None)
        else:
            log_data = ReadWriteLogRecord(log_record)
        # ensure we can instantiate and call the processor
        processor = LogFilterProcessor()
        processor.on_emit(log_data)

        self.assertIn("code.file.path", log_data.log_record.attributes)
        self.assertEqual(
            log_data.log_record.attributes["code.file.path"], "file.txt"
        )
