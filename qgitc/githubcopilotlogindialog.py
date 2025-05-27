# -*- coding: utf-8 -*-

from enum import Enum

import requests
from PySide6.QtCore import QThread, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QDialog

from qgitc.applicationbase import ApplicationBase
from qgitc.common import logger
from qgitc.ui_githubcopilotlogindialog import Ui_GithubCopilotLoginDialog


class LoginStep(Enum):
    VerifyUrl = 0
    AccessCode = 1
    UserInfo = 2


class LoginThread(QThread):
    loginFailed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.deviceCode = None
        self.userCode = None
        self.verificationUri = None
        self.accessToken = None
        self.step = LoginStep.VerifyUrl

    def startVerifyUrl(self):
        self.step = LoginStep.VerifyUrl
        self.start()

    def startAccessCode(self):
        self.step = LoginStep.AccessCode
        self.start()

    def startUserInfo(self):
        self.step = LoginStep.UserInfo
        self.start()

    def run(self):
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
        response = requests.post(
            "https://github.com/login/device/code",
            headers={
                "accept": "application/json",
                "editor-version": "Neovim/0.6.1",
                "editor-plugin-version": "copilot.vim/1.16.0",
                "content-type": "application/json",
                "user-agent": "GithubCopilot/1.155.0",
                "accept-encoding": "gzip,deflate,br"
            },
            # data='{"client_id":"Iv1.b507a08c87ecfe98","scope":"read:user"}',
            json={
                "client_id": "Iv1.b507a08c87ecfe98",
                "scope": "read:user"
            },
            verify=True)

        data: dict = response.json()
        self.deviceCode = data.get("device_code")
        self.userCode = data.get("user_code")
        self.verificationUri = data.get("verification_uri")

        if not self.deviceCode or not self.userCode or not self.verificationUri:
            self.loginFailed.emit(self.tr("Failed to get verification URL"))

    def _getAccessCode(self):
        i = 0
        isMocked = ApplicationBase.instance(
        ).testing and requests.post.__module__.startswith("tests")
        while not self.accessToken and not self.isInterruptionRequested():
            self.msleep(50)
            i += 1
            if i % 100 != 0 and not isMocked:
                continue

            response = requests.post(
                "https://github.com/login/oauth/access_token",
                headers={
                    "accept": "application/json",
                    "editor-version": "Neovim/0.6.1",
                    "editor-plugin-version": "copilot.vim/1.16.0",
                    "content-type": "application/json",
                    "user-agent": "GithubCopilot/1.155.0",
                    "accept-encoding": "gzip,deflate,br"
                },
                # data=f'{{"client_id":"Iv1.b507a08c87ecfe98","device_code":"{self.deviceCode}","grant_type":"urn:ietf:params:oauth:grant-type:device_code"}}',
                json={
                    "client_id": "Iv1.b507a08c87ecfe98",
                    "device_code": self.deviceCode,
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code"
                },
                verify=True)

            data: dict = response.json()
            error = data.get("error")
            if error == "access_denied":
                self.loginFailed.emit(self.tr("Access denied"))
                break
            self.accessToken = data.get("access_token")

    def _getUserInfo(self):
        # TODO: the below URL cannot fetch user name
        # http://api.github.com/copilot_internal/user
        pass


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
            if ApplicationBase.instance().terminateThread(self._loginThread, 100):
                logger.warning("Terminating login thread")
        return super().closeEvent(event)

    def isLoginSuccessful(self):
        return self._loginThread.accessToken is not None

    def setAutoClose(self, autoClose: bool):
        self._autoClose = autoClose
