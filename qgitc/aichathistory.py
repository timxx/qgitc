# -*- coding: utf-8 -*-

import uuid
from datetime import datetime
from typing import Dict, List


class AiChatHistory:
    def __init__(self, historyId: str = None, title: str = "", modelKey: str = "",
                 modelId: str = "", messages: List[Dict] = None, timestamp: str = None):
        self.historyId = historyId or str(uuid.uuid4())
        self.title = title
        self.modelKey = modelKey
        self.modelId = modelId
        self.messages = messages or []
        self.timestamp = timestamp or datetime.now().isoformat()

    def toDict(self):
        return {
            'historyId': self.historyId,
            'title': self.title,
            'modelKey': self.modelKey,
            'modelId': self.modelId,
            'messages': self.messages,
            'timestamp': self.timestamp
        }

    @staticmethod
    def fromDict(data: dict):
        return AiChatHistory(
            historyId=data.get('historyId'),
            title=data.get('title', ''),
            modelKey=data.get('modelKey', ''),
            modelId=data.get('modelId', ''),
            messages=data.get('messages', []),
            timestamp=data.get('timestamp', datetime.now().isoformat())
        )
