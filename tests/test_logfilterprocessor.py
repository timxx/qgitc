import unittest

from opentelemetry.sdk._logs import LogData, LogRecord

from qgitc.otelimpl import LogFilterProcessor


class TestLogFilterProcessor(unittest.TestCase):

    def test_emit_removes_file_path(self):
        log_record = LogRecord(
            attributes={"code.file.path": "/path/to/sensitive/file.txt"}
        )
        log_data = LogData(log_record, None)

        # ensure we can instantiate and call the processor
        processor = LogFilterProcessor()
        processor.on_emit(log_data)

        self.assertIn("code.file.path", log_data.log_record.attributes)
        self.assertEqual(
            log_data.log_record.attributes["code.file.path"], "file.txt"
        )
