# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'ui/aboutdialog.ui'
#
# Created by: PyQt4 UI code generator 4.12.1
#
# WARNING! All changes made in this file will be lost!

from PyQt4 import QtCore, QtGui

try:
    _fromUtf8 = QtCore.QString.fromUtf8
except AttributeError:
    def _fromUtf8(s):
        return s

try:
    _encoding = QtGui.QApplication.UnicodeUTF8
    def _translate(context, text, disambig):
        return QtGui.QApplication.translate(context, text, disambig, _encoding)
except AttributeError:
    def _translate(context, text, disambig):
        return QtGui.QApplication.translate(context, text, disambig)

class Ui_AboutDialog(object):
    def setupUi(self, AboutDialog):
        AboutDialog.setObjectName(_fromUtf8("AboutDialog"))
        AboutDialog.resize(465, 470)
        self.verticalLayout = QtGui.QVBoxLayout(AboutDialog)
        self.verticalLayout.setObjectName(_fromUtf8("verticalLayout"))
        self.tabWidget = QtGui.QTabWidget(AboutDialog)
        self.tabWidget.setObjectName(_fromUtf8("tabWidget"))
        self.tabAbout = QtGui.QWidget()
        self.tabAbout.setObjectName(_fromUtf8("tabAbout"))
        self.verticalLayout_3 = QtGui.QVBoxLayout(self.tabAbout)
        self.verticalLayout_3.setMargin(0)
        self.verticalLayout_3.setObjectName(_fromUtf8("verticalLayout_3"))
        self.appIcon = QtGui.QLabel(self.tabAbout)
        self.appIcon.setText(_fromUtf8(""))
        self.appIcon.setAlignment(QtCore.Qt.AlignCenter)
        self.appIcon.setObjectName(_fromUtf8("appIcon"))
        self.verticalLayout_3.addWidget(self.appIcon)
        self.tbAbout = QtGui.QTextBrowser(self.tabAbout)
        self.tbAbout.setObjectName(_fromUtf8("tbAbout"))
        self.verticalLayout_3.addWidget(self.tbAbout)
        self.tabWidget.addTab(self.tabAbout, _fromUtf8(""))
        self.tabLicense = QtGui.QWidget()
        self.tabLicense.setObjectName(_fromUtf8("tabLicense"))
        self.verticalLayout_2 = QtGui.QVBoxLayout(self.tabLicense)
        self.verticalLayout_2.setMargin(0)
        self.verticalLayout_2.setObjectName(_fromUtf8("verticalLayout_2"))
        self.tbLicense = QtGui.QTextBrowser(self.tabLicense)
        self.tbLicense.setObjectName(_fromUtf8("tbLicense"))
        self.verticalLayout_2.addWidget(self.tbLicense)
        self.tabWidget.addTab(self.tabLicense, _fromUtf8(""))
        self.verticalLayout.addWidget(self.tabWidget)
        self.buttonBox = QtGui.QDialogButtonBox(AboutDialog)
        self.buttonBox.setOrientation(QtCore.Qt.Horizontal)
        self.buttonBox.setStandardButtons(QtGui.QDialogButtonBox.Close)
        self.buttonBox.setCenterButtons(True)
        self.buttonBox.setObjectName(_fromUtf8("buttonBox"))
        self.verticalLayout.addWidget(self.buttonBox)

        self.retranslateUi(AboutDialog)
        self.tabWidget.setCurrentIndex(0)
        QtCore.QObject.connect(self.buttonBox, QtCore.SIGNAL(_fromUtf8("accepted()")), AboutDialog.accept)
        QtCore.QObject.connect(self.buttonBox, QtCore.SIGNAL(_fromUtf8("rejected()")), AboutDialog.reject)
        QtCore.QMetaObject.connectSlotsByName(AboutDialog)

    def retranslateUi(self, AboutDialog):
        AboutDialog.setWindowTitle(_translate("AboutDialog", "About gitc", None))
        self.tabWidget.setTabText(self.tabWidget.indexOf(self.tabAbout), _translate("AboutDialog", "&About", None))
        self.tabWidget.setTabText(self.tabWidget.indexOf(self.tabLicense), _translate("AboutDialog", "&License", None))

