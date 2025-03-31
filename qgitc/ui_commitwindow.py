# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'commitwindow.ui'
##
## Created by: Qt User Interface Compiler version 6.8.2
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from PySide6.QtCore import (QCoreApplication, QDate, QDateTime, QLocale,
    QMetaObject, QObject, QPoint, QRect,
    QSize, QTime, QUrl, Qt)
from PySide6.QtGui import (QBrush, QColor, QConicalGradient, QCursor,
    QFont, QFontDatabase, QGradient, QIcon,
    QImage, QKeySequence, QLinearGradient, QPainter,
    QPalette, QPixmap, QRadialGradient, QTransform)
from PySide6.QtWidgets import (QApplication, QCheckBox, QGroupBox, QHBoxLayout,
    QLabel, QLineEdit, QListView, QMainWindow,
    QMenuBar, QPlainTextEdit, QPushButton, QSizePolicy,
    QSpacerItem, QSplitter, QStatusBar, QVBoxLayout,
    QWidget)

from .patchviewer import PatchViewer
from .waitingspinnerwidget import QtWaitingSpinner

class Ui_CommitWindow(object):
    def setupUi(self, CommitWindow):
        if not CommitWindow.objectName():
            CommitWindow.setObjectName(u"CommitWindow")
        CommitWindow.resize(1059, 607)
        self.centralwidget = QWidget(CommitWindow)
        self.centralwidget.setObjectName(u"centralwidget")
        self.horizontalLayout_2 = QHBoxLayout(self.centralwidget)
        self.horizontalLayout_2.setObjectName(u"horizontalLayout_2")
        self.splitterMain = QSplitter(self.centralwidget)
        self.splitterMain.setObjectName(u"splitterMain")
        self.splitterMain.setOrientation(Qt.Orientation.Horizontal)
        self.splitter = QSplitter(self.splitterMain)
        self.splitter.setObjectName(u"splitter")
        self.splitter.setOrientation(Qt.Orientation.Vertical)
        self.verticalLayoutWidget = QWidget(self.splitter)
        self.verticalLayoutWidget.setObjectName(u"verticalLayoutWidget")
        self.verticalLayout = QVBoxLayout(self.verticalLayoutWidget)
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.verticalLayout.setContentsMargins(0, 0, 0, 0)
        self.horizontalLayout_4 = QHBoxLayout()
        self.horizontalLayout_4.setObjectName(u"horizontalLayout_4")
        self.lbUnstaged = QLabel(self.verticalLayoutWidget)
        self.lbUnstaged.setObjectName(u"lbUnstaged")

        self.horizontalLayout_4.addWidget(self.lbUnstaged)

        self.spinnerUnstaged = QtWaitingSpinner(self.verticalLayoutWidget)
        self.spinnerUnstaged.setObjectName(u"spinnerUnstaged")

        self.horizontalLayout_4.addWidget(self.spinnerUnstaged)

        self.horizontalSpacer_3 = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.horizontalLayout_4.addItem(self.horizontalSpacer_3)


        self.verticalLayout.addLayout(self.horizontalLayout_4)

        self.leFilterFiles = QLineEdit(self.verticalLayoutWidget)
        self.leFilterFiles.setObjectName(u"leFilterFiles")

        self.verticalLayout.addWidget(self.leFilterFiles)

        self.lvFiles = QListView(self.verticalLayoutWidget)
        self.lvFiles.setObjectName(u"lvFiles")

        self.verticalLayout.addWidget(self.lvFiles)

        self.splitter.addWidget(self.verticalLayoutWidget)
        self.verticalLayoutWidget_2 = QWidget(self.splitter)
        self.verticalLayoutWidget_2.setObjectName(u"verticalLayoutWidget_2")
        self.verticalLayout_2 = QVBoxLayout(self.verticalLayoutWidget_2)
        self.verticalLayout_2.setObjectName(u"verticalLayout_2")
        self.verticalLayout_2.setContentsMargins(0, 0, 0, 0)
        self.label = QLabel(self.verticalLayoutWidget_2)
        self.label.setObjectName(u"label")

        self.verticalLayout_2.addWidget(self.label)

        self.leFilterStaged = QLineEdit(self.verticalLayoutWidget_2)
        self.leFilterStaged.setObjectName(u"leFilterStaged")

        self.verticalLayout_2.addWidget(self.leFilterStaged)

        self.lvStaged = QListView(self.verticalLayoutWidget_2)
        self.lvStaged.setObjectName(u"lvStaged")

        self.verticalLayout_2.addWidget(self.lvStaged)

        self.splitter.addWidget(self.verticalLayoutWidget_2)
        self.splitterMain.addWidget(self.splitter)
        self.splitterRight = QSplitter(self.splitterMain)
        self.splitterRight.setObjectName(u"splitterRight")
        self.splitterRight.setOrientation(Qt.Orientation.Vertical)
        self.verticalLayoutWidget_3 = QWidget(self.splitterRight)
        self.verticalLayoutWidget_3.setObjectName(u"verticalLayoutWidget_3")
        self.verticalLayout_7 = QVBoxLayout(self.verticalLayoutWidget_3)
        self.verticalLayout_7.setObjectName(u"verticalLayout_7")
        self.verticalLayout_7.setContentsMargins(0, 0, 0, 0)
        self.horizontalLayout_3 = QHBoxLayout()
        self.horizontalLayout_3.setObjectName(u"horizontalLayout_3")
        self.label_2 = QLabel(self.verticalLayoutWidget_3)
        self.label_2.setObjectName(u"label_2")

        self.horizontalLayout_3.addWidget(self.label_2)

        self.spinnerDiff = QtWaitingSpinner(self.verticalLayoutWidget_3)
        self.spinnerDiff.setObjectName(u"spinnerDiff")

        self.horizontalLayout_3.addWidget(self.spinnerDiff)

        self.horizontalSpacer_4 = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.horizontalLayout_3.addItem(self.horizontalSpacer_4)


        self.verticalLayout_7.addLayout(self.horizontalLayout_3)

        self.viewer = PatchViewer(self.verticalLayoutWidget_3)
        self.viewer.setObjectName(u"viewer")

        self.verticalLayout_7.addWidget(self.viewer)

        self.splitterRight.addWidget(self.verticalLayoutWidget_3)
        self.horizontalLayoutWidget = QWidget(self.splitterRight)
        self.horizontalLayoutWidget.setObjectName(u"horizontalLayoutWidget")
        self.verticalLayout_4 = QVBoxLayout(self.horizontalLayoutWidget)
        self.verticalLayout_4.setObjectName(u"verticalLayout_4")
        self.verticalLayout_4.setContentsMargins(0, 0, 0, 0)
        self.groupBox = QGroupBox(self.horizontalLayoutWidget)
        self.groupBox.setObjectName(u"groupBox")
        self.groupBox.setFlat(True)

        self.verticalLayout_4.addWidget(self.groupBox)

        self.teMessage = QPlainTextEdit(self.horizontalLayoutWidget)
        self.teMessage.setObjectName(u"teMessage")
        sizePolicy = QSizePolicy(QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.teMessage.sizePolicy().hasHeightForWidth())
        self.teMessage.setSizePolicy(sizePolicy)

        self.verticalLayout_4.addWidget(self.teMessage)

        self.horizontalLayout = QHBoxLayout()
        self.horizontalLayout.setObjectName(u"horizontalLayout")
        self.cbAmend = QCheckBox(self.horizontalLayoutWidget)
        self.cbAmend.setObjectName(u"cbAmend")

        self.horizontalLayout.addWidget(self.cbAmend)

        self.horizontalSpacer = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.horizontalLayout.addItem(self.horizontalSpacer)

        self.btnCommit = QPushButton(self.horizontalLayoutWidget)
        self.btnCommit.setObjectName(u"btnCommit")

        self.horizontalLayout.addWidget(self.btnCommit)

        self.horizontalSpacer_2 = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.horizontalLayout.addItem(self.horizontalSpacer_2)

        self.cbRunAction = QCheckBox(self.horizontalLayoutWidget)
        self.cbRunAction.setObjectName(u"cbRunAction")

        self.horizontalLayout.addWidget(self.cbRunAction)


        self.verticalLayout_4.addLayout(self.horizontalLayout)

        self.splitterRight.addWidget(self.horizontalLayoutWidget)
        self.splitterMain.addWidget(self.splitterRight)

        self.horizontalLayout_2.addWidget(self.splitterMain)

        CommitWindow.setCentralWidget(self.centralwidget)
        self.menubar = QMenuBar(CommitWindow)
        self.menubar.setObjectName(u"menubar")
        self.menubar.setGeometry(QRect(0, 0, 1059, 33))
        CommitWindow.setMenuBar(self.menubar)
        self.statusbar = QStatusBar(CommitWindow)
        self.statusbar.setObjectName(u"statusbar")
        CommitWindow.setStatusBar(self.statusbar)

        self.retranslateUi(CommitWindow)

        QMetaObject.connectSlotsByName(CommitWindow)
    # setupUi

    def retranslateUi(self, CommitWindow):
        CommitWindow.setWindowTitle(QCoreApplication.translate("CommitWindow", u"QGitc Commit", None))
        self.lbUnstaged.setText(QCoreApplication.translate("CommitWindow", u"Unstaged", None))
        self.label.setText(QCoreApplication.translate("CommitWindow", u"Staged", None))
        self.label_2.setText(QCoreApplication.translate("CommitWindow", u"Diff", None))
        self.groupBox.setTitle(QCoreApplication.translate("CommitWindow", u"Commit message", None))
        self.cbAmend.setText(QCoreApplication.translate("CommitWindow", u"Amend Last Message", None))
        self.btnCommit.setText(QCoreApplication.translate("CommitWindow", u"&Commit", None))
        self.cbRunAction.setText(QCoreApplication.translate("CommitWindow", u"&Run Action After Commit", None))
    # retranslateUi

