# -*- coding: utf-8 -*-


import tempfile
import os
import sys


__all__ = ["ConflictLogBase", "ConflictLogFile",
           "ConflictLogExcel", "ConflictLogProxy"]


HAVE_EXCEL_API = False

if sys.platform == "win32":
    try:
        from win32com.client import gencache
        HAVE_EXCEL_API = True
    except ImportError:
        pass
elif sys.platform == "linux":
    try:
        from pywpsrpc.rpcetapi import createEtRpcInstance
        HAVE_EXCEL_API = True
    except ImportError:
        pass


class ConflictLogBase:

    def __init__(self):
        pass

    def addFile(self, file):
        return False

    def addCommit(self, commit):
        return False

    def setStatus(self, ok):
        pass

    def isValid(self):
        return False


class ConflictLogFile(ConflictLogBase):
    """ The temporay log file, the format is:
    [f] The conflict file path 1
    \t[a] conflict commit 1
    \t[a] conflict commit N
    \t[b] conflict commit 1
    \t[b] conflict commit N
    \t[s] Y/N
    [f] The conflict file path N
    ...
    """

    def __init__(self):
        self.filePath = os.path.join(
            tempfile.gettempdir(), "qgitc_conflicts.log")
        self._handle = None

    def _ensureHandle(self):
        if self._handle is None:
            self._handle = open(self.filePath, "a+")

    def addFile(self, path):
        self._ensureHandle()

        self._handle.write("[f] " + path + "\n")
        self._handle.flush()
        return True

    def addCommit(self, commit):
        self._handle.flush()
        return True

    def setStatus(self, ok):
        self._handle.write("\t[s] ")
        self._handle.write("Y" if ok else "N")
        self._handle.write("\n")
        self._handle.flush()

    def isValid(self):
        return True

    def toExcelXml(self, path):
        pass

    def unlink(self):
        self._handle.close()
        self._handle = None
        os.remove(self.filePath)


class ConflictLogExcel(ConflictLogBase):

    def __init__(self):
        super().__init__()
        self._curFile = None
        self._isWin = sys.platform == "win32"
        self.app = None
        self.sheet = None

    def _ensureExcel(self):
        if not HAVE_EXCEL_API or self.app:
            return

        try:
            if self._isWin:
                self.app = gencache.EnsureDispatch("Excel.Application")
            else:
                hr, rpc = createEtRpcInstance()
                if hr == 0:
                    _, self.app = rpc.getEtApplication()
            self.app.Visible = True
            hr, book = self.app.Workbooks.Add()
            self.sheet = book.Sheets[1]
            self._initHeader()
        except:
            pass

    def _initHeader(self):
        pass

    def addFile(self, file):
        self._ensureExcel()
        self._curFile = file
        return True

    def addCommit(self, commit):
        if not self.sheet:
            return False
        return True

    def isValid(self):
        return self.sheet is not None


class ConflictLogProxy(ConflictLogBase):

    def __init__(self):
        super().__init__()
        self._file = ConflictLogFile()
        self._excel = ConflictLogExcel()

    def addFile(self, file):
        self._file.addFile(file)
        self._excel.addFile(file)

    def addCommit(self, commit):
        self._file.addCommit(commit)
        self._excel.addCommit(commit)

    def setStatus(self, ok):
        self._file.setStatus(ok)
        self._excel.setStatus(ok)

    def isValid(self):
        return True

    def isExcelValid(self):
        return self._excel.isValid()
