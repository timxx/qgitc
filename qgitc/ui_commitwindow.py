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
from PySide6.QtWidgets import (QApplication, QCheckBox, QHBoxLayout, QLineEdit,
    QListView, QMainWindow, QMenuBar, QPlainTextEdit,
    QPushButton, QSizePolicy, QSpacerItem, QSplitter,
    QStatusBar, QVBoxLayout, QWidget)

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
        self.leFilterStaged = QLineEdit(self.verticalLayoutWidget_2)
        self.leFilterStaged.setObjectName(u"leFilterStaged")

        self.verticalLayout_2.addWidget(self.leFilterStaged)

        self.lvStaged = QListView(self.verticalLayoutWidget_2)
        self.lvStaged.setObjectName(u"lvStaged")

        self.verticalLayout_2.addWidget(self.lvStaged)

        self.splitter.addWidget(self.verticalLayoutWidget_2)
        self.splitterMain.addWidget(self.splitter)
        self.splitter_2 = QSplitter(self.splitterMain)
        self.splitter_2.setObjectName(u"splitter_2")
        self.splitter_2.setOrientation(Qt.Orientation.Vertical)
        self.viewer = QWidget(self.splitter_2)
        self.viewer.setObjectName(u"viewer")
        self.splitter_2.addWidget(self.viewer)
        self.horizontalLayoutWidget = QWidget(self.splitter_2)
        self.horizontalLayoutWidget.setObjectName(u"horizontalLayoutWidget")
        self.horizontalLayout = QHBoxLayout(self.horizontalLayoutWidget)
        self.horizontalLayout.setObjectName(u"horizontalLayout")
        self.horizontalLayout.setContentsMargins(0, 0, 0, 0)
        self.verticalLayout_3 = QVBoxLayout()
        self.verticalLayout_3.setObjectName(u"verticalLayout_3")
        self.btnCommit = QPushButton(self.horizontalLayoutWidget)
        self.btnCommit.setObjectName(u"btnCommit")

        self.verticalLayout_3.addWidget(self.btnCommit)

        self.cbAmend = QCheckBox(self.horizontalLayoutWidget)
        self.cbAmend.setObjectName(u"cbAmend")

        self.verticalLayout_3.addWidget(self.cbAmend)

        self.btnPush = QPushButton(self.horizontalLayoutWidget)
        self.btnPush.setObjectName(u"btnPush")

        self.verticalLayout_3.addWidget(self.btnPush)

        self.verticalSpacer = QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)

        self.verticalLayout_3.addItem(self.verticalSpacer)


        self.horizontalLayout.addLayout(self.verticalLayout_3)

        self.teMessage = QPlainTextEdit(self.horizontalLayoutWidget)
        self.teMessage.setObjectName(u"teMessage")

        self.horizontalLayout.addWidget(self.teMessage)

        self.splitter_2.addWidget(self.horizontalLayoutWidget)
        self.splitterMain.addWidget(self.splitter_2)

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
        self.btnCommit.setText(QCoreApplication.translate("CommitWindow", u"&Commit", None))
        self.cbAmend.setText(QCoreApplication.translate("CommitWindow", u"Amend commit", None))
        self.btnPush.setText(QCoreApplication.translate("CommitWindow", u"&Push", None))
    # retranslateUi

