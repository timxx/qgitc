# -*- coding: utf-8 -*-

import sys

__all__ = ["ConflictLogBase", "ConflictLogXlsx",
           "ConflictLogExcel"]


HAVE_EXCEL_API = False
HAVE_XLSX_WRITER = False

if sys.platform == "win32":
    try:
        from win32com.client import DispatchWithEvents, gencache
        HAVE_EXCEL_API = True
    except ImportError:
        pass
elif sys.platform == "linux":
    try:
        from pywpsrpc.rpcetapi import createEtRpcInstance, etapi
        HAVE_EXCEL_API = True
    except ImportError:
        pass


if not HAVE_EXCEL_API:
    try:
        import openpyxl
        HAVE_XLSX_WRITER = True
    except ImportError:
        pass


class MergeInfo:

    def __init__(self, local, remote, author):
        self.local = local
        self.remote = remote
        self.author = author


class ConflictLogBase:

    def __init__(self):
        # the starting row to log
        self._curRow = 6

    def addFile(self, file):
        return False

    def addCommit(self, commit):
        return False

    def save(self):
        pass

    def setResolveMethod(self, file, desc):
        pass

    def setMergeInfo(self, info):
        pass


class ConflictLogXlsx(ConflictLogBase):

    def __init__(self, logFile):
        super().__init__()
        self.logFile = logFile
        self.book = openpyxl.load_workbook(logFile)
        self.sheet = self.book.active
        self._curFile = None

    def addFile(self, path):
        self._curFile = path
        return True

    def addCommit(self, commit):
        if self._curFile:
            self._curRow += 1
            cell = "A%s" % self._curRow
            self.sheet[cell] = self._curFile
            self._curFile = None

        msg = '{} ("{}", {}, {})'.format(
            commit["sha1"],
            commit["subject"],
            commit["author"],
            commit["date"])

        cell = "{}{}".format("B" if commit["branchA"] else "C", self._curRow)
        self.sheet[cell].alignment = openpyxl.styles.Alignment(
            wrap_text=True, vertical="center")
        text = self.sheet[cell].value
        if text:
            text += "\r\n" + msg
        else:
            text = msg
        self.sheet[cell].value = text

        return True

    def save(self):
        self.book.save(self.logFile)

    def setResolveMethod(self, file, desc):
        self._curRow += 1
        cell = "A%s" % self._curRow
        self.sheet[cell] = file
        cell = "D%s" % self._curRow
        self.sheet[cell] = desc

    def setMergeInfo(self, info):
        self.sheet["B1"] = info.local
        self.sheet["B2"] = info.remote
        self.sheet["B3"] = info.author


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
        self.logFile = logFile
        self._rpc = None
        self._mergeInfo = None

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

            if self._mergeInfo is not None:
                self._setMergeInfo(self._mergeInfo)
                self._mergeInfo = None
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
            self._curRow += 1
            self._setCellValue("A%s" % self._curRow, self._curFile)
            self._curFile = None

        msg = '{} ("{}", {}, {})'.format(
            commit["sha1"],
            commit["subject"],
            commit["author"],
            commit["date"])

        cell = "{}{}".format("B" if commit["branchA"] else "C", self._curRow)
        if not self._setCellValue(cell, msg, True):
            return False

        self.book.Save()
        return True

    def setResolveMethod(self, file, desc):
        self._curRow += 1
        self._setCellValue("A%s" % self._curRow, file)
        self._setCellValue("D%s" % self._curRow, desc)

    def setMergeInfo(self, info):
        # delay for buggy wps on Linux
        if not self.book:
            self._mergeInfo = info
        else:
            self._setMergeInfo(info)

    def _setMergeInfo(self, info):
        self._setCellValue("B1", info.local)
        self._setCellValue("B2", info.remote)
        self._setCellValue("B3", info.author)

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
