# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'ui/gitview.ui'
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

class Ui_GitView(object):
    def setupUi(self, GitView):
        GitView.setObjectName(_fromUtf8("GitView"))
        GitView.resize(668, 630)
        self.verticalLayout_2 = QtGui.QVBoxLayout(GitView)
        self.verticalLayout_2.setObjectName(_fromUtf8("verticalLayout_2"))
        self.horizontalLayout = QtGui.QHBoxLayout()
        self.horizontalLayout.setSizeConstraint(QtGui.QLayout.SetDefaultConstraint)
        self.horizontalLayout.setObjectName(_fromUtf8("horizontalLayout"))
        self.lbBranch = QtGui.QLabel(GitView)
        sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Fixed, QtGui.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.lbBranch.sizePolicy().hasHeightForWidth())
        self.lbBranch.setSizePolicy(sizePolicy)
        self.lbBranch.setObjectName(_fromUtf8("lbBranch"))
        self.horizontalLayout.addWidget(self.lbBranch)
        self.cbBranch = QtGui.QComboBox(GitView)
        self.cbBranch.setObjectName(_fromUtf8("cbBranch"))
        self.horizontalLayout.addWidget(self.cbBranch)
        self.verticalLayout_2.addLayout(self.horizontalLayout)
        self.splitter = QtGui.QSplitter(GitView)
        self.splitter.setFrameShape(QtGui.QFrame.NoFrame)
        self.splitter.setOrientation(QtCore.Qt.Vertical)
        self.splitter.setObjectName(_fromUtf8("splitter"))
        self.logView = LogView(self.splitter)
        self.logView.setFocusPolicy(QtCore.Qt.StrongFocus)
        self.logView.setObjectName(_fromUtf8("logView"))
        self.verticalLayoutWidget = QtGui.QWidget(self.splitter)
        self.verticalLayoutWidget.setObjectName(_fromUtf8("verticalLayoutWidget"))
        self.verticalLayout = QtGui.QVBoxLayout(self.verticalLayoutWidget)
        self.verticalLayout.setMargin(0)
        self.verticalLayout.setObjectName(_fromUtf8("verticalLayout"))
        self.verticalLayout_3 = QtGui.QVBoxLayout()
        self.verticalLayout_3.setObjectName(_fromUtf8("verticalLayout_3"))
        self.horizontalLayout_2 = QtGui.QHBoxLayout()
        self.horizontalLayout_2.setObjectName(_fromUtf8("horizontalLayout_2"))
        self.label = QtGui.QLabel(self.verticalLayoutWidget)
        self.label.setObjectName(_fromUtf8("label"))
        self.horizontalLayout_2.addWidget(self.label)
        self.leSha1 = QtGui.QLineEdit(self.verticalLayoutWidget)
        self.leSha1.setObjectName(_fromUtf8("leSha1"))
        self.horizontalLayout_2.addWidget(self.leSha1)
        spacerItem = QtGui.QSpacerItem(40, 20, QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Minimum)
        self.horizontalLayout_2.addItem(spacerItem)
        self.verticalLayout_3.addLayout(self.horizontalLayout_2)
        self.horizontalLayout_3 = QtGui.QHBoxLayout()
        self.horizontalLayout_3.setObjectName(_fromUtf8("horizontalLayout_3"))
        self.label_3 = QtGui.QLabel(self.verticalLayoutWidget)
        self.label_3.setObjectName(_fromUtf8("label_3"))
        self.horizontalLayout_3.addWidget(self.label_3)
        self.label_2 = QtGui.QLabel(self.verticalLayoutWidget)
        self.label_2.setObjectName(_fromUtf8("label_2"))
        self.horizontalLayout_3.addWidget(self.label_2)
        self.cbFindWhat = QtGui.QComboBox(self.verticalLayoutWidget)
        self.cbFindWhat.setObjectName(_fromUtf8("cbFindWhat"))
        self.cbFindWhat.addItem(_fromUtf8(""))
        self.cbFindWhat.addItem(_fromUtf8(""))
        self.cbFindWhat.addItem(_fromUtf8(""))
        self.horizontalLayout_3.addWidget(self.cbFindWhat)
        self.leFindWhat = QtGui.QLineEdit(self.verticalLayoutWidget)
        self.leFindWhat.setObjectName(_fromUtf8("leFindWhat"))
        self.horizontalLayout_3.addWidget(self.leFindWhat)
        self.cbFindType = QtGui.QComboBox(self.verticalLayoutWidget)
        self.cbFindType.setObjectName(_fromUtf8("cbFindType"))
        self.cbFindType.addItem(_fromUtf8(""))
        self.cbFindType.addItem(_fromUtf8(""))
        self.cbFindType.addItem(_fromUtf8(""))
        self.horizontalLayout_3.addWidget(self.cbFindType)
        self.tbPrev = QtGui.QToolButton(self.verticalLayoutWidget)
        self.tbPrev.setObjectName(_fromUtf8("tbPrev"))
        self.horizontalLayout_3.addWidget(self.tbPrev)
        self.tbNext = QtGui.QToolButton(self.verticalLayoutWidget)
        self.tbNext.setObjectName(_fromUtf8("tbNext"))
        self.horizontalLayout_3.addWidget(self.tbNext)
        self.verticalLayout_3.addLayout(self.horizontalLayout_3)
        self.verticalLayout.addLayout(self.verticalLayout_3)
        self.diffView = DiffView(self.verticalLayoutWidget)
        self.diffView.setObjectName(_fromUtf8("diffView"))
        self.verticalLayout.addWidget(self.diffView)
        self.verticalLayout_2.addWidget(self.splitter)

        self.retranslateUi(GitView)
        QtCore.QMetaObject.connectSlotsByName(GitView)
        GitView.setTabOrder(self.cbBranch, self.logView)
        GitView.setTabOrder(self.logView, self.leSha1)
        GitView.setTabOrder(self.leSha1, self.cbFindWhat)
        GitView.setTabOrder(self.cbFindWhat, self.leFindWhat)
        GitView.setTabOrder(self.leFindWhat, self.cbFindType)
        GitView.setTabOrder(self.cbFindType, self.tbPrev)
        GitView.setTabOrder(self.tbPrev, self.tbNext)

    def retranslateUi(self, GitView):
        GitView.setWindowTitle(_translate("GitView", "GitView", None))
        self.lbBranch.setText(_translate("GitView", "Branch:", None))
        self.label.setText(_translate("GitView", "SHA1 ID:", None))
        self.label_3.setText(_translate("GitView", "Find", None))
        self.label_2.setText(_translate("GitView", "commit", None))
        self.cbFindWhat.setItemText(0, _translate("GitView", "adding/removing string", None))
        self.cbFindWhat.setItemText(1, _translate("GitView", "changing lines matching", None))
        self.cbFindWhat.setItemText(2, _translate("GitView", "containing", None))
        self.leFindWhat.setPlaceholderText(_translate("GitView", "Press Enter to find commits", None))
        self.cbFindType.setItemText(0, _translate("GitView", "Exact", None))
        self.cbFindType.setItemText(1, _translate("GitView", "Ignore case", None))
        self.cbFindType.setItemText(2, _translate("GitView", "Regexp", None))
        self.tbPrev.setToolTip(_translate("GitView", "Find previous", None))
        self.tbPrev.setText(_translate("GitView", "↑", None))
        self.tbNext.setToolTip(_translate("GitView", "Find next", None))
        self.tbNext.setText(_translate("GitView", "↓", None))

from diffview import DiffView
from logview import LogView
