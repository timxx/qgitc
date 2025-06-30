# -*- coding: utf-8 -*-

import json
from enum import Enum
from typing import Dict

from PySide6.QtCore import QObject, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtNetwork import QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import QDialog

from qgitc.applicationbase import ApplicationBase
from qgitc.ui_githubcopilotlogindialog import Ui_GithubCopilotLoginDialog


class LoginStep(Enum):
    VerifyUrl = 0
    AccessCode = 1
    UserInfo = 2


class LoginThread(QObject):
    loginFailed = Signal(str)
    finished = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.deviceCode = None
        self.userCode = None
        self.verificationUri = None
        self.accessToken = None
        self.step = LoginStep.VerifyUrl
        self._reply: QNetworkReply = None

    def startVerifyUrl(self):
        self.step = LoginStep.VerifyUrl
        self.start()

    def startAccessCode(self):
        self.step = LoginStep.AccessCode
        self.start()

    def startUserInfo(self):
        self.step = LoginStep.UserInfo
        self.start()

    def start(self):
        try:
            if self.step == LoginStep.VerifyUrl:
                self._getVerifyUrl()
            elif self.step == LoginStep.AccessCode:
                self._getAccessCode()
            elif self.step == LoginStep.UserInfo:
                self._getUserInfo()
        except Exception as e:
            self.loginFailed.emit(str(e))

    def _getVerifyUrl(self):
        self._post(
            "https://github.com/login/device/code",
            headers={
                b"accept": b"application/json",
                b"editor-version": b"Neovim/0.6.1",
                b"editor-plugin-version": b"copilot.vim/1.16.0",
                b"content-type": b"application/json",
                b"user-agent": b"GithubCopilot/1.155.0",
            },
            data={
                "client_id": "Iv1.b507a08c87ecfe98",
                "scope": "read:user"
            })

    def _getAccessCode(self):
        self._post(
            "https://github.com/login/oauth/access_token",
            headers={
                b"accept": b"application/json",
                b"editor-version": b"Neovim/0.6.1",
                b"editor-plugin-version": b"copilot.vim/1.16.0",
                b"content-type": b"application/json",
                b"user-agent": b"GithubCopilot/1.155.0",
            },
            data={
                "client_id": "Iv1.b507a08c87ecfe98",
                "device_code": self.deviceCode,
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code"
            })

    def _getUserInfo(self):
        # TODO: the below URL cannot fetch user name
        # http://api.github.com/copilot_internal/user
        pass

    def isRunning(self):
        return self._reply is not None and self._reply.isRunning()

    def requestInterruption(self):
        if self.isRunning():
            self._reply.abort()

    def _post(self, url: str, headers: Dict[bytes, bytes], data: Dict[str, str] = None):
        mgr = ApplicationBase.instance().networkManager
        request = QNetworkRequest()
        request.setUrl(url)

        if headers:
            for key, value in headers.items():
                request.setRawHeader(key, value)

        jsonData = json.dumps(data).encode("utf-8") if data else b''
        self._reply = mgr.post(request, jsonData)

        self._reply.finished.connect(self._onFinished)
        self._reply.errorOccurred.connect(self._onError)

    def _onFinished(self):
        reply = self._reply
        reply.deleteLater()
        self._reply = None

        if reply.error() != QNetworkReply.NoError:
            self.finished.emit()
            return

        data: dict = json.loads(reply.readAll().data())
        if self.step == LoginStep.VerifyUrl:
            self.deviceCode = data.get("device_code")
            self.userCode = data.get("user_code")
            self.verificationUri = data.get("verification_uri")

            if not self.deviceCode or not self.userCode or not self.verificationUri:
                self.loginFailed.emit(
                    self.tr("Failed to get verification URL"))
            self.finished.emit()
        elif self.step == LoginStep.AccessCode:
            error = data.get("error")
            if error == "access_denied":
                self.loginFailed.emit(self.tr("Access denied"))
                self.finished.emit()
            else:
                self.accessToken = data.get("access_token")
                if not self.accessToken:
                    QTimer.singleShot(5000, self._getAccessCode)
                else:
                    self.finished.emit()

    def _onError(self, code: QNetworkReply.NetworkError):
        if code == QNetworkReply.NoError:
            return

        if self.step == LoginStep.VerifyUrl:
            self.loginFailed.emit(
                self.tr("Failed to get verification URL: {}").format(code))
        elif self.step == LoginStep.AccessCode:
            self.loginFailed.emit(self.tr("Access denied"))


class GithubCopilotLoginDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.ui = Ui_GithubCopilotLoginDialog()
        self.ui.setupUi(self)

        self._loginThread = LoginThread(self)
        self._loginThread.loginFailed.connect(self._onLoginFailed)
        self._loginThread.finished.connect(self._onLoginFinished)
        self._loginThread.startVerifyUrl()

        self._autoClose = False

    def _onLoginFailed(self, error):
        msg = self.tr("Login failed: {}").format(error)
        self.ui.lbStatus.setText(msg)
        self.ui.progressBar.setRange(0, 1)
        self.ui.progressBar.setValue(1)

    def _onLoginFinished(self):
        if self._loginThread.step == LoginStep.VerifyUrl:
            self._handleVerification()
            return

        if self._loginThread.step == LoginStep.AccessCode:
            self._handleAccessCode()
            return

    def _handleVerification(self):
        if not self._loginThread.userCode or not self._loginThread.verificationUri:
            return

        url = "<a href='{0}'>{0}</a>".format(
            self._loginThread.verificationUri)
        self.ui.lbUrl.setText(url)
        self.ui.lbUserCode.setText(self._loginThread.userCode)

        clipboard = ApplicationBase.instance().clipboard()
        clipboard.setText(self._loginThread.userCode)

        QDesktopServices.openUrl(
            QUrl(self._loginThread.verificationUri))

        msg = self.tr(
            "Please open the following URL in your browser and enter the code to authenticate...")
        self.ui.lbStatus.setText(msg)

        self._loginThread.startAccessCode()

    def _handleAccessCode(self):
        if not self._loginThread.accessToken:
            return

        self.ui.lbStatus.setText(self.tr("Login successful"))
        ApplicationBase.instance().settings().setGithubCopilotAccessToken(
            self._loginThread.accessToken)

        self.ui.progressBar.setRange(0, 1)
        self.ui.progressBar.setValue(1)
        # self._loginThread.startUserInfo()

        if self._autoClose:
            self.accept()

    def closeEvent(self, event):
        if self._loginThread.isRunning():
            self._loginThread.disconnect(self)
            self._loginThread.requestInterruption()
        return super().closeEvent(event)

    def isLoginSuccessful(self):
        return self._loginThread.accessToken is not None

    def setAutoClose(self, autoClose: bool):
        self._autoClose = autoClose
