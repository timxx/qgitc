#!/usr/bin/env python

from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *

import sys
import argparse


def selectImage(parent):
    filter = "Images (*.png *.xpm *.jpg *.gif *.svg)"
    f, _ = QFileDialog.getOpenFileName(parent,
                                    parent.tr("Select Image"),
                                    filter=filter)
    return f


class NewDiffDlg(QDialog):

    def __init__(self, parent=None):
        super(NewDiffDlg, self).__init__(parent)
        self.setWindowTitle(self.tr("New Image Diff"))
        self.resize(580, 150)

        gridLayout = QGridLayout()

        gridLayout.addWidget(QLabel("A (Base):"), 0, 0)
        self.leA = QLineEdit(self)
        gridLayout.addWidget(self.leA, 0, 1)
        self.btnA = QPushButton("&Image...", self)
        gridLayout.addWidget(self.btnA, 0, 2)

        gridLayout.addWidget(QLabel("B:"), 1, 0)
        self.leB = QLineEdit(self)
        gridLayout.addWidget(self.leB, 1, 1)
        self.btnB = QPushButton("I&mage...", self)
        gridLayout.addWidget(self.btnB, 1, 2)

        gridLayout.addWidget(QLabel("C (Optional):"), 2, 0)
        self.leC = QLineEdit(self)
        gridLayout.addWidget(self.leC, 2, 1)
        self.btnC = QPushButton("Im&age...", self)
        gridLayout.addWidget(self.btnC, 2, 2)

        self.cbOutput = QCheckBox(self.tr("&Output"), self)
        gridLayout.addWidget(self.cbOutput, 3, 0)
        self.leO = QLineEdit(self)
        gridLayout.addWidget(self.leO, 3, 1)
        self.btnO = QPushButton("Ima&ge...", self)
        gridLayout.addWidget(self.btnO, 3, 2)

        vlayout = QVBoxLayout(self)
        vlayout.addLayout(gridLayout)

        buttonBox = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        vlayout.addWidget(buttonBox)

        buttonBox.accepted.connect(self.accept)
        buttonBox.rejected.connect(self.reject)

        self.btnA.clicked.connect(self.__onBtnAClicked)
        self.btnB.clicked.connect(self.__onBtnBClicked)
        self.btnC.clicked.connect(self.__onBtnCClicked)
        self.btnO.clicked.connect(self.__onBtnOClicked)

        self.cbOutput.stateChanged.connect(
            self.__onOutputStateChanged)

        self.__onOutputStateChanged(Qt.Unchecked)

    def __onBtnAClicked(self, checked=False):
        f = selectImage(self)
        self.leA.setText(f)

    def __onBtnBClicked(self, checked=False):
        f = selectImage(self)
        self.leB.setText(f)

    def __onBtnCClicked(self, checked=False):
        f = selectImage(self)
        self.leC.setText(f)

    def __onBtnOClicked(self, checked=False):
        f = selectImage(self)
        self.leO.setText(f)

    def __onOutputStateChanged(self, state):
        enabled = True if state == Qt.Checked else False
        self.leO.setEnabled(enabled)
        self.btnO.setEnabled(enabled)

    def imageA(self):
        return self.leA.text().strip()

    def imageB(self):
        return self.leB.text().strip()

    def imageC(self):
        return self.leC.text().strip()

    def imageO(self):
        return self.leO.text().strip()


class ImageViewer(QWidget):

    def __init__(self, parent=None):
        super(ImageViewer, self).__init__(parent)

        self.lbName = QLabel(self)
        self.lePath = QLineEdit(self)
        self.btnBrowse = QPushButton("...", self)
        self.btnBrowse.setFixedWidth(30)

        hlayout = QHBoxLayout()
        hlayout.addWidget(self.lbName)
        hlayout.addWidget(self.lePath)
        hlayout.addWidget(self.btnBrowse)

        self.scrollArea = QScrollArea(self)

        vlayout = QVBoxLayout(self)
        vlayout.addLayout(hlayout)
        vlayout.addWidget(self.scrollArea)

        self.viewer = QLabel(self)
        self.viewer.setAlignment(Qt.AlignCenter)
        self.scrollArea.setWidget(self.viewer)
        self.scrollArea.setWidgetResizable(True)
        self.scrollArea.setAlignment(Qt.AlignCenter)

        self.lePath.textChanged.connect(
            self.__onPathChanged)
        self.btnBrowse.clicked.connect(
            self.__onBtnBrowseClicked)

    def __onPathChanged(self, path):
        pixmap = QPixmap(path)
        self.viewer.setPixmap(pixmap)

    def __onBtnBrowseClicked(self, checked=False):
        f = selectImage(self)
        if f:
            self.lePath.setText(f)

    def setName(self, name):
        self.lbName.setText(name)

    def setImage(self, image):
        if isinstance(image, str):
            self.lePath.setText(image)
        elif isinstance(image, QPixmap):
            self.viewer.setPixmap(image)
        elif isinstance(image, QImage):
            self.viewer.setPixmap(QPixmap.fromImage(image))

    def setBrowseEnabled(self, enabled=True):
        self.lePath.setReadOnly(not enabled)
        self.btnBrowse.setVisible(enabled)

    def scaleImage(self, factor):
        pixmap = self.viewer.pixmap()
        if not pixmap.isNull():
            if isinstance(factor, QSize):
                self.scrollArea.setWidgetResizable(False)
                self.viewer.resize(factor)
            else:
                if factor == 1.0:
                    self.scrollArea.setWidgetResizable(True)
                else:
                    self.scrollArea.setWidgetResizable(False)
                self.viewer.resize(factor * pixmap.size())

    def getImage(self):
        return self.viewer.pixmap()

    def viewSize(self):
        return self.scrollArea.size()


class ImgDiff(QWidget):

    dataChanged = pyqtSignal()

    def __init__(self, parent=None):
        super(ImgDiff, self).__init__(parent)

        self.imageA = ImageViewer(self)
        self.imageB = ImageViewer(self)
        self.imageC = None
        self.imageO = None

        self._outputFile = ""

        self.imageA.setName("A:")
        self.imageB.setName("B:")

        self.hlayout = QHBoxLayout()
        self.hlayout.addWidget(self.imageA)
        self.hlayout.addWidget(self.imageB)

        vlayout = QVBoxLayout(self)
        vlayout.addLayout(self.hlayout)

    def __fitImageView(self, viewer):
        if not viewer:
            return
        image = viewer.getImage()
        if not image:
            return

        if not image.isNull():
            size = image.size()
            size.scale(viewer.viewSize(), Qt.KeepAspectRatio)
            # * 0.99 to hide the scrollbar LoL
            viewer.scaleImage(size * 0.99)

    def diff(self, imageA, imageB, imageC=None, imageO=None):
        self.imageA.setImage(imageA)
        self.imageB.setImage(imageB)

        if imageC:
            if not self.imageC:
                self.imageC = ImageViewer(self)
                self.imageC.setName("C:")
                self.hlayout.addWidget(self.imageC)
            else:
                self.imageC.setVisible(True)

            self.imageC.setImage(imageC)
        elif self.imageC:
            self.imageC.setVisible(False)

        if imageO:
            if not self.imageO:
                self.imageO = ImageViewer(self)
                self.imageO.setBrowseEnabled(False)
                self.imageO.setName("Output:")
                self.layout().addWidget(self.imageO)
            else:
                self.imageO.setVisible(True)

            self.imageO.setImage(imageO)
            self._outputFile = imageO
        elif self.imageO:
            self.imageO.setVisible(False)

    def setBase(self, base):
        if not self.imageC:
            return

        if base in "aA":
            self.imageA.setName("A (Base):")
        elif base in "bB":
            self.imageB.setName("B (Base):")
        elif base in "cC":
            self.imageC.setName("C (Base):")

    def normalSize(self):
        factor = 1.0
        self.imageA.scaleImage(factor)
        self.imageB.scaleImage(factor)
        if self.imageC:
            self.imageC.scaleImage(factor)
        if self.imageO:
            self.imageO.scaleImage(factor)

    def fitWindow(self):
        self.__fitImageView(self.imageA)
        self.__fitImageView(self.imageB)
        self.__fitImageView(self.imageC)
        self.__fitImageView(self.imageO)

    def hasOutput(self):
        return not self.imageO is None

    def outputFile(self):
        return self._outputFile

    def getImageA(self):
        if self.imageA:
            return self.imageA.getImage()
        return None

    def getImageB(self):
        if self.imageB:
            return self.imageB.getImage()
        return None

    def getImageC(self):
        if self.imageC:
            return self.imageC.getImage()
        return None

    def getImageO(self):
        if self.imageO:
            return self.imageO.getImage()
        return None

    def setOutputImage(self, image):
        if self.imageO:
            self.imageO.setImage(image)
            self.dataChanged.emit()


class DiffWindow(QMainWindow):

    def __init__(self, parent=None):
        super(DiffWindow, self).__init__(parent)
        self.setWindowTitle(self.tr("Image Diff"))

        self._diffView = ImgDiff(self)
        self.setCentralWidget(self._diffView)

        self._fitWindow = True
        self._resolved = False

        self.__setupMenu()

        self._diffView.dataChanged.connect(
            self.__onDataChanged)

    def __setupMenu(self):
        self.fileMenu = self.menuBar().addMenu(self.tr("&File"))
        self.fileMenu.addAction(self.tr("&Open"),
                                self.__onMenuOpen,
                                QKeySequence("Ctrl+O"))
        self.fileMenu.addSeparator()
        self.acSave = self.fileMenu.addAction(self.tr("&Save"),
                                              self.__onMenuSave,
                                              QKeySequence("Ctrl+S"))
        self.fileMenu.addSeparator()
        self.fileMenu.addAction(self.tr("&Quit"),
                                self.__onMenuQuit,
                                QKeySequence("Ctrl+Q"))

        self.viewMenu = self.menuBar().addMenu(self.tr("&View"))
        acFitWindow = self.viewMenu.addAction(
            "&Fit Window", self.__onMenuFitWindow)
        acNormal = self.viewMenu.addAction("&Normal", self.__onMenuNormal)
        self.viewMenu.addSeparator()
        self.acShowDiff = self.viewMenu.addAction(self.tr("Show &Difference"),
                                                  self.__onMenuShowDifference)

        self.acSave.setEnabled(False)
        acFitWindow.setCheckable(True)
        acNormal.setCheckable(True)

        acGroup = QActionGroup(self)
        acGroup.addAction(acFitWindow)
        acGroup.addAction(acNormal)

        acFitWindow.setChecked(True)
        self.acShowDiff.setCheckable(True)

        self.mergeMenu = self.menuBar().addMenu("&Merge")
        self.mergeMenu.addAction(self.tr("Choose &A"),
                                 self.__onMenuChooseA,
                                 QKeySequence("Ctrl+1"))
        self.mergeMenu.addAction(self.tr("Choose &B"),
                                 self.__onMenuChooseB,
                                 QKeySequence("Ctrl+2"))
        self.mergeMenu.addAction(self.tr("Choose &C"),
                                 self.__onMenuChooseC,
                                 QKeySequence("Ctrl+3"))
        self.mergeMenu.setEnabled(False)

    def __doQuit(self):
        # output file changed
        if self.acSave.isEnabled():
            r = QMessageBox.question(self,
                                     self.windowTitle(),
                                     self.tr(
                                         "Output file changed, do you want to save?"),
                                     QMessageBox.Yes,
                                     QMessageBox.No,
                                     QMessageBox.Cancel)
            if r == QMessageBox.Yes:
                self.__onMenuSave()
            elif r == QMessageBox.Cancel:
                return

        exit(0 if self._resolved else 1)

    def __onMenuOpen(self):
        dlg = NewDiffDlg(self)
        if dlg.exec() == QDialog.Accepted:
            self._diffView.diff(dlg.imageA(), dlg.imageB(),
                                dlg.imageC(), dlg.imageO())
            self.setBase('A')
            self.mergeMenu.setEnabled(self._diffView.hasOutput())

    def __onMenuSave(self):
        image = self._diffView.getImageO()
        if not image.isNull():
            filePath = self._diffView.outputFile()
            self._resolved = image.save(filePath)
            self.acSave.setEnabled(not self._resolved)
        else:
            print("Empty image!!!")

    def __onMenuQuit(self):
        self.__doQuit()

    def __onMenuFitWindow(self):
        self._fitWindow = True
        self._diffView.fitWindow()

    def __onMenuNormal(self):
        self._fitWindow = False
        self._diffView.normalSize()

    def __onMenuShowDifference(self):
        # TODO:
        pass

    def __onMenuChooseA(self):
        image = self._diffView.getImageA()
        self._diffView.setOutputImage(image)

    def __onMenuChooseB(self):
        image = self._diffView.getImageB()
        self._diffView.setOutputImage(image)

    def __onMenuChooseC(self):
        image = self._diffView.getImageC()
        self._diffView.setOutputImage(image)

    def __onDataChanged(self):
        self._resolved = False
        self.acSave.setEnabled(True)

    def resizeEvent(self, event):
        super(DiffWindow, self).resizeEvent(event)

        if self._fitWindow:
            self._diffView.fitWindow()
        else:
            self._diffView.normalSize()

    def closeEvent(self, event):
        self.__doQuit()
        event.ignore()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close()
            return

        super(DiffWindow, self).keyPressEvent(event)

    def diffView(self):
        return self._diffView

    def diff(self, imageA, imageB, imageC=None, imageO=None):
        if not imageA:
            self.__onMenuOpen()
        else:
            self._diffView.diff(imageA, imageB, imageC, imageO)
            self.mergeMenu.setEnabled(self._diffView.hasOutput())

    def setBase(self, base):
        self._diffView.setBase(base)


def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument("-o", "--output",
                        help="Output file for merging.")
    parser.add_argument("-b", "--base",
                        choices=['A', 'B', 'C', 'a', 'b', 'c'], default='A',
                        help="Specify which is base")
    parser.add_argument(
        "imageA", nargs='?', help="image A to open (base, if not specified via --base).")
    parser.add_argument("imageB", nargs='?', help="image B to open.")
    parser.add_argument("imageC", nargs='?', help="image C to open.")

    args = parser.parse_args()

    app = QApplication(argv)

    window = DiffWindow()
    window.diff(args.imageA, args.imageB, args.imageC, args.output)
    window.setBase(args.base)

    window.showMaximized()

    sys.exit(app.exec())


if __name__ == "__main__":
    main(sys.argv)
