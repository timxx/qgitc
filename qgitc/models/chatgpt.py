# -*- coding: utf-8 -*-

import json

import requests

from qgitc.common import logger
from qgitc.llm import AiModelBase, AiParameters, AiResponse, AiRole


class ChatGPTModel(AiModelBase):

    def __init__(self, url, parent=None):
        super().__init__(url, parent)
        self.api_token = None
        self.model = "gpt-4o-mini"

    def query(self, params: AiParameters):
        payload = {
            "frequency_penalty": 0,
            "max_tokens": params.max_tokens,
            "model": self.model,
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
            role = "assistant"
            content = ""
            first_delta = True
            for chunk in response.iter_lines():
                if self.isInterruptionRequested():
                    return
                if not chunk:
                    continue
                if not chunk.startswith(b"data:"):
                    if not chunk.startswith(b": ping - "):
                        logger.warning(b"Corrupted chunk: %s", chunk)
                    continue
                data = json.loads(chunk[5:].decode("utf-8"))
                delta = data["choices"][0]["delta"]
                if not delta:
                    break
                if "role" in delta:
                    role = delta["role"]
                elif "content" in delta:
                    aiResponse = AiResponse()
                    aiResponse.is_delta = True
                    aiResponse.role = AiRole.Assistant
                    aiResponse.message = delta["content"]
                    aiResponse.first_delta = first_delta
                    self.responseAvailable.emit(aiResponse)
                    content += aiResponse.message
                    first_delta = False
                else:
                    logger.warning(b"Invalid delta: %s", delta)
        else:
            data = json.loads(response.text)
            usage = data["usage"]
            aiResponse = AiResponse()
            aiResponse.total_tokens = usage["total_tokens"]

            for choice in data["choices"]:
                message = choice["message"]
                content = message["content"]
                role = message["role"]
                aiResponse.role = AiRole.Assistant
                aiResponse.message = content
                self.responseAvailable.emit(aiResponse)
                break

        self.add_history(self._makeMessage(role, content))
