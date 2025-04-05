# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'commitoptionsdialog.ui'
##
## Created by: Qt User Interface Compiler version 6.8.3
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
from PySide6.QtWidgets import (QAbstractButton, QApplication, QDialog, QDialogButtonBox,
    QSizePolicy, QWidget)

class Ui_CommitOptionsDialog(object):
    def setupUi(self, CommitOptionsDialog):
        if not CommitOptionsDialog.objectName():
            CommitOptionsDialog.setObjectName(u"CommitOptionsDialog")
        CommitOptionsDialog.resize(629, 294)
        self.buttonBox = QDialogButtonBox(CommitOptionsDialog)
        self.buttonBox.setObjectName(u"buttonBox")
        self.buttonBox.setGeometry(QRect(30, 240, 341, 32))
        self.buttonBox.setOrientation(Qt.Orientation.Horizontal)
        self.buttonBox.setStandardButtons(QDialogButtonBox.StandardButton.Cancel|QDialogButtonBox.StandardButton.Ok)

        self.retranslateUi(CommitOptionsDialog)
        self.buttonBox.accepted.connect(CommitOptionsDialog.accept)
        self.buttonBox.rejected.connect(CommitOptionsDialog.reject)

        QMetaObject.connectSlotsByName(CommitOptionsDialog)
    # setupUi

    def retranslateUi(self, CommitOptionsDialog):
        CommitOptionsDialog.setWindowTitle(QCoreApplication.translate("CommitOptionsDialog", u"Dialog", None))
    # retranslateUi

