# -*- coding: utf-8 -*-

import requests

from qgitc.common import logger
from qgitc.llm import AiModelBase, AiParameters, AiResponse


class ChatGPTModel(AiModelBase):

    def __init__(self, url, model: str = None, parent=None):
        super().__init__(url, model, parent)
        self.api_token = None

    def query(self, params: AiParameters):
        payload = {
            "frequency_penalty": 0,
            "max_tokens": params.max_tokens,
            "model": params.model or self.modelId or "gpt-4.1",
            "presence_penalty": 0,
            "temperature": params.temperature,
            "stream": params.stream
        }

        if params.fill_point is not None:
            payload["prefix"] = params.prompt[:params.fill_point]
            payload["suffix"] = params.prompt[params.fill_point:]
            if params.language is not None and params.language != "None":
                payload["language"] = params.language
        else:
            if params.sys_prompt:
                self.add_history(self._makeMessage(
                    "system", params.sys_prompt))
            self.add_history(self._makeMessage("user", params.prompt))

            payload["messages"] = self._history

        if params.top_p is not None:
            payload["top_p"] = params.top_p

        try:
            self._doQuery(payload, params.stream)
        except requests.exceptions.ConnectionError as e:
            self.serviceUnavailable.emit()
        except Exception as e:
            logger.exception("Error in query")

    def _makeMessage(self, role, prompt):
        return {"role": role, "content": prompt}

    def _doQuery(self, payload, stream=True):
        headers = {
            "Content-Type": "application/json; charset=utf-8"
        }

        if self.api_token:
            headers["api_key"] = self.api_token,

        response = requests.post(
            self.url, headers=headers, json=payload, stream=stream)
        if not response.ok:
            aiResponse = AiResponse()
            aiResponse.message = response.text
            self.responseAvailable.emit(aiResponse)
            return

        if self.isInterruptionRequested():
            return

        if stream:
            role, content = self.handleStreamResponse(response)
        else:
            role, content = self.handleNonStreamResponse(response)

        self.add_history(self._makeMessage(role, content))
