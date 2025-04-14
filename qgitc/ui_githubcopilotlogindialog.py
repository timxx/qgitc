# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'githubcopilotlogindialog.ui'
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
from PySide6.QtWidgets import (QApplication, QDialog, QHBoxLayout, QLabel,
    QProgressBar, QSizePolicy, QSpacerItem, QVBoxLayout,
    QWidget)

class Ui_GithubCopilotLoginDialog(object):
    def setupUi(self, GithubCopilotLoginDialog):
        if not GithubCopilotLoginDialog.objectName():
            GithubCopilotLoginDialog.setObjectName(u"GithubCopilotLoginDialog")
        GithubCopilotLoginDialog.resize(532, 126)
        self.verticalLayout = QVBoxLayout(GithubCopilotLoginDialog)
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.lbStatus = QLabel(GithubCopilotLoginDialog)
        self.lbStatus.setObjectName(u"lbStatus")
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.MinimumExpanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.lbStatus.sizePolicy().hasHeightForWidth())
        self.lbStatus.setSizePolicy(sizePolicy)
        self.lbStatus.setWordWrap(True)

        self.verticalLayout.addWidget(self.lbStatus)

        self.progressBar = QProgressBar(GithubCopilotLoginDialog)
        self.progressBar.setObjectName(u"progressBar")
        self.progressBar.setMaximum(0)
        self.progressBar.setValue(-1)
        self.progressBar.setTextVisible(False)

        self.verticalLayout.addWidget(self.progressBar)

        self.horizontalLayout_2 = QHBoxLayout()
        self.horizontalLayout_2.setObjectName(u"horizontalLayout_2")
        self.label_3 = QLabel(GithubCopilotLoginDialog)
        self.label_3.setObjectName(u"label_3")

        self.horizontalLayout_2.addWidget(self.label_3)

        self.lbUrl = QLabel(GithubCopilotLoginDialog)
        self.lbUrl.setObjectName(u"lbUrl")
        self.lbUrl.setOpenExternalLinks(True)

        self.horizontalLayout_2.addWidget(self.lbUrl)

        self.horizontalSpacer_2 = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.horizontalLayout_2.addItem(self.horizontalSpacer_2)


        self.verticalLayout.addLayout(self.horizontalLayout_2)

        self.horizontalLayout = QHBoxLayout()
        self.horizontalLayout.setObjectName(u"horizontalLayout")
        self.label = QLabel(GithubCopilotLoginDialog)
        self.label.setObjectName(u"label")

        self.horizontalLayout.addWidget(self.label)

        self.lbUserCode = QLabel(GithubCopilotLoginDialog)
        self.lbUserCode.setObjectName(u"lbUserCode")
        self.lbUserCode.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        self.horizontalLayout.addWidget(self.lbUserCode)

        self.horizontalSpacer = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.horizontalLayout.addItem(self.horizontalSpacer)


        self.verticalLayout.addLayout(self.horizontalLayout)

        self.verticalSpacer = QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)

        self.verticalLayout.addItem(self.verticalSpacer)


        self.retranslateUi(GithubCopilotLoginDialog)

        QMetaObject.connectSlotsByName(GithubCopilotLoginDialog)
    # setupUi

    def retranslateUi(self, GithubCopilotLoginDialog):
        GithubCopilotLoginDialog.setWindowTitle(QCoreApplication.translate("GithubCopilotLoginDialog", u"Login to Github", None))
        self.lbStatus.setText(QCoreApplication.translate("GithubCopilotLoginDialog", u"Fetching login information...", None))
        self.label_3.setText(QCoreApplication.translate("GithubCopilotLoginDialog", u"Url:", None))
        self.lbUrl.setText("")
        self.label.setText(QCoreApplication.translate("GithubCopilotLoginDialog", u"User Code:", None))
        self.lbUserCode.setText("")
    # retranslateUi

