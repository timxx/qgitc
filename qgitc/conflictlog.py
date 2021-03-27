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
        from win32com.client import DispatchWithEvents
        HAVE_EXCEL_API = True
    except ImportError:
        pass
elif sys.platform == "linux":
    try:
        from pywpsrpc.rpcetapi import createEtRpcInstance, etapi
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
        self._handle.write('\t[{}] {} ("{}", {}, {})\n'.format(
            "a" if commit["branchA"] else "b",
            commit["sha1"],
            commit["subject"],
            commit["author"],
            commit["date"]
        ))
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


class WorkbookEvents:

    def OnBeforeClose(self, cancel):
        return True


class ConflictLogExcel(ConflictLogBase):

    def __init__(self, logFile):
        super().__init__()
        self._curFile = None
        self._isWin = sys.platform == "win32"
        self.app = None
        self.book = None
        self.sheet = None
        self.row = 1
        self.logFile = logFile
        self._rpc = None

        self._ensureExcel()

    def _ensureExcel(self):
        if not HAVE_EXCEL_API or self.sheet:
            return

        try:
            if self._isWin:
                if not self.app:
                    self.app = gencache.EnsureDispatch("Excel.Application")
                self.app.Visible = True
                self.book = DispatchWithEvents(
                    self.app.Workbooks.Open(self.logFile),
                    WorkbookEvents)
            else:
                if not self._rpc:
                    _, self._rpc = createEtRpcInstance()
                if not self.app:
                    _, self.app = self._rpc.getEtApplication()
                self.app.Visible = True
                _, self.book = self.app.Workbooks.Open(self.logFile)

                self._rpc.registerEvent(self.app,
                                        etapi.DIID_AppEvents,
                                        "WorkbookBeforeClose",
                                        self._onWorkbookBeforeClose)

            self.sheet = self.book.Sheets[1]
        except Exception:
            pass

    def addFile(self, file):
        self._curFile = file
        return True

    def addCommit(self, commit):
        self._ensureExcel()
        if not self.sheet:
            return False

        if self._curFile:
            self.row += 1
            self._setCellValue("A%s" % self.row, self._curFile)
            self._curFile = None

        msg = '{} ("{}", {}, {})'.format(
            commit["sha1"],
            commit["subject"],
            commit["author"],
            commit["date"])

        cell = "{}{}".format("B" if commit["branchA"] else "C", self.row)
        if not self._setCellValue(cell, msg, True):
            return False

        self.book.Save()
        return True

    def isValid(self):
        return self.sheet is not None

    def _setCellValue(self, cell, value, append=False):
        rg = self.sheet.Range(cell)
        rg.WrapText = True
        text = rg.Value
        if text and append:
            text += "\r\n" + value
        else:
            text = value
        rg.Value = text

        return True

    def _onWorkbookBeforeClose(self, wookbook):
        # not allow close the doc
        return wookbook == self.book


class ConflictLogProxy(ConflictLogBase):

    def __init__(self, logFile):
        super().__init__()
        self._file = ConflictLogFile()
        self._excel = ConflictLogExcel(logFile)

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
