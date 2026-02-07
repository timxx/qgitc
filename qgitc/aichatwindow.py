from typing import Union

from qgitc.aichatwidget import AiChatWidget
from qgitc.aichatwindowcontextprovider import AiChatWindowContextProvider
from qgitc.statewindow import StateWindow


class AiChatWindow(StateWindow):

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle(self.tr("AI Assistant"))
        centralWidget = AiChatWidget(self)
        centralWidget.setContextProvider(AiChatWindowContextProvider(self))
        self.setCentralWidget(centralWidget)

    def codeReview(self, commit):
        self.centralWidget().codeReview(commit)

    def codeReviewForStagedFiles(self, submodules: Union[list, dict]):
        self.centralWidget().codeReviewForStagedFiles(submodules)

    def closeEvent(self, event):
        self.centralWidget().queryClose()
        return super().closeEvent(event)
