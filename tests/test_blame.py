# -*- coding: utf-8 -*-
import os
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest, QSignalSpy
from qgitc.application import Application
from qgitc.gitutils import Git
from tests.base import TestBase


class TestBlame(TestBase):
    def setUp(self):
        super().setUp()
        self.window = self.app.getWindow(Application.BlameWindow)
        self.window.showMaximized()

    def tearDown(self):
        self.window.close()
        super().tearDown()

    def testBlame(self):
        viewer = self.window._view.viewer
        spyFetcher = QSignalSpy(self.window._view._fetcher.fetchFinished)
        spyRev = QSignalSpy(viewer.revisionActivated)

        file = os.path.join(self.gitDir.name, "test.py")
        self.window.blame(file, lineNo=1)
        self.assertTrue(spyFetcher.wait(3000))
        self.assertEqual(viewer.textLineCount(), 2)
        self.assertEqual("#!/usr/bin/python3", viewer.textLineAt(0).text())

        self.assertEqual(1, spyRev.count())

        sha1 = Git.checkOutput(
            ["log", "-1", "--pretty=format:%H", file]).rstrip().decode()

        self.assertEqual(spyRev.at(0)[0].sha1, sha1)

        pos = viewer.textLineAt(1).boundingRect().center()
        for i in range(1):
            pos.setY(pos.y() + viewer.textLineAt(i).boundingRect().height())

        spyClicked = QSignalSpy(viewer.textLineClicked)
        QTest.mouseClick(viewer.viewport(), Qt.LeftButton, pos=pos.toPoint())
        spyClicked.wait(100)
        self.assertEqual(1, spyClicked.count())
        self.assertEqual(spyClicked.at(0)[0].lineNo(), 1)

    def testFind(self):
        spyFetcher = QSignalSpy(self.window._view._fetcher.fetchFinished)
        file = os.path.join(self.gitDir.name, "README.md")
        self.window.blame(file)
        self.assertTrue(spyFetcher.wait(3000))

        self.assertIsNone(self.window._findWidget)
        QTest.keyClick(self.window, Qt.Key_F, Qt.ControlModifier)
        QTest.qWait(300)
        self.assertIsNotNone(self.window._findWidget)

        findWidget = self.window._findWidget
        spyFind = QSignalSpy(findWidget.find)

        QTest.keyClick(findWidget._leFind, 'T')
        QTest.keyClick(findWidget._leFind, 'e')
        QTest.keyClick(findWidget._leFind, 's')
        QTest.keyClick(findWidget._leFind, 't')

        # we delay 200ms in the find widget to emit the signal
        QTest.qWait(300)
        self.assertEqual(1, spyFind.count())

        self.assertEqual("Test", spyFind.at(0)[0])
        self.assertEqual(len(findWidget._findResult), 1)
