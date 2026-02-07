# -*- coding: utf-8 -*-

from PySide6.QtCore import Qt
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QPlainTextEdit, QPushButton, QVBoxLayout, QWidget

from qgitc.findpanel import FindPanel
from tests.base import TestBase


class TestFindPanel(TestBase):
    def setUp(self):
        super().setUp()

        self.window = QWidget()
        layout = QVBoxLayout(self.window)
        layout.setContentsMargins(0, 0, 0, 0)

        self.edit = QPlainTextEdit(self.window)
        self.otherButton = QPushButton("Other", self.window)

        layout.addWidget(self.edit)
        layout.addWidget(self.otherButton)

        self.window.resize(520, 300)
        self.window.show()
        QTest.qWaitForWindowExposed(self.window)

        self.panel = FindPanel(self.edit.viewport(), self.edit)

    def tearDown(self):
        self.window.close()
        super().tearDown()

    def doCreateRepo(self):
        pass

    def testFindRequestedEmittedAfterTyping(self):
        self.panel.showAnimate()
        QTest.qWait(30)

        spy = QSignalSpy(self.panel.findRequested)

        QTest.keyClicks(self.panel._leFind, "line")
        # debounce timer is 200ms
        self.wait(260)

        self.assertEqual(1, spy.count())
        self.assertEqual("line", spy.at(0)[0])

    def testLayoutSwitchNoOverlapNarrowAndWide(self):
        # Narrow
        self.window.resize(260, 250)
        self.wait(50)
        self.panel.showAnimate()
        self.wait(220)

        self.assertFalse(self.panel._compactLayout)

        le = self.panel._leFind.geometry()
        for w in (self.panel._lbStatus, self.panel._tbPrev, self.panel._tbNext, self.panel._tbClose):
            self.assertFalse(le.intersects(w.geometry()))

        # Wide
        self.window.resize(700, 250)
        self.wait(80)

        # Trigger a size recalculation
        self.panel.resize(self.panel._getShowSize())
        self.wait(30)

        self.assertTrue(self.panel._compactLayout)

        le = self.panel._leFind.geometry()
        for w in (self.panel._lbStatus, self.panel._tbPrev, self.panel._tbNext, self.panel._tbClose):
            self.assertFalse(le.intersects(w.geometry()))
