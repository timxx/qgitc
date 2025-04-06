# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'commitwindow.ui'
##
## Created by: Qt User Interface Compiler version 6.9.0
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
from PySide6.QtWidgets import (QApplication, QCheckBox, QFrame, QHBoxLayout,
    QLabel, QLineEdit, QMainWindow, QPlainTextEdit,
    QProgressBar, QPushButton, QSizePolicy, QSpacerItem,
    QSplitter, QStackedWidget, QStatusBar, QToolButton,
    QVBoxLayout, QWidget)

from .coloredicontoolbutton import ColoredIconToolButton
from .commitmessageedit import CommitMessageEdit
from .emptystatelistview import EmptyStateListView
from .menubutton import MenuButton
from .patchviewer import PatchViewer
from .waitingspinnerwidget import QtWaitingSpinner

class Ui_CommitWindow(object):
    def setupUi(self, CommitWindow):
        if not CommitWindow.objectName():
            CommitWindow.setObjectName(u"CommitWindow")
        CommitWindow.resize(932, 594)
        self.centralwidget = QWidget(CommitWindow)
        self.centralwidget.setObjectName(u"centralwidget")
        self.horizontalLayout_2 = QHBoxLayout(self.centralwidget)
        self.horizontalLayout_2.setObjectName(u"horizontalLayout_2")
        self.splitterMain = QSplitter(self.centralwidget)
        self.splitterMain.setObjectName(u"splitterMain")
        self.splitterMain.setOrientation(Qt.Orientation.Horizontal)
        self.splitterLeft = QSplitter(self.splitterMain)
        self.splitterLeft.setObjectName(u"splitterLeft")
        self.splitterLeft.setOrientation(Qt.Orientation.Vertical)
        self.frame = QFrame(self.splitterLeft)
        self.frame.setObjectName(u"frame")
        self.frame.setFrameShape(QFrame.Shape.StyledPanel)
        self.frame.setFrameShadow(QFrame.Shadow.Raised)
        self.verticalLayout_5 = QVBoxLayout(self.frame)
        self.verticalLayout_5.setSpacing(6)
        self.verticalLayout_5.setObjectName(u"verticalLayout_5")
        self.verticalLayout_5.setContentsMargins(4, 4, 4, 4)
        self.horizontalLayout_4 = QHBoxLayout()
        self.horizontalLayout_4.setObjectName(u"horizontalLayout_4")
        self.tbRefresh = ColoredIconToolButton(self.frame)
        self.tbRefresh.setObjectName(u"tbRefresh")
        self.tbRefresh.setIconSize(QSize(20, 20))

        self.horizontalLayout_4.addWidget(self.tbRefresh)

        self.tbWDChanges = MenuButton(self.frame)
        self.tbWDChanges.setObjectName(u"tbWDChanges")
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.tbWDChanges.sizePolicy().hasHeightForWidth())
        self.tbWDChanges.setSizePolicy(sizePolicy)
        self.tbWDChanges.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.tbWDChanges.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.tbWDChanges.setArrowType(Qt.ArrowType.NoArrow)

        self.horizontalLayout_4.addWidget(self.tbWDChanges)

        self.spinnerUnstaged = QtWaitingSpinner(self.frame)
        self.spinnerUnstaged.setObjectName(u"spinnerUnstaged")

        self.horizontalLayout_4.addWidget(self.spinnerUnstaged)

        self.horizontalSpacer_3 = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.horizontalLayout_4.addItem(self.horizontalSpacer_3)


        self.verticalLayout_5.addLayout(self.horizontalLayout_4)

        self.leFilterFiles = QLineEdit(self.frame)
        self.leFilterFiles.setObjectName(u"leFilterFiles")

        self.verticalLayout_5.addWidget(self.leFilterFiles)

        self.lvFiles = EmptyStateListView(self.frame)
        self.lvFiles.setObjectName(u"lvFiles")

        self.verticalLayout_5.addWidget(self.lvFiles)

        self.splitterLeft.addWidget(self.frame)
        self.frame_2 = QFrame(self.splitterLeft)
        self.frame_2.setObjectName(u"frame_2")
        self.frame_2.setFrameShape(QFrame.Shape.StyledPanel)
        self.frame_2.setFrameShadow(QFrame.Shadow.Raised)
        self.verticalLayout_3 = QVBoxLayout(self.frame_2)
        self.verticalLayout_3.setObjectName(u"verticalLayout_3")
        self.verticalLayout_3.setContentsMargins(4, 4, 4, 4)
        self.horizontalLayout_6 = QHBoxLayout()
        self.horizontalLayout_6.setSpacing(3)
        self.horizontalLayout_6.setObjectName(u"horizontalLayout_6")
        self.tbUnstageAll = ColoredIconToolButton(self.frame_2)
        self.tbUnstageAll.setObjectName(u"tbUnstageAll")
        self.tbUnstageAll.setIconSize(QSize(20, 20))

        self.horizontalLayout_6.addWidget(self.tbUnstageAll)

        self.tbUnstage = ColoredIconToolButton(self.frame_2)
        self.tbUnstage.setObjectName(u"tbUnstage")
        sizePolicy.setHeightForWidth(self.tbUnstage.sizePolicy().hasHeightForWidth())
        self.tbUnstage.setSizePolicy(sizePolicy)
        self.tbUnstage.setIconSize(QSize(20, 20))
        self.tbUnstage.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)

        self.horizontalLayout_6.addWidget(self.tbUnstage)

        self.horizontalSpacer_7 = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.horizontalLayout_6.addItem(self.horizontalSpacer_7)

        self.tbStage = ColoredIconToolButton(self.frame_2)
        self.tbStage.setObjectName(u"tbStage")
        self.tbStage.setIconSize(QSize(20, 20))
        self.tbStage.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)

        self.horizontalLayout_6.addWidget(self.tbStage)

        self.tbStageAll = ColoredIconToolButton(self.frame_2)
        self.tbStageAll.setObjectName(u"tbStageAll")
        self.tbStageAll.setIconSize(QSize(20, 20))

        self.horizontalLayout_6.addWidget(self.tbStageAll)


        self.verticalLayout_3.addLayout(self.horizontalLayout_6)

        self.leFilterStaged = QLineEdit(self.frame_2)
        self.leFilterStaged.setObjectName(u"leFilterStaged")

        self.verticalLayout_3.addWidget(self.leFilterStaged)

        self.lvStaged = EmptyStateListView(self.frame_2)
        self.lvStaged.setObjectName(u"lvStaged")

        self.verticalLayout_3.addWidget(self.lvStaged)

        self.splitterLeft.addWidget(self.frame_2)
        self.splitterMain.addWidget(self.splitterLeft)
        self.splitterRight = QSplitter(self.splitterMain)
        self.splitterRight.setObjectName(u"splitterRight")
        self.splitterRight.setOrientation(Qt.Orientation.Vertical)
        self.frame_3 = QFrame(self.splitterRight)
        self.frame_3.setObjectName(u"frame_3")
        self.frame_3.setFrameShape(QFrame.Shape.StyledPanel)
        self.frame_3.setFrameShadow(QFrame.Shadow.Raised)
        self.verticalLayout = QVBoxLayout(self.frame_3)
        self.verticalLayout.setSpacing(6)
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.verticalLayout.setContentsMargins(4, 4, 4, 4)
        self.horizontalLayout_5 = QHBoxLayout()
        self.horizontalLayout_5.setObjectName(u"horizontalLayout_5")
        self.label_3 = QLabel(self.frame_3)
        self.label_3.setObjectName(u"label_3")

        self.horizontalLayout_5.addWidget(self.label_3)

        self.spinnerDiff = QtWaitingSpinner(self.frame_3)
        self.spinnerDiff.setObjectName(u"spinnerDiff")

        self.horizontalLayout_5.addWidget(self.spinnerDiff)

        self.horizontalSpacer_5 = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.horizontalLayout_5.addItem(self.horizontalSpacer_5)


        self.verticalLayout.addLayout(self.horizontalLayout_5)

        self.viewer = PatchViewer(self.frame_3)
        self.viewer.setObjectName(u"viewer")

        self.verticalLayout.addWidget(self.viewer)

        self.splitterRight.addWidget(self.frame_3)
        self.stackedWidget = QStackedWidget(self.splitterRight)
        self.stackedWidget.setObjectName(u"stackedWidget")
        self.pageMessage = QWidget()
        self.pageMessage.setObjectName(u"pageMessage")
        self.verticalLayout_4 = QVBoxLayout(self.pageMessage)
        self.verticalLayout_4.setObjectName(u"verticalLayout_4")
        self.verticalLayout_4.setContentsMargins(0, 0, 0, 0)
        self.frame_4 = QFrame(self.pageMessage)
        self.frame_4.setObjectName(u"frame_4")
        self.frame_4.setFrameShape(QFrame.Shape.StyledPanel)
        self.frame_4.setFrameShadow(QFrame.Shadow.Raised)
        self.verticalLayout_2 = QVBoxLayout(self.frame_4)
        self.verticalLayout_2.setObjectName(u"verticalLayout_2")
        self.verticalLayout_2.setContentsMargins(4, 4, 4, 4)
        self.horizontalLayout_3 = QHBoxLayout()
        self.horizontalLayout_3.setObjectName(u"horizontalLayout_3")
        self.label = QLabel(self.frame_4)
        self.label.setObjectName(u"label")

        self.horizontalLayout_3.addWidget(self.label)

        self.btnGenMessage = ColoredIconToolButton(self.frame_4)
        self.btnGenMessage.setObjectName(u"btnGenMessage")

        self.horizontalLayout_3.addWidget(self.btnGenMessage)

        self.btnCancelGen = ColoredIconToolButton(self.frame_4)
        self.btnCancelGen.setObjectName(u"btnCancelGen")

        self.horizontalLayout_3.addWidget(self.btnCancelGen)

        self.btnCodeReview = ColoredIconToolButton(self.frame_4)
        self.btnCodeReview.setObjectName(u"btnCodeReview")

        self.horizontalLayout_3.addWidget(self.btnCodeReview)

        self.btnShowLog = ColoredIconToolButton(self.frame_4)
        self.btnShowLog.setObjectName(u"btnShowLog")

        self.horizontalLayout_3.addWidget(self.btnShowLog)

        self.horizontalSpacer_4 = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.horizontalLayout_3.addItem(self.horizontalSpacer_4)

        self.tbOptions = ColoredIconToolButton(self.frame_4)
        self.tbOptions.setObjectName(u"tbOptions")
        sizePolicy.setHeightForWidth(self.tbOptions.sizePolicy().hasHeightForWidth())
        self.tbOptions.setSizePolicy(sizePolicy)
        self.tbOptions.setIconSize(QSize(16, 16))
        self.tbOptions.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)

        self.horizontalLayout_3.addWidget(self.tbOptions)


        self.verticalLayout_2.addLayout(self.horizontalLayout_3)

        self.teMessage = CommitMessageEdit(self.frame_4)
        self.teMessage.setObjectName(u"teMessage")
        sizePolicy1 = QSizePolicy(QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Expanding)
        sizePolicy1.setHorizontalStretch(0)
        sizePolicy1.setVerticalStretch(0)
        sizePolicy1.setHeightForWidth(self.teMessage.sizePolicy().hasHeightForWidth())
        self.teMessage.setSizePolicy(sizePolicy1)

        self.verticalLayout_2.addWidget(self.teMessage)

        self.horizontalLayout = QHBoxLayout()
        self.horizontalLayout.setObjectName(u"horizontalLayout")
        self.cbAmend = QCheckBox(self.frame_4)
        self.cbAmend.setObjectName(u"cbAmend")

        self.horizontalLayout.addWidget(self.cbAmend)

        self.horizontalSpacer = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.horizontalLayout.addItem(self.horizontalSpacer)

        self.btnCommit = QPushButton(self.frame_4)
        self.btnCommit.setObjectName(u"btnCommit")

        self.horizontalLayout.addWidget(self.btnCommit)

        self.horizontalSpacer_2 = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.horizontalLayout.addItem(self.horizontalSpacer_2)

        self.cbRunAction = QCheckBox(self.frame_4)
        self.cbRunAction.setObjectName(u"cbRunAction")

        self.horizontalLayout.addWidget(self.cbRunAction)


        self.verticalLayout_2.addLayout(self.horizontalLayout)


        self.verticalLayout_4.addWidget(self.frame_4)

        self.stackedWidget.addWidget(self.pageMessage)
        self.pageProgress = QWidget()
        self.pageProgress.setObjectName(u"pageProgress")
        self.verticalLayout_7 = QVBoxLayout(self.pageProgress)
        self.verticalLayout_7.setObjectName(u"verticalLayout_7")
        self.verticalLayout_7.setContentsMargins(0, 0, 0, 0)
        self.frame_5 = QFrame(self.pageProgress)
        self.frame_5.setObjectName(u"frame_5")
        self.frame_5.setFrameShape(QFrame.Shape.StyledPanel)
        self.frame_5.setFrameShadow(QFrame.Shadow.Raised)
        self.verticalLayout_6 = QVBoxLayout(self.frame_5)
        self.verticalLayout_6.setObjectName(u"verticalLayout_6")
        self.verticalLayout_6.setContentsMargins(4, 4, 4, 4)
        self.lbStatus = QLabel(self.frame_5)
        self.lbStatus.setObjectName(u"lbStatus")

        self.verticalLayout_6.addWidget(self.lbStatus)

        self.progressBar = QProgressBar(self.frame_5)
        self.progressBar.setObjectName(u"progressBar")
        self.progressBar.setValue(0)
        self.progressBar.setTextVisible(False)

        self.verticalLayout_6.addWidget(self.progressBar)

        self.teOutput = QPlainTextEdit(self.frame_5)
        self.teOutput.setObjectName(u"teOutput")
        self.teOutput.setReadOnly(True)

        self.verticalLayout_6.addWidget(self.teOutput)

        self.horizontalLayout_7 = QHBoxLayout()
        self.horizontalLayout_7.setObjectName(u"horizontalLayout_7")
        self.horizontalSpacer_6 = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.horizontalLayout_7.addItem(self.horizontalSpacer_6)

        self.btnAction = QPushButton(self.frame_5)
        self.btnAction.setObjectName(u"btnAction")

        self.horizontalLayout_7.addWidget(self.btnAction)

        self.horizontalSpacer_8 = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.horizontalLayout_7.addItem(self.horizontalSpacer_8)


        self.verticalLayout_6.addLayout(self.horizontalLayout_7)


        self.verticalLayout_7.addWidget(self.frame_5)

        self.stackedWidget.addWidget(self.pageProgress)
        self.splitterRight.addWidget(self.stackedWidget)
        self.splitterMain.addWidget(self.splitterRight)

        self.horizontalLayout_2.addWidget(self.splitterMain)

        CommitWindow.setCentralWidget(self.centralwidget)
        self.statusbar = QStatusBar(CommitWindow)
        self.statusbar.setObjectName(u"statusbar")
        CommitWindow.setStatusBar(self.statusbar)
        QWidget.setTabOrder(self.teMessage, self.btnCommit)
        QWidget.setTabOrder(self.btnCommit, self.cbAmend)
        QWidget.setTabOrder(self.cbAmend, self.lvFiles)
        QWidget.setTabOrder(self.lvFiles, self.tbUnstageAll)
        QWidget.setTabOrder(self.tbUnstageAll, self.tbUnstage)
        QWidget.setTabOrder(self.tbUnstage, self.tbStage)
        QWidget.setTabOrder(self.tbStage, self.tbStageAll)
        QWidget.setTabOrder(self.tbStageAll, self.leFilterStaged)
        QWidget.setTabOrder(self.leFilterStaged, self.lvStaged)
        QWidget.setTabOrder(self.lvStaged, self.tbRefresh)
        QWidget.setTabOrder(self.tbRefresh, self.leFilterFiles)
        QWidget.setTabOrder(self.leFilterFiles, self.tbWDChanges)
        QWidget.setTabOrder(self.tbWDChanges, self.cbRunAction)

        self.retranslateUi(CommitWindow)

        self.stackedWidget.setCurrentIndex(0)


        QMetaObject.connectSlotsByName(CommitWindow)
    # setupUi

    def retranslateUi(self, CommitWindow):
        CommitWindow.setWindowTitle(QCoreApplication.translate("CommitWindow", u"QGitc Commit", None))
        self.tbRefresh.setText("")
        self.tbWDChanges.setText(QCoreApplication.translate("CommitWindow", u"Working directory changes", None))
        self.tbUnstageAll.setText("")
        self.tbUnstage.setText(QCoreApplication.translate("CommitWindow", u"&Unstage", None))
        self.tbStage.setText(QCoreApplication.translate("CommitWindow", u"&Stage", None))
        self.tbStageAll.setText("")
        self.label_3.setText(QCoreApplication.translate("CommitWindow", u"Diff", None))
        self.label.setText(QCoreApplication.translate("CommitWindow", u"Commit message", None))
#if QT_CONFIG(tooltip)
        self.btnGenMessage.setToolTip(QCoreApplication.translate("CommitWindow", u"Generate Commit Message with AI Assistant", None))
#endif // QT_CONFIG(tooltip)
        self.btnGenMessage.setText("")
#if QT_CONFIG(tooltip)
        self.btnCancelGen.setToolTip(QCoreApplication.translate("CommitWindow", u"Cancel", None))
#endif // QT_CONFIG(tooltip)
        self.btnCancelGen.setText("")
#if QT_CONFIG(tooltip)
        self.btnCodeReview.setToolTip(QCoreApplication.translate("CommitWindow", u"Make Code Review With AI Assistant", None))
#endif // QT_CONFIG(tooltip)
        self.btnCodeReview.setText("")
#if QT_CONFIG(tooltip)
        self.btnShowLog.setToolTip(QCoreApplication.translate("CommitWindow", u"Show Log Window", None))
#endif // QT_CONFIG(tooltip)
        self.btnShowLog.setText("")
        self.tbOptions.setText(QCoreApplication.translate("CommitWindow", u"Options", None))
        self.cbAmend.setText(QCoreApplication.translate("CommitWindow", u"&Amend last message", None))
        self.btnCommit.setText(QCoreApplication.translate("CommitWindow", u"&Commit", None))
#if QT_CONFIG(shortcut)
        self.btnCommit.setShortcut(QCoreApplication.translate("CommitWindow", u"Ctrl+Return", None))
#endif // QT_CONFIG(shortcut)
#if QT_CONFIG(tooltip)
        self.cbRunAction.setToolTip(QCoreApplication.translate("CommitWindow", u"Run custom actions after commit, please config actions in Options", None))
#endif // QT_CONFIG(tooltip)
        self.cbRunAction.setText(QCoreApplication.translate("CommitWindow", u"&Run actions after commit", None))
        self.lbStatus.setText(QCoreApplication.translate("CommitWindow", u"Working on commit...", None))
        self.btnAction.setText(QCoreApplication.translate("CommitWindow", u"&Abort", None))
    # retranslateUi

