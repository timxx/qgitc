# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'aboutdialog.ui'
#
# Created by: PyQt5 UI code generator 5.14.1
#
# WARNING! All changes made in this file will be lost!


from PyQt5 import QtCore, QtGui, QtWidgets


class Ui_AboutDialog(object):
    def setupUi(self, AboutDialog):
        AboutDialog.setObjectName("AboutDialog")
        AboutDialog.resize(465, 470)
        self.verticalLayout = QtWidgets.QVBoxLayout(AboutDialog)
        self.verticalLayout.setObjectName("verticalLayout")
        self.tabWidget = QtWidgets.QTabWidget(AboutDialog)
        self.tabWidget.setObjectName("tabWidget")
        self.tabAbout = QtWidgets.QWidget()
        self.tabAbout.setObjectName("tabAbout")
        self.verticalLayout_3 = QtWidgets.QVBoxLayout(self.tabAbout)
        self.verticalLayout_3.setObjectName("verticalLayout_3")
        self.appIcon = QtWidgets.QLabel(self.tabAbout)
        self.appIcon.setText("")
        self.appIcon.setAlignment(QtCore.Qt.AlignCenter)
        self.appIcon.setObjectName("appIcon")
        self.verticalLayout_3.addWidget(self.appIcon)
        self.tbAbout = QtWidgets.QTextBrowser(self.tabAbout)
        self.tbAbout.setObjectName("tbAbout")
        self.verticalLayout_3.addWidget(self.tbAbout)
        self.tabWidget.addTab(self.tabAbout, "")
        self.tabLicense = QtWidgets.QWidget()
        self.tabLicense.setObjectName("tabLicense")
        self.verticalLayout_2 = QtWidgets.QVBoxLayout(self.tabLicense)
        self.verticalLayout_2.setObjectName("verticalLayout_2")
        self.tbLicense = QtWidgets.QTextBrowser(self.tabLicense)
        self.tbLicense.setObjectName("tbLicense")
        self.verticalLayout_2.addWidget(self.tbLicense)
        self.tabWidget.addTab(self.tabLicense, "")
        self.verticalLayout.addWidget(self.tabWidget)
        self.buttonBox = QtWidgets.QDialogButtonBox(AboutDialog)
        self.buttonBox.setOrientation(QtCore.Qt.Horizontal)
        self.buttonBox.setStandardButtons(QtWidgets.QDialogButtonBox.Close)
        self.buttonBox.setCenterButtons(True)
        self.buttonBox.setObjectName("buttonBox")
        self.verticalLayout.addWidget(self.buttonBox)

        self.retranslateUi(AboutDialog)
        self.tabWidget.setCurrentIndex(0)
        self.buttonBox.accepted.connect(AboutDialog.accept)
        self.buttonBox.rejected.connect(AboutDialog.reject)
        QtCore.QMetaObject.connectSlotsByName(AboutDialog)

    def retranslateUi(self, AboutDialog):
        _translate = QtCore.QCoreApplication.translate
        AboutDialog.setWindowTitle(_translate("AboutDialog", "About gitc"))
        self.tabWidget.setTabText(self.tabWidget.indexOf(self.tabAbout), _translate("AboutDialog", "&About"))
        self.tabWidget.setTabText(self.tabWidget.indexOf(self.tabLicense), _translate("AboutDialog", "&License"))
