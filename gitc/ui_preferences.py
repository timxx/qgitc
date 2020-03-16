# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'preferences.ui'
##
## Created by: Qt User Interface Compiler version 5.14.1
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from PySide2.QtCore import (QCoreApplication, QMetaObject, QObject, QPoint,
    QRect, QSize, QUrl, Qt)
from PySide2.QtGui import (QBrush, QColor, QConicalGradient, QCursor, QFont,
    QFontDatabase, QIcon, QLinearGradient, QPalette, QPainter, QPixmap,
    QRadialGradient)
from PySide2.QtWidgets import *

from .colorwidget import ColorWidget


class Ui_Preferences(object):
    def setupUi(self, Preferences):
        if Preferences.objectName():
            Preferences.setObjectName(u"Preferences")
        Preferences.resize(529, 316)
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

        self.horizontalSpacer = QSpacerItem(40, 20, QSizePolicy.Expanding, QSizePolicy.Minimum)

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

        self.horizontalSpacer_2 = QSpacerItem(40, 20, QSizePolicy.Expanding, QSizePolicy.Minimum)

        self.horizontalLayout_3.addItem(self.horizontalSpacer_2)


        self.verticalLayout_6.addLayout(self.horizontalLayout_3)


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
        sizePolicy = QSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
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
        sizePolicy1 = QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        sizePolicy1.setHorizontalStretch(0)
        sizePolicy1.setVerticalStretch(0)
        sizePolicy1.setHeightForWidth(self.colorB.sizePolicy().hasHeightForWidth())
        self.colorB.setSizePolicy(sizePolicy1)
        self.colorB.setFocusPolicy(Qt.StrongFocus)

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
        self.colorA.setFocusPolicy(Qt.StrongFocus)

        self.gridLayout.addWidget(self.colorA, 0, 1, 1, 1)


        self.verticalLayout_3.addWidget(self.groupBox)

        self.groupBox_2 = QGroupBox(self.tabSummary)
        self.groupBox_2.setObjectName(u"groupBox_2")
        self.gridLayout_2 = QGridLayout(self.groupBox_2)
        self.gridLayout_2.setObjectName(u"gridLayout_2")
        self.label_3 = QLabel(self.groupBox_2)
        self.label_3.setObjectName(u"label_3")

        self.gridLayout_2.addWidget(self.label_3, 0, 0, 1, 1)

        self.label_4 = QLabel(self.groupBox_2)
        self.label_4.setObjectName(u"label_4")

        self.gridLayout_2.addWidget(self.label_4, 1, 0, 1, 1)

        self.leBugUrl = QLineEdit(self.groupBox_2)
        self.leBugUrl.setObjectName(u"leBugUrl")

        self.gridLayout_2.addWidget(self.leBugUrl, 1, 1, 1, 1)

        self.leCommitUrl = QLineEdit(self.groupBox_2)
        self.leCommitUrl.setObjectName(u"leCommitUrl")

        self.gridLayout_2.addWidget(self.leCommitUrl, 0, 1, 1, 1)

        self.label_5 = QLabel(self.groupBox_2)
        self.label_5.setObjectName(u"label_5")

        self.gridLayout_2.addWidget(self.label_5, 2, 0, 1, 1)

        self.leBugPattern = QLineEdit(self.groupBox_2)
        self.leBugPattern.setObjectName(u"leBugPattern")

        self.gridLayout_2.addWidget(self.leBugPattern, 2, 1, 1, 1)


        self.verticalLayout_3.addWidget(self.groupBox_2)

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
        self.tableView.setSelectionBehavior(QAbstractItemView.SelectRows)

        self.verticalLayout_8.addWidget(self.tableView)

        self.horizontalLayout_2 = QHBoxLayout()
        self.horizontalLayout_2.setObjectName(u"horizontalLayout_2")
        self.btnAdd = QPushButton(self.groupBox_7)
        self.btnAdd.setObjectName(u"btnAdd")

        self.horizontalLayout_2.addWidget(self.btnAdd)

        self.btnDelete = QPushButton(self.groupBox_7)
        self.btnDelete.setObjectName(u"btnDelete")

        self.horizontalLayout_2.addWidget(self.btnDelete)

        self.horizontalSpacer_3 = QSpacerItem(40, 20, QSizePolicy.Expanding, QSizePolicy.Minimum)

        self.horizontalLayout_2.addItem(self.horizontalSpacer_3)


        self.verticalLayout_8.addLayout(self.horizontalLayout_2)


        self.verticalLayout_7.addWidget(self.groupBox_7)

        self.tabWidget.addTab(self.tabTools, "")

        self.verticalLayout_2.addWidget(self.tabWidget)

        self.buttonBox = QDialogButtonBox(Preferences)
        self.buttonBox.setObjectName(u"buttonBox")
        self.buttonBox.setOrientation(Qt.Horizontal)
        self.buttonBox.setStandardButtons(QDialogButtonBox.Cancel|QDialogButtonBox.Ok)

        self.verticalLayout_2.addWidget(self.buttonBox)

#if QT_CONFIG(shortcut)
        self.label_10.setBuddy(self.sbTabSize)
        self.label_11.setBuddy(self.cbIgnoreWhitespace)
        self.label_6.setBuddy(self.cbFamilyLog)
        self.label_7.setBuddy(self.cbSizeLog)
        self.label_9.setBuddy(self.cbSizeDiff)
        self.label_8.setBuddy(self.cbFamilyDiff)
        self.label_2.setBuddy(self.colorB)
        self.label.setBuddy(self.colorA)
        self.label_3.setBuddy(self.leCommitUrl)
        self.label_4.setBuddy(self.leBugUrl)
        self.label_5.setBuddy(self.leBugPattern)
#endif // QT_CONFIG(shortcut)
        QWidget.setTabOrder(self.btnAdd, self.tableView)
        QWidget.setTabOrder(self.tableView, self.cbSizeDiff)
        QWidget.setTabOrder(self.cbSizeDiff, self.colorA)
        QWidget.setTabOrder(self.colorA, self.colorB)
        QWidget.setTabOrder(self.colorB, self.leCommitUrl)
        QWidget.setTabOrder(self.leCommitUrl, self.leBugUrl)
        QWidget.setTabOrder(self.leBugUrl, self.leBugPattern)
        QWidget.setTabOrder(self.leBugPattern, self.buttonBox)
        QWidget.setTabOrder(self.buttonBox, self.cbEsc)
        QWidget.setTabOrder(self.cbEsc, self.cbState)
        QWidget.setTabOrder(self.cbState, self.cbShowWhitespace)
        QWidget.setTabOrder(self.cbShowWhitespace, self.sbTabSize)
        QWidget.setTabOrder(self.sbTabSize, self.cbIgnoreWhitespace)
        QWidget.setTabOrder(self.cbIgnoreWhitespace, self.cbFamilyDiff)
        QWidget.setTabOrder(self.cbFamilyDiff, self.tabWidget)
        QWidget.setTabOrder(self.tabWidget, self.cbFamilyLog)
        QWidget.setTabOrder(self.cbFamilyLog, self.cbSizeLog)

        self.retranslateUi(Preferences)
        self.buttonBox.accepted.connect(Preferences.accept)
        self.buttonBox.rejected.connect(Preferences.reject)

        self.tabWidget.setCurrentIndex(3)


        QMetaObject.connectSlotsByName(Preferences)
    # setupUi

    def retranslateUi(self, Preferences):
        Preferences.setWindowTitle(QCoreApplication.translate("Preferences", u"Preferences", None))
        self.groupBox_6.setTitle(QCoreApplication.translate("Preferences", u"Application", None))
        self.cbEsc.setText(QCoreApplication.translate("Preferences", u"&Quit also via Esc key", None))
        self.cbState.setText(QCoreApplication.translate("Preferences", u"&Remember window state", None))
        self.groupBox_5.setTitle(QCoreApplication.translate("Preferences", u"Diff view", None))
        self.cbShowWhitespace.setText(QCoreApplication.translate("Preferences", u"&Visualize whitespace", None))
        self.label_10.setText(QCoreApplication.translate("Preferences", u"&Tab size:", None))
        self.label_11.setText(QCoreApplication.translate("Preferences", u"&Ignore whitespace:", None))
        self.cbIgnoreWhitespace.setItemText(0, QCoreApplication.translate("Preferences", u"None", None))
        self.cbIgnoreWhitespace.setItemText(1, QCoreApplication.translate("Preferences", u"At end of line", None))
        self.cbIgnoreWhitespace.setItemText(2, QCoreApplication.translate("Preferences", u"All", None))

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
        self.label_3.setText(QCoreApplication.translate("Preferences", u"C&ommit URL:", None))
        self.label_4.setText(QCoreApplication.translate("Preferences", u"B&UG URL:", None))
        self.label_5.setText(QCoreApplication.translate("Preferences", u"BUG &Pattern:", None))
        self.tabWidget.setTabText(self.tabWidget.indexOf(self.tabSummary), QCoreApplication.translate("Preferences", u"Co&mmit", None))
        self.groupBox_7.setTitle(QCoreApplication.translate("Preferences", u"Tools", None))
        self.label_12.setText(QCoreApplication.translate("Preferences", u"You must add the tool to git config mergetool/difftool section to make it works.", None))
        self.btnAdd.setText(QCoreApplication.translate("Preferences", u"&Add", None))
        self.btnDelete.setText(QCoreApplication.translate("Preferences", u"&Delete", None))
        self.tabWidget.setTabText(self.tabWidget.indexOf(self.tabTools), QCoreApplication.translate("Preferences", u"&Tools", None))
    # retranslateUi

