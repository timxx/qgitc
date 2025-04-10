# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'preferences.ui'
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
from PySide6.QtWidgets import (QAbstractButton, QAbstractItemView, QApplication, QCheckBox,
    QComboBox, QDialog, QDialogButtonBox, QFontComboBox,
    QGridLayout, QGroupBox, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QPushButton, QSizePolicy,
    QSpacerItem, QSpinBox, QTabWidget, QTableView,
    QVBoxLayout, QWidget)

from .colorwidget import ColorWidget
from .linkeditwidget import LinkEditWidget

class Ui_Preferences(object):
    def setupUi(self, Preferences):
        if not Preferences.objectName():
            Preferences.setObjectName(u"Preferences")
        Preferences.resize(659, 430)
        self.verticalLayout_2 = QVBoxLayout(Preferences)
        self.verticalLayout_2.setObjectName(u"verticalLayout_2")
        self.tabWidget = QTabWidget(Preferences)
        self.tabWidget.setObjectName(u"tabWidget")
        self.tabGeneral = QWidget()
        self.tabGeneral.setObjectName(u"tabGeneral")
        self.verticalLayout = QVBoxLayout(self.tabGeneral)
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.groupBox_6 = QGroupBox(self.tabGeneral)
        self.groupBox_6.setObjectName(u"groupBox_6")
        self.verticalLayout_5 = QVBoxLayout(self.groupBox_6)
        self.verticalLayout_5.setObjectName(u"verticalLayout_5")
        self.cbEsc = QCheckBox(self.groupBox_6)
        self.cbEsc.setObjectName(u"cbEsc")

        self.verticalLayout_5.addWidget(self.cbEsc)

        self.cbState = QCheckBox(self.groupBox_6)
        self.cbState.setObjectName(u"cbState")

        self.verticalLayout_5.addWidget(self.cbState)

        self.horizontalLayout_8 = QHBoxLayout()
        self.horizontalLayout_8.setObjectName(u"horizontalLayout_8")
        self.cbCheckUpdates = QCheckBox(self.groupBox_6)
        self.cbCheckUpdates.setObjectName(u"cbCheckUpdates")

        self.horizontalLayout_8.addWidget(self.cbCheckUpdates)

        self.sbDays = QSpinBox(self.groupBox_6)
        self.sbDays.setObjectName(u"sbDays")
        self.sbDays.setMinimum(1)

        self.horizontalLayout_8.addWidget(self.sbDays)

        self.label_14 = QLabel(self.groupBox_6)
        self.label_14.setObjectName(u"label_14")

        self.horizontalLayout_8.addWidget(self.label_14)

        self.horizontalSpacer_8 = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.horizontalLayout_8.addItem(self.horizontalSpacer_8)


        self.verticalLayout_5.addLayout(self.horizontalLayout_8)

        self.horizontalLayout_10 = QHBoxLayout()
        self.horizontalLayout_10.setObjectName(u"horizontalLayout_10")
        self.label_18 = QLabel(self.groupBox_6)
        self.label_18.setObjectName(u"label_18")

        self.horizontalLayout_10.addWidget(self.label_18)

        self.cbColorSchema = QComboBox(self.groupBox_6)
        self.cbColorSchema.setObjectName(u"cbColorSchema")

        self.horizontalLayout_10.addWidget(self.cbColorSchema)

        self.label_23 = QLabel(self.groupBox_6)
        self.label_23.setObjectName(u"label_23")

        self.horizontalLayout_10.addWidget(self.label_23)

        self.cbStyle = QComboBox(self.groupBox_6)
        self.cbStyle.setObjectName(u"cbStyle")

        self.horizontalLayout_10.addWidget(self.cbStyle)

        self.horizontalSpacer_9 = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.horizontalLayout_10.addItem(self.horizontalSpacer_9)


        self.verticalLayout_5.addLayout(self.horizontalLayout_10)

        self.horizontalLayout_15 = QHBoxLayout()
        self.horizontalLayout_15.setObjectName(u"horizontalLayout_15")
        self.label_21 = QLabel(self.groupBox_6)
        self.label_21.setObjectName(u"label_21")

        self.horizontalLayout_15.addWidget(self.label_21)

        self.cbLogLevel = QComboBox(self.groupBox_6)
        self.cbLogLevel.setObjectName(u"cbLogLevel")

        self.horizontalLayout_15.addWidget(self.cbLogLevel)

        self.horizontalSpacer_12 = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.horizontalLayout_15.addItem(self.horizontalSpacer_12)


        self.verticalLayout_5.addLayout(self.horizontalLayout_15)

        self.horizontalLayout_9 = QHBoxLayout()
        self.horizontalLayout_9.setObjectName(u"horizontalLayout_9")
        self.label_15 = QLabel(self.groupBox_6)
        self.label_15.setObjectName(u"label_15")

        self.horizontalLayout_9.addWidget(self.label_15)

        self.leGitPath = QLineEdit(self.groupBox_6)
        self.leGitPath.setObjectName(u"leGitPath")

        self.horizontalLayout_9.addWidget(self.leGitPath)

        self.btnChooseGit = QPushButton(self.groupBox_6)
        self.btnChooseGit.setObjectName(u"btnChooseGit")

        self.horizontalLayout_9.addWidget(self.btnChooseGit)


        self.verticalLayout_5.addLayout(self.horizontalLayout_9)


        self.verticalLayout.addWidget(self.groupBox_6)

        self.groupBox_5 = QGroupBox(self.tabGeneral)
        self.groupBox_5.setObjectName(u"groupBox_5")
        self.verticalLayout_6 = QVBoxLayout(self.groupBox_5)
        self.verticalLayout_6.setObjectName(u"verticalLayout_6")
        self.horizontalLayout = QHBoxLayout()
        self.horizontalLayout.setObjectName(u"horizontalLayout")
        self.cbShowWhitespace = QCheckBox(self.groupBox_5)
        self.cbShowWhitespace.setObjectName(u"cbShowWhitespace")

        self.horizontalLayout.addWidget(self.cbShowWhitespace)

        self.label_10 = QLabel(self.groupBox_5)
        self.label_10.setObjectName(u"label_10")

        self.horizontalLayout.addWidget(self.label_10)

        self.sbTabSize = QSpinBox(self.groupBox_5)
        self.sbTabSize.setObjectName(u"sbTabSize")
        self.sbTabSize.setMinimum(1)
        self.sbTabSize.setMaximum(8)
        self.sbTabSize.setValue(4)

        self.horizontalLayout.addWidget(self.sbTabSize)

        self.horizontalSpacer = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.horizontalLayout.addItem(self.horizontalSpacer)


        self.verticalLayout_6.addLayout(self.horizontalLayout)

        self.horizontalLayout_3 = QHBoxLayout()
        self.horizontalLayout_3.setObjectName(u"horizontalLayout_3")
        self.label_11 = QLabel(self.groupBox_5)
        self.label_11.setObjectName(u"label_11")

        self.horizontalLayout_3.addWidget(self.label_11)

        self.cbIgnoreWhitespace = QComboBox(self.groupBox_5)
        self.cbIgnoreWhitespace.addItem("")
        self.cbIgnoreWhitespace.addItem("")
        self.cbIgnoreWhitespace.addItem("")
        self.cbIgnoreWhitespace.setObjectName(u"cbIgnoreWhitespace")

        self.horizontalLayout_3.addWidget(self.cbIgnoreWhitespace)

        self.horizontalSpacer_2 = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.horizontalLayout_3.addItem(self.horizontalSpacer_2)


        self.verticalLayout_6.addLayout(self.horizontalLayout_3)

        self.cbShowPC = QCheckBox(self.groupBox_5)
        self.cbShowPC.setObjectName(u"cbShowPC")

        self.verticalLayout_6.addWidget(self.cbShowPC)


        self.verticalLayout.addWidget(self.groupBox_5)

        self.tabWidget.addTab(self.tabGeneral, "")
        self.tabFonts = QWidget()
        self.tabFonts.setObjectName(u"tabFonts")
        self.verticalLayout_4 = QVBoxLayout(self.tabFonts)
        self.verticalLayout_4.setObjectName(u"verticalLayout_4")
        self.groupBox_3 = QGroupBox(self.tabFonts)
        self.groupBox_3.setObjectName(u"groupBox_3")
        self.gridLayout_3 = QGridLayout(self.groupBox_3)
        self.gridLayout_3.setObjectName(u"gridLayout_3")
        self.cbSizeLog = QComboBox(self.groupBox_3)
        self.cbSizeLog.setObjectName(u"cbSizeLog")

        self.gridLayout_3.addWidget(self.cbSizeLog, 1, 1, 1, 1)

        self.label_6 = QLabel(self.groupBox_3)
        self.label_6.setObjectName(u"label_6")
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.label_6.sizePolicy().hasHeightForWidth())
        self.label_6.setSizePolicy(sizePolicy)

        self.gridLayout_3.addWidget(self.label_6, 0, 0, 1, 1)

        self.label_7 = QLabel(self.groupBox_3)
        self.label_7.setObjectName(u"label_7")

        self.gridLayout_3.addWidget(self.label_7, 1, 0, 1, 1)

        self.cbFamilyLog = QFontComboBox(self.groupBox_3)
        self.cbFamilyLog.setObjectName(u"cbFamilyLog")

        self.gridLayout_3.addWidget(self.cbFamilyLog, 0, 1, 1, 1)


        self.verticalLayout_4.addWidget(self.groupBox_3)

        self.groupBox_4 = QGroupBox(self.tabFonts)
        self.groupBox_4.setObjectName(u"groupBox_4")
        self.gridLayout_4 = QGridLayout(self.groupBox_4)
        self.gridLayout_4.setObjectName(u"gridLayout_4")
        self.cbFamilyDiff = QFontComboBox(self.groupBox_4)
        self.cbFamilyDiff.setObjectName(u"cbFamilyDiff")

        self.gridLayout_4.addWidget(self.cbFamilyDiff, 0, 1, 1, 1)

        self.label_9 = QLabel(self.groupBox_4)
        self.label_9.setObjectName(u"label_9")

        self.gridLayout_4.addWidget(self.label_9, 1, 0, 1, 1)

        self.cbSizeDiff = QComboBox(self.groupBox_4)
        self.cbSizeDiff.setObjectName(u"cbSizeDiff")

        self.gridLayout_4.addWidget(self.cbSizeDiff, 1, 1, 1, 1)

        self.label_8 = QLabel(self.groupBox_4)
        self.label_8.setObjectName(u"label_8")
        sizePolicy.setHeightForWidth(self.label_8.sizePolicy().hasHeightForWidth())
        self.label_8.setSizePolicy(sizePolicy)

        self.gridLayout_4.addWidget(self.label_8, 0, 0, 1, 1)


        self.verticalLayout_4.addWidget(self.groupBox_4)

        self.tabWidget.addTab(self.tabFonts, "")
        self.tabSummary = QWidget()
        self.tabSummary.setObjectName(u"tabSummary")
        self.verticalLayout_3 = QVBoxLayout(self.tabSummary)
        self.verticalLayout_3.setObjectName(u"verticalLayout_3")
        self.groupBox = QGroupBox(self.tabSummary)
        self.groupBox.setObjectName(u"groupBox")
        self.gridLayout = QGridLayout(self.groupBox)
        self.gridLayout.setObjectName(u"gridLayout")
        self.colorB = ColorWidget(self.groupBox)
        self.colorB.setObjectName(u"colorB")
        sizePolicy1 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        sizePolicy1.setHorizontalStretch(0)
        sizePolicy1.setVerticalStretch(0)
        sizePolicy1.setHeightForWidth(self.colorB.sizePolicy().hasHeightForWidth())
        self.colorB.setSizePolicy(sizePolicy1)
        self.colorB.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self.gridLayout.addWidget(self.colorB, 1, 1, 1, 1)

        self.label_2 = QLabel(self.groupBox)
        self.label_2.setObjectName(u"label_2")

        self.gridLayout.addWidget(self.label_2, 1, 0, 1, 1)

        self.label = QLabel(self.groupBox)
        self.label.setObjectName(u"label")

        self.gridLayout.addWidget(self.label, 0, 0, 1, 1)

        self.colorA = ColorWidget(self.groupBox)
        self.colorA.setObjectName(u"colorA")
        sizePolicy1.setHeightForWidth(self.colorA.sizePolicy().hasHeightForWidth())
        self.colorA.setSizePolicy(sizePolicy1)
        self.colorA.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self.gridLayout.addWidget(self.colorA, 0, 1, 1, 1)


        self.verticalLayout_3.addWidget(self.groupBox)

        self.groupBox_2 = QGroupBox(self.tabSummary)
        self.groupBox_2.setObjectName(u"groupBox_2")
        self.verticalLayout_9 = QVBoxLayout(self.groupBox_2)
        self.verticalLayout_9.setObjectName(u"verticalLayout_9")
        self.linkEditWidget = LinkEditWidget(self.groupBox_2)
        self.linkEditWidget.setObjectName(u"linkEditWidget")

        self.verticalLayout_9.addWidget(self.linkEditWidget)

        self.horizontalLayout_4 = QHBoxLayout()
        self.horizontalLayout_4.setObjectName(u"horizontalLayout_4")
        self.cbFallback = QCheckBox(self.groupBox_2)
        self.cbFallback.setObjectName(u"cbFallback")

        self.horizontalLayout_4.addWidget(self.cbFallback)

        self.btnGlobal = QPushButton(self.groupBox_2)
        self.btnGlobal.setObjectName(u"btnGlobal")

        self.horizontalLayout_4.addWidget(self.btnGlobal)

        self.horizontalSpacer_4 = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.horizontalLayout_4.addItem(self.horizontalSpacer_4)


        self.verticalLayout_9.addLayout(self.horizontalLayout_4)


        self.verticalLayout_3.addWidget(self.groupBox_2)

        self.groupBox_10 = QGroupBox(self.tabSummary)
        self.groupBox_10.setObjectName(u"groupBox_10")
        self.horizontalLayout_5 = QHBoxLayout(self.groupBox_10)
        self.horizontalLayout_5.setObjectName(u"horizontalLayout_5")
        self.label_17 = QLabel(self.groupBox_10)
        self.label_17.setObjectName(u"label_17")

        self.horizontalLayout_5.addWidget(self.label_17)

        self.cbCommitSince = QComboBox(self.groupBox_10)
        self.cbCommitSince.setObjectName(u"cbCommitSince")

        self.horizontalLayout_5.addWidget(self.cbCommitSince)

        self.horizontalSpacer_5 = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.horizontalLayout_5.addItem(self.horizontalSpacer_5)


        self.verticalLayout_3.addWidget(self.groupBox_10)

        self.tabWidget.addTab(self.tabSummary, "")
        self.tabTools = QWidget()
        self.tabTools.setObjectName(u"tabTools")
        self.verticalLayout_7 = QVBoxLayout(self.tabTools)
        self.verticalLayout_7.setObjectName(u"verticalLayout_7")
        self.groupBox_7 = QGroupBox(self.tabTools)
        self.groupBox_7.setObjectName(u"groupBox_7")
        self.verticalLayout_8 = QVBoxLayout(self.groupBox_7)
        self.verticalLayout_8.setObjectName(u"verticalLayout_8")
        self.label_12 = QLabel(self.groupBox_7)
        self.label_12.setObjectName(u"label_12")

        self.verticalLayout_8.addWidget(self.label_12)

        self.tableView = QTableView(self.groupBox_7)
        self.tableView.setObjectName(u"tableView")
        self.tableView.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)

        self.verticalLayout_8.addWidget(self.tableView)

        self.horizontalLayout_2 = QHBoxLayout()
        self.horizontalLayout_2.setObjectName(u"horizontalLayout_2")
        self.btnAdd = QPushButton(self.groupBox_7)
        self.btnAdd.setObjectName(u"btnAdd")

        self.horizontalLayout_2.addWidget(self.btnAdd)

        self.btnDelete = QPushButton(self.groupBox_7)
        self.btnDelete.setObjectName(u"btnDelete")

        self.horizontalLayout_2.addWidget(self.btnDelete)

        self.horizontalSpacer_6 = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.horizontalLayout_2.addItem(self.horizontalSpacer_6)

        self.lbConfigImgDiff = QLabel(self.groupBox_7)
        self.lbConfigImgDiff.setObjectName(u"lbConfigImgDiff")

        self.horizontalLayout_2.addWidget(self.lbConfigImgDiff)


        self.verticalLayout_8.addLayout(self.horizontalLayout_2)

        self.groupBox_8 = QGroupBox(self.groupBox_7)
        self.groupBox_8.setObjectName(u"groupBox_8")
        self.horizontalLayout_6 = QHBoxLayout(self.groupBox_8)
        self.horizontalLayout_6.setSpacing(3)
        self.horizontalLayout_6.setObjectName(u"horizontalLayout_6")
        self.horizontalLayout_6.setContentsMargins(3, 3, 3, 3)
        self.label_3 = QLabel(self.groupBox_8)
        self.label_3.setObjectName(u"label_3")

        self.horizontalLayout_6.addWidget(self.label_3)

        self.cbDiffName = QComboBox(self.groupBox_8)
        self.cbDiffName.addItem(u"opendiff")
        self.cbDiffName.addItem(u"kdiff3")
        self.cbDiffName.addItem(u"tkdiff")
        self.cbDiffName.addItem(u"xxdiff")
        self.cbDiffName.addItem(u"meld")
        self.cbDiffName.addItem(u"kompare")
        self.cbDiffName.addItem(u"gvimdiff")
        self.cbDiffName.addItem(u"diffuse")
        self.cbDiffName.addItem(u"diffmerge")
        self.cbDiffName.addItem(u"ecmerge")
        self.cbDiffName.addItem(u"p4merge")
        self.cbDiffName.addItem(u"araxis")
        self.cbDiffName.addItem(u"bc")
        self.cbDiffName.addItem(u"codecompare")
        self.cbDiffName.addItem(u"smerge")
        self.cbDiffName.addItem(u"emerge")
        self.cbDiffName.setObjectName(u"cbDiffName")
        self.cbDiffName.setEditable(True)
        self.cbDiffName.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)

        self.horizontalLayout_6.addWidget(self.cbDiffName)

        self.horizontalSpacer_3 = QSpacerItem(10, 20, QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum)

        self.horizontalLayout_6.addItem(self.horizontalSpacer_3)

        self.label_4 = QLabel(self.groupBox_8)
        self.label_4.setObjectName(u"label_4")

        self.horizontalLayout_6.addWidget(self.label_4)

        self.leDiffCmd = QLineEdit(self.groupBox_8)
        self.leDiffCmd.setObjectName(u"leDiffCmd")

        self.horizontalLayout_6.addWidget(self.leDiffCmd)


        self.verticalLayout_8.addWidget(self.groupBox_8)

        self.groupBox_9 = QGroupBox(self.groupBox_7)
        self.groupBox_9.setObjectName(u"groupBox_9")
        self.horizontalLayout_7 = QHBoxLayout(self.groupBox_9)
        self.horizontalLayout_7.setSpacing(3)
        self.horizontalLayout_7.setObjectName(u"horizontalLayout_7")
        self.horizontalLayout_7.setContentsMargins(3, 3, 3, 3)
        self.label_5 = QLabel(self.groupBox_9)
        self.label_5.setObjectName(u"label_5")

        self.horizontalLayout_7.addWidget(self.label_5)

        self.cbMergeName = QComboBox(self.groupBox_9)
        self.cbMergeName.addItem(u"opendiff")
        self.cbMergeName.addItem(u"kdiff3")
        self.cbMergeName.addItem(u"tkdiff")
        self.cbMergeName.addItem(u"xxdiff")
        self.cbMergeName.addItem(u"meld")
        self.cbMergeName.addItem(u"tortoisemerge")
        self.cbMergeName.addItem(u"gvimdiff")
        self.cbMergeName.addItem(u"diffuse")
        self.cbMergeName.addItem(u"diffmerge")
        self.cbMergeName.addItem(u"ecmerge")
        self.cbMergeName.addItem(u"p4merge")
        self.cbMergeName.addItem(u"araxis")
        self.cbMergeName.addItem(u"bc")
        self.cbMergeName.addItem(u"codecompare")
        self.cbMergeName.addItem(u"smerge")
        self.cbMergeName.addItem(u"emerge")
        self.cbMergeName.setObjectName(u"cbMergeName")
        self.cbMergeName.setEditable(True)
        self.cbMergeName.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)

        self.horizontalLayout_7.addWidget(self.cbMergeName)

        self.horizontalSpacer_7 = QSpacerItem(10, 20, QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum)

        self.horizontalLayout_7.addItem(self.horizontalSpacer_7)

        self.label_13 = QLabel(self.groupBox_9)
        self.label_13.setObjectName(u"label_13")

        self.horizontalLayout_7.addWidget(self.label_13)

        self.leMergeCmd = QLineEdit(self.groupBox_9)
        self.leMergeCmd.setObjectName(u"leMergeCmd")

        self.horizontalLayout_7.addWidget(self.leMergeCmd)


        self.verticalLayout_8.addWidget(self.groupBox_9)


        self.verticalLayout_7.addWidget(self.groupBox_7)

        self.tabWidget.addTab(self.tabTools, "")
        self.tabLLM = QWidget()
        self.tabLLM.setObjectName(u"tabLLM")
        self.verticalLayout_11 = QVBoxLayout(self.tabLLM)
        self.verticalLayout_11.setObjectName(u"verticalLayout_11")
        self.groupBox_13 = QGroupBox(self.tabLLM)
        self.groupBox_13.setObjectName(u"groupBox_13")
        self.verticalLayout_12 = QVBoxLayout(self.groupBox_13)
        self.verticalLayout_12.setObjectName(u"verticalLayout_12")
        self.cbUseLocalLLM = QCheckBox(self.groupBox_13)
        self.cbUseLocalLLM.setObjectName(u"cbUseLocalLLM")

        self.verticalLayout_12.addWidget(self.cbUseLocalLLM)

        self.horizontalLayout_13 = QHBoxLayout()
        self.horizontalLayout_13.setObjectName(u"horizontalLayout_13")
        self.label_16 = QLabel(self.groupBox_13)
        self.label_16.setObjectName(u"label_16")

        self.horizontalLayout_13.addWidget(self.label_16)

        self.leServerUrl = QLineEdit(self.groupBox_13)
        self.leServerUrl.setObjectName(u"leServerUrl")

        self.horizontalLayout_13.addWidget(self.leServerUrl)


        self.verticalLayout_12.addLayout(self.horizontalLayout_13)


        self.verticalLayout_11.addWidget(self.groupBox_13)

        self.groupBox_14 = QGroupBox(self.tabLLM)
        self.groupBox_14.setObjectName(u"groupBox_14")
        self.verticalLayout_15 = QVBoxLayout(self.groupBox_14)
        self.verticalLayout_15.setObjectName(u"verticalLayout_15")
        self.horizontalLayout_14 = QHBoxLayout()
        self.horizontalLayout_14.setObjectName(u"horizontalLayout_14")
        self.label_20 = QLabel(self.groupBox_14)
        self.label_20.setObjectName(u"label_20")

        self.horizontalLayout_14.addWidget(self.label_20)

        self.btnGithubCopilot = QPushButton(self.groupBox_14)
        self.btnGithubCopilot.setObjectName(u"btnGithubCopilot")

        self.horizontalLayout_14.addWidget(self.btnGithubCopilot)

        self.horizontalSpacer_11 = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.horizontalLayout_14.addItem(self.horizontalSpacer_11)


        self.verticalLayout_15.addLayout(self.horizontalLayout_14)


        self.verticalLayout_11.addWidget(self.groupBox_14)

        self.groupBox_15 = QGroupBox(self.tabLLM)
        self.groupBox_15.setObjectName(u"groupBox_15")
        self.verticalLayout_16 = QVBoxLayout(self.groupBox_15)
        self.verticalLayout_16.setObjectName(u"verticalLayout_16")
        self.horizontalLayout_16 = QHBoxLayout()
        self.horizontalLayout_16.setObjectName(u"horizontalLayout_16")
        self.label_22 = QLabel(self.groupBox_15)
        self.label_22.setObjectName(u"label_22")

        self.horizontalLayout_16.addWidget(self.label_22)

        self.leExcludedFiles = QLineEdit(self.groupBox_15)
        self.leExcludedFiles.setObjectName(u"leExcludedFiles")

        self.horizontalLayout_16.addWidget(self.leExcludedFiles)


        self.verticalLayout_16.addLayout(self.horizontalLayout_16)


        self.verticalLayout_11.addWidget(self.groupBox_15)

        self.verticalSpacer = QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)

        self.verticalLayout_11.addItem(self.verticalSpacer)

        self.tabWidget.addTab(self.tabLLM, "")
        self.tabCommitMessage = QWidget()
        self.tabCommitMessage.setObjectName(u"tabCommitMessage")
        self.verticalLayout_10 = QVBoxLayout(self.tabCommitMessage)
        self.verticalLayout_10.setObjectName(u"verticalLayout_10")
        self.groupBox_11 = QGroupBox(self.tabCommitMessage)
        self.groupBox_11.setObjectName(u"groupBox_11")
        self.verticalLayout_13 = QVBoxLayout(self.groupBox_11)
        self.verticalLayout_13.setObjectName(u"verticalLayout_13")
        self.cbIgnoreComment = QCheckBox(self.groupBox_11)
        self.cbIgnoreComment.setObjectName(u"cbIgnoreComment")

        self.verticalLayout_13.addWidget(self.cbIgnoreComment)

        self.cbTab = QCheckBox(self.groupBox_11)
        self.cbTab.setObjectName(u"cbTab")

        self.verticalLayout_13.addWidget(self.cbTab)

        self.horizontalLayout_11 = QHBoxLayout()
        self.horizontalLayout_11.setObjectName(u"horizontalLayout_11")
        self.label_19 = QLabel(self.groupBox_11)
        self.label_19.setObjectName(u"label_19")

        self.horizontalLayout_11.addWidget(self.label_19)

        self.leGroupChars = QLineEdit(self.groupBox_11)
        self.leGroupChars.setObjectName(u"leGroupChars")

        self.horizontalLayout_11.addWidget(self.leGroupChars)


        self.verticalLayout_13.addLayout(self.horizontalLayout_11)


        self.verticalLayout_10.addWidget(self.groupBox_11)

        self.groupBox_12 = QGroupBox(self.tabCommitMessage)
        self.groupBox_12.setObjectName(u"groupBox_12")
        self.verticalLayout_14 = QVBoxLayout(self.groupBox_12)
        self.verticalLayout_14.setObjectName(u"verticalLayout_14")
        self.tvActions = QTableView(self.groupBox_12)
        self.tvActions.setObjectName(u"tvActions")
        self.tvActions.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)

        self.verticalLayout_14.addWidget(self.tvActions)

        self.horizontalLayout_12 = QHBoxLayout()
        self.horizontalLayout_12.setObjectName(u"horizontalLayout_12")
        self.btnAddAction = QPushButton(self.groupBox_12)
        self.btnAddAction.setObjectName(u"btnAddAction")

        self.horizontalLayout_12.addWidget(self.btnAddAction)

        self.btnDelAction = QPushButton(self.groupBox_12)
        self.btnDelAction.setObjectName(u"btnDelAction")

        self.horizontalLayout_12.addWidget(self.btnDelAction)

        self.horizontalSpacer_10 = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.horizontalLayout_12.addItem(self.horizontalSpacer_10)


        self.verticalLayout_14.addLayout(self.horizontalLayout_12)


        self.verticalLayout_10.addWidget(self.groupBox_12)

        self.tabWidget.addTab(self.tabCommitMessage, "")

        self.verticalLayout_2.addWidget(self.tabWidget)

        self.buttonBox = QDialogButtonBox(Preferences)
        self.buttonBox.setObjectName(u"buttonBox")
        self.buttonBox.setOrientation(Qt.Orientation.Horizontal)
        self.buttonBox.setStandardButtons(QDialogButtonBox.StandardButton.Cancel|QDialogButtonBox.StandardButton.Ok)

        self.verticalLayout_2.addWidget(self.buttonBox)

#if QT_CONFIG(shortcut)
        self.label_18.setBuddy(self.cbColorSchema)
        self.label_10.setBuddy(self.sbTabSize)
        self.label_11.setBuddy(self.cbIgnoreWhitespace)
        self.label_6.setBuddy(self.cbFamilyLog)
        self.label_7.setBuddy(self.cbSizeLog)
        self.label_9.setBuddy(self.cbSizeDiff)
        self.label_8.setBuddy(self.cbFamilyDiff)
        self.label_2.setBuddy(self.colorB)
        self.label.setBuddy(self.colorA)
#endif // QT_CONFIG(shortcut)
        QWidget.setTabOrder(self.btnAdd, self.tableView)
        QWidget.setTabOrder(self.tableView, self.cbSizeDiff)
        QWidget.setTabOrder(self.cbSizeDiff, self.colorA)
        QWidget.setTabOrder(self.colorA, self.colorB)
        QWidget.setTabOrder(self.colorB, self.buttonBox)
        QWidget.setTabOrder(self.buttonBox, self.cbEsc)
        QWidget.setTabOrder(self.cbEsc, self.cbState)
        QWidget.setTabOrder(self.cbState, self.cbShowWhitespace)
        QWidget.setTabOrder(self.cbShowWhitespace, self.sbTabSize)
        QWidget.setTabOrder(self.sbTabSize, self.cbIgnoreWhitespace)
        QWidget.setTabOrder(self.cbIgnoreWhitespace, self.cbFamilyDiff)
        QWidget.setTabOrder(self.cbFamilyDiff, self.cbFamilyLog)
        QWidget.setTabOrder(self.cbFamilyLog, self.cbSizeLog)

        self.retranslateUi(Preferences)
        self.buttonBox.rejected.connect(Preferences.reject)

        self.tabWidget.setCurrentIndex(0)
        self.cbDiffName.setCurrentIndex(-1)
        self.cbMergeName.setCurrentIndex(-1)


        QMetaObject.connectSlotsByName(Preferences)
    # setupUi

    def retranslateUi(self, Preferences):
        Preferences.setWindowTitle(QCoreApplication.translate("Preferences", u"Preferences", None))
        self.groupBox_6.setTitle(QCoreApplication.translate("Preferences", u"Application", None))
        self.cbEsc.setText(QCoreApplication.translate("Preferences", u"&Quit also via Esc key", None))
        self.cbState.setText(QCoreApplication.translate("Preferences", u"&Remember window state", None))
        self.cbCheckUpdates.setText(QCoreApplication.translate("Preferences", u"Check updates every", None))
        self.label_14.setText(QCoreApplication.translate("Preferences", u"day(s)", None))
        self.label_18.setText(QCoreApplication.translate("Preferences", u"Color Schema", None))
        self.label_23.setText(QCoreApplication.translate("Preferences", u"UI Style", None))
        self.label_21.setText(QCoreApplication.translate("Preferences", u"Log Level", None))
        self.label_15.setText(QCoreApplication.translate("Preferences", u"Git:", None))
        self.btnChooseGit.setText(QCoreApplication.translate("Preferences", u"&Browse", None))
        self.groupBox_5.setTitle(QCoreApplication.translate("Preferences", u"Diff view", None))
        self.cbShowWhitespace.setText(QCoreApplication.translate("Preferences", u"&Visualize whitespace", None))
        self.label_10.setText(QCoreApplication.translate("Preferences", u"&Tab size:", None))
        self.label_11.setText(QCoreApplication.translate("Preferences", u"&Ignore whitespace:", None))
        self.cbIgnoreWhitespace.setItemText(0, QCoreApplication.translate("Preferences", u"None", None))
        self.cbIgnoreWhitespace.setItemText(1, QCoreApplication.translate("Preferences", u"At end of line", None))
        self.cbIgnoreWhitespace.setItemText(2, QCoreApplication.translate("Preferences", u"All", None))

        self.cbShowPC.setText(QCoreApplication.translate("Preferences", u"Show parent and child", None))
        self.tabWidget.setTabText(self.tabWidget.indexOf(self.tabGeneral), QCoreApplication.translate("Preferences", u"&General", None))
        self.groupBox_3.setTitle(QCoreApplication.translate("Preferences", u"Log view", None))
        self.label_6.setText(QCoreApplication.translate("Preferences", u"&Family:", None))
        self.label_7.setText(QCoreApplication.translate("Preferences", u"&Size:", None))
        self.groupBox_4.setTitle(QCoreApplication.translate("Preferences", u"Diff view", None))
        self.label_9.setText(QCoreApplication.translate("Preferences", u"S&ize:", None))
        self.label_8.setText(QCoreApplication.translate("Preferences", u"F&amily:", None))
        self.tabWidget.setTabText(self.tabWidget.indexOf(self.tabFonts), QCoreApplication.translate("Preferences", u"&Fonts", None))
        self.groupBox.setTitle(QCoreApplication.translate("Preferences", u"Color", None))
        self.label_2.setText(QCoreApplication.translate("Preferences", u"Branch &B:", None))
        self.label.setText(QCoreApplication.translate("Preferences", u"Branch &A:", None))
        self.groupBox_2.setTitle(QCoreApplication.translate("Preferences", u"Links", None))
#if QT_CONFIG(tooltip)
        self.cbFallback.setToolTip(QCoreApplication.translate("Preferences", u"Use global settings when no match current setting", None))
#endif // QT_CONFIG(tooltip)
        self.cbFallback.setText(QCoreApplication.translate("Preferences", u"Fallbac&k to Global", None))
        self.btnGlobal.setText(QCoreApplication.translate("Preferences", u"&Edit Global", None))
        self.groupBox_10.setTitle(QCoreApplication.translate("Preferences", u"Composite Mode", None))
        self.label_17.setText(QCoreApplication.translate("Preferences", u"Max Commits:", None))
        self.tabWidget.setTabText(self.tabWidget.indexOf(self.tabSummary), QCoreApplication.translate("Preferences", u"Co&mmit", None))
        self.groupBox_7.setTitle(QCoreApplication.translate("Preferences", u"Tools", None))
        self.label_12.setText(QCoreApplication.translate("Preferences", u"You must add the tool to git config mergetool/difftool section to make it works.", None))
        self.btnAdd.setText(QCoreApplication.translate("Preferences", u"&Add", None))
        self.btnDelete.setText(QCoreApplication.translate("Preferences", u"&Delete", None))
        self.lbConfigImgDiff.setText(QCoreApplication.translate("Preferences", u"<a href='#config'>Config imgdiff as tool for diff or merge</a>", None))
        self.groupBox_8.setTitle(QCoreApplication.translate("Preferences", u"Diff", None))
        self.label_3.setText(QCoreApplication.translate("Preferences", u"Name:", None))

#if QT_CONFIG(tooltip)
        self.cbDiffName.setToolTip(QCoreApplication.translate("Preferences", u"Specify diff tool name or choose default one", None))
#endif // QT_CONFIG(tooltip)
        self.label_4.setText(QCoreApplication.translate("Preferences", u"Command:", None))
#if QT_CONFIG(tooltip)
        self.leDiffCmd.setToolTip(QCoreApplication.translate("Preferences", u"The command line and arguments, for example:\n"
"imgdiff \"$LOCAL\" \"$REMOTE\"", None))
#endif // QT_CONFIG(tooltip)
        self.groupBox_9.setTitle(QCoreApplication.translate("Preferences", u"Merge", None))
        self.label_5.setText(QCoreApplication.translate("Preferences", u"Name:", None))

#if QT_CONFIG(tooltip)
        self.cbMergeName.setToolTip(QCoreApplication.translate("Preferences", u"Specify merge tool name or choose default one", None))
#endif // QT_CONFIG(tooltip)
        self.label_13.setText(QCoreApplication.translate("Preferences", u"Command:", None))
#if QT_CONFIG(tooltip)
        self.leMergeCmd.setToolTip(QCoreApplication.translate("Preferences", u"The command line and arguments, for example:\n"
"imgdiff \"$BASE\" \"$LOCAL\" \"$REMOTE\" -o \"$MERGED\"", None))
#endif // QT_CONFIG(tooltip)
        self.tabWidget.setTabText(self.tabWidget.indexOf(self.tabTools), QCoreApplication.translate("Preferences", u"&Tools", None))
        self.groupBox_13.setTitle(QCoreApplication.translate("Preferences", u"Local LLM", None))
        self.cbUseLocalLLM.setText(QCoreApplication.translate("Preferences", u"Use Local LLM", None))
        self.label_16.setText(QCoreApplication.translate("Preferences", u"Server:", None))
        self.groupBox_14.setTitle(QCoreApplication.translate("Preferences", u"GitHub Copilot", None))
        self.label_20.setText(QCoreApplication.translate("Preferences", u"Account:", None))
        self.btnGithubCopilot.setText("")
        self.groupBox_15.setTitle(QCoreApplication.translate("Preferences", u"AI Assistant", None))
        self.label_22.setText(QCoreApplication.translate("Preferences", u"Files to Exclude:", None))
#if QT_CONFIG(tooltip)
        self.leExcludedFiles.setToolTip(QCoreApplication.translate("Preferences", u"Specify the file extensions to exclude for code review or generate commit message", None))
#endif // QT_CONFIG(tooltip)
        self.leExcludedFiles.setPlaceholderText(QCoreApplication.translate("Preferences", u"e.g. .ts, .ui", None))
        self.tabWidget.setTabText(self.tabWidget.indexOf(self.tabLLM), QCoreApplication.translate("Preferences", u"&LLM", None))
        self.groupBox_11.setTitle(QCoreApplication.translate("Preferences", u"Commit &Message", None))
        self.cbIgnoreComment.setText(QCoreApplication.translate("Preferences", u"Ignore comment line", None))
        self.cbTab.setText(QCoreApplication.translate("Preferences", u"Tab to next group", None))
        self.label_19.setText(QCoreApplication.translate("Preferences", u"Group Chars:", None))
#if QT_CONFIG(tooltip)
        self.leGroupChars.setToolTip(QCoreApplication.translate("Preferences", u"Each pair separate by space, such as `() []`", None))
#endif // QT_CONFIG(tooltip)
        self.groupBox_12.setTitle(QCoreApplication.translate("Preferences", u"Commit &Action", None))
        self.btnAddAction.setText(QCoreApplication.translate("Preferences", u"Add", None))
        self.btnDelAction.setText(QCoreApplication.translate("Preferences", u"Delete", None))
        self.tabWidget.setTabText(self.tabWidget.indexOf(self.tabCommitMessage), QCoreApplication.translate("Preferences", u"&Commit Message", None))
    # retranslateUi

