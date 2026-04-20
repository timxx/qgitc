# -*- coding: utf-8 -*-

import unittest
from unittest.mock import MagicMock, patch

from PySide6.QtCore import SIGNAL, QProcess

from qgitc.actionrunner import ActionRunner


class TestActionRunner(unittest.TestCase):
    def setUp(self):
        self.runner = ActionRunner()

    def testWriteInput(self):
        mock_process = MagicMock()
        self.runner._process = mock_process

        self.runner.writeInput(b'y\n')

        mock_process.write.assert_called_once_with(b'y\n')

    def testDetectsPromptFromTrailingStdoutBuffer(self):
        mock_process = MagicMock()
        mock_process.readAllStandardOutput.return_value.data.return_value = b'Password: '
        self.runner._process = mock_process
        stdoutSpy = MagicMock()
        stdinSpy = MagicMock()
        self.runner.stdoutAvailable.connect(stdoutSpy)
        self.runner.stdinRequired.connect(stdinSpy)

        self.runner.onStdoutReady()

        stdoutSpy.assert_called_once_with(b'Password: ')
        stdinSpy.assert_called_once_with('Password: ', True)
        self.assertIsNone(self.runner._stdoutChunk)

    def testDoesNotRepeatSamePrompt(self):
        mock_process = MagicMock()
        mock_process.readAllStandardOutput.return_value.data.side_effect = [
            b'Proceed? ',
            b'Proceed? ',
        ]
        self.runner._process = mock_process
        stdoutSpy = MagicMock()
        stdinSpy = MagicMock()
        self.runner.stdoutAvailable.connect(stdoutSpy)
        self.runner.stdinRequired.connect(stdinSpy)

        self.runner.onStdoutReady()
        self.runner.onStdoutReady()

        self.assertEqual(stdoutSpy.call_count, 2)
        stdinSpy.assert_called_once_with('Proceed? ', False)

    def testDoesNotDetectPromptFromCompletedStdoutBlock(self):
        mock_process = MagicMock()
        mock_process.readAllStandardOutput.return_value.data.return_value = b'Password: \n'
        self.runner._process = mock_process
        stdoutSpy = MagicMock()
        stdinSpy = MagicMock()
        self.runner.stdoutAvailable.connect(stdoutSpy)
        self.runner.stdinRequired.connect(stdinSpy)

        self.runner.onStdoutReady()

        stdoutSpy.assert_called_once_with(b'Password: \n')
        stdinSpy.assert_not_called()

    def testEmitsCompletedStdoutBeforeTrailingPromptChunk(self):
        mock_process = MagicMock()
        mock_process.readAllStandardOutput.return_value.data.return_value = b'line1\nProceed? '
        self.runner._process = mock_process

        events = []

        def onStdout(data):
            events.append(('stdout', data))

        def onStdin(prompt, isSecret):
            events.append(('stdin', prompt, isSecret))

        self.runner.stdoutAvailable.connect(onStdout)
        self.runner.stdinRequired.connect(onStdin)

        self.runner.onStdoutReady()

        self.assertEqual(
            events,
            [
                ('stdout', b'line1\n'),
                ('stdout', b'Proceed? '),
                ('stdin', 'Proceed? ', False),
            ],
        )
        self.assertIsNone(self.runner._stdoutChunk)

    @patch('qgitc.actionrunner.QObject.disconnect')
    @patch('qgitc.actionrunner.logger')
    def testCancelRunningProcess(self, mock_logger, mock_disconnect):
        mock_process = MagicMock()
        mock_process.state.return_value = QProcess.Running
        self.runner._process = mock_process
        self.runner._stdoutChunk = b'some'
        self.runner._stderrChunk = b'err'
        self.runner.exitCode = 123

        self.runner.cancel()

        self.assertIsNone(self.runner._process)
        self.assertIsNone(self.runner._stdoutChunk)
        self.assertIsNone(self.runner._stderrChunk)
        self.assertEqual(self.runner.exitCode, 0)
        mock_disconnect.assert_any_call(mock_process,
                                        SIGNAL('readyReadStandardOutput()'),
                                        self.runner.onStdoutReady)
        mock_disconnect.assert_any_call(mock_process,
                                        SIGNAL('finished(int, QProcess::ExitStatus)'),
                                        self.runner.onRunFinished)
        mock_disconnect.assert_any_call(mock_process,
                                        SIGNAL('readyReadStandardError()'),
                                        self.runner.onStderrReady)
        mock_process.close.assert_called_once()
        mock_process.waitForFinished.assert_called_once_with(100)
        mock_logger.warning.assert_called_once_with("Kill action process")
        mock_process.kill.assert_called_once()

    def testCancelNoProcess(self):
        self.runner._process = None
        self.runner._stdoutChunk = b'data'
        self.runner._stderrChunk = b'data'
        self.runner.exitCode = 42

        self.runner.cancel()

        self.assertIsNone(self.runner._process)
        self.assertIsNone(self.runner._stdoutChunk)
        self.assertIsNone(self.runner._stderrChunk)
        self.assertEqual(self.runner.exitCode, 0)

    @patch('qgitc.actionrunner.QProcess')
    def testRunCommand(self, mock_qprocess):
        mock_process = MagicMock()
        mock_qprocess.return_value = mock_process
        self.runner._process = None

        args = "echo hello"
        cwd = "/tmp"
        self.runner.run(args, cwd)

        mock_process.setWorkingDirectory.assert_called_once_with(cwd)
        mock_process.readyReadStandardOutput.connect.assert_called_once_with(self.runner.onStdoutReady)
        mock_process.readyReadStandardError.connect.assert_called_once_with(self.runner.onStderrReady)
        mock_process.finished.connect.assert_called_once_with(self.runner.onRunFinished)
        mock_process.startCommand.assert_called_once_with(args)

    @patch('qgitc.actionrunner.QProcess')
    def testRunArgs(self, mock_qprocess):
        mock_process = MagicMock()
        mock_qprocess.return_value = mock_process
        self.runner._process = None

        args = ["ls", "-l"]
        cwd = "/tmp"
        self.runner.run(args, cwd)

        mock_process.setWorkingDirectory.assert_called_once_with(cwd)
        mock_process.readyReadStandardOutput.connect.assert_called_once_with(self.runner.onStdoutReady)
        mock_process.readyReadStandardError.connect.assert_called_once_with(self.runner.onStderrReady)
        mock_process.finished.connect.assert_called_once_with(self.runner.onRunFinished)
        mock_process.start.assert_called_once_with(args[0], args[1:])

    def testStdoutReadySeparator(self):
        mock_process = MagicMock()
        data = b'line1\nline2\npartial'
        mock_process.readAllStandardOutput.return_value.data.return_value = data
        self.runner._process = mock_process
        self.runner._stdoutChunk = b'prev'
        self.runner._separator = b'\n'
        self.runner.stdoutAvailable = MagicMock()

        self.runner.onStdoutReady()

        # Should emit only complete lines, chunk should be set for incomplete
        self.assertTrue(self.runner.stdoutAvailable.emit.called)
        self.assertEqual(self.runner._stdoutChunk, b'partial')

    def testStdoutReadyNoSeparator(self):
        mock_process = MagicMock()
        data = b'output'
        mock_process.readAllStandardOutput.return_value.data.return_value = data
        self.runner._process = mock_process
        self.runner._separator = None
        self.runner.stdoutAvailable = MagicMock()

        self.runner.onStdoutReady()
        self.runner.stdoutAvailable.emit.assert_called_once_with(data)

    def testStderrReadySeparator(self):
        mock_process = MagicMock()
        data = b'err1\nerr2\nerrpartial'
        mock_process.readAllStandardError.return_value.data.return_value = data
        self.runner._process = mock_process
        self.runner._stderrChunk = b'prev'
        self.runner._separator = b'\n'
        self.runner.stderrAvailable = MagicMock()

        self.runner.onStderrReady()

        self.assertTrue(self.runner.stderrAvailable.emit.called)
        self.assertEqual(self.runner._stderrChunk, b'errpartial')

    def testStderrReadyNoSeparator(self):
        mock_process = MagicMock()
        data = b'error'
        mock_process.readAllStandardError.return_value.data.return_value = data
        self.runner._process = mock_process
        self.runner._separator = None
        self.runner.stderrAvailable = MagicMock()

        self.runner.onStderrReady()
        self.runner.stderrAvailable.emit.assert_called_once_with(data)

    def testFinishedWithChunks(self):
        stdoutSpy = MagicMock()
        stdinSpy = MagicMock()
        self.runner._stdoutChunk = b'Password: '
        self.runner._stderrChunk = b'errleft'
        self.runner._process = MagicMock()
        self.runner.stdoutAvailable.connect(stdoutSpy)
        self.runner.stderrAvailable = MagicMock()
        self.runner.stdinRequired.connect(stdinSpy)
        self.runner.finished = MagicMock()

        self.runner.onRunFinished(5, 0)

        stdoutSpy.assert_called_once_with(b'Password: ')
        self.runner.stderrAvailable.emit.assert_called_once_with(b'errleft')
        stdinSpy.assert_not_called()
        self.assertIsNone(self.runner._process)
        self.assertIsNone(self.runner._stdoutChunk)
        self.assertIsNone(self.runner._stderrChunk)
        self.assertEqual(self.runner.exitCode, 5)
        self.runner.finished.emit.assert_called_once_with(5)
