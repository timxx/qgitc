# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'gitview.ui'
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
from PySide6.QtWidgets import (QApplication, QComboBox, QFrame, QHBoxLayout,
    QLabel, QLayout, QLineEdit, QSizePolicy,
    QSpacerItem, QSplitter, QVBoxLayout, QWidget)

from .coloredicontoolbutton import ColoredIconToolButton
from .diffview import DiffView
from .logview import (LogGraph, LogView)
from .waitingspinnerwidget import QtWaitingSpinner

class Ui_GitView(object):
    def setupUi(self, GitView):
        if not GitView.objectName():
            GitView.setObjectName(u"GitView")
        GitView.resize(668, 630)
        self.verticalLayout_2 = QVBoxLayout(GitView)
        self.verticalLayout_2.setObjectName(u"verticalLayout_2")
        self.horizontalLayout = QHBoxLayout()
        self.horizontalLayout.setObjectName(u"horizontalLayout")
        self.horizontalLayout.setSizeConstraint(QLayout.SizeConstraint.SetDefaultConstraint)
        self.branchSpinner = QtWaitingSpinner(GitView)
        self.branchSpinner.setObjectName(u"branchSpinner")

        self.horizontalLayout.addWidget(self.branchSpinner)

        self.lbBranch = QLabel(GitView)
        self.lbBranch.setObjectName(u"lbBranch")
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.lbBranch.sizePolicy().hasHeightForWidth())
        self.lbBranch.setSizePolicy(sizePolicy)

        self.horizontalLayout.addWidget(self.lbBranch)

        self.cbBranch = QComboBox(GitView)
        self.cbBranch.setObjectName(u"cbBranch")

        self.horizontalLayout.addWidget(self.cbBranch)


        self.verticalLayout_2.addLayout(self.horizontalLayout)

        self.splitter = QSplitter(GitView)
        self.splitter.setObjectName(u"splitter")
        self.splitter.setFrameShape(QFrame.Shape.NoFrame)
        self.splitter.setOrientation(Qt.Orientation.Vertical)
        self.logWidget = QSplitter(self.splitter)
        self.logWidget.setObjectName(u"logWidget")
        self.logWidget.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.logWidget.setFrameShape(QFrame.Shape.StyledPanel)
        self.logWidget.setFrameShadow(QFrame.Shadow.Sunken)
        self.logWidget.setOrientation(Qt.Orientation.Horizontal)
        self.logWidget.setHandleWidth(1)
        self.logGraph = LogGraph(self.logWidget)
        self.logGraph.setObjectName(u"logGraph")
        self.logWidget.addWidget(self.logGraph)
        self.logView = LogView(self.logWidget)
        self.logView.setObjectName(u"logView")
        self.logWidget.addWidget(self.logView)
        self.splitter.addWidget(self.logWidget)
        self.verticalLayoutWidget = QWidget(self.splitter)
        self.verticalLayoutWidget.setObjectName(u"verticalLayoutWidget")
        self.verticalLayout = QVBoxLayout(self.verticalLayoutWidget)
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.verticalLayout.setContentsMargins(0, 0, 0, 0)
        self.verticalLayout_3 = QVBoxLayout()
        self.verticalLayout_3.setObjectName(u"verticalLayout_3")
        self.horizontalLayout_2 = QHBoxLayout()
        self.horizontalLayout_2.setObjectName(u"horizontalLayout_2")
        self.diffSpinner = QtWaitingSpinner(self.verticalLayoutWidget)
        self.diffSpinner.setObjectName(u"diffSpinner")

        self.horizontalLayout_2.addWidget(self.diffSpinner)

        self.label = QLabel(self.verticalLayoutWidget)
        self.label.setObjectName(u"label")

        self.horizontalLayout_2.addWidget(self.label)

        self.leSha1 = QLineEdit(self.verticalLayoutWidget)
        self.leSha1.setObjectName(u"leSha1")

        self.horizontalLayout_2.addWidget(self.leSha1)

        self.horizontalSpacer = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.horizontalLayout_2.addItem(self.horizontalSpacer)


        self.verticalLayout_3.addLayout(self.horizontalLayout_2)

        self.horizontalLayout_3 = QHBoxLayout()
        self.horizontalLayout_3.setObjectName(u"horizontalLayout_3")
        self.findSpinner = QtWaitingSpinner(self.verticalLayoutWidget)
        self.findSpinner.setObjectName(u"findSpinner")

        self.horizontalLayout_3.addWidget(self.findSpinner)

        self.label_3 = QLabel(self.verticalLayoutWidget)
        self.label_3.setObjectName(u"label_3")

        self.horizontalLayout_3.addWidget(self.label_3)

        self.label_2 = QLabel(self.verticalLayoutWidget)
        self.label_2.setObjectName(u"label_2")

        self.horizontalLayout_3.addWidget(self.label_2)

        self.cbFindWhat = QComboBox(self.verticalLayoutWidget)
        self.cbFindWhat.addItem("")
        self.cbFindWhat.addItem("")
        self.cbFindWhat.addItem("")
        self.cbFindWhat.setObjectName(u"cbFindWhat")

        self.horizontalLayout_3.addWidget(self.cbFindWhat)

        self.leFindWhat = QLineEdit(self.verticalLayoutWidget)
        self.leFindWhat.setObjectName(u"leFindWhat")

        self.horizontalLayout_3.addWidget(self.leFindWhat)

        self.cbFindType = QComboBox(self.verticalLayoutWidget)
        self.cbFindType.addItem("")
        self.cbFindType.addItem("")
        self.cbFindType.addItem("")
        self.cbFindType.setObjectName(u"cbFindType")

        self.horizontalLayout_3.addWidget(self.cbFindType)

        self.tbPrev = ColoredIconToolButton(self.verticalLayoutWidget)
        self.tbPrev.setObjectName(u"tbPrev")
        self.tbPrev.setIconSize(QSize(20, 20))

        self.horizontalLayout_3.addWidget(self.tbPrev)

        self.tbNext = ColoredIconToolButton(self.verticalLayoutWidget)
        self.tbNext.setObjectName(u"tbNext")
        self.tbNext.setIconSize(QSize(20, 20))

        self.horizontalLayout_3.addWidget(self.tbNext)


        self.verticalLayout_3.addLayout(self.horizontalLayout_3)


        self.verticalLayout.addLayout(self.verticalLayout_3)

        self.diffView = DiffView(self.verticalLayoutWidget)
        self.diffView.setObjectName(u"diffView")

        self.verticalLayout.addWidget(self.diffView)

        self.splitter.addWidget(self.verticalLayoutWidget)

        self.verticalLayout_2.addWidget(self.splitter)

        QWidget.setTabOrder(self.cbBranch, self.logWidget)
        QWidget.setTabOrder(self.logWidget, self.leSha1)
        QWidget.setTabOrder(self.leSha1, self.cbFindWhat)
        QWidget.setTabOrder(self.cbFindWhat, self.leFindWhat)
        QWidget.setTabOrder(self.leFindWhat, self.cbFindType)
        QWidget.setTabOrder(self.cbFindType, self.tbPrev)
        QWidget.setTabOrder(self.tbPrev, self.tbNext)

        self.retranslateUi(GitView)

        QMetaObject.connectSlotsByName(GitView)
    # setupUi

    def retranslateUi(self, GitView):
        GitView.setWindowTitle(QCoreApplication.translate("GitView", u"GitView", None))
        self.lbBranch.setText(QCoreApplication.translate("GitView", u"Branch:", None))
        self.label.setText(QCoreApplication.translate("GitView", u"Commit ID:", None))
        self.label_3.setText(QCoreApplication.translate("GitView", u"Find", None))
        self.label_2.setText(QCoreApplication.translate("GitView", u"commit", None))
        self.cbFindWhat.setItemText(0, QCoreApplication.translate("GitView", u"adding/removing string", None))
        self.cbFindWhat.setItemText(1, QCoreApplication.translate("GitView", u"changing lines matching", None))
        self.cbFindWhat.setItemText(2, QCoreApplication.translate("GitView", u"containing", None))

        self.leFindWhat.setPlaceholderText(QCoreApplication.translate("GitView", u"Press Enter to find commits", None))
        self.cbFindType.setItemText(0, QCoreApplication.translate("GitView", u"Exact", None))
        self.cbFindType.setItemText(1, QCoreApplication.translate("GitView", u"Ignore case", None))
        self.cbFindType.setItemText(2, QCoreApplication.translate("GitView", u"Regexp", None))

#if QT_CONFIG(tooltip)
        self.tbPrev.setToolTip(QCoreApplication.translate("GitView", u"Find previous", None))
#endif // QT_CONFIG(tooltip)
        self.tbPrev.setText("")
#if QT_CONFIG(tooltip)
        self.tbNext.setToolTip(QCoreApplication.translate("GitView", u"Find next", None))
#endif // QT_CONFIG(tooltip)
        self.tbNext.setText("")
    # retranslateUi

