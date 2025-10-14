# -*- coding: utf-8 -*-

from qgitc.llm import AiModelBase, AiParameters, AiRole


class ChatGPTModel(AiModelBase):

    def __init__(self, url, model: str = None, parent=None):
        super().__init__(url, model, parent)
        self.url = ""

    def queryAsync(self, params: AiParameters):
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
            self.addHistory(AiRole.User, params.prompt)
        else:
            if params.sys_prompt:
                self.addHistory(AiRole.System, params.sys_prompt)
            self.addHistory(AiRole.User, params.prompt)

            payload["messages"] = self.toOpenAiMessages()

        if params.top_p is not None:
            payload["top_p"] = params.top_p

        self._doQuery(payload, params.stream)

    def _doQuery(self, payload, stream=True):
        headers = {
            b"Content-Type": b"application/json; charset=utf-8"
        }
        self.post(self.url, headers=headers, data=payload, stream=stream)

    def _handleFinished(self):
        if self._content:
            self.addHistory(self._role, self._content)
