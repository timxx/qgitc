# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'commitactionwidget.ui'
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
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QHBoxLayout, QHeaderView,
    QPushButton, QSizePolicy, QSpacerItem, QTableView,
    QVBoxLayout, QWidget)

class Ui_CommitActionWidget(object):
    def setupUi(self, CommitActionWidget):
        if not CommitActionWidget.objectName():
            CommitActionWidget.setObjectName(u"CommitActionWidget")
        CommitActionWidget.resize(663, 357)
        self.verticalLayout = QVBoxLayout(CommitActionWidget)
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.verticalLayout.setContentsMargins(0, 0, 0, 0)
        self.tvActions = QTableView(CommitActionWidget)
        self.tvActions.setObjectName(u"tvActions")
        self.tvActions.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)

        self.verticalLayout.addWidget(self.tvActions)

        self.horizontalLayout_12 = QHBoxLayout()
        self.horizontalLayout_12.setObjectName(u"horizontalLayout_12")
        self.btnAddAction = QPushButton(CommitActionWidget)
        self.btnAddAction.setObjectName(u"btnAddAction")

        self.horizontalLayout_12.addWidget(self.btnAddAction)

        self.btnDelAction = QPushButton(CommitActionWidget)
        self.btnDelAction.setObjectName(u"btnDelAction")

        self.horizontalLayout_12.addWidget(self.btnDelAction)

        self.horizontalSpacer_10 = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.horizontalLayout_12.addItem(self.horizontalSpacer_10)


        self.verticalLayout.addLayout(self.horizontalLayout_12)


        self.retranslateUi(CommitActionWidget)

        QMetaObject.connectSlotsByName(CommitActionWidget)
    # setupUi

    def retranslateUi(self, CommitActionWidget):
        CommitActionWidget.setWindowTitle(QCoreApplication.translate("CommitActionWidget", u"Form", None))
        self.btnAddAction.setText(QCoreApplication.translate("CommitActionWidget", u"Add", None))
        self.btnDelAction.setText(QCoreApplication.translate("CommitActionWidget", u"Delete", None))
    # retranslateUi

