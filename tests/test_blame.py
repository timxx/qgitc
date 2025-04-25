# -*- coding: utf-8 -*-
import os
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest, QSignalSpy
from qgitc.application import Application
from tests.base import TestBase


class TestBlame(TestBase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.window = cls.app.getWindow(Application.BlameWindow)
        cls.window.showMaximized()

    @classmethod
    def tearDownClass(cls):
        cls.window.close()
        super().tearDownClass()

    def testBlame(self):
        viewer = self.window._view.viewer
        spyFetcher = QSignalSpy(self.window._view._fetcher.fetchFinished)
        spyRev = QSignalSpy(viewer.revisionActivated)

        file = os.path.normpath(os.path.dirname(__file__) + "/../qgitc.py")
        self.window.blame(file, lineNo=1)
        self.assertTrue(spyFetcher.wait(3000))
        self.assertTrue(viewer.textLineCount() > 3)
        self.assertEqual("#!/usr/bin/python3", viewer.textLineAt(0).text())

        self.assertEqual(1, spyRev.count())
        self.assertEqual(spyRev.at(0)[0].sha1,
                         "1ea319103d40a9e3d56f7ebe75449bc49f639dcf")

        pos = viewer.textLineAt(2).boundingRect().center()
        for i in range(2):
            pos.setY(pos.y() + viewer.textLineAt(i).boundingRect().height())

        spyClicked = QSignalSpy(viewer.textLineClicked)
        QTest.mouseClick(viewer.viewport(), Qt.LeftButton, pos=pos.toPoint())
        spyClicked.wait(100)
        self.assertEqual(1, spyClicked.count())
        self.assertEqual(spyClicked.at(0)[0].lineNo(), 2)

        self.assertEqual(2, spyRev.count())
        self.assertEqual(spyRev.at(1)[0].sha1,
                         "901fe56fdebd63bc0ef52d0ca1de07144aa6ae6f")

    def testFind(self):
        spyFetcher = QSignalSpy(self.window._view._fetcher.fetchFinished)
        file = os.path.normpath(os.path.dirname(__file__) + "/../LICENSE")
        self.window.blame(file)
        self.assertTrue(spyFetcher.wait(3000))

        self.assertIsNone(self.window._findWidget)
        QTest.keyClick(self.window, Qt.Key_F, Qt.ControlModifier)
        QTest.qWait(300)
        self.assertIsNotNone(self.window._findWidget)

        findWidget = self.window._findWidget
        spyFind = QSignalSpy(findWidget.find)

        QTest.keyClick(findWidget._leFind, 'L')
        QTest.keyClick(findWidget._leFind, 'I')
        QTest.keyClick(findWidget._leFind, 'C')
        QTest.keyClick(findWidget._leFind, 'E')
        QTest.keyClick(findWidget._leFind, 'N')
        QTest.keyClick(findWidget._leFind, 'S')
        QTest.keyClick(findWidget._leFind, 'E')

        # we delay 200ms in the find widget to emit the signal
        QTest.qWait(300)
        self.assertEqual(1, spyFind.count())

        self.assertEqual("LICENSE", spyFind.at(0)[0])
        self.assertTrue(len(findWidget._findResult) > 1)
